import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Импортируем тестируемые хендлеры и состояния
from handlers.admin_products import (
    product_add_cancel,
    product_edit_value,
    product_add_confirm,
    show_admin_product_text,
    product_delete_yes,
    restore_yes,
)
from handlers.admin_products import product_edit_value, clear_url_ozon, clear_url_youtube
from forms.users import AdminProductState

# ==============================================================================
# Локальные фикстуры и заглушки
# ==============================================================================

class MockSqliteRow:
    """Заглушка, имитирующая поведение sqlite3.Row (поддержка ТОЛЬКО __getitem__)"""
    def __init__(self, **kwargs):
        self._data = kwargs

    def __getitem__(self, key):
        return self._data[key]


@pytest.fixture
def mock_state():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.set_data = AsyncMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


@pytest.fixture
def mock_callback():
    callback = MagicMock()
    callback.data = "test_data"
    callback.message = MagicMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 12345
    callback.message.message_id = 999

    callback.message.answer = AsyncMock()
    callback.message.delete = AsyncMock()
    callback.message.answer_photo = AsyncMock()

    callback.bot = AsyncMock()
    callback.bot.edit_message_media = AsyncMock()
    callback.bot.send_photo = AsyncMock()
    callback.bot.delete_message = AsyncMock()

    callback.message.bot = callback.bot
    callback.answer = AsyncMock()
    return callback


@pytest.fixture
def mock_message():
    message = MagicMock()
    message.text = ""
    message.chat = MagicMock()
    message.chat.id = 12345
    message.message_id = 999

    message.delete = AsyncMock()
    message.answer = AsyncMock()
    message.answer_photo = AsyncMock()

    message.bot = AsyncMock()
    message.bot.edit_message_media = AsyncMock()
    message.bot.send_photo = AsyncMock()
    message.bot.delete_message = AsyncMock()

    return message


# ==============================================================================
# Тесты
# ==============================================================================

@pytest.mark.asyncio
async def test_add_product_fsm_cancel_preserves_list_context(mock_callback, mock_state):
    """Тест 1: Отмена добавления сохраняет контекст списка (admin_page, admin_products)"""
    mock_callback.data = "product_add_cancel"
    mock_state.get_data.return_value = {
        "admin_page": 2,
        "admin_products": [{"id": 1, "name": "Test"}],
        "product_data": {"name": "New"},
        "add_return_callback": "product_page_admin_2",
    }

    with patch("handlers.admin_products.show_admin_product", new_callable=AsyncMock) as mock_show:
        await product_add_cancel(mock_callback, mock_state)

    call_args = mock_state.set_data.call_args[0][0]
    assert "admin_page" in call_args
    assert "admin_products" in call_args
    assert "product_data" not in call_args
    assert "add_return_callback" not in call_args

    mock_state.set_state.assert_called_once_with(None)
    mock_show.assert_called_once()


@pytest.mark.asyncio
@patch("handlers.admin_products.update_product")
@patch("handlers.admin_products.get_product_by_id")
async def test_edit_product_value_updates_cache_as_dict(mock_get_product, mock_update_product, mock_message, mock_state):
    """Тест 2: Редактирование значения корректно обновляет cache, конвертируя sqlite3.Row в dict"""
    mock_message.text = "1500"
    mock_state.get_data.return_value = {
        "editing_product_id": 1,
        "editing_field": "price",
        "admin_products": [MockSqliteRow(id=1, name="Old", description="Desc", price=100, category="C", quantity=5, ozon_url=None, image_file_id=None)],
    }
    mock_get_product.return_value = MockSqliteRow(id=1, name="Old", description="Desc", price=100, category="C", quantity=5, ozon_url=None, youtube_url=None, image_file_id=None)
    mock_update_product.return_value = {"success": True, "product_id": 1, "restocked": False}

    await product_edit_value(mock_message, mock_state)

    mock_update_product.assert_called_once()
    mock_state.update_data.assert_called_once()

    update_call_kwargs = mock_state.update_data.call_args[1]
    updated_products = update_call_kwargs["admin_products"]

    assert len(updated_products) == 1
    updated_item = updated_products[0]

    # Усиленные проверки: элемент должен быть dict, и все остальные поля должны сохраниться
    assert isinstance(updated_item, dict), "Элемент кэша должен быть преобразован в dict"
    assert updated_item["price"] == 1500
    assert updated_item["name"] == "Old"
    assert updated_item["quantity"] == 5
    assert updated_item["image_file_id"] is None


