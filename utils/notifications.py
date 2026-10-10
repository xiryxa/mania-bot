import logging
from aiogram import Bot

from db import get_product_subscribers, delete_subscription, get_product_by_id, escape_html

logger = logging.getLogger(__name__)


async def notify_back_in_stock(product_id: int, bot: Bot) -> None:
    """
    Уведомляет подписчиков о появлении товара в наличии.
    Удаляет подписку ТОЛЬКО после успешной отправки сообщения (Rule: безопасное удаление).
    """
    subscribers = await get_product_subscribers(product_id)
    if not subscribers:
        return

    # Получаем объект товара из БД
    product = await get_product_by_id(product_id)
    
    # Исправление: product - это sqlite3.Row. Оператор "in" проверяет значения, а не ключи.
    # Поэтому мы просто проверяем наличие объекта и безопасно берем имя по ключу.
    if product:
        product_name = escape_html(str(product["name"]))
    else:
        # Этот блок сработает ТОЛЬКО если товар реально был удален из БД
        product_name = f"Товар (ID: {product_id})"
        logger.warning(f"⚠️ Товар ID {product_id} физически не найден в БД при попытке уведомления.")

    for user_id in subscribers:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"🔔 <b>Хорошие новости!</b>\n\n"
                    f"Товар «{product_name}» снова появился в наличии.\n"
                    f"Переходите в каталог, чтобы оформить заказ: /shop"
                ),
                parse_mode="HTML"
            )
            
            # Удаляем подписку ТОЛЬКО если сообщение успешно отправлено
            await delete_subscription(user_id, product_id)
            logger.info(f"✅ Уведомление о наличии отправлено пользователю {user_id} (товар {product_id})")
            
        except Exception as e:
            # Если отправка не удалась (например, юзер заблокировал бота), 
            # подписку НЕ удаляем. Она останется в БД для будущих попыток.
            logger.warning(f"⚠️ Не удалось отправить уведомление пользователю {user_id} о товаре {product_id}: {e}")