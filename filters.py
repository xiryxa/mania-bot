# ==================== ИМПОРТЫ ====================
from os import getenv

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message


# ==================== ФИЛЬТРЫ ====================
class IsAdmin(BaseFilter):
    """
    Фильтр для проверки, является ли пользователь администратором.
    Используется для защиты админских callback'ов и команд.
    """

    async def __call__(self, obj: CallbackQuery | Message) -> bool:
        ADMIN_IDS = [
            int(id.strip())
            for id in getenv("ADMIN_IDS", "").split(",")
            if id.strip()
        ]
        return obj.from_user.id in ADMIN_IDS