@pytest.mark.asyncio
@patch("handlers.admin_products.add_product")
async def test_add_product_full_cycle_with_photo_and_confirm(mock_add_product, mock_callback, mock_state):
    """Тест 3: Полный confirm создания товара с фото вызывает add_product и очищает FSM"""
    mock_callback.data = "product_add_confirm"
    mock_state.get_data.return_value = {
        "product_data": {
            "name": "Test", "price": 100, "category": "goose",
            "quantity": 1, "image_file_id": "file_123"
        },
        "add_bot_message_id": 999
    }
    mock_add_product.return_value = True

    await product_add_confirm(mock_callback, mock_state)

    mock_add_product.assert_called_once()
    call_kwargs = mock_add_product.call_args[1]
    assert call_kwargs["image_file_id"] == "file_123"

    mock_state.clear.assert_called_once()
    mock_state.set_state.assert_called_once_with(AdminProductState.selecting_action)


@pytest.mark.asyncio
@patch("handlers.admin_products.render_admin_banner", new_callable=AsyncMock)
async def test_pagination_context_preserved_in_text_list(mock_render_banner, mock_message, mock_state):
    """Тест 4: Пагинация текстового списка сохраняет admin_page в кнопке возврата"""
    mock_state.get_data.return_value = {
        "admin_products": [
            {"id": 1, "name": "T1", "description": "D1", "price": 10, "category": "C", "quantity": 1, "image_file_id": None}
        ],
        "admin_page": 2
    }

    await show_admin_product_text(mock_message, mock_state, 2)

    mock_render_banner.assert_called_once()
    keyboard = mock_render_banner.call_args[0][2]

    return_btn = None
    for row in keyboard.inline_keyboard:
        for btn in row:
            if btn.text == "🖼️ Вернуться к просмотру с фото":
                return_btn = btn
                break

    assert return_btn is not None
    assert return_btn.callback_data == "product_page_admin_2"


@pytest.mark.asyncio
@patch("handlers.admin_products.update_product")
@patch("handlers.admin_products.get_product_by_id")
async def test_edit_product_invalid_input_rejection(mock_get_product, mock_update_product, mock_message, mock_state):
    """Тест 5: Некорректный ввод цены отсекается до вызова update_product"""
    mock_message.text = "-50"
    mock_state.get_data.return_value = {
        "editing_product_id": 1,
        "editing_field": "price"
    }
    mock_get_product.return_value = MockSqliteRow(id=1, name="Test", description="D", price=100, category="C", quantity=5, ozon_url=None, youtube_url=None, image_file_id=None)

    await product_edit_value(mock_message, mock_state)

    mock_message.answer.assert_called_once()
    assert "корректную цену" in mock_message.answer.call_args[0][0]
    mock_update_product.assert_not_called()


@pytest.mark.asyncio
@patch("handlers.admin_products.restore_product")
@patch("handlers.admin_products.delete_product")
@patch("handlers.admin_products.get_product_by_id")
async def test_delete_and_restore_product_flow(mock_get_product, mock_delete_product, mock_restore_product, mock_callback, mock_state):
    """Тест 6: Delete + Restore проходят через handler-уровень и вызывают нужные DB-функции"""
    mock_product = MockSqliteRow(id=1, name="Test", price=100, category="C", quantity=5, ozon_url=None, image_file_id=None)
    mock_get_product.return_value = mock_product

    # --- Тест удаления ---
    mock_callback.data = "delete_yes_1"
    mock_state.get_data.return_value = {"delete_return_callback": "admin_products"}
    mock_delete_product.return_value = {"success": True, "active_orders": 0}

    await product_delete_yes(mock_callback, mock_state)

    mock_delete_product.assert_called_once_with(1)
    assert mock_callback.bot.edit_message_media.called or mock_callback.message.answer_photo.called

    # --- Изоляция теста восстановления ---
    mock_callback.bot.edit_message_media.reset_mock()
    mock_callback.message.answer_photo.reset_mock()

    # --- Тест восстановления ---
    mock_callback.data = "restore_yes_1"
    mock_restore_product.return_value = True

    await restore_yes(mock_callback, mock_state)

    mock_restore_product.assert_called_once_with(1)
    assert mock_callback.bot.edit_message_media.called or mock_callback.message.answer_photo.called




