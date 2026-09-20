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

    # Получаем название товара для персонализации сообщения
    product = await get_product_by_id(product_id)
    product_name = escape_html(product[1] if product and len(product) > 1 else "товар")

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