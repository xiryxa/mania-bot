# ==================== ИМПОРТЫ ====================
import logging
from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from utils.validators import validate_fullname, validate_phone, validate_city
from email_validator import EmailNotValidError, validate_email
from db import (
    check_and_notify_low_stock,
    create_order_and_decrease_stock,
    escape_html,
    format_moscow_time,
    get_order_by_id,
    get_product_by_id,
    get_product_stock,
    get_user_by_telegram_id,
    get_user_orders_count,
    get_user_orders_paginated,
    LOW_STOCK_THRESHOLD,
    update_order_status,
    update_user,
)
from forms.users import Form, OrderState, ProfileState, UpdateState

# ==================== НАСТРОЙКА ====================
logger = logging.getLogger(__name__)
router = Router()


# ==================== ОБЩИЕ ФУНКЦИИ ====================
async def show_profile(message: Message, user_data, state: FSMContext = None):
    if state:
        await state.set_state(ProfileState.viewing)
        await state.update_data(existing_user=user_data)

    orders_count = await get_user_orders_count(user_data[0])

    created_at_raw = user_data[7] if len(user_data) > 7 else None
    if created_at_raw:
        created_at_str = format_moscow_time(created_at_raw)
        created_at_date = created_at_str.split()[0]
    else:
        created_at_date = "неизвестно"

    text = (
        f"👤 <b>Ваш профиль</b>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>ФИО:</b> {escape_html(user_data[1]) or 'не указано'}\n"
        f"📞 <b>Телефон:</b> {escape_html(user_data[2]) or 'не указан'}\n"
        f"✉️ <b>Email:</b> {escape_html(user_data[3]) or 'не указан'}\n"
        f"🏙️ <b>Город:</b> {escape_html(user_data[4]) or 'не указан'}\n"
        f"\n🆔 <b>Юзернейм:</b> @{escape_html(user_data[6]) or 'нет'}\n"
        f"📅 <b>Дата регистрации:</b> {created_at_date}\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🛒 <b>Заказов:</b> {orders_count}"
    )

    keyboard_buttons = []
    if orders_count > 0:
        keyboard_buttons.append([InlineKeyboardButton(text="📋 Мои заказы", callback_data="profile_orders")])
    keyboard_buttons.append([InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="update_data")])
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="close_profile")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"show_profile edit failed: {e}, sending new")
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def start_register_message(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start")]
        ]
    )

    text = (
        "📝 <b>Регистрация</b>\n\n"
        "Для оформления заказов нам нужны ваши контактные данные.\n"
        "Введите ваше <b>ФИО</b>:"
    )

    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await state.set_state(Form.name)


# ==================== ОСНОВНЫЕ CALLBACK-ЗАПРОСЫ ====================
@router.callback_query(lambda c: c.data == "start_shop")
async def start_shop_callback(callback: CallbackQuery):
    """Переход в магазин из главного меню (редактирует сообщение)"""
    from handlers.shop import shop_main

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🦆 Манки", callback_data="shop_category_manks")],
            [InlineKeyboardButton(text="🛖 Засидки", callback_data="shop_category_zasadki")],
            [InlineKeyboardButton(text="👕 Аксессуары", callback_data="shop_category_accessories")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start")],
        ]
    )

    await callback.message.edit_text(
        "🛒 <b>Добро пожаловать в MANIA!</b>\n\n"
        "Здесь вы можете заказать профессиональные манки для охоты на гуся и утку.\n\n"
        "Выберите категорию:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()



@router.callback_query(lambda c: c.data == "start_profile")
async def start_profile_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    existing_user = await get_user_by_telegram_id(user_id)
    if existing_user:
        await state.update_data(existing_user=existing_user)
        await show_profile(callback.message, existing_user, state)
    else:
        try:
            await callback.message.edit_text("📭 Вы ещё не зарегистрированы.")
        except Exception as e:
            logger.warning(f"start_profile_callback edit failed: {e}")
            await callback.message.answer("📭 Вы ещё не зарегистрированы.")
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("product_") and c.data[8:].isdigit())
async def product_detail(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = await get_product_by_id(product_id)
    if not product:
        try:
            await callback.message.edit_text("❌ Товар не найден.")
        except Exception as e:
            logger.warning(f"product_detail edit failed: {e}")
            await callback.message.answer("❌ Товар не найден.")
        await callback.answer()
        return

    description = escape_html(product[2] or "Описание отсутствует")
    text = (
        f"🔹 <b>{escape_html(product[1])}</b>\n"
        f"🏷️ {escape_html(product[4])}\n"
        f"📝 {description}\n"
        f"💰 {product[3]} ₽\n"
        f"✅ {'В наличии' if product[5] else 'Нет в наличии'}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 Заказать", callback_data=f"order_product_{product_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_shop")],
        ]
    )
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"product_detail edit failed: {e}, sending new")
        await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(lambda c: c.data == "back_to_shop")
