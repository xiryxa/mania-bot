# ==================== ИМПОРТЫ ====================
import logging
from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from db import (
    escape_html,
    format_moscow_time,
    get_order_by_id,
    get_product_by_id,
    get_user_orders_count,
    notify_user_safe,
    update_order_status,
)

# ==================== НАСТРОЙКА ====================
logger = logging.getLogger(__name__)
router = Router()


# ==================== МЕНЮ МОИХ ЗАКАЗОВ ====================
@router.callback_query(F.data == "profile_orders")
async def profile_orders_callback(callback: CallbackQuery, state: FSMContext):
    """Меню заказов пользователя с фильтрами"""
    from db import get_user_orders_count_by_status, get_user_orders_count

    await state.update_data(profile_orders_page=0, profile_orders_filter="all")

    user_id = callback.from_user.id
    total_new = await get_user_orders_count_by_status(user_id, ["новый", "в обработке", "отправлен"])
    total_completed = await get_user_orders_count_by_status(user_id, ["доставлен", "отменён"])
    total_all = await get_user_orders_count(user_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    if total_new > 0:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text=f"🆕 Активные ({total_new})", callback_data="profile_orders_filter_new")]
        )
    if total_completed > 0:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text=f"✅ Завершённые ({total_completed})", callback_data="profile_orders_filter_completed")]
        )
    if total_all > 0:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text=f"📋 Все заказы ({total_all})", callback_data="profile_orders_filter_all")]
        )

    keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_profile")])

    if total_all == 0:
        await callback.message.edit_text(
            "📭 У вас пока нет заказов.\n\n"
            "Перейдите в /shop, чтобы сделать первый заказ!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_profile")]
                ]
            ),
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📋 <b>Мои заказы</b>\n\n"
        "Выберите категорию для просмотра:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("profile_orders_filter_"))
async def profile_orders_filter_callback(callback: CallbackQuery, state: FSMContext):
    """Показать заказы с выбранным фильтром"""
    from db import get_user_orders_count_by_status

    filter_type = callback.data.split("_")[3]
    status_filter_map = {
        "new": ["новый", "в обработке", "отправлен"],
        "completed": ["доставлен", "отменён"],
        "all": None,
    }
    status_filter = status_filter_map.get(filter_type)

    user_id = callback.from_user.id
    await state.update_data(profile_orders_filter=filter_type, profile_orders_page=0)
    await show_profile_orders_list(callback.message, state, user_id, status_filter, page=0)
    await callback.answer()


@router.callback_query(F.data == "profile_orders_back_to_menu")
async def profile_orders_back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в меню выбора категорий заказов"""
    from db import get_user_orders_count_by_status, get_user_orders_count

    await state.update_data(profile_orders_page=0, profile_orders_filter="all")

    data = await state.get_data()
    last_id = data.get("profile_last_photo_message_id")
    if last_id:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=last_id)
        except Exception:
            pass
        await state.update_data(profile_last_photo_message_id=None)

    try:
        await callback.message.delete()
    except Exception:
        pass

    user_id = callback.from_user.id
    total_new = await get_user_orders_count_by_status(user_id, ["новый", "в обработке", "отправлен"])
    total_completed = await get_user_orders_count_by_status(user_id, ["доставлен", "отменён"])
    total_all = await get_user_orders_count(user_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    if total_new > 0:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text=f"🆕 Активные ({total_new})", callback_data="profile_orders_filter_new")]
        )
    if total_completed > 0:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text=f"✅ Завершённые ({total_completed})", callback_data="profile_orders_filter_completed")]
        )
    if total_all > 0:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text=f"📋 Все заказы ({total_all})", callback_data="profile_orders_filter_all")]
        )
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_profile")])

    await callback.message.answer(
        "📋 <b>Мои заказы</b>\n\n"
        "Выберите категорию для просмотра:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("profile_orders_page_"))
async def profile_orders_page_callback(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы в заказах пользователя"""
    data = await state.get_data()
    page = data.get("profile_orders_page", 0)
    filter_type = data.get("profile_orders_filter", "all")

    if "prev" in callback.data:
        page -= 1
    elif "next" in callback.data:
        page += 1
    else:
        try:
            page = int(callback.data.split("_")[3])
        except ValueError:
            pass

    await state.update_data(profile_orders_page=page)

    user_id = callback.from_user.id
    status_filter_map = {
        "new": ["новый", "в обработке", "отправлен"],
        "completed": ["доставлен", "отменён"],
        "all": None,
    }
    statuses = status_filter_map.get(filter_type)

    await show_profile_orders_list(callback.message, state, user_id, statuses, page)
    await callback.answer()


