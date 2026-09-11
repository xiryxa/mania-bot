import asyncio
import logging
from os import getenv

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ErrorEvent
from dotenv import load_dotenv

from config import setup_bot_commands
from db import init_db
from handlers.admin import admin_router
from handlers.admin_products import router as products_router
from handlers.callbacks import router as callbacks_router
from handlers.fallback import router as fallback_router
from handlers.navigation import router as navigation_router
from handlers.profile import router as profile_router
from handlers.router import router as user_router
from handlers.shop import router as shop_router

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== ЗАГРУЗКА ПЕРЕМЕННЫХ ====================
load_dotenv()
TOKEN = getenv("BOT_TOKEN")

# ==================== ИНИЦИАЛИЗАЦИЯ ДИСПЕТЧЕРА ====================
dp = Dispatcher()

# ==================== ПОДКЛЮЧЕНИЕ РОУТЕРОВ ====================
dp.include_router(admin_router)
dp.include_router(user_router)
dp.include_router(navigation_router)
dp.include_router(profile_router)
dp.include_router(callbacks_router)
dp.include_router(products_router)
dp.include_router(shop_router)
dp.include_router(fallback_router)


# ==================== ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК ====================
@dp.errors()
async def errors_handler(event: ErrorEvent):
    logger.error(f"Exception: {event.exception}", exc_info=True)
    if event.update.callback_query:
        try:
            await event.update.callback_query.answer("Произошла ошибка, попробуйте позже.")
        except Exception:
            pass
    return True


# ==================== ТОЧКА ВХОДА ====================
async def main():
    await init_db()
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    await setup_bot_commands(bot)
    logger.info("🤖 Бот запущен! Нажмите Ctrl+C для остановки.")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(
            bot,
            drop_pending_updates=True,
            allowed_updates=dp.resolve_used_update_types()
        )
    except asyncio.CancelledError:
        logger.info("⏹️ Бот остановлен")
    finally:
        await bot.session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 До свидания!")