async def back_to_shop(callback: CallbackQuery):
    """Возврат в главное меню магазина (редактирует сообщение)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🦆 Манки", callback_data="shop_category_manks")],
            [InlineKeyboardButton(text="🛖 Засидки", callback_data="shop_category_zasadki")],
            [InlineKeyboardButton(text="👕 Аксессуары", callback_data="shop_category_accessories")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start")],
        ]
    )
    await callback.message.edit_text(
        "🛒 <b>Добро пожаловать в MANIA!</b>\n\n"
        "Здесь вы можете заказать профессиональные манки для охоты на гуся и утку.\n\n"
        "Выберите категорию:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "start_register")
async def start_register_callback(callback: CallbackQuery, state: FSMContext):
    """Переход к регистрации из главного меню (для незарегистрированных)"""
    await start_register_message(callback.message, state)
    await callback.answer()



@router.callback_query(lambda c: c.data == "close_profile")
async def close_profile_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("👤 Профиль закрыт.")
    except Exception as e:
        logger.warning(f"close_profile edit failed: {e}")
        await callback.message.answer("👤 Профиль закрыт.")
    await callback.answer()


# ==================== ОБНОВЛЕНИЕ ДАННЫХ ====================
@router.callback_query(lambda c: c.data == "update_data")
async def update_data_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    existing_user = data.get("existing_user")
    if not existing_user:
        try:
            await callback.message.edit_text("❌ Данные не найдены.")
        except Exception as e:
            logger.warning(f"update_data_callback edit failed: {e}")
            await callback.message.answer("❌ Данные не найдены.")
        await callback.answer()
        return

    buttons = [
        [InlineKeyboardButton(text="👤 ФИО", callback_data="update_name")],
        [InlineKeyboardButton(text="📞 Телефон", callback_data="update_phone")],
        [InlineKeyboardButton(text="✉️ Email", callback_data="update_email")],
        [InlineKeyboardButton(text="🏙️ Город", callback_data="update_city")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_profile")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = (
        f"📋 <b>Что хотите изменить?</b>\n\n"
        f"👤 ФИО: {escape_html(existing_user[1]) or 'не указано'}\n"
        f"📞 Телефон: {escape_html(existing_user[2]) or 'не указан'}\n"
        f"✉️ Email: {escape_html(existing_user[3]) or 'не указан'}\n"
        f"🏙️ Город: {escape_html(existing_user[4]) or 'не указан'}\n"
    )
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"update_data_callback edit failed: {e}, sending new")
        await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("update_"))
async def update_field_callback(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[1]
    data = await state.get_data()
    existing_user = data.get("existing_user")
    if not existing_user:
        try:
            await callback.message.edit_text("❌ Данные не найдены.")
        except Exception as e:
            logger.warning(f"update_field_callback edit failed: {e}")
            await callback.message.answer("❌ Данные не найдены.")
        await callback.answer()
        return

    field_names = {
        "name": ("ФИО", UpdateState.name),
        "phone": ("телефон", UpdateState.phone),
        "email": ("email", UpdateState.email),
        "city": ("город", UpdateState.city),
    }
    field_name, new_state = field_names.get(field, (None, None))
    if not new_state:
        await callback.answer()
        return

    await state.update_data(update_field=field)
    await state.set_state(new_state)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="back_to_profile")]
        ]
    )
    try:
        await callback.message.edit_text(
            f"✏️ Введите новое <b>{field_name}</b>:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"update_field_callback edit failed: {e}, sending new")
        await callback.message.answer(
            f"✏️ Введите новое <b>{field_name}</b>:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@router.callback_query(lambda c: c.data == "back_to_profile")
async def back_to_profile_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    existing_user = data.get("existing_user")
    if not existing_user:
        try:
            await callback.message.edit_text("❌ Данные не найдены.")
        except Exception as e:
            logger.warning(f"back_to_profile_callback edit failed: {e}")
            await callback.message.answer("❌ Данные не найдены.")
        await callback.answer()
        return

    updated_user = await get_user_by_telegram_id(callback.from_user.id)
    if updated_user:
        await state.update_data(existing_user=updated_user)
        await show_profile(callback.message, updated_user, state)
    else:
        await show_profile(callback.message, existing_user, state)
    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_update")
async def cancel_update_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("✅ Обновление данных отменено. Ваши данные остались прежними.")
    except Exception as e:
        logger.warning(f"cancel_update_callback edit failed: {e}")
        await callback.message.answer("✅ Обновление данных отменено. Ваши данные остались прежними.")
    await callback.answer()


# ==================== ОБНОВЛЕНИЕ ПОЛЕЙ (FSM) ====================
@router.message(UpdateState.name, F.text)
async def update_name(message: Message, state: FSMContext):
    fullname = message.text.strip()
    valid, error = validate_fullname(fullname)
    if not valid:
        await message.answer(error)
        return

    data = await state.get_data()
    existing_user = data.get("existing_user")
    if existing_user:
        await update_user(
            telegram_id=message.from_user.id,
            fullname=fullname,
            phone=existing_user[2],
            email=existing_user[3],
            city=existing_user[4],
            address=existing_user[5],
            username=message.from_user.username,
        )
        updated_user = await get_user_by_telegram_id(message.from_user.id)
        if updated_user:
            await state.update_data(existing_user=updated_user)
            await show_profile(message, updated_user, state)
        else:
            await message.answer("✅ <b>ФИО обновлено!</b>", parse_mode=ParseMode.HTML)
            await state.clear()


@router.message(UpdateState.phone, F.text)
async def update_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    valid, error = validate_phone(phone)
    if not valid:
        await message.answer(error, parse_mode=ParseMode.HTML)
        return

    data = await state.get_data()
    existing_user = data.get("existing_user")
    if existing_user:
        await update_user(
            telegram_id=message.from_user.id,
            fullname=existing_user[1],
            phone=phone,
            email=existing_user[3],
            city=existing_user[4],
            address=existing_user[5],
            username=message.from_user.username,
        )
        updated_user = await get_user_by_telegram_id(message.from_user.id)
        if updated_user:
            await state.update_data(existing_user=updated_user)
            await show_profile(message, updated_user, state)
        else:
            await message.answer("✅ <b>Телефон обновлён!</b>", parse_mode=ParseMode.HTML)
            await state.clear()


@router.message(UpdateState.email, F.text)
async def update_email(message: Message, state: FSMContext):
    email_raw = message.text.strip()
    try:
        valid = validate_email(email_raw)
        email = valid.normalized
    except EmailNotValidError as e:
        await message.answer(
            f"❌ Некорректный email: {str(e)}\nПопробуйте ещё раз:",
            parse_mode=ParseMode.HTML,
        )
        return

    data = await state.get_data()
    existing_user = data.get("existing_user")
    if existing_user:
        await update_user(
            telegram_id=message.from_user.id,
            fullname=existing_user[1],
            phone=existing_user[2],
            email=email,
            city=existing_user[4],
            address=existing_user[5],
            username=message.from_user.username,
        )
        updated_user = await get_user_by_telegram_id(message.from_user.id)
        if updated_user:
            await state.update_data(existing_user=updated_user)
            await show_profile(message, updated_user, state)
        else:
            await message.answer("✅ <b>Email обновлён!</b>", parse_mode=ParseMode.HTML)
            await state.clear()


@router.message(UpdateState.city, F.text)
async def update_city(message: Message, state: FSMContext):
    city = message.text.strip()
    valid, error = validate_city(city)
    if not valid:
        await message.answer(error)
        return

    data = await state.get_data()
    existing_user = data.get("existing_user")
    if existing_user:
        await update_user(
            telegram_id=message.from_user.id,
            fullname=existing_user[1],
            phone=existing_user[2],
            email=existing_user[3],
            city=city,
            address=existing_user[5],
            username=message.from_user.username,
        )
        updated_user = await get_user_by_telegram_id(message.from_user.id)
        if updated_user:
            await state.update_data(existing_user=updated_user)
            await show_profile(message, updated_user, state)
        else:
            await message.answer("✅ <b>Город обновлён!</b>", parse_mode=ParseMode.HTML)
            await state.clear()


# ==================== ЗАКАЗЫ (FSM) ====================
@router.callback_query(lambda c: c.data.startswith("order_product_"))
async def order_product_callback(callback: CallbackQuery, state: FSMContext):
    """Выбор товара для заказа"""
    user_id = callback.from_user.id
    user = await get_user_by_telegram_id(user_id)
    if not user:
        try:
            await callback.message.edit_text(
                "❌ Вы не зарегистрированы!\n\n"
                "Пожалуйста, сначала пройдите регистрацию через /register,\n"
                "а затем оформите заказ заново.",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"order_product_callback edit failed: {e}, sending new")
            await callback.message.answer(
                "❌ Вы не зарегистрированы!\n\n"
                "Пожалуйста, сначала пройдите регистрацию через /register,\n"
                "а затем оформите заказ заново.",
                parse_mode=ParseMode.HTML,
            )
        await callback.answer()
        return

    product_id = int(callback.data.split("_")[2])
    product = await get_product_by_id(product_id)
    if not product:
        try:
            await callback.message.edit_text("❌ Товар не найден.")
        except Exception as e:
            logger.warning(f"order_product_callback edit failed: {e}, sending new")
            await callback.message.answer("❌ Товар не найден.")
        await callback.answer()
        return

    await state.update_data(product_id=product_id, quantity=1)
    await state.set_state(OrderState.quantity)
    await show_quantity_selector(callback.message, state)
    await callback.answer()


@router.callback_query(lambda c: c.data == "profile_orders")
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


@router.callback_query(lambda c: c.data.startswith("profile_orders_filter_"))
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
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_orders_photo_message_id)
        except Exception:
            pass
        await state.update_data(profile_last_photo_message_id=None)

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"show_profile_orders_list edit failed: {e}, sending new")
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def show_quantity_selector(message: Message, state: FSMContext):
    """Показать счётчик количества"""
    data = await state.get_data()
    quantity = data.get("quantity", 1)
    product_id = data.get("product_id")
    product = await get_product_by_id(product_id)
    current_stock = await get_product_stock(product_id)

    text = (
        f"🔹 <b>{escape_html(product[1])}</b>\n"
        f"💰 {product[3]} ₽\n"
        f"📦 Доступно: <b>{current_stock}</b> шт.\n\n"
        f"📦 <b>Количество:</b> {quantity} шт."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➖", callback_data="qty_minus"),
                InlineKeyboardButton(text=f"{quantity}", callback_data="qty_display"),
                InlineKeyboardButton(text="➕", callback_data="qty_plus"),
            ],
            [
                InlineKeyboardButton(text="✅ Далее", callback_data="qty_confirm"),
                InlineKeyboardButton(text="⬅️ Отмена", callback_data="order_cancel"),
            ],
        ]
    )

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"show_quantity_selector edit failed: {e}, sending new")
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@router.callback_query(lambda c: c.data == "profile_orders_back_to_menu")
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


@router.callback_query(lambda c: c.data.startswith("qty_"))
async def quantity_control(callback: CallbackQuery, state: FSMContext):
    """Управление количеством: ➖, ➕, ✅ Далее"""
    action = callback.data
    data = await state.get_data()
    quantity = data.get("quantity", 1)
    product_id = data.get("product_id")

    if action == "qty_minus":
        quantity = max(1, quantity - 1)
        await state.update_data(quantity=quantity)
        await show_quantity_selector(callback.message, state)

    elif action == "qty_back":
        await show_quantity_selector(callback.message, state)

    elif action == "qty_plus":
        if quantity >= 99:
            await callback.answer("❌ Максимум 99 шт.", show_alert=True)
            return
        quantity += 1
        await state.update_data(quantity=quantity)
        await show_quantity_selector(callback.message, state)

    elif action == "qty_display":
        await callback.answer(f"Количество: {quantity} шт.", show_alert=True)

    elif action == "qty_confirm":
        if quantity < 1:
            await callback.answer("❌ Минимум 1 шт.", show_alert=True)
            return

        current_stock = await get_product_stock(product_id)

        if current_stock < quantity:
            product = await get_product_by_id(product_id)
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад к выбору количества", callback_data="qty_back")]
                ]
            )
            try:
                await callback.message.edit_text(
                    f"❌ <b>Недостаточно товара на складе!</b>\n\n"
                    f"📦 Товар: {escape_html(product[1])}\n"
                    f"📦 Доступно: <b>{current_stock}</b> шт.\n"
                    f"🛒 Запрошено: <b>{quantity}</b> шт.\n\n"
                    f"Пожалуйста, уменьшите количество или выберите другой товар.",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.warning(f"qty_confirm edit error: {e}")
                await callback.message.answer(
                    f"❌ <b>Недостаточно товара на складе!</b>\n\n"
                    f"📦 Товар: {escape_html(product[1])}\n"
                    f"📦 Доступно: <b>{current_stock}</b> шт.\n"
                    f"🛒 Запрошено: <b>{quantity}</b> шт.\n\n"
                    f"Пожалуйста, уменьшите количество или выберите другой товар.",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
            await callback.answer()
            return

        await state.update_data(quantity=quantity)
        await ask_delivery_method(callback.message, state)

    await callback.answer()


async def ask_delivery_method(message: Message, state: FSMContext):
    """Спросить способ доставки с подробным описанием"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📮 Почта России", callback_data="delivery_post")],
            [InlineKeyboardButton(text="🚚 СДЭК", callback_data="delivery_cdek")],
            [InlineKeyboardButton(text="🚚 Яндекс Доставка", callback_data="delivery_yandex")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="order_cancel")],
        ]
    )

    text = (
        "🚚 <b>Выберите способ доставки:</b>\n\n"
        "📮 <b>Почта России</b> — доступна по всей стране.\n"
        "• Отправка по номеру телефона (нужно согласие получателя).\n"
        "• Получение по паспорту или СМС-коду в отделении.\n"
        "• Срок хранения — 15 дней.\n"
        "Срок: 5–14 дней.\n"
        '<a href="https://www.pochta.ru/support">📄 Подробнее о правилах</a>\n\n'
        "🚚 <b>СДЭК</b> — быстрая доставка по городам.\n"
        "• Получение в пункте выдачи по паспорту или СДЭК ID.\n"
        "• Рекомендуем проверять товар при получении.\n"
        "Срок: 2–5 рабочих дней.\n"
        '<a href="https://www.cdek.ru/ru/faq/">📄 Подробнее о правилах</a>\n\n'
        "🚚 <b>Яндекс Доставка</b> — курьерская доставка до двери.\n"
        "• Курьер приедет по указанному адресу.\n"
        "• Отслеживание статуса доставки в реальном времени.\n"
        "• Быстрая и надёжная доставка по городам России.\n"
        "Срок: 1–3 дня.\n"
        '<a href="https://yandex.ru/delivery">📄 Подробнее о правилах</a>'
    )

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"ask_delivery_method edit failed: {e}, sending new")
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    await state.set_state(OrderState.delivery_method)

