# ==================== ИМПОРТЫ ====================
import csv
import io
import logging
from os import getenv
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    InputMediaPhoto
)
from dotenv import load_dotenv

from db import (
    escape_html,
    format_moscow_time,
    get_orders,
    get_user_count,
    get_users,
    update_order_status,
    update_order_tracking_number,
    clear_order_tracking_number,
    decrease_product_stock,
    get_product_stock,
    get_order_by_id,
    notify_user_safe,
    get_status_notification_text,
    update_order_status_atomic
)
from filters import IsAdmin
from forms.users import AdminOrdersState, AdminState
from config import ADMIN_NAV_BANNER_ID

# ==================== НАСТРОЙКА ====================
logger = logging.getLogger(__name__)
load_dotenv()

admin_router = Router()

ADMIN_IDS = [int(id.strip()) for id in getenv("ADMIN_IDS", "").split(",") if id.strip()]
ADMIN_USERNAMES = [name.strip() for name in getenv("ADMIN_USERNAMES", "").split(",") if name.strip()]

STATUSES = {
    "new": {"label": "🆕 Новый", "db_value": "новый"},
    "processing": {"label": "🔄 В обработке", "db_value": "в обработке"},
    "shipped": {"label": "📦 Отправлен", "db_value": "отправлен"},
    "delivered": {"label": "✅ Доставлен", "db_value": "доставлен"},
    "cancelled": {"label": "❌ Отменён", "db_value": "отменён"},
}

STATUS_MESSAGES = {
    "в обработке": "🔄 Ваш заказ #{id} принят в обработку! Мы уже готовим «{product}» к отправке.",
    "отправлен": "📦 Ваш заказ #{id} отправлен!\n🚚 Способ доставки: {delivery}\n📍 Адрес: {address}",
    "доставлен": "✅ Заказ #{id} доставлен! Спасибо за покупку 🦆\nБудем рады видеть вас снова.",
    "отменён": "❌ Заказ #{id} отменён. Если это ошибка — напишите нам, контакты в /about.",
}


# ==================== ЕДИНЫЙ БАННЕР ДЛЯ АДМИНКИ ====================
async def render_admin_banner(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
    banner_file_id: str = ADMIN_NAV_BANNER_ID,
) -> None:
    """
    Универсальный рендер экранов админки с единым баннером.
    Всегда использует edit_message_media, избегая конфликтов text <-> photo.
    """
    try:
        await message.bot.edit_message_media(
            chat_id=message.chat.id,
            message_id=message.message_id,
            media=InputMediaPhoto(
                media=banner_file_id,
                caption=text,
                parse_mode=ParseMode.HTML
            ),
            reply_markup=keyboard
        )
    except Exception as e:
        error_text = str(e).lower()
        
        # 1. Игнорируем "message is not modified" — это не ошибка
        if "message is not modified" in error_text:
            return
        
        # 2. Если сообщение текстовое, edit_message_media закономерно падает.
        # Это ожидаемое поведение при переходе из текстовых разделов (например, Товаров).
        if "message media can't be edited" in error_text or "there is no text in the message" in error_text:
            logger.info(f"render_admin_banner: сообщение текстовое, применяем fallback (отправляем новое фото).")
        else:
            # 3. Все остальные ошибки логируем как WARNING
            logger.warning(f"render_admin_banner edit failed: {e}, sending new")
            
        try:
            await message.delete()
        except Exception:
            pass
            
        await message.answer_photo(
            photo=banner_file_id,
            caption=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
async def show_admin_panel(message: Message, state: FSMContext):
    """Главное меню админ-панели"""
    await state.set_state(AdminState.in_panel)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [
                InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_list_users"),
                InlineKeyboardButton(text="👑 Список админов", callback_data="admin_list_admins"),
            ],
            [InlineKeyboardButton(text="📋 Заказы", callback_data="admin_orders_menu")],
            [InlineKeyboardButton(text="📦 Управление товарами", callback_data="admin_products")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast_start")],
            [InlineKeyboardButton(text="📊 Экспорт заказов", callback_data="admin_export_orders")],
            [InlineKeyboardButton(text="🚪 Выйти", callback_data="admin_exit")],
        ]
    )
    
    text = "🔐<b>=========Админ-панель=========</b>\n\nВыберите действие:"
    
    # Используем единый баннер вместо edit_text/answer
    await render_admin_banner(message, text, keyboard)