# ==================== ОТОБРАЖЕНИЕ СПИСКА ЗАКАЗОВ ====================
async def show_profile_orders_list(
    message: Message,
    state: FSMContext,
    user_id: int,
    statuses: list = None,
    page: int = 0,
):
    """Показать заказы пользователя с пагинацией и фильтром"""
    from db import (
        get_user_orders_paginated_by_status,
        get_user_orders_count_by_status,
        get_user_orders_count,
        format_moscow_time,
        get_product_by_id,
    )

    limit = 1
    offset = page * limit

    orders = await get_user_orders_paginated_by_status(user_id, statuses, offset, limit)

    if statuses:
        total = await get_user_orders_count_by_status(user_id, statuses)
    else:
        total = await get_user_orders_count(user_id)

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    if not orders:
        total_new = await get_user_orders_count_by_status(user_id, ["новый", "в обработке", "отправлен"])
        total_completed = await get_user_orders_count_by_status(user_id, ["доставлен", "отменён"])
        total_all = await get_user_orders_count(user_id)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        if total_new > 0:
            keyboard.inline_keyboard.append(
                [InlineKeyboardButton(text=f"🆕 Активные ({total_new})", callback_data="profile_orders_filter_new")]
            )
        if total_completed > 0:
            keyboard.inline_keyboard.append(
                [InlineKeyboardButton(text=f"✅ Завершённые ({total_completed})", callback_data="profile_orders_filter_completed")]
            )
        if total_all > 0:
            keyboard.inline_keyboard.append(
                [InlineKeyboardButton(text=f"📋 Все заказы ({total_all})", callback_data="profile_orders_filter_all")]
            )
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_profile")])

        await message.edit_text(
            "📭 В этой категории пока нет заказов.\n\n"
            "Выберите другую категорию:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        return

    order = orders[0]
    status = order[5] or "новый"

    unit_price = order[9] if len(order) > 9 and order[9] else 0
    quantity = order[2] or 0
    total_price = quantity * unit_price

    product_image = None
    product_id = order[8]
    if product_id:
        product = await get_product_by_id(product_id)
        if product and len(product) > 7:
            product_image = product[7]

    status_emoji = {
        "новый": "🆕",
        "в обработке": "🔄",
        "отправлен": "📦",
        "доставлен": "✅",
        "отменён": "❌",
    }
    emoji = status_emoji.get(status, "📌")

    data = await state.get_data()
    filter_type = data.get("profile_orders_filter", "all")
    filter_names = {
        "new": "🆕 Активные заказы",
        "completed": "✅ Завершённые заказы",
        "all": "📋 Все заказы",
    }
    title = filter_names.get(filter_type, "📋 Все заказы")

    text = (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📄 Заказ {page + 1} из {total_pages}\n\n"
        f"{emoji} <b>Заказ #{order[0]}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🛒 <b>Товар:</b> {escape_html(order[1])}\n"
        f"📦 <b>Количество:</b> {quantity} шт.\n"
        f"💰 <b>Цена за шт.:</b> {unit_price} ₽\n"
        f"💵 <b>Сумма:</b> {total_price} ₽\n"
        f"🚚 <b>Доставка:</b> {order[3]}\n"
        f"📍 <b>Адрес:</b> {escape_html(order[4])}\n"
    )
    if order[10]:
        text += f"📦 <b>Трек-номер:</b> {escape_html(order[10])}\n"
    text += f"📅 <b>Дата:</b> {format_moscow_time(order[7])}\n"
    text += f"📌 <b>Статус:</b> {status}\n"
    if order[6]:
        text += f"📝 <b>Комментарий:</b> {escape_html(order[6])}\n"

    keyboard_buttons = []

    if status == "отправлен":
        keyboard_buttons.append(
            [InlineKeyboardButton(text="✅ Я получил заказ", callback_data=f"confirm_delivery_{order[0]}")]
        )

    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data="profile_orders_page_prev"))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data="profile_orders_page_next"))
    if pagination_buttons:
        keyboard_buttons.append(pagination_buttons)

    total_new = await get_user_orders_count_by_status(user_id, ["новый", "в обработке", "отправлен"])
    total_completed = await get_user_orders_count_by_status(user_id, ["доставлен", "отменён"])
    total_all = await get_user_orders_count(user_id)

    filter_row = []
    if total_new > 0:
        filter_row.append(InlineKeyboardButton(text=f"🆕 {total_new}", callback_data="profile_orders_filter_new"))
    if total_completed > 0:
        filter_row.append(InlineKeyboardButton(text=f"✅ {total_completed}", callback_data="profile_orders_filter_completed"))
    if total_all > 0:
        filter_row.append(InlineKeyboardButton(text=f"📋 {total_all}", callback_data="profile_orders_filter_all"))
    if filter_row:
        keyboard_buttons.append(filter_row)

    keyboard_buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="profile_orders_back_to_menu")]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    data = await state.get_data()
    last_orders_photo_message_id = data.get("profile_last_photo_message_id")

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
                await state.update_data(profile_last_photo_message_id=photo_msg.message_id)
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
            logger.warning(f"Error editing/sending order photo in profile: {e}, fallback to new message")
            photo_msg = await message.answer_photo(
                photo=product_image,
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            await state.update_data(profile_last_photo_message_id=photo_msg.message_id)
            try:
                await message.delete()
            except Exception:
                pass
            return

    # Если фото нет — текстовый вариант
    if last_orders_photo_message_id:
        # Удаляем старое фото-сообщение и сразу отправляем новое текстовое
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_orders_photo_message_id)
        except Exception:
            pass
        await state.update_data(profile_last_photo_message_id=None)
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        return

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"show_profile_orders_list edit failed: {e}, sending new")
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


