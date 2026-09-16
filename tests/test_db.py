import sys
import os
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import db

@pytest.mark.asyncio
async def test_create_order_and_decrease_stock_success(initialized_db):
    await db.add_user(1, "Иван Петров", "+79000000000", "test@test.com", "Москва")
    await db.add_product("Манок", "Описание", 1000, "Утки", 5)
    
    result = await db.create_order_and_decrease_stock(
        user_id=1, product_id=1, quantity=2, 
        delivery_method="Почта", delivery_address="Москва, ул. Ленина 1"
    )
    
    assert result["success"] is True
    assert result["order_id"] is not None
    assert await db.get_product_stock(1) == 3

@pytest.mark.asyncio
async def test_create_order_and_decrease_stock_insufficient(initialized_db):
    await db.add_user(1, "Иван Петров", "+79000000000", "test@test.com", "Москва")
    await db.add_product("Манок", "Описание", 1000, "Утки", 2)
    
    result = await db.create_order_and_decrease_stock(
        user_id=1, product_id=1, quantity=5, 
        delivery_method="Почта", delivery_address="Москва, ул. Ленина 1"
    )
    
    assert result["success"] is False
    assert "Недостаточно товара" in result["message"]
    assert await db.get_product_stock(1) == 2  # Остаток не изменился

@pytest.mark.asyncio
async def test_stock_return_on_cancel_and_restore(initialized_db):
    await db.add_user(1, "Иван Петров", "+79000000000", "test@test.com", "Москва")
    await db.add_product("Манок", "Описание", 1000, "Утки", 5)
    
    # 1. Создаем заказ (остаток станет 2)
    order_res = await db.create_order_and_decrease_stock(
        user_id=1, product_id=1, quantity=3, 
        delivery_method="Почта", delivery_address="Москва"
    )
    order_id = order_res["order_id"]
    assert await db.get_product_stock(1) == 2
    
    # 2. Отменяем заказ (возврат на склад, остаток станет 5)
    await db.return_stock_on_cancel(order_id)
    assert await db.get_product_stock(1) == 5
    
    # 3. Симулируем, что кто-то другой выкупил весь остаток (станет 0)
    await db.decrease_product_stock(1, 5)
    assert await db.get_product_stock(1) == 0
    
    # 4. Пытаемся "вернуть" первый заказ в работу (списание 3 шт.)
    # Функция атомарна и вернет False, так как остатка не хватает
    success = await db.decrease_product_stock(1, 3)
    assert success is False
    assert await db.get_product_stock(1) == 0  # Остаток не ушёл в минус