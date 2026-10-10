"""
Тесты для BUYER-ORDER-01: оформление заказа покупателем
"""
import pytest
import pytest_asyncio
import db
import aiosqlite
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, CallbackQuery, User
from aiogram.fsm.context import FSMContext

from db import (
    init_db,
    create_order_and_decrease_stock,
    get_product_stock,
    DATABASE
)
from handlers.orders import (
    order_product_callback,
    order_address_invalid_type
)
from forms.users import OrderState


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    yield


@pytest.mark.asyncio
async def test_create_order_inactive_product():
    import db
    async with aiosqlite.connect(db.DATABASE) as connection:
        connection.row_factory = aiosqlite.Row
        cursor = await connection.execute(
            "INSERT INTO products (name, description, price, category, quantity, is_active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            ("Неактивный товар для теста", "Описание", 1000, "Тест", 10)
        )
        await connection.commit()
        product_id = cursor.lastrowid
        await connection.execute("UPDATE products SET is_active = 0 WHERE id = ?", (product_id,))
        await connection.commit()
        cursor = await connection.execute("SELECT is_active FROM products WHERE id = ?", (product_id,))
        row = await cursor.fetchone()
        assert row["is_active"] == 0

    result = await create_order_and_decrease_stock(
        user_id=12345,
        product_id=product_id,
        quantity=1,
        delivery_method="Почта",
        delivery_address="Тестовый адрес",
        comment=None
    )
    
    assert result["success"] is False
    assert "недоступен" in result["message"].lower()
    
    stock = await get_product_stock(product_id)
    assert stock == 10


@pytest.mark.asyncio
async def test_order_product_callback_clears_fsm():
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = User(id=12345, is_bot=False, first_name="Test")
    callback.data = "order_product_99999"
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    
    state = MagicMock(spec=FSMContext)
    state.clear = AsyncMock()
    
    mock_user = {
        "id": 12345, "fullname": "Test", "phone": "+7999",
        "email": "t@t.com", "city": "M", "address": "A", "username": "u"
    }
    with patch("handlers.orders.get_user_by_telegram_id", new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = mock_user
        await order_product_callback(callback, state)
    
    state.clear.assert_called_once()
    assert "не найден" in callback.message.edit_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_quantity_control_statefilter_added():
    from handlers.orders import quantity_control
    import inspect
    
    full_source = inspect.getsource(inspect.getmodule(quantity_control))
    assert "StateFilter(OrderState.quantity)" in full_source
    assert 'F.data.startswith("qty_")' in full_source


@pytest.mark.asyncio
async def test_order_address_invalid_type():
    message = MagicMock(spec=Message)
    message.answer = AsyncMock()
    message.from_user = User(id=12345, is_bot=False, first_name="Test")
    state = MagicMock(spec=FSMContext)
    
    await order_address_invalid_type(message, state)
    
    message.answer.assert_called_once()
    call_text = message.answer.call_args[0][0]
    assert "текстом" in call_text.lower()
    assert "адрес" in call_text.lower()
