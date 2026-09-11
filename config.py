# ==================== ИМПОРТЫ ====================
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault


# ==================== КОНСТАНТЫ ====================
ABOUT_MANIA = """
<b>🦆 MANIA — ОХОТНИЧЬЯ КОМАНДА</b>

Мы — <b>MANIA</b>, охотничья команда, объединённая любовью к охоте, природе и настоящему охотничьему делу.

Мы сами охотимся, участвуем в соревнованиях по приманиванию и постоянно тестируем оборудование в реальных условиях. Именно собственный практический опыт помогает нам создавать продукцию, которую мы используем сами и которой доверяем.

<b>Что мы предлагаем:</b>

🦆 <b>Манки</b> — для охоты на гуся и утку.

🛖 <b>Скрадки и засидки</b> — для комфортной и эффективной охоты.

🌿 <b>Маскировку</b> — сети, чехлы и другие решения для разных условий охоты.

👕 <b>Одежду и аксессуары</b> — охотничье снаряжение для практического использования.

Мы постоянно совершенствуем нашу продукцию, учитывая собственный опыт охоты и реальные потребности охотников.

<b>🌐 Наш официальный сайт:</b>
https://maniateam.ru/

<b>📺 Наш YouTube-канал:</b>
https://www.youtube.com/@MANIAteam

<b>📞 Для связи, по вопросам и для покупки:</b>
<b>+7 903 528-94-13</b> — манки (Whatsapp, Viber)
<b>+7 928 041-89-89</b> — скрадки (Whatsapp, Viber)

<b>🦆 MANIA — охотничья команда.</b> <i>Приманивайте и будьте с Манией!</i>
"""

# ==================== КАТЕГОРИИ ТОВАРОВ ====================
CATEGORY_MAP = {
    "goose": "гусь",
    "duck": "утка",
}

# ==================== НАСТРОЙКА КОМАНД БОТА ====================
async def setup_bot_commands(bot: Bot):
    """Устанавливает команды бота для всех пользователей и отдельно для админов"""
    # Локальный импорт для избежания циклической зависимости
    from handlers.admin import ADMIN_IDS

    user_commands = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="shop", description="🛒 Магазин"),
        BotCommand(command="profile", description="👤 Профиль"),
        BotCommand(command="about", description="🦆 О команде"),
    ]
    await bot.set_my_commands(commands=user_commands, scope=BotCommandScopeDefault())

    admin_commands = user_commands + [
        BotCommand(command="admin", description="🔐 Панель администратора")
    ]

    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                commands=admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:
            pass