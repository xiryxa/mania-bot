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
    order_address_invalid_type,
    show_quantity_selector
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


@pytest.mark.asyncio
async def test_show_quantity_selector_success():
    """Штатное отображение селектора для активного товара с остатком (текстовое сообщение)"""
    message = MagicMock(spec=Message)
    message.photo = None  # Явно текстовое сообщение
    message.edit_text = AsyncMock()
    message.edit_caption = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"product_id": 1, "quantity": 2})

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product, \
         patch("handlers.orders.get_product_stock", new_callable=AsyncMock) as mock_get_stock:

        mock_get_product.return_value = {"name": "Test Product", "price": 100, "is_active": 1}
        mock_get_stock.return_value = 5

        await show_quantity_selector(message, state)

        message.edit_text.assert_called_once()
        message.edit_caption.assert_not_called()
        call_args = message.edit_text.call_args
        assert "Test Product" in call_args.kwargs["text"]
        assert "Доступно: <b>5</b>" in call_args.kwargs["text"]
        assert "Количество:</b> 2" in call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_show_quantity_selector_success_with_photo():
    """Штатное отображение селектора для фото-сообщения"""
    message = MagicMock(spec=Message)
    message.photo = [MagicMock()]  # Явно фото-сообщение
    message.edit_text = AsyncMock()
    message.edit_caption = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"product_id": 1, "quantity": 1})

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product, \
         patch("handlers.orders.get_product_stock", new_callable=AsyncMock) as mock_get_stock:

        mock_get_product.return_value = {"name": "Test Product", "price": 100, "is_active": 1}
        mock_get_stock.return_value = 5

        await show_quantity_selector(message, state)

        message.edit_caption.assert_called_once()
        message.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_show_quantity_selector_deleted_product():
    """Очистка FSM и сообщение об ошибке, если товар удалён (текстовое сообщение)"""
    message = MagicMock(spec=Message)
    message.photo = None
    message.edit_text = AsyncMock()
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.clear = AsyncMock()
    state.get_data = AsyncMock(return_value={"product_id": 99})

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product:
        mock_get_product.return_value = None

        await show_quantity_selector(message, state)

        state.clear.assert_called_once()
        message.edit_text.assert_called_once()
        assert "больше не доступен" in message.edit_text.call_args.kwargs["text"].lower()
        message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_show_quantity_selector_inactive_product():
    """Очистка FSM и сообщение об ошибке, если товар деактивирован"""
    message = MagicMock(spec=Message)
    message.photo = None
    message.edit_text = AsyncMock()
    message.answer = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.clear = AsyncMock()
    state.get_data = AsyncMock(return_value={"product_id": 1})

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product:
        mock_get_product.return_value = {"name": "Test Product", "is_active": 0}

        await show_quantity_selector(message, state)

        state.clear.assert_called_once()
        message.edit_text.assert_called_once()
        assert "больше не доступен" in message.edit_text.call_args.kwargs["text"].lower()


@pytest.mark.asyncio
async def test_show_quantity_selector_deleted_with_photo():
    """Недоступный товар для фото-сообщения использует edit_caption"""
    message = MagicMock(spec=Message)
    message.photo = [MagicMock()]
    message.edit_text = AsyncMock()
    message.edit_caption = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.clear = AsyncMock()
    state.get_data = AsyncMock(return_value={"product_id": 99})

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product:
        mock_get_product.return_value = None

        await show_quantity_selector(message, state)

        state.clear.assert_called_once()
        message.edit_caption.assert_called_once()
        message.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_show_quantity_selector_zero_stock():
    """Очистка FSM и сообщение, если остаток равен 0"""
    message = MagicMock(spec=Message)
    message.photo = None
    message.edit_text = AsyncMock()
    message.answer = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.clear = AsyncMock()
    state.get_data = AsyncMock(return_value={"product_id": 1})

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product, \
         patch("handlers.orders.get_product_stock", new_callable=AsyncMock) as mock_get_stock:

        mock_get_product.return_value = {"name": "Test Product", "is_active": 1}
        mock_get_stock.return_value = 0

        await show_quantity_selector(message, state)

        state.clear.assert_called_once()
        message.edit_text.assert_called_once()
        assert "временно отсутствует" in message.edit_text.call_args.kwargs["text"].lower()


