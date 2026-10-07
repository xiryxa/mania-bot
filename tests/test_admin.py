import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from handlers.admin import (
    orders_filter_callback,
    orders_page_callback,
    view_order_detail_callback,
    back_to_orders_list_callback,
    show_order_detail,
    admin_change_status_callback,
    add_tracking_callback,
    process_tracking_number,
    adminbacktoorder,
    confirm_clear_tracking_callback,
    AdminOrdersState,
)


class MockSqliteRow(dict):
    pass


def make_mock_order(order_id=1, status="новый", tracking_number=None, comment=""):
    return MockSqliteRow({
        "id": order_id,
        "order_fullname": "Test User",
        "order_phone": "+79990000000",
        "email": "test@test.com",
        "city": "Moscow",
        "name": "Test Product",
        "quantity": 1,
        "unit_price": 100,
        "delivery_method": "Courier",
        "delivery_address": "Test Address",
        "status": status,
        "tracking_number": tracking_number,
        "comment": comment,
        "user_id": 12345,
        "created_at": "2026-10-07 12:00:00",
        "product_id": 1
    })


@pytest.fixture
def mock_callback():
    cb = MagicMock()
    cb.data = "test_data"
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.chat.id = 123
    cb.message.message_id = 456
    cb.from_user = MagicMock()
    cb.from_user.username = "test_admin"
    cb.answer = AsyncMock()
    cb.message.bot = MagicMock()
    cb.message.bot.delete_message = AsyncMock()
    cb.message.bot.edit_message_media = AsyncMock()
    cb.message.bot.edit_message_text = AsyncMock()
    return cb


@pytest.fixture
def mock_state():
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


@pytest.fixture
def mock_message():
    msg = MagicMock()
    msg.chat.id = 123
    msg.message_id = 456
    msg.text = "1234567890"
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.delete_message = AsyncMock()
    msg.bot.edit_message_media = AsyncMock()
    msg.bot.edit_message_text = AsyncMock()
    msg.answer_photo = AsyncMock()
    return msg


# ==============================================================================
# 1. Контекст фильтра и пагинации
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.show_orders_list", new_callable=AsyncMock)
async def test_orders_filter_and_pagination_context(mock_show_list, mock_callback, mock_state):
    mock_callback.data = "orders_filter_active"
    await orders_filter_callback(mock_callback, mock_state)

    mock_show_list.assert_called_once_with(mock_callback.message, mock_state, "active", page=0)
    mock_callback.answer.assert_called_once()

    mock_show_list.reset_mock()
    mock_callback.answer.reset_mock()
    mock_callback.data = "orders_page_2"
    mock_state.get_data.return_value = {"orders_filter": "active"}
    await orders_page_callback(mock_callback, mock_state)

    mock_show_list.assert_called_once_with(mock_callback.message, mock_state, "active", 2)
    mock_callback.answer.assert_called_once()


# ==============================================================================
# 2. Сохранение контекста перед открытием заказа
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.show_order_detail", new_callable=AsyncMock)
@patch("handlers.admin.get_order_by_id")
async def test_view_order_detail_saves_return_context(mock_get_order, mock_show_detail, mock_callback, mock_state):
    mock_callback.data = "view_order_1"
    mock_state.get_data.return_value = {"orders_filter": "active", "orders_page": 2}
    mock_get_order.return_value = make_mock_order()

    await view_order_detail_callback(mock_callback, mock_state)

    mock_state.update_data.assert_called_with(return_to_filter="active", return_to_page=2)
    mock_show_detail.assert_called_once()


# ==============================================================================
# 3. Возврат к исходному списку
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.show_orders_list", new_callable=AsyncMock)
async def test_back_to_orders_list_restores_context(mock_show_list, mock_callback, mock_state):
    mock_state.get_data.return_value = {"return_to_filter": "active", "return_to_page": 2}
    await back_to_orders_list_callback(mock_callback, mock_state)
    mock_show_list.assert_called_once_with(mock_callback.message, mock_state, "active", 2)


