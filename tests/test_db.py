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
    
    
@pytest.mark.asyncio
async def test_update_order_status_atomic_cancel_and_restore(initialized_db):
    """Тест атомарного изменения статуса: отмена и восстановление заказа"""
    # 1. Создаем пользователя и товар (5 шт)
    await db.add_user(1, "Иван Петров", "+79000000000", "test@test.com", "Москва")
    await db.add_product("Манок", "Описание", 1000, "Утки", 5)
    
    # 2. Создаем заказ на 2 шт (остаток станет 3)
    order_res = await db.create_order_and_decrease_stock(
        user_id=1, product_id=1, quantity=2, 
        delivery_method="Почта", delivery_address="Москва"
    )
    order_id = order_res["order_id"]
    assert await db.get_product_stock(1) == 3
    
    # 3. Отменяем заказ (остаток должен стать 5)
    result = await db.update_order_status_atomic(order_id, "отменён")
    assert result["success"] is True
    assert result["old_status"] == "новый"
    assert result["new_status"] == "отменён"
    assert await db.get_product_stock(1) == 5
    
    # 4. Повторная отмена (идемпотентность: остаток не должен измениться второй раз)
    result_repeat = await db.update_order_status_atomic(order_id, "отменён")
    assert result_repeat["success"] is True
    assert result_repeat["message"] == "Статус не изменился"
    assert await db.get_product_stock(1) == 5
    
    # 5. Восстанавливаем заказ в "в обработке" (остаток должен стать 3)
    result_restore = await db.update_order_status_atomic(order_id, "в обработке")
    assert result_restore["success"] is True
    assert result_restore["old_status"] == "отменён"
    assert result_restore["new_status"] == "в обработке"
    assert await db.get_product_stock(1) == 3


@pytest.mark.asyncio
async def test_update_order_status_atomic_restore_insufficient_stock(initialized_db):
    """Тест атомарного восстановления заказа при недостатке товара на складе"""
    # 1. Создаем пользователя и товар (2 шт). В свежей БД этот товар получит id=1
    await db.add_user(2, "Петр Сидоров", "+79000000001", "test2@test.com", "Москва")
    await db.add_product("Манок 2", "Описание 2", 1500, "Гусь", 2)
    
    # 2. Создаем заказ на 2 шт (остаток станет 0). Используем product_id=1
    order_res = await db.create_order_and_decrease_stock(
        user_id=2, product_id=1, quantity=2, 
        delivery_method="Почта", delivery_address="Москва"
    )
    order_id = order_res["order_id"]
    assert await db.get_product_stock(1) == 0
    
    # 3. Отменяем заказ (остаток должен стать 2)
    result_cancel = await db.update_order_status_atomic(order_id, "отменён")
    assert result_cancel["success"] is True
    assert await db.get_product_stock(1) == 2
    
    # 4. Симулируем, что весь остаток (2 шт) купили в другом заказе
    await db.decrease_product_stock(1, 2)
    assert await db.get_product_stock(1) == 0
    
    # 5. Пытаемся восстановить первый заказ (требуется 2 шт, но на складе 0)
    result_restore = await db.update_order_status_atomic(order_id, "в обработке")
    assert result_restore["success"] is False
    assert "Недостаточно товара на складе" in result_restore["message"]
    
    # Статус заказа не должен измениться, остаток не уйдет в минус
    order = await db.get_order_by_id(order_id)
    assert order[10] == "отменён"
    assert await db.get_product_stock(1) == 0
    
    
@pytest.mark.asyncio
async def test_delete_product_soft_delete(initialized_db):
    """
    Проверка: мягкое удаление товара (delete_product).
    Товар должен исчезнуть из активных и появиться в удаленных.
    """
    # 1. Создаем товар
    await db.add_product("Манок", "Описание", 1000, "Утки", 5)
    
    # 2. Проверяем, что он активен
    active_products = await db.get_all_products()
    assert len(active_products) == 1
    product_id = active_products[0][0]
    
    # 3. Скрываем товар
    result = await db.delete_product(product_id)
    assert result["success"] is True
    assert result["active_orders"] == 0
    
    # 4. Проверяем, что он исчез из активных и появился в удаленных
    assert len(await db.get_all_products()) == 0
    
    deleted_products = await db.get_deleted_products()
    assert len(deleted_products) == 1
    assert deleted_products[0][0] == product_id
    
    
@pytest.mark.asyncio
async def test_subscribe_to_product_success_and_duplicate(initialized_db):
    """
    Проверка: успешная подписка на товар и отказ при повторной подписке.
    """
    # 1. Создаем пользователя и товар
    await db.add_user(1, "Иван Петров", "+79000000000", "test@test.com", "Москва")
    await db.add_product("Манок", "Описание", 1000, "Утки", 5)
    
    # 2. Первая подписка успешна
    result1 = await db.subscribe_to_product(1, 1)
    assert result1["success"] is True
    
    # 3. Повторная подписка того же пользователя на тот же товар отклонена
    result2 = await db.subscribe_to_product(1, 1)
    assert result2["success"] is False
    
    # 4. Проверяем список подписчиков
    subscribers = await db.get_product_subscribers(1)
    assert subscribers == [1]


@pytest.mark.asyncio
async def test_update_product_restocked_flag(initialized_db):
    """
    Проверка: корректность флага restocked при изменении остатков товара.
    """
    # 1. Создаем товар с quantity=0
    await db.add_product("Манок", "Описание", 1000, "Утки", 0)
    product_id = 1

    # 2. Обновляем, оставляя quantity=0 -> restocked должен быть False
    result1 = await db.update_product(
        product_id=product_id,
        name="Манок",
        description="Описание",
        price=1000,
        category="Утки",
        quantity=0
    )
    assert result1["success"] is True
    assert result1["restocked"] is False

    # 3. Обновляем до quantity=5 -> restocked должен быть True (переход 0 -> >0)
    result2 = await db.update_product(
        product_id=product_id,
        name="Манок",
        description="Описание",
        price=1000,
        category="Утки",
        quantity=5
    )
    assert result2["success"] is True
    assert result2["restocked"] is True

    # 4. Обновляем с 5 до 10 -> restocked должен быть False (уже был >0)
    result3 = await db.update_product(
        product_id=product_id,
        name="Манок",
        description="Описание",
        price=1000,
        category="Утки",
        quantity=10
    )
    assert result3["success"] is True
    assert result3["restocked"] is False
    
