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
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    InputMediaPhoto
)
from dotenv import load_dotenv

from db import (
    escape_html,
    format_moscow_time,
    get_orders,
    get_user_count,
    get_users,
    return_stock_on_cancel,
    update_order_status,
    update_order_tracking_number,
)
from filters import IsAdmin
from forms.users import AdminOrdersState, AdminState

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


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
async def show_admin_panel(message: Message, state: FSMContext):
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
            [InlineKeyboardButton(text="📊 Экспорт заказов", callback_data="admin_export_orders")],
            [InlineKeyboardButton(text="🚪 Выйти", callback_data="admin_exit")],
        ]
    )
    try:
        await message.edit_text(
            "🔐 <b>Админ-панель</b>\n\nВыберите действие:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"show_admin_panel edit failed: {e}, sending new")
        await message.answer(
            "🔐 <b>Админ-панель</b>\n\nВыберите действие:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )


async def show_users_list(message: Message):
    users = await get_users()
    if not users:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")]
            ]
        )
        try:
            await message.edit_text(
                "📭 Пока нет зарегистрированных пользователей.",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"show_users_list edit failed: {e}, sending new")
            await message.answer(
                "📭 Пока нет зарегистрированных пользователей.",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        return

    text = "👥 <b>Список пользователей:</b>\n\n"
    for user in users:
        created_at_raw = user[7] if len(user) > 7 else None
        if created_at_raw:
            created_at_str = format_moscow_time(created_at_raw)
            created_at_date = created_at_str.split()[0]
        else:
            created_at_date = "неизвестно"

        text += (
            f"🔹 <b>{escape_html(user[1])}</b>\n"
            f"   📞 {escape_html(user[2]) or 'не указан'}\n"
            f"   📧 {escape_html(user[3]) or 'не указан'}\n"
            f"   🏙️ {escape_html(user[4]) or 'не указан'}\n"
            f"   📍 {escape_html(user[5]) or 'не указан'}\n"
            f"   🆔 @{escape_html(user[6]) or 'нет'}\n"
            f"   📅 {created_at_date}\n"
            f"   ─────────────\n"
        )

    if len(text) > 3500:
        text = text[:3400] + "\n\n... и ещё много других."

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")]
        ]
    )
    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"show_users_list edit failed: {e}, sending new")
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def show_admins_list(message: Message):
    if not ADMIN_IDS:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")]
            ]
        )
        try:
            await message.edit_text(
                "👑 Список администраторов пуст.",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"show_admins_list edit failed: {e}, sending new")
            await message.answer(
                "👑 Список администраторов пуст.",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        return

    text = "👑 <b>Список администраторов:</b>\n\n"
    for i, admin_id in enumerate(ADMIN_IDS):
        username = ADMIN_USERNAMES[i] if i < len(ADMIN_USERNAMES) else "неизвестен"
        text += f"🔹 <b>@{escape_html(username)}</b>\n"
        text += f"   📌 ID: <code>{admin_id}</code>\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")]
        ]
    )
    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"show_admins_list edit failed: {e}, sending new")
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


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
    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"show_stats edit failed: {e}, sending new")
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