async def show_users_list(message: Message):
    users = await get_users()
    if not users:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")]
            ]
        )
        text = "📭 Пока нет зарегистрированных пользователей."
        await render_admin_banner(message, text, keyboard)
        return

    text = "👥 <b>Список пользователей:</b>\n\n"
    for user in users:
        created_at_raw = user["created_at"] if len(user) > 7 else None
        if created_at_raw:
            created_at_str = format_moscow_time(created_at_raw)
            created_at_date = created_at_str.split()[0]
        else:
            created_at_date = "неизвестно"

        text += (
            f"🔹<b>{escape_html(user['fullname'])}</b>\n"
            f"📞{escape_html(user['phone']) or 'не указан'}\n"
            f"✉︎{escape_html(user['email']) or 'не указан'}\n"
            f"🏙️ {escape_html(user['city']) or 'не указан'}\n"
            f"📍 {escape_html(user['address']) or 'не указан'}\n"
            f"🆔 @{escape_html(user['username']) or 'нет'}\n"
            f"📅 {created_at_date}\n"
            f"─────────────\n"
        )

    if len(text) > 3500:
        text = text[:3400] + "\n\n... и ещё много других."

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")]
        ]
    )
    await render_admin_banner(message, text, keyboard)


async def show_admins_list(message: Message):
    if not ADMIN_IDS:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")]
            ]
        )
        text = "👑 Список администраторов пуст."
        await render_admin_banner(message, text, keyboard)
        return

    text = "👑 <b>Список администраторов:</b>\n\n"
    for i, admin_id in enumerate(ADMIN_IDS):
        username = ADMIN_USERNAMES[i] if i < len(ADMIN_USERNAMES) else "неизвестен"
        text += f"🔹<b>@{escape_html(username)}</b>\n"
        text += f"📌 ID: <code>{admin_id}</code>\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")]
        ]
    )
    await render_admin_banner(message, text, keyboard)


async def show_stats(message: Message):
    total_users = await get_user_count()
    total_admins = len(ADMIN_IDS)
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"👑 Всего админов: <b>{total_admins}</b>"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")]
        ]
    )
    await render_admin_banner(message, text, keyboard)