@pytest.mark.asyncio
async def test_show_quantity_selector_caps_quantity():
    """Корректировка количества, если оно превышает актуальный остаток"""
    message = MagicMock(spec=Message)
    message.photo = None
    message.edit_text = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"product_id": 1, "quantity": 5})
    state.update_data = AsyncMock()

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product, \
         patch("handlers.orders.get_product_stock", new_callable=AsyncMock) as mock_get_stock:

        mock_get_product.return_value = {"name": "Test Product", "price": 100, "is_active": 1}
        mock_get_stock.return_value = 2

        await show_quantity_selector(message, state)

        state.update_data.assert_called_once_with(quantity=2)
        call_args = message.edit_text.call_args
        assert "Количество:</b> 2" in call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_show_quantity_selector_fallback_on_edit_error():
    """При ошибке редактирования вызывается answer, а delete не вызывается"""
    message = MagicMock(spec=Message)
    message.photo = None
    message.edit_text = AsyncMock(side_effect=Exception("Bad Request: message is not modified"))
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"product_id": 1, "quantity": 1})

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product, \
         patch("handlers.orders.get_product_stock", new_callable=AsyncMock) as mock_get_stock:

        mock_get_product.return_value = {"name": "Test Product", "price": 100, "is_active": 1}
        mock_get_stock.return_value = 5

        await show_quantity_selector(message, state)

        message.edit_text.assert_called_once()
        message.answer.assert_called_once()
        message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_show_quantity_selector_photo_edit_caption_error():
    """При ошибке edit_caption для фото вызывается answer, а delete не вызывается"""
    message = MagicMock(spec=Message)
    message.photo = [MagicMock()]  # Явно фото-сообщение
    message.edit_caption = AsyncMock(side_effect=Exception("Bad Request: message is not modified"))
    message.edit_text = AsyncMock()
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"product_id": 1, "quantity": 1})

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product, \
         patch("handlers.orders.get_product_stock", new_callable=AsyncMock) as mock_get_stock:

        mock_get_product.return_value = {"name": "Test Product", "price": 100, "is_active": 1}
        mock_get_stock.return_value = 5

        await show_quantity_selector(message, state)

        message.edit_caption.assert_called_once()
        message.edit_text.assert_not_called()
        message.answer.assert_called_once()
        message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_show_quantity_selector_zero_stock_with_photo():
    """Нулевой остаток для фото-сообщения использует edit_caption"""
    message = MagicMock(spec=Message)
    message.photo = [MagicMock()]  # Явно фото-сообщение
    message.edit_text = AsyncMock()
    message.edit_caption = AsyncMock()
    message.answer = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.clear = AsyncMock()
    state.get_data = AsyncMock(return_value={"product_id": 1})

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product, \
         patch("handlers.orders.get_product_stock", new_callable=AsyncMock) as mock_get_stock:

        mock_get_product.return_value = {"name": "Test Product", "is_active": 1}
        mock_get_stock.return_value = 0

        await show_quantity_selector(message, state)

        state.clear.assert_called_once()
        message.edit_caption.assert_called_once()
        message.edit_text.assert_not_called()
        assert "временно отсутствует" in message.edit_caption.call_args.kwargs["caption"].lower()


@pytest.mark.asyncio
async def test_show_quantity_selector_invalid_quantity_type():
    """Корректировка некорректного типа quantity и его запись в FSM"""
    message = MagicMock(spec=Message)
    message.photo = None
    message.edit_text = AsyncMock()
    state = MagicMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"product_id": 1, "quantity": "invalid_string"})
    state.update_data = AsyncMock()

    with patch("handlers.orders.get_product_by_id", new_callable=AsyncMock) as mock_get_product, \
         patch("handlers.orders.get_product_stock", new_callable=AsyncMock) as mock_get_stock:

        mock_get_product.return_value = {"name": "Test Product", "price": 100, "is_active": 1}
        mock_get_stock.return_value = 5

        await show_quantity_selector(message, state)

        state.update_data.assert_called_once_with(quantity=1)
        call_args = message.edit_text.call_args
        assert "Количество:</b> 1" in call_args.kwargs["text"]