# ==============================================================================
# 4. Карточка заказа: Комментарий <= 250 символов
# ==============================================================================
@pytest.mark.asyncio
@patch("db.get_product_by_id")
@patch("db.get_order_by_id")
async def test_show_order_detail_comment_not_truncated_under_250(mock_get_order, mock_get_product, mock_message, mock_state):
    comment_250 = "A" * 250
    mock_get_order.return_value = make_mock_order(comment=comment_250)
    mock_get_product.return_value = None

    await show_order_detail(mock_message, mock_state, 1)

    call_args = mock_message.bot.edit_message_text.call_args
    assert call_args is not None
    caption = call_args.kwargs.get("text") or call_args.args[0]

    comment_section = caption.split("📝 <b>КОММЕНТАРИЙ</b>")[1].split("━━━━━━━━━━━━━")[0]
    assert comment_250 in comment_section
    assert not comment_section.endswith("...")


# ==============================================================================
# 5. Карточка заказа: Комментарий > 250 символов
# ==============================================================================
@pytest.mark.asyncio
@patch("db.get_product_by_id")
@patch("db.get_order_by_id")
async def test_show_order_detail_comment_truncated_over_250(mock_get_order, mock_get_product, mock_message, mock_state):
    comment_251 = "A" * 251
    mock_get_order.return_value = make_mock_order(comment=comment_251)
    mock_get_product.return_value = None

    await show_order_detail(mock_message, mock_state, 1)

    call_args = mock_message.bot.edit_message_text.call_args
    assert call_args is not None
    caption = call_args.kwargs.get("text") or call_args.args[0]

    comment_section = caption.split("📝 <b>КОММЕНТАРИЙ</b>")[1].split("━━━━━━━━━━━━━")[0]
    assert ("A" * 250 + "...") in comment_section
    assert comment_251 not in comment_section


# ==============================================================================
# 6. Карточка заказа: Media fallback
# ==============================================================================
@pytest.mark.asyncio
@patch("db.get_product_by_id")
@patch("db.get_order_by_id")
async def test_show_order_detail_media_fallback(mock_get_order, mock_get_product, mock_message, mock_state):
    mock_get_order.return_value = make_mock_order()
    mock_get_product.return_value = {
        "id": 1, "name": "t", "price": 1, "stock": 1,
        "cat": "t", "desc": "t", "image_file_id": "file_123", "created": "t"
    }

    mock_message.bot.edit_message_media.side_effect = Exception("Bad Request: chat not found")

    await show_order_detail(mock_message, mock_state, 1)

    mock_message.bot.delete_message.assert_called_once_with(chat_id=123, message_id=456)
    mock_message.answer_photo.assert_called_once()
    assert mock_message.answer_photo.call_args.kwargs["photo"] == "file_123"


# ==============================================================================
# 7. Смена статуса: Успешная смена
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.notify_user_safe", new_callable=AsyncMock)
@patch("handlers.admin.show_order_detail", new_callable=AsyncMock)
@patch("handlers.admin.update_order_status_atomic")
@patch("handlers.admin.get_order_by_id")
async def test_change_status_success_and_notification(mock_get_order, mock_update_atomic, mock_show_detail, mock_notify, mock_callback, mock_state):
    mock_callback.data = "ostatus_1_processing"
    mock_get_order.return_value = make_mock_order(status="новый")
    mock_update_atomic.return_value = {"success": True, "old_status": "новый", "message": "ok"}

    await admin_change_status_callback(mock_callback, mock_state)

    mock_update_atomic.assert_called_once_with(1, "в обработке")
    mock_notify.assert_called_once()
    mock_show_detail.assert_called_once_with(mock_callback.message, mock_state, 1)


# ==============================================================================
# 8. Смена статуса: Недостаточно товара / ошибка
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.update_order_status_atomic")
@patch("handlers.admin.get_order_by_id")
async def test_change_status_fails_on_insufficient_stock(mock_get_order, mock_update_atomic, mock_callback, mock_state):
    mock_callback.data = "ostatus_1_shipped"
    mock_get_order.return_value = make_mock_order()
    mock_update_atomic.return_value = {"success": False, "message": "Недостаточно товара на складе"}

    await admin_change_status_callback(mock_callback, mock_state)

    mock_callback.answer.assert_called_once_with("❌ Недостаточно товара на складе", show_alert=True)