# ==================== КОМАНДА /command ДЛЯ АДМИНОВ ====================
@admin_router.message(Command("command"), F.from_user.id.in_(ADMIN_IDS))
async def admin_command_list(message: Message):
    text = (
        "📋 <b>Команды бота</b>\n"
        "═══════════════════════\n\n"
        "🏠 <b>Главное</b>\n"
        "  /start — запустить бота\n"
        "  /command — список команд\n\n"
        "  /support — поддержка\n\n"
        "📝 <b>Профиль</b>\n"
        "  /register — регистрация\n"
        "  /cancel — отменить действие\n\n"
        "🦆 <b>Информация</b>\n"
        "  /about — о компании MANIA\n\n"
        "🛒 <b>Магазин</b>\n"
        "  /shop — посмотреть товары\n"
        "═══════════════════════\n"
        "🔐 <b>Админ-раздел</b>\n"
        "  👑 /admin — панель администратора"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


# ==================== ВХОД В АДМИН-ПАНЕЛЬ ====================
@admin_router.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def admin_panel(message: Message, state: FSMContext):
    """Вход в админ-панель по команде /admin"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [
                InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_list_users"),
                InlineKeyboardButton(text="👑 Список админов", callback_data="admin_list_admins"),
            ],
            [InlineKeyboardButton(text="📋 Заказы", callback_data="admin_orders_menu")],
            [InlineKeyboardButton(text="📦 Управление товарами", callback_data="admin_products")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast_start")],
            [InlineKeyboardButton(text="📊 Экспорт заказов", callback_data="admin_export_orders")],
            [InlineKeyboardButton(text="🚪 Выйти", callback_data="admin_exit")],
        ]
    )
    await state.set_state(AdminState.in_panel)
    
    text = "🔐 <b>Админ-панель</b>\n\nВыберите действие:"
    
    # При первом вызове edit_message_media упадет (так как это новое сообщение), 
    # и сработает наш fallback на answer_photo с баннером.
    await render_admin_banner(message, text, keyboard)


# ==================== ОБРАБОТКА КНОПОК ====================
@admin_router.callback_query(F.data.startswith("admin_"), IsAdmin())
async def admin_callback(callback: CallbackQuery, state: FSMContext):
    action = callback.data
    if action == "admin_list_users":
        await show_users_list(callback.message)
        await callback.answer()
    elif action == "admin_list_admins":
        await show_admins_list(callback.message)
        await callback.answer()
    elif action == "admin_stats":
        await show_stats(callback.message)
        await callback.answer()
    elif action == "admin_products":
        from handlers.admin_products import admin_products_menu

        await admin_products_menu(callback, state)
        await callback.answer()
    elif action == "admin_orders_menu":
        await admin_orders_menu(callback, state)
        await callback.answer()
    elif action == "admin_export_orders":
        await export_orders_csv(callback.message)
        await callback.answer()
    elif action == "admin_exit":
        await state.clear()
        text = "🚪 <b>Вы вышли из админ-панели.</b>\n\nИспользуйте /admin для возврата."
        await render_admin_banner(callback.message, text, InlineKeyboardMarkup(inline_keyboard=[]))
        await callback.answer()
    elif action == "admin_back_to_panel":
        await show_admin_panel(callback.message, state)
        await callback.answer()


# ==================== ИЗМЕНЕНИЕ СТАТУСА ЗАКАЗА ====================
@admin_router.callback_query(F.data.startswith("ostatus_"), IsAdmin())
async def admin_change_status_callback(callback: CallbackQuery, state: FSMContext):
    """Изменение статуса заказа"""
    parts = callback.data.split("_")
    order_id = int(parts[1])
    key = parts[2]

    if key not in STATUSES:
        await callback.answer("Неизвестный статус.")
        return

    new_status = STATUSES[key]["db_value"]

    order = await get_order_by_id(order_id)
    if not order:
        await callback.answer("Заказ не найден.")
        return

    current_status = order["status"] if len(order) > 10 else None

    if current_status == new_status:
        await callback.answer("ℹ️ Статус уже установлен", show_alert=True)
        return

    try:
        # ---- Атомарное изменение статуса и остатков в БД ----
        result = await update_order_status_atomic(order_id, new_status)
        
        if not result["success"]:
            await callback.answer(f"❌ {result['message']}", show_alert=True)
            return
            
        old_status = result["old_status"]
        
        if result["message"] == "Статус не изменился":
            await callback.answer("ℹ️ Статус уже установлен", show_alert=True)
            return

        # === Уведомление о появлении товара в наличии (Шаг 3) ===
        if result.get("restocked") and result.get("product_id"):
            from utils.notifications import notify_back_in_stock
            await notify_back_in_stock(result["product_id"], callback.bot)
        # ========================================================

        data = await state.get_data()
        status_filter = data.get("orders_filter")
        page = data.get("orders_page", 0)

        user_id = order["user_id"]
        product_name = order["name"] or "товар"
        delivery_method = order["delivery_method"] or "не указан"
        delivery_address = order["delivery_address"] or "не указан"

        # Получаем текст уведомления (он будет разным для движения вперёд и для отката)
        notify_text = get_status_notification_text(
            old_status, new_status, order_id, product_name, delivery_method, delivery_address
        )

        notification_sent = False
        if notify_text and user_id:
            notification_sent = await notify_user_safe(
                callback.bot,
                chat_id=user_id,
                text=notify_text,
            )

        # Логируем действие для админа
        logger.info(
            f"🔄 Статус заказа #{order_id} изменён с '{old_status}' на '{new_status}'. "
            f"Уведомление клиенту: {'✅ отправлено' if notification_sent else '⚠️ не доставлено (бот заблокирован)'}"
        )

        if key == "shipped":
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Добавить трек-номер", callback_data=f"add_tracking_{order_id}")],
                    [InlineKeyboardButton(text="📋 Вернуться к заказу", callback_data=f"back_to_order_{order_id}")],
                ]
            )

            try:
                await callback.message.delete()
            except Exception:
                pass

            status_text = "✅ Клиент уведомлён" if notification_sent else "⚠️ Клиент не уведомлён (бот заблокирован)"

            await callback.message.answer(
                f"✅ <b>Статус заказа #{order_id} изменён на:</b>\n"
                f"{STATUSES[key]['label']}\n\n"
                f"{status_text}\n\n"
                f"Хотите добавить трек-номер для отслеживания?",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )

            await state.update_data(
                orders_filter=status_filter,
                orders_page=page,
                tracking_order_id=order_id,
            )

            await callback.answer(f"✅ Статус изменён на {STATUSES[key]['label']}")
            return

        if key == "cancelled":
            for admin_id in ADMIN_IDS:
                await notify_user_safe(
                    callback.bot,
                    chat_id=admin_id,
                    text=f"🔄 Заказ #{order_id} отменён администратором @{callback.from_user.username or callback.from_user.id}",
                )

        await show_orders_list(callback.message, state, status_filter, page)

        if notification_sent:
            await callback.answer(
                f"✅ Статус изменён на {STATUSES[key]['label']}, клиент уведомлён",
                show_alert=True,
            )
        else:
            await callback.answer(
                f"✅ Статус изменён на {STATUSES[key]['label']} (клиент не получил уведомление)",
                show_alert=True,
            )

    except Exception as e:
        logger.error(f"Error changing order status: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при изменении статуса", show_alert=True)


@admin_router.callback_query(F.data.startswith("add_tracking_"), IsAdmin())
async def add_tracking_callback(callback: CallbackQuery, state: FSMContext):
    """Запрос трек-номера для заказа"""
    order_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    status_filter = data.get("orders_filter")
    page = data.get("orders_page", 0)

    await state.update_data(
        tracking_order_id=order_id,
        orders_filter=status_filter,
        orders_page=page,
    )
    await state.set_state(AdminOrdersState.adding_tracking)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_back_to_order")]
        ]
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    # Отправляем сообщение с запросом и сохраняем его ID
    sent_msg = await callback.message.answer(
        f"📦 <b>Добавление трек-номера для заказа #{order_id}</b>\n\n"
        f"Введите трек-номер для отслеживания:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await state.update_data(tracking_prompt_message_id=sent_msg.message_id)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("change_status_"), IsAdmin())
async def admin_change_status_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора статуса для заказа (отдельное сообщение)"""
    order_id = int(callback.data.split("_")[2])

    from db import get_order_by_id

    order = await get_order_by_id(order_id)

    if not order:
        await callback.message.edit_text("❌ Заказ не найден.")
        await callback.answer()
        return

    data = await state.get_data()
    status_filter = data.get("orders_filter")
    page = data.get("orders_page", 0)
    await state.update_data(
        changing_order_id=order_id,
        orders_filter=status_filter,
        orders_page=page,
    )

    status_buttons = []
    for key, status_info in STATUSES.items():
        if key == "cancelled":
            status_buttons.append(
                [
                    InlineKeyboardButton(
                        text=status_info["label"],
                        callback_data=f"confirm_cancel_{order_id}",
                    )
                ]
            )
        else:
            status_buttons.append(
                [
                    InlineKeyboardButton(
                        text=status_info["label"],
                        callback_data=f"ostatus_{order_id}_{key}",
                    )
                ]
            )

    status_buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад к заказу", callback_data=f"back_to_order_{order_id}")]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=status_buttons)

    text = (
        f"🔄 <b>Изменение статуса заказа #{order_id}</b>\n\n"
        f"👤 Клиент: {escape_html(order['order_fullname'] or 'не указан')}\n"
        f"🛒 Товар: {escape_html(order['name'] or 'не указан')}\n"
        f"📌 Текущий статус: {order['status'] or 'новый'}\n\n"
        f"Выберите новый статус:"
    )

    await render_admin_banner(callback.message, text, keyboard)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("confirm_cancel_"), IsAdmin())
