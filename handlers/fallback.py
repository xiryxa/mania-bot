# ==================== ИМПОРТЫ ====================
from aiogram import Router
from aiogram.types import Message


# ==================== РОУТЕР ====================
router = Router()


# ==================== ОБРАБОТЧИК НЕИЗВЕСТНЫХ КОМАНД ====================
@router.message()
async def unknown_command(message: Message):
    """Обработчик сообщений, не попавших в другие роутеры"""
    await message.answer(
        "❌ Я не знаю такой команды.\n"
        "Напишите /command для списка команд"
    )