# ==============================================================================
# 9. Смена статуса: Идемпотентность
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.update_order_status_atomic")
@patch("handlers.admin.get_order_by_id")
async def test_change_status_idempotency(mock_get_order, mock_update_atomic, mock_callback, mock_state):
    mock_callback.data = "ostatus_1_processing"
    mock_get_order.return_value = make_mock_order(status="в обработке")
    mock_update_atomic.return_value = {"success": True, "old_status": "в обработке", "message": "Статус не изменился"}

    await admin_change_status_callback(mock_callback, mock_state)

    mock_callback.answer.assert_called_once_with("ℹ️ Статус уже установлен", show_alert=True)


# ==============================================================================
# 10. Смена статуса: Перевод в "отправлен"
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.notify_user_safe", new_callable=AsyncMock)
@patch("handlers.admin.update_order_status_atomic")
@patch("handlers.admin.get_order_by_id")
async def test_change_status_to_shipped_prompts_tracking(mock_get_order, mock_update_atomic, mock_notify, mock_callback, mock_state):
    mock_callback.data = "ostatus_1_shipped"
    mock_get_order.return_value = make_mock_order(status="в обработке")
    mock_update_atomic.return_value = {"success": True, "old_status": "в обработке", "message": "ok"}

    await admin_change_status_callback(mock_callback, mock_state)

    mock_update_atomic.assert_called_once_with(1, "отправлен")
    mock_notify.assert_called_once()
    mock_callback.answer.assert_called()


# ==============================================================================
# 11. Добавление трека: Переход в FSM
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.get_order_by_id")
async def test_add_tracking_sets_fsm_state_and_data(mock_get_order, mock_callback, mock_state):
    mock_callback.data = "add_tracking_1"
    mock_get_order.return_value = make_mock_order()
    mock_state.get_data.return_value = {"orders_filter": "active", "orders_page": 0}
    mock_callback.message.bot.edit_message_media = AsyncMock()

    await add_tracking_callback(mock_callback, mock_state)

    mock_state.set_state.assert_called_once_with(AdminOrdersState.adding_tracking)
    mock_state.update_data.assert_any_call(
        tracking_order_id=1,
        orders_filter="active",
        orders_page=0
    )
    mock_state.update_data.assert_any_call(tracking_prompt_message_id=456)


# ==============================================================================
# 12. Добавление трека: Успешный ввод (реальный show_order_detail)
# ==============================================================================
@pytest.mark.asyncio
@patch("db.format_moscow_time")
@patch("db.get_product_by_id")
@patch("db.get_order_by_id")
@patch("handlers.admin.notify_user_safe", new_callable=AsyncMock)
@patch("handlers.admin.update_order_tracking_number", new_callable=AsyncMock)
@patch("handlers.admin.get_order_by_id")
async def test_process_tracking_number_success_flow(
    mock_admin_get_order, mock_update_tracking, mock_notify,
    mock_db_get_order, mock_get_product, mock_format_time,
    mock_message, mock_state
):
    mock_state.get_data.return_value = {"tracking_order_id": 1, "tracking_prompt_message_id": 456}
    mock_admin_get_order.return_value = make_mock_order()
    mock_db_get_order.return_value = make_mock_order()
    mock_get_product.return_value = None
    mock_format_time.return_value = "2026-10-07 12:00:00"

    await process_tracking_number(mock_message, mock_state)

    mock_update_tracking.assert_called_once_with(1, "1234567890")

    edit_call = mock_message.bot.edit_message_text.call_args
    assert edit_call is not None
    assert edit_call.kwargs.get("message_id") == 456

    mock_state.clear.assert_called_once()


# ==============================================================================
# 13. Добавление трека: Слишком короткий трек
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.update_order_tracking_number", new_callable=AsyncMock)
async def test_process_tracking_number_rejects_short_input(mock_update_tracking, mock_message, mock_state):
    mock_message.text = "AB"
    mock_state.get_data.return_value = {"tracking_order_id": 1}

    await process_tracking_number(mock_message, mock_state)

    mock_message.answer.assert_called_once()
    assert "Слишком короткий" in mock_message.answer.call_args.args[0]
    mock_update_tracking.assert_not_called()
    mock_state.clear.assert_not_called()