async def confirm_cancel_callback(callback: CallbackQuery, state: FSMContext):
    """Подтверждение отмены заказа"""
    from db import get_order_by_id

    order_id = int(callback.data.split("_")[2])

    order = await get_order_by_id(order_id)
    if not order:
        await callback.message.edit_text("❌ Заказ не найден.")
        await callback.answer()
        return

    data = await state.get_data()
    status_filter = data.get("orders_filter")
    page = data.get("orders_page", 0)

    await state.update_data(
        changing_order_id=order_id,
        orders_filter=status_filter,
        orders_page=page,
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, отменить заказ",
                    callback_data=f"ostatus_{order_id}_cancelled",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Нет, вернуться",
                    callback_data=f"change_status_{order_id}",
                )
            ],
        ]
    )

    unit_price = order["unit_price"] if len(order) > 13 and order["unit_price"] else 0
    quantity = order["quantity"] or 0
    total_price = quantity * unit_price

    text = (
        f"⚠️ <b>Подтверждение отмены заказа #{order_id}</b>\n\n"
        f"👤 Клиент: {escape_html(order['order_fullname'] or 'не указан')}\n"
        f"🛒 Товар: {escape_html(order['name'] or 'не указан')}\n"
        f"📦 Количество: {quantity} шт.\n"
        f"💰 Цена за шт.: {unit_price} ₽\n"
        f"💵 Сумма: {total_price} ₽\n"
        f"\n<b>Вы уверены, что хотите отменить этот заказ?</b>\n"
        f"⚠️ При отмене товар вернётся на склад."
    )

    await render_admin_banner(callback.message, text, keyboard)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("back_to_order_"), IsAdmin())
async def back_to_order_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат к заказу из меню выбора статуса"""
    order_id = int(callback.data.split("_")[-1])
    await show_order_detail(callback.message, state, order_id)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("view_order_detail_"), IsAdmin())
async def view_order_detail_callback(callback: CallbackQuery, state: FSMContext):
    """Переход к детальной карточке из списка с сохранением контекста возврата"""
    order_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    await state.update_data(
        return_to_filter=data.get("orders_filter"),
        return_to_page=data.get("orders_page", 0)
    )
    await show_order_detail(callback.message, state, order_id)
    await callback.answer()


@admin_router.callback_query(F.data == "back_to_orders_list", IsAdmin())
async def back_to_orders_list_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку заказов из детальной карточки"""
    data = await state.get_data()
    status_filter = data.get("return_to_filter")
    page = data.get("return_to_page", 0)
    
    # Rule 2: try edit, fallback to answer if failed
    try:
        await show_orders_list(callback.message, state, status_filter, page)
    except Exception as e:
        logger.warning(f"back_to_orders_list edit failed: {e}")
        await callback.answer("⚠️ Не удалось вернуться к списку. Попробуйте снова.", show_alert=True)
    
    await callback.answer()

