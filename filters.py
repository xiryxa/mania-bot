# ==================== ИМПОРТЫ ====================
from os import getenv

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from dotenv import load_dotenv


# ==================== ЗАГРУЗКА ПЕРЕМЕННЫХ ====================
load_dotenv()


# ==================== КОНСТАНТЫ ====================
ADMIN_IDS = [
    int(id.strip())
    for id in getenv("ADMIN_IDS", "").split(",")
    if id.strip()
]


# ==================== ФИЛЬТРЫ ====================
class IsAdmin(BaseFilter):
    """
    Фильтр для проверки, является ли пользователь администратором.
    Используется для защиты админских callback'ов и команд.
    """

    async def __call__(self, obj: CallbackQuery | Message) -> bool:
        return obj.from_user.id in ADMIN_IDS