# ==================== КОМАНДА /command ДЛЯ АДМИНОВ ====================
@admin_router.message(Command("command"), F.from_user.id.in_(ADMIN_IDS))
async def admin_command_list(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/start")],
            [KeyboardButton(text="/command"), KeyboardButton(text="/about")],
            [KeyboardButton(text="/register"), KeyboardButton(text="/cancel")],
            [KeyboardButton(text="/admin")],
        ],
        resize_keyboard=True,
    )
    text = (
        "📋 <b>Команды бота</b>\n"
        "═══════════════════════\n\n"
        "🏠 <b>Главное</b>\n"
        "  /start — запустить бота\n"
        "  /command — список команд\n\n"
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
    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


# ==================== ВХОД В АДМИН-ПАНЕЛЬ ====================
@admin_router.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def admin_panel(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [
                InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_list_users"),
                InlineKeyboardButton(text="👑 Список админов", callback_data="admin_list_admins"),
            ],
            [InlineKeyboardButton(text="📋 Заказы", callback_data="admin_orders_menu")],
            [InlineKeyboardButton(text="📦 Управление товарами", callback_data="admin_products")],
            [InlineKeyboardButton(text="📊 Экспорт заказов", callback_data="admin_export_orders")],
            [InlineKeyboardButton(text="🚪 Выйти", callback_data="admin_exit")],
        ]
    )
    await state.set_state(AdminState.in_panel)
    await message.answer(
        "🔐 <b>Админ-панель</b>\n\nВыберите действие:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


# ==================== ОБРАБОТКА КНОПОК ====================
@admin_router.callback_query(StateFilter(AdminState.in_panel), F.data.startswith("admin_"))
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
        try:
            await callback.message.edit_text("🚪 Вы вышли из админ-панели.")
        except Exception as e:
            logger.warning(f"admin_exit edit failed: {e}")
            await callback.message.answer("🚪 Вы вышли из админ-панели.")
        await callback.answer()
    elif action == "admin_back_to_panel":
        await show_admin_panel(callback.message, state)
        await callback.answer()


# ==================== ИЗМЕНЕНИЕ СТАТУСА ЗАКАЗА ====================
@admin_router.callback_query(F.data.startswith("ostatus_"), IsAdmin())
async def admin_change_status_callback(callback: CallbackQuery, state: FSMContext):
    """Изменение статуса заказа"""
    from db import (
        get_order_by_id,
        notify_user_safe,
        return_stock_on_cancel,
        get_product_stock,
        decrease_product_stock,
    )

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

    current_status = order[10] if len(order) > 10 else None

    if current_status == new_status:
        await callback.answer("ℹ️ Статус уже установлен", show_alert=True)
        return

    try:
        old_status = current_status
        await update_order_status(order_id, new_status)

        # ---- Возврат товара при отмене ----
        if key == "cancelled" and old_status != "отменён":
            stock_restored = await return_stock_on_cancel(order_id)
            if stock_restored:
                logger.info(f"✅ Stock restored for cancelled order #{order_id}")
            else:
                logger.warning(f"⚠️ Failed to restore stock for order #{order_id}")

        # ---- Симметричный возврат из "отменён" в активный статус ----
        if old_status == "отменён" and new_status != "отменён":
            product_id = order[15] if len(order) > 15 else None  # product_id в индексе 15
            quantity = order[7] or 0  # количество в заказе

            if product_id and quantity > 0:
                current_stock = await get_product_stock(product_id)

                if current_stock >= quantity:
                    success = await decrease_product_stock(product_id, quantity)
                    if success:
                        logger.info(f"✅ Stock decreased for restored order #{order_id} (product {product_id}, qty {quantity})")
                    else:
                        logger.warning(f"⚠️ Failed to decrease stock for restored order #{order_id}")
                else:
                    warning_text = (
                        f"⚠️ <b>Недостаточно товара на складе для возврата заказа в работу!</b>\n\n"
                        f"Заказ #{order_id}\n"
                        f"Товар: {escape_html(order[6] or 'не указан')}\n"
                        f"Количество: {quantity} шт.\n"
                        f"Доступно на складе: {current_stock} шт.\n\n"
                        f"Статус заказа изменён, но товар на складе не зарезервирован.\n"
                        f"Пожалуйста, пополните склад или свяжитесь с клиентом."
                    )
                    for admin_id in ADMIN_IDS:
                        await notify_user_safe(
                            callback.bot,
                            chat_id=admin_id,
                            text=warning_text
                        )
                    await callback.answer(
                        f"⚠️ Товара недостаточно: {current_stock} шт. вместо {quantity}",
                        show_alert=True
                    )
            else:
                logger.warning(f"⚠️ Order #{order_id} has no product_id or quantity, cannot restore stock")

        data = await state.get_data()
        status_filter = data.get("orders_filter")
        page = data.get("orders_page", 0)

        user_id = order[1]
        product_name = order[6] or "товар"
        delivery_method = order[8] or "не указан"
        delivery_address = order[9] or "не указан"

        notify_text = None
        if new_status in STATUS_MESSAGES:
            notify_text = STATUS_MESSAGES[new_status].format(
                id=order_id,
                product=escape_html(product_name),
                delivery=escape_html(delivery_method),
                address=escape_html(delivery_address),
            )

        notification_sent = False
        if notify_text and user_id:
            notification_sent = await notify_user_safe(
                callback.bot,
                chat_id=user_id,
                text=notify_text,
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

            status_text = "✅ Клиент уведомлён" if notification_sent else "⚠️ Клиент не уведомлён (заблокировал бота?)"

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
                f"✅ Статус изменён на {STATUSES[key]['label']}, но клиент не уведомлён",
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
        f"👤 Клиент: {escape_html(order[2] or 'не указан')}\n"
        f"🛒 Товар: {escape_html(order[6] or 'не указан')}\n"
        f"📌 Текущий статус: {order[10] or 'новый'}\n\n"
        f"Выберите новый статус:"
    )

    await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
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

    unit_price = order[13] if len(order) > 13 and order[13] else 0
    quantity = order[7] or 0
    total_price = quantity * unit_price

    text = (
        f"⚠️ <b>Подтверждение отмены заказа #{order_id}</b>\n\n"
        f"👤 Клиент: {escape_html(order[2] or 'не указан')}\n"
        f"🛒 Товар: {escape_html(order[6] or 'не указан')}\n"
        f"📦 Количество: {quantity} шт.\n"
        f"💰 Цена за шт.: {unit_price} ₽\n"
        f"💵 Сумма: {total_price} ₽\n"
        f"\n<b>Вы уверены, что хотите отменить этот заказ?</b>\n"
        f"⚠️ При отмене товар вернётся на склад."
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("back_to_order_"), IsAdmin())
async def back_to_order_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат к заказу из меню выбора статуса"""
    order_id = int(callback.data.split("_")[3])
    
    data = await state.get_data()
    status_filter = data.get("orders_filter")
    page = data.get("orders_page", 0)
    
    # Устанавливаем ID текущего сообщения (меню выбора статуса) как фото-сообщение,
    # чтобы show_orders_list отредактировала именно его
    await state.update_data(last_orders_photo_message_id=callback.message.message_id)
    
    # Показываем карточку заказа (она заменит текущее сообщение)
    await show_orders_list(callback.message, state, status_filter, page)
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
        user_id = order[1] if order else None

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

        # Показываем карточку заказа (отправим новое сообщение)
        await show_orders_list(message, state, status_filter, page)

        # Отдельное уведомление об успехе (можно объединить с карточкой, но пока так)
        if notification_sent:
            await message.answer(
                f"✅ <b>Трек-номер для заказа #{order_id} добавлен!</b>\n"
                f"📦 {escape_html(tracking_number)}\n\n"
                f"✅ Клиент уведомлён",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.answer(
                f"✅ <b>Трек-номер для заказа #{order_id} добавлен!</b>\n"
                f"📦 {escape_html(tracking_number)}\n\n"
                f"⚠️ Клиент не уведомлён (заблокировал бота?)",
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
        quantity = order[7] or 0
        unit_price = order[13] if len(order) > 13 and order[13] else 0
        total_price = quantity * unit_price

        writer.writerow(
            [
                order[0],
                order[1] or "",
                order[2] or "",
                order[3] or "",
                order[4] or "",
                order[6] or "",
                quantity,
                unit_price,
                total_price,
                order[8] or "",
                order[9] or "",
                order[14] or "",
                order[10] or "",
                order[11] or "",
                order[12] or "",
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
async def show_orders_list(
    message: Message,
    state: FSMContext,
    status_filter: str = None,
    page: int = 0,
):
    """Показать один заказ с пагинацией и фото товара"""
    from db import get_orders_paginated, get_orders_count, get_product_by_id

    limit = 1
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
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_orders_menu")]
            ]
        )
        try:
            await message.edit_text(
                "📭 Нет заказов с выбранным фильтром.",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"show_orders_list edit failed: {e}, sending new")
            await message.answer("📭 Нет заказов с выбранным фильтром.", reply_markup=keyboard)
        return

    order = orders[0]

    product_id = order[12]
    product_image = None
    if product_id:
        product = await get_product_by_id(product_id)
        if product and len(product) > 7:
            product_image = product[7]

    unit_price = order[13] if len(order) > 13 and order[13] else 0
    quantity = order[6] or 0
    total_price = quantity * unit_price

    status = order[9] or "новый"

    status_emoji = {
        "новый": "🆕",
        "в обработке": "🔄",
        "отправлен": "📦",
        "доставлен": "✅",
        "отменён": "❌",
    }
    emoji = status_emoji.get(status, "📌")

    filter_names = {
        "active": "🟢 Активные заказы",
        "completed": "✅ Завершённые заказы",
        None: "📋 Все заказы",
    }
    title = filter_names.get(status_filter, "📋 Все заказы")

    text = (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📄 Заказ {page + 1} из {total_pages}\n\n"
        f"{emoji} <b>Заказ #{order[0]}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Клиент:</b> {escape_html(order[1])}\n"
        f"📞 <b>Телефон:</b> {escape_html(order[2])}\n"
        f"📧 <b>Email:</b> {escape_html(order[3] or 'не указан')}\n"
        f"🏙️ <b>Город:</b> {escape_html(order[4] or 'не указан')}\n\n"
        f"🛒 <b>Товар:</b> {escape_html(order[5])}\n"
        f"📦 <b>Количество:</b> {quantity} шт.\n"
        f"💰 <b>Цена за шт.:</b> {unit_price} ₽\n"
        f"💵 <b>Сумма:</b> {total_price} ₽\n"
        f"🚚 <b>Доставка:</b> {order[7]}\n"
        f"📍 <b>Адрес:</b> {escape_html(order[8])}\n"
    )

    if order[11]:
        text += f"📦 <b>Трек-номер:</b> {escape_html(order[11])}\n"
    if order[14]:
        text += f"📝 <b>Комментарий:</b> {escape_html(order[14])}\n"
    text += f"📌 <b>Статус:</b> {status}\n"
    text += f"📅 <b>Создан:</b> {format_moscow_time(order[10])}\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━\n"

    keyboard_rows = [
        [InlineKeyboardButton(text="🔄 Изменить статус", callback_data=f"change_status_{order[0]}")],
        [
            InlineKeyboardButton(text="🔵 Активные", callback_data="orders_filter_active"),
            InlineKeyboardButton(text="🟢 Все", callback_data="orders_filter_all"),
            InlineKeyboardButton(text="✅ Заверш.", callback_data="orders_filter_completed"),
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"orders_page_{page - 1}") if page > 0 else None,
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"orders_page_{page + 1}") if page < total_pages - 1 else None,
        ],
        [InlineKeyboardButton(text="📊 Экспорт заказов", callback_data="admin_export_orders")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_orders_menu")],
    ]

    keyboard_rows[2] = [btn for btn in keyboard_rows[2] if btn is not None]
    keyboard_rows = [row for row in keyboard_rows if row]

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    data = await state.get_data()
    last_orders_photo_message_id = data.get("last_orders_photo_message_id")

    # Если есть фото — используем edit_message_media
    if product_image:
        try:
            if last_orders_photo_message_id:
                # Редактируем существующее фото-сообщение
                await message.bot.edit_message_media(
                    chat_id=message.chat.id,
                    message_id=last_orders_photo_message_id,
                    media=InputMediaPhoto(
                        media=product_image,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=keyboard,
                )
                return
            else:
                # Первое фото — отправляем новое сообщение
                photo_msg = await message.answer_photo(
                    photo=product_image,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
                await state.update_data(last_orders_photo_message_id=photo_msg.message_id)
                try:
                    await message.delete()
                except Exception:
                    pass
                return
        except Exception as e:
            error_text = str(e).lower()
            # Если ошибка "message is not modified" — просто игнорируем
            if "message is not modified" in error_text:
                return
            # Иначе — fallback с отправкой нового фото
            logger.warning(f"Error editing/sending order photo: {e}, fallback to new message")
            photo_msg = await message.answer_photo(
                photo=product_image,
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            await state.update_data(last_orders_photo_message_id=photo_msg.message_id)
            try:
                await message.delete()
            except Exception:
                pass
            return

    # Если фото нет — текстовый вариант
    if last_orders_photo_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_orders_photo_message_id)
        except Exception:
            pass
        await state.update_data(last_orders_photo_message_id=None)

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"show_orders_list edit failed: {e}, sending new")
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


# ==================== ОБРАБОТКА ЗАКАЗОВ ====================
@admin_router.callback_query(StateFilter(AdminState.in_panel), F.data == "admin_orders_menu")
async def admin_orders_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора фильтра заказов"""
    data = await state.get_data()
    last_id = data.get("last_orders_photo_message_id")
    if last_id:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=last_id)
        except Exception:
            pass
        await state.update_data(last_orders_photo_message_id=None)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Активные", callback_data="orders_filter_active")],
            [InlineKeyboardButton(text="📋 Все заказы", callback_data="orders_filter_all")],
            [InlineKeyboardButton(text="✅ Завершённые", callback_data="orders_filter_completed")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")],
        ]
    )

    try:
        await callback.message.edit_text(
            "📋 <b>Выберите категорию заказов:</b>\n\n"
            "🟢 <b>Активные</b> — Новые и в обработке\n"
            "📋 <b>Все</b> — Все заказы без фильтра\n"
            "✅ <b>Завершённые</b> — Доставленные и отменённые",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"admin_orders_menu edit failed: {e}, sending new")
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "📋 <b>Выберите категорию заказов:</b>\n\n"
            "🟢 <b>Активные</b> — Новые и в обработке\n"
            "📋 <b>Все</b> — Все заказы без фильтра\n"
            "✅ <b>Завершённые</b> — Доставленные и отменённые",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@admin_router.callback_query(StateFilter(AdminState.in_panel), F.data.startswith("orders_filter_"))
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


@admin_router.callback_query(StateFilter(AdminState.in_panel), F.data.startswith("orders_page_"))
async def orders_page_callback(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы заказов"""
    page = int(callback.data.split("_")[2])
    data = await state.get_data()
    status_filter = data.get("orders_filter")
    await show_orders_list(callback.message, state, status_filter, page)
    await callback.answer()


@admin_router.callback_query(StateFilter(AdminOrdersState.adding_tracking), F.data == "admin_back_to_order")
async def admin_back_to_order(callback: CallbackQuery, state: FSMContext):
    """Возврат к заказу без добавления трек-номера"""
    data = await state.get_data()
    order_id = data.get("tracking_order_id")
    status_filter = data.get("orders_filter", None)
    page = data.get("orders_page", 0)

    await state.clear()

    # Устанавливаем ID текущего сообщения (запрос трек-номера) как фото-сообщение,
    # чтобы show_orders_list отредактировала именно его
    await state.update_data(last_orders_photo_message_id=callback.message.message_id)

    if order_id:
        await show_orders_list(callback.message, state, status_filter, page)
    else:
        await callback.message.edit_text("❌ Заказ не найден.")
    await callback.answer()