# ==================== ОБРАБОТКА ВВОДА ТРЕК-НОМЕРА ====================
@admin_router.message(StateFilter(AdminOrdersState.adding_tracking), F.text, IsAdmin())
async def process_tracking_number(message: Message, state: FSMContext):
    """Сохранение трек-номера"""
    from db import get_order_by_id, notify_user_safe

    data = await state.get_data()
    order_id = data.get("tracking_order_id")
    status_filter = data.get("orders_filter", None)
    page = data.get("orders_page", 0)
    prompt_msg_id = data.get("tracking_prompt_message_id")

    if not order_id:
        return

    tracking_number = message.text.strip()
    if len(tracking_number) < 3:
        await message.answer("❌ Слишком короткий трек-номер. Введите корректный номер.")
        return

    try:
        await update_order_tracking_number(order_id, tracking_number)

        order = await get_order_by_id(order_id)
        user_id = order["user_id"] if order else None

        notification_sent = False
        if user_id:
            notify_text = (
                f"📦 <b>Трек-номер для заказа #{order_id}</b>\n\n"
                f"🔢 <b>Трек-номер:</b> {escape_html(tracking_number)}\n\n"
                f"Вы можете отслеживать посылку по этому номеру."
            )
            notification_sent = await notify_user_safe(
                message.bot,
                chat_id=user_id,
                text=notify_text,
            )

        # Удаляем сообщение с запросом трек-номера, если оно есть
        if prompt_msg_id:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
            except Exception:
                pass
            await state.update_data(tracking_prompt_message_id=None)

        # Удаляем сообщение пользователя с трек-номером
        try:
            await message.delete()
        except Exception:
            pass

        # Одно сообщение: подтверждение + кнопка возврата к заказу
        if notification_sent:
            status_line = "✅ Клиент уведомлён"
        else:
            status_line = "⚠️ Клиент не уведомлён (заблокировал бота?)"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📋 Вернуться к заказу", callback_data=f"back_to_order_{order_id}")]
            ]
        )

        await message.answer(
            f"✅ <b>Трек-номер для заказа #{order_id} добавлен!</b>\n"
            f"📦 {escape_html(tracking_number)}\n\n"
            f"{status_line}",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )

    except Exception as e:
        logger.error(f"Error adding tracking: {e}", exc_info=True)
        await message.answer(
            f"❌ Ошибка при добавлении трек-номера для заказа #{order_id}.",
            parse_mode=ParseMode.HTML,
        )

    await state.clear()


# ==================== ЕСЛИ НЕ АДМИН ====================
@admin_router.message(Command("admin"))
async def admin_not_allowed(message: Message):
    await message.answer(
        "⛔ <b>Доступ запрещён!</b>\n\nЭта команда доступна только администраторам.",
        parse_mode=ParseMode.HTML,
    )


# ==================== ВЫХОД ИЗ АДМИНКИ ПО /cancel ====================
@admin_router.message(Command("cancel"), StateFilter(AdminState.in_panel))
async def cancel_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚪 Вы вышли из админ-панели.")


# ==================== ЭКСПОРТ ЗАКАЗОВ В CSV ====================
async def export_orders_csv(message: Message):
    """Экспорт всех заказов в CSV"""
    orders = await get_orders()

    if not orders:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")]
            ]
        )
        try:
            await message.edit_text(
                "📭 Нет заказов для экспорта.",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"export_orders_csv edit failed: {e}, sending new")
            await message.answer("📭 Нет заказов для экспорта.", reply_markup=keyboard)
        return

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow(
        [
            "№ заказа",
            "Клиент",
            "Телефон",
            "Email",
            "Город",
            "Товар",
            "Кол-во",
            "Цена за шт.",
            "Сумма",
            "Способ доставки",
            "Адрес доставки",
            "Комментарий",
            "Статус",
            "Трек-номер",
            "Дата создания",
        ]
    )

    for order in orders:
        quantity = order["quantity"] or 0
        unit_price = order["unit_price"] if len(order) > 13 and order["unit_price"] else 0
        total_price = quantity * unit_price

        writer.writerow(
            [
                order["id"],
                order["order_fullname"] or "",
                order["order_phone"] or "",
                order["email"] or "",
                order["city"] or "",
                order["name"] or "",
                quantity,
                unit_price,
                total_price,
                order["delivery_method"] or "",
                order["delivery_address"] or "",
                order["comment"] or "",
                order["status"] or "",
                order["created_at"] or "",
                order["tracking_number"] or "",
            ]
        )

    csv_bytes = output.getvalue().encode("utf-8-sig")
    output.close()

    document = BufferedInputFile(csv_bytes, filename="orders.csv")

    try:
        await message.answer_document(
            document,
            caption=f"📊 <b>Экспорт заказов</b>\n\nВсего: {len(orders)} заказов",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Error sending CSV: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка при экспорте заказов. Попробуйте позже.",
            parse_mode=ParseMode.HTML,
        )