@router.callback_query(lambda c: c.data.startswith("delivery_"))
async def order_delivery(callback: CallbackQuery, state: FSMContext):
    """Выбор способа доставки"""
    method = callback.data.split("_")[1]
    method_names = {
        "post": "Почта России",
        "cdek": "СДЭК",
        "yandex": "Яндекс Доставка",
    }

    # Ссылки на карты ПВЗ только для Почты и СДЭК
    map_links = {
        "post": "https://yandex.ru/maps/?text=Почта%20России&mode=search",
        "cdek": "https://yandex.ru/maps/?text=CDEK&mode=search",
        # Яндекс Доставка — курьер, карта не нужна
    }

    address_examples = {
        "post": "г. Уткинск, ул. Охотничья, д. 7, индекс 123456",
        "cdek": "г. Уткинск, ул. Свистковая, д. 5, ПВЗ СДЭК",
        "yandex": "г. Уткинск, ул. Охотничья, д. 7, кв. 12",
    }

    address_prompts = {
        "post": "Укажите полный адрес с почтовым индексом.",
        "cdek": "Укажите адрес пункта выдачи СДЭК.",
        "yandex": "Укажите полный адрес для курьерской доставки (улица, дом, квартира, подъезд).",
    }

    delivery_method = method_names.get(method, method)
    await state.update_data(delivery_method=delivery_method)
    await state.set_state(OrderState.address)

    # Формируем клавиатуру: кнопка с картой только для Почты и СДЭК
    keyboard_buttons = []
    if method in map_links:
        keyboard_buttons.append(
            [InlineKeyboardButton(text="🗺️ Посмотреть пункты выдачи на карте", url=map_links[method])]
        )
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="order_cancel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    example_address = address_examples.get(method, "")
    prompt = address_prompts.get(method, "")

    # Текст сообщения
    text = (
        f"📍 <b>Укажите адрес доставки</b>\n\n"
        f"Вы выбрали: <b>{delivery_method}</b>\n\n"
        f"{prompt}\n\n"
    )

    if method != "yandex":
        text += "Чтобы найти ближайший пункт выдачи, нажмите на кнопку ниже.\n"
    text += "Затем укажите точный адрес в сообщении.\n\n"
    text += f"<i>Пример:</i>\n"
    text += f"<code>{example_address}</code>"

    try:
        sent_message = await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        await state.update_data(prompt_message_id=sent_message.message_id)
    except Exception as e:
        logger.warning(f"order_delivery edit failed: {e}, sending new")
        sent_message = await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        await state.update_data(prompt_message_id=sent_message.message_id)
    await callback.answer()


