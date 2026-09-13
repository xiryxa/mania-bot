# ==================== ИМПОРТЫ ====================
import asyncio
import logging
from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from db import get_all_user_ids
from filters import IsAdmin
from forms.users import BroadcastState

# ==================== НАСТРОЙКА ====================
logger = logging.getLogger(__name__)
router = Router()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
async def broadcast_message(
    bot,
    user_ids: list[int],
    text: str = None,
    photo_file_id: str = None,
) -> tuple[int, int]:
    """
    Массовая рассылка. Возвращает (sent, failed).

    - Между отправками пауза ~0.05 сек (~20 сообщений/сек) — защита от лимитов Telegram.
    - При TelegramRetryAfter (бот упёрся в лимит) — ждём, потом повторяем попытку.
    - При TelegramForbiddenError (пользователь заблокировал бота) — пропускаем.
    - Любая другая ошибка — логируем, но продолжаем (не роняем рассылку).
    """
    sent = 0
    failed = 0

    for user_id in user_ids:
        try:
            if photo_file_id:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=photo_file_id,
                    caption=text or "",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=text or "",
                    parse_mode=ParseMode.HTML,
                )
            sent += 1
        except TelegramRetryAfter as e:
            # Telegram явно сказал, сколько ждать
            logger.warning(f"Broadcast hit retry_after {e.retry_after}s, waiting...")
            await asyncio.sleep(e.retry_after)
            # Повторная попытка для того же user_id
            try:
                if photo_file_id:
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=photo_file_id,
                        caption=text or "",
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    await bot.send_message(
                        chat_id=user_id,
                        text=text or "",
                        parse_mode=ParseMode.HTML,
                    )
                sent += 1
            except Exception as retry_err:
                logger.warning(f"Broadcast retry failed for {user_id}: {retry_err}")
                failed += 1
        except TelegramForbiddenError:
            # Пользователь заблокировал бота — пропускаем молча
            failed += 1
        except Exception as e:
            logger.warning(f"Broadcast failed for {user_id}: {e}")
            failed += 1

        # Пауза между отправками, чтобы не долбить API
        await asyncio.sleep(0.05)

    return sent, failed