# ==================== ОТОБРАЖЕНИЕ ЗАКАЗОВ ====================
async def show_orders_list(message: Message, state: FSMContext, status_filter: str = None, page: int = 0):
    """Показать компактный список заказов с пагинацией"""
    from db import get_orders_paginated, get_orders_count
    
    limit = 5
    offset = page * limit
    orders = await get_orders_paginated(status_filter, offset, limit)
    total = await get_orders_count(status_filter)
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    await state.update_data(
        orders_page=page,
        orders_filter=status_filter,
        orders_total=total,
        orders_total_pages=total_pages,
    )

    if not orders:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_orders_menu")]]
        )
        try:
            await message.edit_text("📋 Нет заказов с выбранным фильтром.", reply_markup=keyboard, parse_mode=ParseMode.HTML)
        except Exception:
            await message.answer("📋 Нет заказов с выбранным фильтром.", reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return

    filter_names = {
        "active": "🔵 Активные заказы",
        "completed": "🟢 Завершённые заказы",
        None: "📋 Все заказы",
    }
    title = filter_names.get(status_filter, "📋 Все заказы")
    text = f"{title}\n━━━━━━━━━━━━━\n"

    keyboard_rows = []
    status_emoji = {"новый": "🆕", "в обработке": "🔄", "отправлен": "📦", "доставлен": "✅", "отменён": "❌"}

    for order in orders:
        # Явное присвоение переменных (формат get_orders_paginated)
        o_id = order["id"]
        fullname = order["order_fullname"] or "Неизвестно"
        product_name = order["name"] or "Товар"
        quantity = order["quantity"] or 0
        unit_price = order["unit_price"] or 0
        total_price = quantity * unit_price
        status = order["status"] or "новый"
    
        emoji = status_emoji.get(status, "📌")
    
        # Для кнопок: обрезаем до 25 символов или до конца слова
        if len(product_name) > 25:
            short_name = product_name[:25].rsplit(" ", 1)[0] + "..."
        else:
            short_name = product_name
    
        # Для текста: используем полное название
        full_name = product_name
    
        text += f"{emoji} <b>#{o_id}</b> — {escape_html(fullname)} — {escape_html(full_name)} — {total_price} ₽\n\n"
    
        # Уникальная кнопка для каждого заказа
        button_text = f"{emoji} #{o_id} — {escape_html(short_name)}"
        keyboard_rows.append([
            InlineKeyboardButton(text=button_text, callback_data=f"view_order_detail_{o_id}")
        ])

    text += f"━━━━━━━━━━━━━\nСтраница {page + 1} из {total_pages}"

    # Фильтры
    keyboard_rows.append([
        InlineKeyboardButton(text="🔵 Активные", callback_data="orders_filter_active"),
        InlineKeyboardButton(text="📋 Все", callback_data="orders_filter_all"),
        InlineKeyboardButton(text="🟢 Заверш.", callback_data="orders_filter_completed"),
    ])

    # Пагинация
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"orders_page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"orders_page_{page+1}"))
    if nav_row:
        keyboard_rows.append(nav_row)

    # Экспорт и Назад
    keyboard_rows.append([InlineKeyboardButton(text="📊 Экспорт заказов", callback_data="admin_export_orders")])
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_orders_menu")])

    # Убираем пустые строки
    keyboard_rows = [row for row in keyboard_rows if row]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    await render_admin_banner(message, text, keyboard)


# ==================== ОБРАБОТКА ЗАКАЗОВ ====================
@admin_router.callback_query(F.data == "admin_orders_menu", IsAdmin())
async def admin_orders_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора фильтра заказов"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔵 Активные", callback_data="orders_filter_active")],
            [InlineKeyboardButton(text="📋 Все заказы", callback_data="orders_filter_all")],
            [InlineKeyboardButton(text="🟢 Завершённые", callback_data="orders_filter_completed")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")],
        ]
    )

    text = (
        "<b>Выберите <u><i>категорию</i></u> заказов:</b>\n\n"
        "🔵 <b>Активные</b> — Новые и в обработке\n"
        "📋 <b>Все</b> — Все заказы без фильтра\n"
        "🟢 <b>Завершённые</b> — Доставленные и отменённые"
    )

    await render_admin_banner(callback.message, text, keyboard)


