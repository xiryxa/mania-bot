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
)
from email_validator import EmailNotValidError, validate_email

from utils.validators import validate_fullname, validate_phone, validate_city
from db import (
    escape_html,
    format_moscow_time,
    get_user_by_telegram_id,
    get_user_orders_count,
    update_user,
)
from forms.users import Form, ProfileState, UpdateState

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


# ==================== ПРОФИЛЬ / РЕГИСТРАЦИЯ (CALLBACK) ====================
@router.callback_query(F.data == "start_profile")
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


@router.callback_query(F.data == "start_register")
async def start_register_callback(callback: CallbackQuery, state: FSMContext):
    """Переход к регистрации из главного меню (для незарегистрированных)"""
    await start_register_message(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "close_profile")
async def close_profile_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("👤 Профиль закрыт.")
    except Exception as e:
        logger.warning(f"close_profile edit failed: {e}")
        await callback.message.answer("👤 Профиль закрыт.")
    await callback.answer()


# ==================== ОБНОВЛЕНИЕ ДАННЫХ ====================
@router.callback_query(F.data == "update_data")
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


@router.callback_query(F.data.startswith("update_"))
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


@router.callback_query(F.data == "back_to_profile")
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


@router.callback_query(F.data == "cancel_update")
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