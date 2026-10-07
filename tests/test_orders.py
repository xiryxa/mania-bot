import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from handlers.orders import create_order_from_state


@pytest.mark.asyncio
@patch("handlers.orders.check_and_notify_low_stock", new_callable=AsyncMock)
@patch("handlers.orders.get_product_stock")
@patch("handlers.orders.get_product_by_id")
@patch("handlers.orders.create_order_and_decrease_stock")
@patch("handlers.orders.get_user_by_telegram_id")
async def test_create_order_from_state_product_deleted_race_condition(
    mock_get_user, mock_create_order, mock_get_product, mock_get_stock, mock_check_low_stock
):
    # Arrange: Имитируем состояние после успешного создания заказа, но товар уже удален
    mock_message = MagicMock()
    mock_message.from_user.id = 12345
    mock_message.bot = MagicMock()
    mock_message.bot.send_message = AsyncMock()
    mock_message.answer = AsyncMock()
    mock_message.delete = AsyncMock()
    mock_message.chat.id = 12345

    mock_state = MagicMock()
    mock_state.get_data = AsyncMock(return_value={
        "user": {"fullname": "Test User", "phone": "123", "email": "test@test.com", "city": "Moscow"},
        "product_id": 999,
        "quantity": 1,
        "delivery_method": "СДЭК",
        "delivery_address": "Test Address",
        "comment": "Test comment"
    })
    mock_state.clear = AsyncMock()

    mock_get_user.return_value = {"id": 12345}
    # Заказ успешно создан
    mock_create_order.return_value = {"success": True, "message": "Заказ оформлен.", "order_id": 123}
    # Race condition: товар удален из БД до отправки уведомления
    mock_get_product.return_value = None
    mock_get_stock.return_value = 0

    # Act
    await create_order_from_state(mock_message, mock_state, user_id=12345)

    # Assert
    mock_state.clear.assert_called_once()
    mock_message.delete.assert_called_once()

    # Проверяем, что уведомление админу отправлено безопасно с fallback-названием
    admin_call_args = mock_message.bot.send_message.call_args
    assert admin_call_args is not None
    assert "Удаленный товар" in admin_call_args.kwargs["text"]

    # Проверяем, что пользователь получил сообщение об успехе
    user_call_args = mock_message.answer.call_args
    assert user_call_args is not None
    assert "✅ <b>Заказ оформлен!</b>" in user_call_args.args[0]


# ==============================================================================
# Regression test for ADV-NOTIFY-01: Empty ADMIN_IDS
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.ADMIN_IDS", [])
@patch("handlers.orders.check_and_notify_low_stock", new_callable=AsyncMock)
@patch("handlers.orders.get_product_stock")
@patch("handlers.orders.get_product_by_id")
@patch("handlers.orders.create_order_and_decrease_stock")
@patch("handlers.orders.get_user_by_telegram_id")
async def test_create_order_from_state_empty_admin_ids(
    mock_get_user, mock_create_order, mock_get_product, mock_get_stock, mock_check_low_stock
):
    # Arrange
    mock_message = MagicMock()
    mock_message.from_user.id = 12345
    mock_message.bot = MagicMock()
    mock_message.bot.send_message = AsyncMock()
    mock_message.answer = AsyncMock()
    mock_message.delete = AsyncMock()
    mock_message.chat.id = 12345

    mock_state = MagicMock()
    mock_state.get_data = AsyncMock(return_value={
        "user": {"fullname": "Test User", "phone": "123", "email": "test@test.com", "city": "Moscow"},
        "product_id": 999,
        "quantity": 1,
        "delivery_method": "СДЭК",
        "delivery_address": "Test Address",
        "comment": "Test comment"
    })
    mock_state.clear = AsyncMock()

    mock_get_user.return_value = {"id": 12345}
    mock_create_order.return_value = {"success": True, "message": "Заказ оформлен.", "order_id": 123}
    mock_get_product.return_value = {"name": "Test Product", "price": 100}
    mock_get_stock.return_value = 5

    # Act
    await create_order_from_state(mock_message, mock_state, user_id=12345)

    # Assert
    # 1. Order flow completes successfully
    mock_state.clear.assert_called_once()

    # 2. User gets success message
    user_call_args = mock_message.answer.call_args
    assert "✅ <b>Заказ оформлен!</b>" in user_call_args.args[0]

    # 3. Admin notification is NOT sent
    admin_calls = [call for call in mock_message.bot.send_message.call_args_list if "🆕 <b>Новый заказ!</b>" in call.kwargs.get("text", "")]
    assert len(admin_calls) == 0

    # 4. Low stock notification is NOT triggered
    mock_check_low_stock.assert_not_called()