@admin_router.callback_query(F.data.startswith("orders_filter_"), IsAdmin())
async def orders_filter_callback(callback: CallbackQuery, state: FSMContext):
    """Выбор фильтра заказов"""
    filter_type = callback.data.split("_")[2]

    status_filter_map = {
        "active": "active",
        "all": None,
        "completed": "completed",
    }
    status_filter = status_filter_map.get(filter_type, None)
    await show_orders_list(callback.message, state, status_filter, page=0)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("orders_page_"), IsAdmin())
async def orders_page_callback(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы заказов"""
    page = int(callback.data.split("_")[2])
    data = await state.get_data()
    status_filter = data.get("orders_filter")
    await show_orders_list(callback.message, state, status_filter, page)
    await callback.answer()


@admin_router.callback_query(StateFilter(AdminOrdersState.adding_tracking), F.data == "admin_back_to_order", IsAdmin())
async def admin_back_to_order(callback: CallbackQuery, state: FSMContext):
    """Возврат к заказу без добавления трек-номера"""
    data = await state.get_data()
    order_id = data.get("tracking_order_id")
    await state.clear()
    
    if order_id:
        await show_order_detail(callback.message, state, order_id)
    else:
        try:
            await callback.message.edit_text("❌ Заказ не найден.")
        except Exception:
            await callback.message.answer("❌ Заказ не найден.")
    await callback.answer()
    
    
    
# ==================== РУЧНАЯ ОЧИСТКА ТРЕК-НОМЕРА ====================
@admin_router.callback_query(F.data.startswith("clear_tracking_"), IsAdmin())
async def clear_tracking_callback(callback: CallbackQuery, state: FSMContext):
    """Запрос подтверждения на очистку трек-номера заказа"""
    order_id = int(callback.data.split("_")[2])
    order = await get_order_by_id(order_id)
    
    # order["tracking_number"] — это tracking_number в get_order_by_id
    if not order or not order["tracking_number"]:
        await callback.answer("ℹ️ У этого заказа уже нет трек-номера.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, очистить", callback_data=f"confirm_clear_tracking_{order_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"back_to_order_{order_id}")],
        ]
    )
    
    text = (
        f"🗑 <b>Подтвердите очистку трек-номера</b>\n\n"
        f"Заказ #{order_id}\n"
        f"Текущий трек-номер: <code>{escape_html(order['tracking_number'])}</code>\n\n"
        f"Вы уверены, что хотите удалить его?"
    )
    
    # Правило 2: try/except с logger.warning и фоллбеком на answer()
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"clear_tracking_callback edit failed: {e}, deleting old and sending new")
        # Удаляем старое фото-сообщение
        try:
            await callback.message.delete()
        except Exception:
            pass
        # Отправляем новое текстовое
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("confirm_clear_tracking_"), IsAdmin())
async def confirm_clear_tracking_callback(callback: CallbackQuery, state: FSMContext):
    """Финальное подтверждение и очистка трек-номера с уведомлением клиента"""
    order_id = int(callback.data.split("_")[3])
    
    # 1. Получаем user_id для уведомления
    order = await get_order_by_id(order_id)
    user_id = order["user_id"] if order else None

    # 2. Очищаем трек-номер в БД
    await clear_order_tracking_number(order_id)

    # 3. Уведомляем клиента (Правило 4: notify_user_safe не уронит бота)
    if user_id:
        notify_text = (
            f"⚠️ <b>Внимание: трек-номер для заказа #{order_id} аннулирован.</b>\n\n"
            f"Пожалуйста, игнорируйте предыдущее сообщение с трек-номером.\n"
            f"Мы отправим вам новый трек-номер, как только он будет готов.\n\n"
            f"По всем вопросам — контакты в /about."
        )
        await notify_user_safe(callback.bot, chat_id=user_id, text=notify_text)

    # 4. Подтверждение админу и возврат к заказу
    await callback.answer("✅ Трек-номер успешно очищен!", show_alert=True)
    
    text_response = "✅ Трек-номер очищен. Клиент уведомлён об аннулировании."
    keyboard_response = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Вернуться к заказу", callback_data=f"back_to_order_{order_id}")]
        ]
    )
    
    # Правило 2: try/except с logger.warning и фоллбеком на answer()
    try:
        await callback.message.edit_text(
            text_response,
            reply_markup=keyboard_response,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"confirm_clear_tracking_callback edit failed: {e}, deleting old and sending new")
        # Удаляем старое фото-сообщение
        try:
            await callback.message.delete()
        except Exception:
            pass
        # Отправляем новое текстовое
        await callback.message.answer(
            text_response,
            reply_markup=keyboard_response,
            parse_mode=ParseMode.HTML,
        )
        
        
async def show_order_detail(message: Message, state: FSMContext, order_id: int):
    """Показать подробную карточку конкретного заказа"""
    from db import get_order_by_id, get_product_by_id, format_moscow_time
    
    order = await get_order_by_id(order_id)
    if not order:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_orders_menu")]]
        )
        try:
            await message.edit_text("❌ Заказ не найден.", reply_markup=keyboard, parse_mode=ParseMode.HTML)
        except Exception:
            await message.answer("❌ Заказ не найден.", reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return

    # Явное присвоение переменных для избежания магических индексов (формат get_order_by_id)
    o_id = order["id"]
    fullname = order["order_fullname"] or "не указан"
    phone = order["order_phone"] or "не указан"
    email = order["email"] or "не указан"
    city = order["city"] or "не указан"
    product_name = order["name"] or "не указан"
    quantity = order["quantity"] or 0
    delivery_method = order["delivery_method"] or "не указан"
    delivery_address = order["delivery_address"] or "не указан"
    status = order["status"] or "новый"
    created_at = order["created_at"]
    tracking_number = order["tracking_number"]
    unit_price = order["unit_price"] or 0
    comment = order["comment"]
    product_id = order["product_id"]

    total_price = quantity * unit_price

    status_emoji = {
        "новый": "🆕", "в обработке": "🔄", "отправлен": "📦", "доставлен": "✅", "отменён": "❌",
    }
    emoji = status_emoji.get(status, "📌")

    text = (
        f"{emoji} <b>Заказ #{o_id}</b>\n"
        f"━━━━━━━━━━━━━\n"
        f"👤 <b>Клиент:</b> {escape_html(fullname)}\n"
        f"📞 <b>Телефон:</b> {escape_html(phone)}\n"
        f"📧 <b>Email:</b> {escape_html(email)}\n"
        f"🏙️ <b>Город:</b> {escape_html(city)}\n\n"
        f"🛒 <b>Товар:</b> {escape_html(product_name)}\n"
        f"📦 <b>Количество:</b> {quantity} шт.\n"
        f"💰 <b>Цена за шт.:</b> {unit_price} ₽\n"
        f"💵 <b>Сумма:</b> {total_price} ₽\n"
        f"🚚 <b>Доставка:</b> {escape_html(delivery_method)}\n"
        f"📍 <b>Адрес:</b> {escape_html(delivery_address)}\n"
    )

    if tracking_number:
        text += f"📦 <b>Трек-номер:</b> {escape_html(tracking_number)}\n"
    if comment:
        text += f"📝 <b>Комментарий:</b> {escape_html(comment)}\n"

    text += (
        f"📌 <b>Статус:</b> {status}\n"
        f"📅 <b>Создан:</b> {format_moscow_time(created_at)}\n"
        f"━━━━━━━━━━━━━\n"
    )

    # Формирование клавиатуры
    keyboard_rows = []
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Изменить статус", callback_data=f"change_status_{o_id}")])
    if tracking_number:
        keyboard_rows.append([InlineKeyboardButton(text="🗑 Очистить трек", callback_data=f"clear_tracking_{o_id}")])
    
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_orders_list")])
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_orders_menu")])
    
    keyboard_rows = [row for row in keyboard_rows if row]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    # Обработка фото (Rule 2: try/except + fallback)
    product_image = None
    if product_id:
        product = await get_product_by_id(product_id)
        if product and len(product) > 7:
            product_image = product["image_file_id"]

    try:
        if product_image:
            await message.bot.edit_message_media(
                chat_id=message.chat.id,
                message_id=message.message_id,
                media=InputMediaPhoto(media=product_image, caption=text, parse_mode=ParseMode.HTML),
                reply_markup=keyboard,
            )
        else:
            await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"show_order_detail edit failed: {e}, fallback to new message")
        try:
            await message.delete()
        except Exception:
            pass
        
        if product_image:
            await message.answer_photo(photo=product_image, caption=text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            
            
# ==================== ВРЕМЕННАЯ КОМАНДА ДЛЯ ПОЛУЧЕНИЯ FILE_ID ====================
@admin_router.message(Command("getphotoid"), IsAdmin())
async def get_photo_id_command(message: Message, state: FSMContext):
    """Временная команда для получения file_id фотографии"""
    await state.set_state(AdminState.waiting_for_photo)
    await message.answer(
        "📷 <b>Отправьте фотографию</b>\n\n"
        "Я верну вам <code>file_id</code>, который можно использовать в коде.",
        parse_mode=ParseMode.HTML
    )


@admin_router.message(StateFilter(AdminState.waiting_for_photo), F.photo, IsAdmin())
async def process_photo_for_id(message: Message, state: FSMContext):
    """Обработка фотографии для получения file_id"""
    file_id = message.photo[-1].file_id
    
    await message.answer(
        f"✅ <b>File ID получен:</b>\n\n"
        f"<code>{file_id}</code>\n\n"
        f"Скопируйте его и используйте в коде.",
        parse_mode=ParseMode.HTML
    )
    
    await state.clear()
    logger.info(f"📷 Получен file_id через /getphotoid: {file_id}")