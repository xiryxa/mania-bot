# ==================== ИМПОРТЫ ====================
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, Message


# ==================== НАСТРОЙКА ====================
logger = logging.getLogger(__name__)


# ==================== РОУТЕР ====================
router = Router()


# ==================== ОБРАБОТЧИК НЕИЗВЕСТНЫХ СООБЩЕНИЙ ====================
@router.message()
async def unknown_command(message: Message):
    """Обработчик сообщений, не попавших в другие роутеры"""
    text = message.text or ""

    # Если это похоже на команду (начинается с /)
    if text.startswith("/"):
        await message.answer(
            "❌ Я не знаю такой команды.\n"
            "Напишите /command для списка команд"
        )
        return

    # Обычное текстовое сообщение
    await message.answer(
        "📭 <b>Этот чат — для заказов, а не для переписки.</b>\n\n"
        "Сообщения, которые вы пишете сюда, не попадают к оператору.\n\n"
        "💬 <b>Чтобы связаться с нами:</b>\n"
        "• Откройте раздел /about — там наши контакты\n"
        "• Или напишите напрямую по телефону из описания\n\n"
        "🦆 <i>Приманивайте и будьте с Манией!</i>",
        parse_mode="HTML",
    )


# ==================== ОБРАБОТЧИК «МЁРТВЫХ» КНОПОК ====================
@router.callback_query()
async def unhandled_callback(callback: CallbackQuery):
    """
    Ловит callback_query, которые не нашли свой хэндлер.
    Логирует WARNING для наблюдаемости и сообщает пользователю,
    что кнопка больше не актуальна.
    """
    logger.warning(
        f"Unhandled callback: data={callback.data!r}, "
        f"user_id={callback.from_user.id}"
    )

    if callback.message:
        fallback_text = (
            "❌ <b>Кнопка больше не актуальна.</b>\n\n"
            "Этот экран уже не соответствует текущему состоянию.\n"
            "Вернитесь назад и попробуйте ещё раз."
        )

        try:
            await callback.message.edit_caption(
                caption=fallback_text,
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            try:
                await callback.message.edit_text(
                    fallback_text,
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception:
                pass

    await callback.answer(
        "❌ Кнопка устарела.\n"
        "Вернитесь назад и попробуйте ещё раз.",
        show_alert=True,
    )