@router.message(StateFilter(OrderState.address), F.text)
async def order_address(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_telegram_id(user_id)
    if not user:
        await message.answer(
            "❌ Вы не зарегистрированы!\n\n"
            "Пожалуйста, сначала пройдите регистрацию через /register,\n"
            "а затем оформите заказ заново.",
            parse_mode=ParseMode.HTML,
        )
        await state.clear()
        return

    address = message.text.strip()
    if len(address) < 5:
        await message.answer("❌ Слишком короткий адрес. Введите полный адрес (минимум 5 символов):")
        return

    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except Exception:
            pass
        await state.update_data(prompt_message_id=None)

    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(delivery_address=address, user=user)
    await ask_comment(message, state)


async def ask_comment(message: Message, state: FSMContext):
    """Запрос комментария к заказу"""
    await state.set_state(OrderState.comment)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Пропустить", callback_data="comment_skip")]
        ]
    )

    text = (
        "📝 <b>Комментарий к заказу</b>\n\n"
        "Если у вас есть особые пожелания по доставке, "
        "времени, способу связи или что-то ещё — напишите здесь.\n\n"
        "Если ничего не нужно — нажмите «Пропустить»."
    )

    try:
        sent_msg = await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        await state.update_data(comment_message_id=sent_msg.message_id)
    except Exception:
        sent_msg = await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        await state.update_data(comment_message_id=sent_msg.message_id)


