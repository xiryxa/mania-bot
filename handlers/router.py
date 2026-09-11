# ==================== ИМПОРТЫ ====================
from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from email_validator import EmailNotValidError, validate_email
from utils.validators import validate_fullname, validate_phone, validate_city
from db import add_user, escape_html, get_user_by_telegram_id, update_user
from forms.users import Form
from handlers.navigation import about_message
from handlers.callbacks import show_profile, start_register_message

# ==================== РОУТЕР ====================
router = Router()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
async def get_main_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Динамическая клавиатура в зависимости от регистрации"""
    user = await get_user_by_telegram_id(user_id)
    is_registered = user is not None

    if is_registered:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="/start")],
                [KeyboardButton(text="/command"), KeyboardButton(text="/about")],
                [KeyboardButton(text="/profile"), KeyboardButton(text="/cancel")],
                [KeyboardButton(text="/shop")],
            ],
            resize_keyboard=True,
        )
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="/start")],
                [KeyboardButton(text="/command"), KeyboardButton(text="/about")],
                [KeyboardButton(text="/register"), KeyboardButton(text="/cancel")],
                [KeyboardButton(text="/shop")],
            ],
            resize_keyboard=True,
        )

    return keyboard


# ==================== КОМАНДЫ ====================
@router.message(Command("start"))
@router.message(F.text.lower() == "старт")
async def start(message: Message):
    user_id = message.from_user.id
    user = await get_user_by_telegram_id(user_id)
    is_registered = user is not None

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Каталог", callback_data="start_shop")],
            [InlineKeyboardButton(text="📞 О нас", callback_data="start_about")],
        ]
    )

    if is_registered:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="👤 Профиль", callback_data="start_profile")]
        )
    else:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="📝 Регистрация", callback_data="start_register")]
        )

    await message.answer(
        "🦆 <b>Добро пожаловать в MANIA!</b>\n\n"
        "Мы — команда практикующих охотников.\n"
        "Здесь вы можете заказать профессиональные манки для охоты на гуся и утку.\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("command"))
async def command(message: Message):
    user_id = message.from_user.id
    user = await get_user_by_telegram_id(user_id)
    is_registered = user is not None

    keyboard = await get_main_reply_keyboard(user_id)

    if is_registered:
        text = (
            "📋 <b>Команды:</b>\n\n"
            "/start - 🏠 Главное меню\n"
            "/command - 📋 Список команд\n"
            "/profile - 👤 Мой профиль\n"
            "/shop - 🛒 Товары\n"
            "/about - 🦆 О нас\n"
            "/cancel - ❌ Отменить действие"
        )
    else:
        text = (
            "📋 <b>Команды:</b>\n\n"
            "/start - 🏠 Главное меню\n"
            "/command - 📋 Список команд\n"
            "/register - 📝 Регистрация\n"
            "/shop - 🛒 Товары\n"
            "/about - 🦆 О нас\n"
            "/cancel - ❌ Отменить действие"
        )

    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@router.message(Command("about"))
async def about(message: Message):
    await about_message(message)


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❌ Нет активных процессов для отмены.")
        return

    state_name = str(current_state)

    if "Form" in state_name:
        await message.answer("❌ Регистрация отменена. Вы можете начать заново через /register.")
    elif "AdminState" in state_name:
        await message.answer("🚪 Вы вышли из админ-панели.")
    elif "UpdateState" in state_name:
        await message.answer("❌ Обновление данных отменено. Ваши данные остались прежними.")
    else:
        await message.answer("❌ Действие отменено.")

    await state.clear()


@router.message(Command("register"))
async def register(message: Message, state: FSMContext):
    user_id = message.from_user.id
    existing_user = await get_user_by_telegram_id(user_id)

    if existing_user:
        await state.update_data(existing_user=existing_user)
        await show_profile(message, existing_user)
        return

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


# ==================== FSM РЕГИСТРАЦИЯ ====================
@router.message(Form.name, F.text)
async def process_name(message: Message, state: FSMContext):
    fullname = message.text.strip()
    valid, error = validate_fullname(fullname)
    if not valid:
        await message.answer(error, parse_mode=ParseMode.HTML)
        return

    await state.update_data(name=fullname)
    await message.answer(
        "📞 Введите ваш <b>номер телефона</b> для связи:\n"
        "Например: <code>+7 903 528-94-13</code>",
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(Form.phone)


@router.message(Form.phone, F.text)
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    valid, error = validate_phone(phone)
    if not valid:
        await message.answer(error, parse_mode=ParseMode.HTML)
        return

    await state.update_data(phone=phone)
    await message.answer(
        "📧 Введите ваш <b>email</b> для связи:\n"
        "Например: <code>example@mail.com</code>",
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(Form.email)


@router.message(Form.email, F.text)
async def process_email(message: Message, state: FSMContext):
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
    await state.update_data(email=email)
    await message.answer(
        "🏙️ Введите ваш <b>город</b> (например, Москва):",
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(Form.city)


@router.message(Form.city, F.text)
async def process_city(message: Message, state: FSMContext):
    city = message.text.strip()
    valid, error = validate_city(city)
    if not valid:
        await message.answer(error, parse_mode=ParseMode.HTML)
        return

    city = city.title()
    await state.update_data(city=city)

    user_data = await state.get_data()
    existing_user = await get_user_by_telegram_id(message.from_user.id)

    if existing_user:
        await update_user(
            telegram_id=message.from_user.id,
            fullname=user_data.get("name"),
            phone=user_data.get("phone"),
            email=user_data.get("email"),
            city=city,
            address=user_data.get("address"),
            username=message.from_user.username,
        )
        await message.answer(
            f"✅ <b>Данные обновлены!</b>\n\n"
            f"📝 <b>Ваши данные:</b>\n"
            f"👤 ФИО: {user_data.get('name')}\n"
            f"📞 Телефон: {user_data.get('phone')}\n"
            f"📧 Email: {user_data.get('email')}\n"
            f"🏙️ Город: {city}",
            parse_mode=ParseMode.HTML,
        )
    else:
        await add_user(
            telegram_id=message.from_user.id,
            fullname=user_data.get("name"),
            phone=user_data.get("phone"),
            email=user_data.get("email"),
            city=city,
            address=None,
            username=message.from_user.username,
        )
        await message.answer(
            f"✅ <b>Регистрация завершена!</b>\n\n"
            f"📝 <b>Ваши данные:</b>\n"
            f"👤 ФИО: {user_data.get('name')}\n"
            f"📞 Телефон: {user_data.get('phone')}\n"
            f"📧 Email: {user_data.get('email')}\n"
            f"🏙️ Город: {city}",
            parse_mode=ParseMode.HTML,
        )

    await state.clear()


# ==================== ПРОФИЛЬ ====================
@router.message(Command("profile"))
async def profile(message: Message, state: FSMContext):
    user_id = message.from_user.id
    existing_user = await get_user_by_telegram_id(user_id)

    if existing_user:
        await state.update_data(existing_user=existing_user)
        await show_profile(message, existing_user, state)
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Зарегистрироваться", callback_data="start_register")]
            ]
        )
        await message.answer(
            "📭 Вы ещё не зарегистрированы.\n"
            "Нажмите кнопку ниже, чтобы создать профиль:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )