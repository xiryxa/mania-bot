"""Регрессионные тесты для списка товаров в магазине"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import CallbackQuery, Message, User
from aiogram.fsm.context import FSMContext

from handlers.shop import shop_show_list


@pytest.mark.asyncio
async def test_shop_show_list_refreshes_stale_stock_from_db():
    """
    Проверяет, что shop_show_list запрашивает актуальный остаток из БД,
    обновляет FSM-кэш и отображает пользователю верный статус (❌, 0 шт.),
    даже если в кэше лежало устаревшее положительное значение.
    """
    # Arrange
    callback = MagicMock(spec=CallbackQuery)
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.from_user = User(id=123, is_bot=False, first_name="Test")
    callback.answer = AsyncMock()
    state = MagicMock(spec=FSMContext)
    # Имитируем устаревший кэш FSM: товар был в наличии (5 шт.)
    stale_products = [
        {"id": 42, "name": "Манок Гусь", "price": 1500, "quantity": 5}
    ]
    state.get_data = AsyncMock(return_value={
        "shop_products": stale_products,
        "shop_category": "Гусь",
        "shop_last_photo_message_id": None,
        "shop_page": 0
    })
    state.update_data = AsyncMock()
    # Act & Assert
    with patch("handlers.shop.get_product_stock", new_callable=AsyncMock) as mock_get_stock:
        # Имитируем, что в БД товар уже раскуплен (остаток 0)
        mock_get_stock.return_value = 0
        await shop_show_list(callback, state)
        # 1. Проверяем, что был сделан запрос в БД для этого товара
        mock_get_stock.assert_called_once_with(42)
        # 2. Проверяем, что FSM-кэш был обновлён актуальным значением (0)
        state.update_data.assert_called_once()
        updated_data = state.update_data.call_args.kwargs
        assert "shop_products" in updated_data
        assert updated_data["shop_products"][0]["quantity"] == 0
        # 3. Проверяем, что пользователь видит правильный текст (❌ и 0 шт.)
        callback.message.edit_text.assert_called_once()
        # text передаётся как первый позиционный аргумент
        sent_text = callback.message.edit_text.call_args.args[0]
        assert "❌" in sent_text
        assert "0 шт." in sent_text
        assert "1500 ₽" in sent_text
    callback.answer.assert_called_once()