@pytest.mark.asyncio
@patch("handlers.admin_products.update_product")
@patch("handlers.admin_products.get_product_by_id")
async def test_edit_product_category_invalid_input_rejection(mock_get_product, mock_update_product, mock_message, mock_state):
    """Тест: недопустимая категория при текстовом редактировании отклоняется"""
    mock_message.text = "недопустимая_категория"
    mock_state.get_data.return_value = {
        "editing_product_id": 1,
        "editing_field": "category"
    }
    mock_get_product.return_value = MockSqliteRow(
        id=1, name="Test", description="D", price=100,
        category="гусь", quantity=5, ozon_url=None, youtube_url=None, image_file_id=None
    )

    await product_edit_value(mock_message, mock_state)

    # Проверяем, что админ получил сообщение об ошибке
    mock_message.answer.assert_called_once()
    assert "Некорректная категория" in mock_message.answer.call_args[0][0]
    assert "гусь" in mock_message.answer.call_args[0][0]
    assert "утка" in mock_message.answer.call_args[0][0]

    # Проверяем, что update_product НЕ вызван
    mock_update_product.assert_not_called()


@pytest.mark.asyncio
@patch("handlers.admin_products.update_product")
@patch("handlers.admin_products.get_product_by_id")
async def test_edit_product_preserves_urls_in_cache(mock_get_product, mock_update_product, mock_message, mock_state):
    """Тест: редактирование цены сохраняет ozon_url и youtube_url в кэше admin_products"""
    mock_message.text = "2000"
    mock_state.get_data.return_value = {
        "editing_product_id": 1,
        "editing_field": "price",
        "admin_products": [
            MockSqliteRow(id=1, name="Test", description="D", price=100, category="C", quantity=5, ozon_url="https://ozon.ru", youtube_url="https://youtube.com", image_file_id="file123")
        ],
    }
    mock_get_product.return_value = MockSqliteRow(id=1, name="Test", description="D", price=100, category="C", quantity=5, ozon_url="https://ozon.ru", youtube_url="https://youtube.com", image_file_id="file123")
    mock_update_product.return_value = {"success": True, "product_id": 1, "restocked": False}

    await product_edit_value(mock_message, mock_state)

    mock_update_product.assert_called_once_with(
        product_id=1,
        name="Test",
        description="D",
        price=2000,
        category="C",
        quantity=5,
        ozon_url="https://ozon.ru",
        youtube_url="https://youtube.com",
        image_file_id="file123",
    )

    update_data_calls = mock_state.update_data.call_args_list
    admin_products_update = None
    for call in update_data_calls:
        if "admin_products" in call.kwargs:
            admin_products_update = call.kwargs["admin_products"]
            break
    assert admin_products_update is not None
    assert admin_products_update[0]["ozon_url"] == "https://ozon.ru"
    assert admin_products_update[0]["youtube_url"] == "https://youtube.com"


@pytest.mark.asyncio
@patch("handlers.admin_products.update_product")
@patch("handlers.admin_products.get_product_by_id")
async def test_clear_ozon_url_preserves_youtube_and_cache(mock_get_product, mock_update_product, mock_callback, mock_state):
    """Тест: очистка Ozon URL сохраняет YouTube и обновляет кэш"""
    mock_callback.data = "clear_url_ozon"
    mock_callback.from_user.id = 123
    mock_state.get_data.return_value = {
        "editing_product_id": 1,
        "admin_products": [
            MockSqliteRow(id=1, name="Test", description="D", price=100, category="C", quantity=5, ozon_url="https://ozon.ru", youtube_url="https://youtube.com", image_file_id="file123")
        ],
    }
    mock_get_product.return_value = MockSqliteRow(id=1, name="Test", description="D", price=100, category="C", quantity=5, ozon_url="https://ozon.ru", youtube_url="https://youtube.com", image_file_id="file123")
    mock_update_product.return_value = {"success": True}

    await clear_url_ozon(mock_callback, mock_state)

    mock_update_product.assert_called_once_with(
        product_id=1, name="Test", description="D", price=100, category="C", quantity=5,
        ozon_url=None, youtube_url="https://youtube.com", image_file_id="file123"
    )

    update_data_calls = mock_state.update_data.call_args_list
    admin_products_update = next((call.kwargs["admin_products"] for call in update_data_calls if "admin_products" in call.kwargs), None)
    assert admin_products_update is not None
    assert admin_products_update[0]["ozon_url"] is None
    assert admin_products_update[0]["youtube_url"] == "https://youtube.com"