@router.callback_query(StateFilter(OrderState.comment), F.data == "comment_skip")
async def comment_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить комментарий"""
    await callback.answer()

    data = await state.get_data()
    comment_message_id = data.get("comment_message_id")
    if comment_message_id:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=comment_message_id)
        except Exception:
            pass

    await state.update_data(comment=None)
    await create_order_from_state(callback.message, state)


async def create_order_from_state(message: Message, state: FSMContext):
    """Создать заказ из данных в состоянии и отправить уведомление админу"""
    data = await state.get_data()
    user = data.get("user")
    if not user:
        await message.answer(
            "❌ Ошибка: пользователь не найден. Пожалуйста, зарегистрируйтесь через /register и попробуйте снова.",
            parse_mode=ParseMode.HTML,
        )
        await state.clear()
        return

    user_id = message.from_user.id
    product_id = data.get("product_id")
    requested_quantity = data.get("quantity", 1)
    address = data.get("delivery_address")
    delivery_method = data.get("delivery_method")
    comment = data.get("comment")

    result = await create_order_and_decrease_stock(
        user_id=user_id,
        product_id=product_id,
        quantity=requested_quantity,
        delivery_method=delivery_method,
        delivery_address=address,
        comment=comment,
    )

    if not result["success"]:
        await message.answer(f"❌ {result['message']}", parse_mode=ParseMode.HTML)
        if "Недостаточно" in result["message"]:
            await state.set_state(OrderState.quantity)
            await show_quantity_selector(message, state)
        return

    await state.clear()

    try:
        await message.delete()
    except Exception:
        pass

    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except Exception as e:
            logger.warning(f"Failed to delete prompt message: {e}")

    try:
        product = await get_product_by_id(product_id)

        from handlers.admin import ADMIN_IDS

        admin_chat_id = ADMIN_IDS[0] if ADMIN_IDS else user_id

        new_stock = await get_product_stock(product_id)
        product_price = product[3] if product else 0
        total_price = requested_quantity * product_price

        admin_text = (
            f"🆕 <b>Новый заказ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>Клиент:</b> {escape_html(user[1])}\n"
            f"📞 <b>Телефон:</b> {escape_html(user[2])}\n"
            f"📧 <b>Email:</b> {escape_html(user[3] or 'не указан')}\n"
            f"🏙️ <b>Город:</b> {escape_html(user[4] or 'не указан')}\n"
            f"🛒 <b>Товар:</b> {escape_html(product[1])}\n"
            f"📦 <b>Количество:</b> {requested_quantity}\n"
            f"💰 <b>Цена за шт.:</b> {product_price} ₽\n"
            f"💵 <b>Сумма:</b> {total_price} ₽\n"
            f"🚚 <b>Доставка:</b> {delivery_method}\n"
            f"📍 <b>Адрес:</b> {escape_html(address)}\n"
        )
        if comment:
            admin_text += f"📝 <b>Комментарий:</b> {escape_html(comment)}\n"
        admin_text += f"📊 <b>Остаток на складе:</b> {new_stock} шт.\n"
        admin_text += f"━━━━━━━━━━━━━━━━━━━━━"

        await message.bot.send_message(chat_id=admin_chat_id, text=admin_text, parse_mode=ParseMode.HTML)

        if new_stock == 0:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✏️ Перейти к редактированию", callback_data=f"edit_select_{product_id}")],
                    [InlineKeyboardButton(text="📦 Управление товарами", callback_data="admin_products")],
                ]
            )
            await message.bot.send_message(
                chat_id=admin_chat_id,
                text=(
                    f"⚠️ <b>Товар закончился на складе!</b>\n\n"
                    f"📦 <b>Товар:</b> {escape_html(product[1])}\n"
                    f"🆔 ID: <code>{product_id}</code>\n\n"
                    f"Чтобы изменить количество, перейдите в редактирование товара."
                ),
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )

        if new_stock > 0 and new_stock <= LOW_STOCK_THRESHOLD:
            await check_and_notify_low_stock(
                product_id=product_id,
                product_name=product[1] if product else "товар",
                new_stock=new_stock,
                bot=message.bot,
                admin_chat_id=admin_chat_id,
            )

    except Exception as e:
        logger.error(f"Failed to send notification to admin: {e}", exc_info=True)

    await message.answer(
        "✅ <b>Заказ оформлен!</b>\n\n"
        "В ближайшее время с вами свяжется оператор для подтверждения.\n\n"
        "Проследить статус заказа можно в вашем профиле (/profile).\n\n"
        "🦆 <i>Приманивайте и будьте с Манией!</i>",
        parse_mode=ParseMode.HTML,
    )


@router.message(StateFilter(OrderState.comment), F.text)
async def process_comment(message: Message, state: FSMContext):
    comment = message.text.strip()
    if len(comment) > 500:
        await message.answer("❌ Комментарий слишком длинный. Максимум 500 символов.")
        return

    data = await state.get_data()
    comment_message_id = data.get("comment_message_id")
    if comment_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=comment_message_id)
        except Exception:
            pass

    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(comment=comment)
    await create_order_from_state(message, state)


@router.callback_query(lambda c: c.data == "order_cancel")
async def order_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена заказа"""
    await state.clear()
    try:
        await callback.message.edit_text("❌ Заказ отменён.")
    except Exception as e:
        logger.warning(f"order_cancel edit failed: {e}")
        await callback.message.answer("❌ Заказ отменён.")
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("profile_orders_page_"))
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


# ==================== ПОДТВЕРЖДЕНИЕ ПОЛУЧЕНИЯ ЗАКАЗА ====================
@router.callback_query(lambda c: c.data.startswith("confirm_delivery_"))
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