# ==================== ПОДТВЕРЖДЕНИЕ ПОЛУЧЕНИЯ ЗАКАЗА ====================
@router.callback_query(F.data.startswith("confirm_delivery_"))
async def confirm_delivery_callback(callback: CallbackQuery, state: FSMContext):
    """Подтверждение получения заказа покупателем"""
    from db import get_order_by_id, notify_user_safe
    from handlers.admin import ADMIN_IDS

    await state.clear()

    order_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    order = await get_order_by_id(order_id)
    if not order:
        await callback.message.edit_text("❌ Заказ не найден.")
        await callback.answer()
        return

    if order[1] != user_id:
        await callback.answer("❌ Это не ваш заказ.")
        return

    if order[10] != "отправлен":
        await callback.message.edit_text(
            "❌ Вы можете подтвердить получение только для заказов со статусом 'отправлен'.",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return

    await update_order_status(order_id, "доставлен")

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        f"✅ <b>Заказ #{order_id} отмечен как доставленный!</b>\n\n"
        f"Спасибо, что пользуетесь нашими услугами!\n"
        f"🦆 <i>Приманивайте и будьте с Манией!</i>",
        parse_mode=ParseMode.HTML,
    )

    if ADMIN_IDS:
        admin_chat_id = ADMIN_IDS[0]
        product_name = order[6] or "не указан"
        fullname = order[2] or "не указан"

        unit_price = order[13] if len(order) > 13 and order[13] else 0
        quantity = order[7] or 0
        total_price = quantity * unit_price

        admin_text = (
            f"✅ <b>Клиент подтвердил получение заказа #{order_id}!</b>\n\n"
            f"👤 Клиент: {escape_html(fullname)}\n"
            f"🛒 Товар: {escape_html(product_name)}\n"
            f"📦 Количество: {quantity} шт.\n"
            f"💰 Цена за шт.: {unit_price} ₽\n"
            f"💵 Сумма: {total_price} ₽\n"
            f"🚚 Доставка: {order[8] or 'не указан'}\n"
            f"📍 Адрес: {escape_html(order[9] or 'не указан')}\n"
        )
        if order[14]:
            admin_text += f"📝 Комментарий: {escape_html(order[14])}\n"

        await notify_user_safe(callback.bot, chat_id=admin_chat_id, text=admin_text)

    await callback.answer()