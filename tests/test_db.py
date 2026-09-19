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
    
# ==============================================================================
# Изоляция снепшота данных и логика уведомлений о статусе
# ==============================================================================

@pytest.mark.asyncio
async def test_order_snapshot_isolation(initialized_db):
    """
    Проверка: изменение профиля пользователя не меняет данные в уже созданном заказе.
    Регрессионный тест для фичи снепшота данных (order_fullname, order_phone).
    """
    import aiosqlite
    
    # 1. Создаем пользователя с исходными данными
    await db.add_user(
        telegram_id=999,
        fullname="Иван Иванов",
        phone="+79001112233",
        email="test@test.com",
        city="Москва",
        address="ул. Ленина 1"
    )
    
    # 2. Добавляем тестовый товар
    await db.add_product("Тестовый манок", "Описание", 1000, "goose", 10)
    
    # 3. Создаем заказ (в этот момент фиксируется снепшот данных)
    result = await db.create_order_and_decrease_stock(
        user_id=999,
        product_id=1,
        quantity=1,
        delivery_method="Почта",
        delivery_address="ул. Ленина 1",
        comment="Тестовый коммент"
    )
    
    assert result["success"] is True
    order_id = result["order_id"]
    assert order_id is not None
    
    # 4. Меняем данные пользователя ПОСЛЕ создания заказа
    # Используем прямой доступ к БД (db.DATABASE уже пропатчен на временный файл через conftest)
    async with aiosqlite.connect(db.DATABASE) as test_db:
        await test_db.execute(
            "UPDATE users SET fullname = ?, phone = ? WHERE id = ?",
            ("Петр Петров", "+79998887766", 999)
        )
        await test_db.commit()
    
    # 5. Читаем заказ и проверяем, что в нем остались СТАРЫЕ данные (снепшот)
    # Согласно get_order_by_id: индекс 2 = order_fullname, 3 = order_phone
    order = await db.get_order_by_id(order_id)
    
    assert order is not None
    assert order[2] == "Иван Иванов", f"Ожидался 'Иван Иванов', получено: {order[2]}"
    assert order[3] == "+79001112233", f"Ожидался '+79001112233', получено: {order[3]}"


def test_status_notification_forward_movement():
    """Движение вперед: новый -> в обработке. Должно прийти стандартное уведомление."""
    text = db.get_status_notification_text(
        old_status="новый",
        new_status="в обработке",
        order_id=1,
        product_name="Манок",
        delivery_method="Почта",
        delivery_address="Адрес"
    )
    assert text is not None
    assert "принят в обработку" in text


def test_status_notification_rollback():
    """Откат назад: отправлен -> в обработке. Должно прийти нейтральное сообщение о факте изменения (без выдуманных причин)."""
    text = db.get_status_notification_text(
        old_status="отправлен",
        new_status="в обработке",
        order_id=1,
        product_name="Манок",
        delivery_method="Почта",
        delivery_address="Адрес"
    )
    assert text is not None
    # Проверяем новый нейтральный текст, согласованный с Claude
    assert "вернулся в стадию обработки" in text
    assert "Продолжается подготовка" in text
    assert "/about" in text


def test_status_notification_no_change():
    """Статус не изменился. Уведомления быть не должно (возврат None)."""
    text = db.get_status_notification_text(
        old_status="в обработке",
        new_status="в обработке",
        order_id=1,
        product_name="Манок",
        delivery_method="Почта",
        delivery_address="Адрес"
    )
    assert text is None