@pytest.mark.asyncio
@patch("handlers.admin_products.update_product")
@patch("handlers.admin_products.get_product_by_id")
async def test_clear_youtube_url_preserves_ozon_and_cache(mock_get_product, mock_update_product, mock_callback, mock_state):
    """Тест: очистка YouTube URL сохраняет Ozon и обновляет кэш"""
    mock_callback.data = "clear_url_youtube"
    mock_callback.from_user.id = 123
    mock_state.get_data.return_value = {
        "editing_product_id": 1,
        "admin_products": [
            MockSqliteRow(id=1, name="Test", description="D", price=100, category="C", quantity=5, ozon_url="https://ozon.ru", youtube_url="https://youtube.com", image_file_id="file123")
        ],
    }
    mock_get_product.return_value = MockSqliteRow(id=1, name="Test", description="D", price=100, category="C", quantity=5, ozon_url="https://ozon.ru", youtube_url="https://youtube.com", image_file_id="file123")
    mock_update_product.return_value = {"success": True}

    await clear_url_youtube(mock_callback, mock_state)

    mock_update_product.assert_called_once_with(
        product_id=1, name="Test", description="D", price=100, category="C", quantity=5,
        ozon_url="https://ozon.ru", youtube_url=None, image_file_id="file123"
    )

    update_data_calls = mock_state.update_data.call_args_list
    admin_products_update = next((call.kwargs["admin_products"] for call in update_data_calls if "admin_products" in call.kwargs), None)
    assert admin_products_update is not None
    assert admin_products_update[0]["ozon_url"] == "https://ozon.ru"
    assert admin_products_update[0]["youtube_url"] is None


@pytest.mark.asyncio
@patch("handlers.admin_products.render_admin_banner")
@patch("handlers.admin_products.get_product_by_id")
async def test_edit_field_ozon_url_shows_correct_buttons(mock_get_product, mock_render_banner, mock_callback, mock_state):
    """Тест: при существующем Ozon URL показываются кнопки изменить/очистить"""
    mock_callback.data = "edit_field_ozon_url"
    mock_callback.message.message_id = 1
    mock_state.get_data.return_value = {"editing_product_id": 1}
    mock_get_product.return_value = {
        "id": 1, "name": "T", "description": "D", "price": 100, "category": "C",
        "quantity": 5, "ozon_url": "https://ozon.ru", "youtube_url": None, "image_file_id": None
    }

    from handlers.admin_products import product_edit_field
    await product_edit_field(mock_callback, mock_state)

    mock_render_banner.assert_called_once()
    call_args = mock_render_banner.call_args
    text = call_args.args[1]
    keyboard = call_args.args[2]

    assert "https://ozon.ru" in text
    assert "Ссылка не добавлена" not in text

    callback_datas = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "edit_url_ozon" in callback_datas
    assert "clear_url_ozon" in callback_datas


