# ==================== ИМПОРТЫ ====================
import logging
from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import ABOUT_MANIA
from db import get_user_by_telegram_id

# ==================== НАСТРОЙКА ====================
logger = logging.getLogger(__name__)
router = Router()


# ==================== ОБЩИЕ ФУНКЦИИ ====================
async def about_message(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 Подробнее о нас", callback_data="more_info")],
            [InlineKeyboardButton(text="📩 Связаться с нами", url="https://t.me/SanchaZ23")],
            [InlineKeyboardButton(text="🌐 Наш сайт", url="https://maniateam.ru")],
            [InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_to_start")],
        ]
    )

    text = (
        "🦆 <b>MANIA — охотничья команда</b>\n\n"
        "Мы производим и продаём профессиональные манки для охоты на гуся и утку.\n\n"
        "📦 <b>Что доступно для покупки:</b>\n"
        "• Манки для гуся\n"
        "• Манки для утки\n\n"
        "📞 <b>Как заказать:</b>\n"
        "1. Пройдите регистрацию (/register)\n"
        "2. Откройте каталог (/shop) и выберите товар\n"
        "3. Нажмите «📩 Заказать» и оформите заказ прямо в боте\n\n"
        "После оформления оператор свяжется с вами для подтверждения деталей доставки и оплаты.\n\n"
        "💬 Если возникли вопросы — напишите нам по кнопке ниже\n\n"
        "Нажмите «Подробнее о нас», чтобы узнать больше о команде."
    )

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"about_message edit failed: {e}, sending new")
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


# ==================== ABOUT / НАВИГАЦИЯ ====================
@router.callback_query(F.data == "more_info")
async def more_info_callback(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 Написать в Telegram для заказа", url="https://t.me/SanchaZ23")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_about")],
        ]
    )
    try:
        await callback.message.edit_text(ABOUT_MANIA, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"more_info edit failed: {e}, sending new")
        await callback.message.answer(ABOUT_MANIA, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data == "back_to_about")
async def back_to_about(callback: CallbackQuery):
    await about_message(callback.message)
    await callback.answer()


@router.callback_query(F.data == "start_about")
async def start_about_callback(callback: CallbackQuery):
    """Переход в раздел 'О нас' из главного меню (редактирует сообщение)"""
    await about_message(callback.message)
    await callback.answer()


@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext = None):
    """Возврат в главное меню с динамической клавиатурой"""
    if state:
        await state.clear()

    user_id = callback.from_user.id
    user = await get_user_by_telegram_id(user_id)
    is_registered = user is not None

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Каталог", callback_data="start_shop")],
            [InlineKeyboardButton(text="📞 О нас", callback_data="start_about")],
        ]
    )

    if is_registered:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="👤 Профиль", callback_data="start_profile")])
    else:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="📝 Регистрация", callback_data="start_register")])

    try:
        await callback.message.edit_text(
            "🦆 <b>Добро пожаловать в MANIA!</b>\n\n"
            "Мы — команда практикующих охотников.\n"
            "Здесь вы можете заказать профессиональные манки для охоты на гуся и утку.\n\n"
            "Выберите действие:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"back_to_start edit failed: {e}, sending new")
        await callback.message.answer(
            "🦆 <b>Добро пожаловать в MANIA!</b>\n\n"
            "Мы — команда практикующих охотников.\n"
            "Здесь вы можете заказать профессиональные манки для охоты на гуся и утку.\n\n"
            "Выберите действие:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()