# ==============================================================================
# 14. Добавление трека: Текущее поведение при ошибке show_order_detail
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.notify_user_safe", new_callable=AsyncMock)
@patch("handlers.admin.show_order_detail", new_callable=AsyncMock)
@patch("handlers.admin.update_order_tracking_number", new_callable=AsyncMock)
@patch("handlers.admin.get_order_by_id")
async def test_process_tracking_number_current_fallback_on_edit_error(mock_get_order, mock_update_tracking, mock_notify, mock_show_detail, mock_message, mock_state):
    mock_state.get_data.return_value = {"tracking_order_id": 1, "tracking_prompt_message_id": 456}
    mock_get_order.return_value = make_mock_order()

    # Эмулируем полный сбой рендеринга (исключение пробрасывается во внешний except)
    mock_show_detail.side_effect = Exception("Complete render failure")

    await process_tracking_number(mock_message, mock_state)

    # Проверяем, что сработал внешний обработчик ошибок и админ получил уведомление о сбое
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "Ошибка при добавлении трек-номера" in call_args.args[0]

    # Проверяем, что ложное сообщение об успехе НЕ было отправлено
    assert "Трек-номер добавлен!" not in call_args.args[0]


# ==============================================================================
# 15. Отмена добавления трека
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.show_order_detail", new_callable=AsyncMock)
async def test_cancel_tracking_addition_clears_state(mock_show_detail, mock_callback, mock_state):
    mock_callback.data = "adminbacktoorder"
    mock_state.get_data.return_value = {"tracking_order_id": 1, "tracking_prompt_message_id": 456}

    await adminbacktoorder(mock_callback, mock_state)

    mock_state.clear.assert_called_once()
    mock_show_detail.assert_called_once_with(mock_callback.message, mock_state, 1, target_message_id=456)


# ==============================================================================
# 16. Очистка трека: Подтверждение
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.show_order_detail", new_callable=AsyncMock)
@patch("handlers.admin.notify_user_safe", new_callable=AsyncMock)
@patch("handlers.admin.clear_order_tracking_number", new_callable=AsyncMock)
@patch("handlers.admin.get_order_by_id")
async def test_confirm_clear_tracking_updates_and_returns(mock_get_order, mock_clear_tracking, mock_notify, mock_show_detail, mock_callback, mock_state):
    mock_callback.data = "confirm_clear_tracking_1"
    mock_get_order.return_value = make_mock_order(tracking_number="TRACK123")

    await confirm_clear_tracking_callback(mock_callback, mock_state)

    mock_clear_tracking.assert_called_once_with(1)
    mock_notify.assert_called_once()
    mock_show_detail.assert_called_once_with(mock_callback.message, mock_state, 1, target_message_id=456)


# ==============================================================================
# 17. Несуществующие заказы: При смене статуса
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.get_order_by_id")
async def test_change_status_nonexistent_order(mock_get_order, mock_callback, mock_state):
    mock_callback.data = "ostatus_999_processing"
    mock_get_order.return_value = None

    await admin_change_status_callback(mock_callback, mock_state)

    mock_callback.answer.assert_called_once_with("Заказ не найден.")


# ==============================================================================
# 18. Несуществующие заказы: При добавлении трека
# ==============================================================================
@pytest.mark.asyncio
@patch("handlers.admin.get_order_by_id")
async def test_add_tracking_nonexistent_order(mock_get_order, mock_callback, mock_state):
    mock_callback.data = "add_tracking_999"
    mock_get_order.return_value = None

    await add_tracking_callback(mock_callback, mock_state)

    mock_callback.answer.assert_called_once_with("❌ Заказ не найден.", show_alert=True)


# ==============================================================================
# 19. Добавление трека: Нетекстовое сообщение
# ==============================================================================
@pytest.mark.asyncio
async def test_process_tracking_number_rejects_non_text_input(mock_message, mock_state):
    from handlers.admin import process_tracking_number_invalid_type

    # Эмулируем сообщение без текста (например, фото)
    mock_message.text = None
    mock_message.content_type = "photo"

    await process_tracking_number_invalid_type(mock_message, mock_state)

    # Проверяем, что админ получил понятное сообщение об ошибке
    mock_message.answer.assert_called_once()
    assert "введите трек-номер текстом" in mock_message.answer.call_args.args[0]

    # Проверяем, что состояние НЕ очищается (админ остаётся в FSM)
    mock_state.clear.assert_not_called()