@pytest.mark.asyncio
@patch("handlers.admin_products.render_admin_banner")
@patch("handlers.admin_products.get_product_by_id")
async def test_edit_field_youtube_url_none_shows_correct_buttons(mock_get_product, mock_render_banner, mock_callback, mock_state):
    """Тест: при отсутствующем YouTube URL показывается 'Ссылка не добавлена' и НЕТ кнопки очистки"""
    mock_callback.data = "edit_field_youtube_url"
    mock_callback.message.message_id = 1
    mock_state.get_data.return_value = {"editing_product_id": 1}
    mock_get_product.return_value = {
        "id": 1, "name": "T", "description": "D", "price": 100, "category": "C",
        "quantity": 5, "ozon_url": None, "youtube_url": None, "image_file_id": None
    }

    from handlers.admin_products import product_edit_field
    await product_edit_field(mock_callback, mock_state)

    mock_render_banner.assert_called_once()
    call_args = mock_render_banner.call_args
    text = call_args.args[1]
    keyboard = call_args.args[2]

    assert "Ссылка не добавлена" in text

    callback_datas = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "edit_url_youtube" in callback_datas
    assert "clear_url_youtube" not in callback_datas
@pytest.mark.asyncio
@patch("handlers.admin_products.get_product_by_id")
async def test_edit_url_edits_existing_message(mock_get_product, mock_callback, mock_state):
    """Тест: при входе в редактирование URL редактируется существующее сообщение, а не создается новое"""
    mock_callback.data = "edit_url_ozon"
    mock_callback.message.message_id = 123
    mock_state.get_data.return_value = {"editing_product_id": 1}
    mock_get_product.return_value = {
        "id": 1, "name": "T", "description": "D", "price": 100, "category": "C",
        "quantity": 5, "ozon_url": "https://ozon.ru", "youtube_url": None, "image_file_id": "file123"
    }
    from handlers.admin_products import edit_url_ozon
    await edit_url_ozon(mock_callback, mock_state)
    # Проверяем, что был вызван edit_message_media (для фото) или edit_text (для баннера)
    assert mock_callback.bot.edit_message_media.called or mock_callback.message.edit_text.called
    # Проверяем, что edit_bot_message_id был сохранен в state
    update_data_calls = mock_state.update_data.call_args_list
    assert any("edit_bot_message_id" in call.kwargs for call in update_data_calls)
@pytest.mark.asyncio
@patch("handlers.admin_products.update_product")
@patch("handlers.admin_products.get_product_by_id")
async def test_edit_url_value_edits_same_message(mock_get_product, mock_update_product, mock_message, mock_state):
    """Тест: после ввода новой ссылки product_edit_value редактирует ТО ЖЕ сообщение, а не создает новое"""
    mock_message.text = "https://new-ozon.ru"
    mock_message.chat.id = 123
    mock_message.bot.edit_message_media = AsyncMock()
    mock_message.answer = AsyncMock()
    mock_message.answer_photo = AsyncMock()
    mock_state.get_data.return_value = {
        "editing_product_id": 1,
        "editing_field": "ozon_url",
        "edit_bot_message_id": 456,  # ID сообщения, которое должно редактироваться
        "admin_products": [
            MockSqliteRow(id=1, name="Test", description="D", price=100, category="C", quantity=5,
                         ozon_url="https://old-ozon.ru", youtube_url="https://youtube.com", image_file_id="file123")
        ],
    }
    mock_get_product.return_value = MockSqliteRow(
        id=1, name="Test", description="D", price=100, category="C", quantity=5,
        ozon_url="https://old-ozon.ru", youtube_url="https://youtube.com", image_file_id="file123"
    )
    mock_update_product.return_value = {"success": True, "product_id": 1, "restocked": False}

    from handlers.admin_products import product_edit_value
    await product_edit_value(mock_message, mock_state)

    # 1. Ссылка успешно сохранена, вторая ссылка не потеряна
    assert mock_update_product.call_args.kwargs["ozon_url"] == "https://new-ozon.ru"
    assert mock_update_product.call_args.kwargs["youtube_url"] == "https://youtube.com"

    # 2. Редактируется ТО ЖЕ сообщение (по edit_bot_message_id)
    mock_message.bot.edit_message_media.assert_called_once()
    call_kwargs = mock_message.bot.edit_message_media.call_args.kwargs
    assert call_kwargs["message_id"] == 456
    assert call_kwargs["chat_id"] == 123

    # 3. Новое фото/меню НЕ отправляется (answer_photo не вызывался)
    # (message.answer вызывается только для штатного временного уведомления "✅ ... обновлено!")
    mock_message.answer_photo.assert_not_called()