# ==================== СТАРТ РАССЫЛКИ ====================
@router.callback_query(F.data == "broadcast_start", IsAdmin())
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Кнопка «📢 Рассылка» в админ-панели."""
    await state.set_state(BroadcastState.composing)
    await state.update_data(broadcast_text=None, broadcast_photo=None)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]
        ]
    )

    text = (
        "📢 <b>Рассылка</b>\n\n"
        "Отправьте текст рассылки (или фото с подписью), который получат все "
        "зарегистрированные пользователи.\n\n"
        "После получения я покажу предпросмотр и попрошу подтверждение."
    )

    try:
        sent = await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await state.update_data(broadcast_start_message_id=sent.message_id)
    except Exception:
        sent = await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await state.update_data(broadcast_start_message_id=sent.message_id)
    await callback.answer()


# ==================== ПРИЁМ КОНТЕНТА ====================
@router.message(StateFilter(BroadcastState.composing), F.photo, IsAdmin())
async def broadcast_get_photo(message: Message, state: FSMContext):
    """Приём фото с подписью (или без)."""
    photo_file_id = message.photo[-1].file_id
    caption = message.caption.strip() if message.caption else None

    await state.update_data(broadcast_photo=photo_file_id, broadcast_text=caption)

    users = await get_all_user_ids()
    count = len(users)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Отправить всем ({count})", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
        ]
    )

    preview_caption = (
        "📢 <b>Предпросмотр рассылки</b>\n\n"
        "👇 Так это увидят пользователи:\n\n"
        f"<blockquote>{caption or '<i>(без текста)</i>'}</blockquote>\n\n"
        f"👥 Получателей: <b>{count}</b>"
    )

    # Удаляем сообщение-промпт «📢 Рассылка. Отправьте текст…»
    data = await state.get_data()
    start_msg_id = data.get("broadcast_start_message_id")
    if start_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=start_msg_id)
        except Exception:
            pass
        await state.update_data(broadcast_start_message_id=None)

    # Показываем предпросмотр
    await message.answer_photo(
        photo=photo_file_id,
        caption=preview_caption,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )

    # Удаляем сообщение админа с фото
    try:
        await message.delete()
    except Exception:
        pass

    await state.set_state(BroadcastState.confirming)


@router.message(StateFilter(BroadcastState.composing), F.text, IsAdmin())
async def broadcast_get_text(message: Message, state: FSMContext):
    """Приём текста рассылки."""
    text = message.text.strip()
    if not text:
        await message.answer("❌ Пустое сообщение. Введите текст рассылки.")
        return

    await state.update_data(broadcast_text=text, broadcast_photo=None)

    users = await get_all_user_ids()
    count = len(users)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Отправить всем ({count})", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
        ]
    )

    preview = (
        "📢 <b>Предпросмотр рассылки</b>\n\n"
        "👇 Так это увидят пользователи:\n\n"
        f"<blockquote>{text}</blockquote>\n\n"
        f"👥 Получателей: <b>{count}</b>"
    )

    # Удаляем сообщение-промпт «📢 Рассылка. Отправьте текст…»
    data = await state.get_data()
    start_msg_id = data.get("broadcast_start_message_id")
    if start_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=start_msg_id)
        except Exception:
            pass
        await state.update_data(broadcast_start_message_id=None)

    # Показываем предпросмотр
    try:
        await message.answer(preview, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        await message.answer(preview, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    # Удаляем сообщение админа с текстом
    try:
        await message.delete()
    except Exception:
        pass

    await state.set_state(BroadcastState.confirming)


# ==================== ОТМЕНА ====================
@router.callback_query(F.data == "broadcast_cancel", IsAdmin())
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки на любом этапе."""
    await state.clear()

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer("❌ Рассылка отменена.")
    await callback.answer()


# ==================== ПОДТВЕРЖДЕНИЕ И РАССЫЛКА ====================
@router.callback_query(
    StateFilter(BroadcastState.confirming),
    F.data == "broadcast_confirm",
    IsAdmin(),
)
async def broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение — запускаем рассылку."""
    data = await state.get_data()
    text = data.get("broadcast_text")
    photo_file_id = data.get("broadcast_photo")

    users = await get_all_user_ids()
    total = len(users)

    if total == 0:
        await callback.message.edit_text("📭 Нет зарегистрированных пользователей.")
        await state.clear()
        await callback.answer()
        return

    # Меняем сообщение — «Отправка...»
    try:
        await callback.message.edit_caption(
            caption=f"⏳ Отправка... 0/{total}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        try:
            await callback.message.edit_text(
                f"⏳ Отправка... 0/{total}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    await callback.answer("Рассылка запущена")

    # Запускаем рассылку
    sent, failed = await broadcast_message(
        bot=callback.bot,
        user_ids=users,
        text=text,
        photo_file_id=photo_file_id,
    )

    # Итоговое сообщение
    result_text = (
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: <b>{sent}</b>\n"
        f"❌ Не доставлено: <b>{failed}</b> (заблокировали бота или ошибка)\n"
        f"👥 Всего получателей: <b>{total}</b>"
    )

    try:
        await callback.message.edit_caption(
            caption=result_text,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        try:
            await callback.message.edit_text(
                result_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await callback.message.answer(
                result_text,
                parse_mode=ParseMode.HTML,
            )

    await state.clear()


# ==================== ПРОЧИЕ СООБЩЕНИЯ ====================
@router.message(StateFilter(BroadcastState.composing), IsAdmin())
async def broadcast_invalid(message: Message, state: FSMContext):
    """Если прислали не текст и не фото — просим прислать корректно."""
    await message.answer(
        "❌ Пришлите текст или фото с подписью для рассылки.\n\n"
        "Если хотите отменить — нажмите кнопку «❌ Отмена»."
    )