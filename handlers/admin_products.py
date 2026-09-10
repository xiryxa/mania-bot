# ==================== ИМПОРТЫ ====================
import logging
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    InputMediaPhoto
)
from db import (
    add_product,
    delete_product,
    escape_html,
    get_all_products,
    get_deleted_products,
    get_product_by_id,
    restore_product,
    update_product,
    update_product_image
)
from filters import IsAdmin
from forms.users import AdminProductEditState, AdminProductState

# ==================== НАСТРОЙКА ====================
logger = logging.getLogger(__name__)
router = Router()


# ==================== ВХОД В УПРАВЛЕНИЕ ТОВАРАМИ ====================
@router.callback_query(F.data == "admin_products", IsAdmin())
async def admin_products_menu(callback: CallbackQuery, state: FSMContext):
    """Меню управления товарами"""
    data = await state.get_data()
    last_photo_message_id = data.get("admin_last_photo_message_id")
    if last_photo_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=last_photo_message_id,
            )
        except Exception:
            pass
        await state.update_data(admin_last_photo_message_id=None)

    await state.set_state(AdminProductState.selecting_action)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить товар", callback_data="product_add")],
            [InlineKeyboardButton(text="✏️ Редактировать товар", callback_data="product_edit")],
            [InlineKeyboardButton(text="🗑️ Удалить товар", callback_data="product_delete")],
            [InlineKeyboardButton(text="📋 Список товаров", callback_data="product_list")],
            [InlineKeyboardButton(text="🗑 Удалённые товары", callback_data="deleted_products_list")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_panel")],
        ]
    )

    try:
        await callback.message.edit_text(
            "📦 <b>Управление товарами</b>\n\n"
            "Выберите действие:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"admin_products_menu edit failed: {e}, sending new")
        await callback.message.answer(
            "📦 <b>Управление товарами</b>\n\n"
            "Выберите действие:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


# ==================== КНОПКА "НАЗАД" В АДМИН-ПАНЕЛЬ ====================
@router.callback_query(
    StateFilter(AdminProductState.selecting_action),
    F.data == "admin_back_to_panel",
    IsAdmin(),
)
async def products_back_to_panel(callback: CallbackQuery, state: FSMContext):
    """Возврат в админ-панель из управления товарами"""
    from handlers.admin import show_admin_panel

    await state.clear()
    await show_admin_panel(callback.message, state)
    await callback.answer()


# ==================== СПИСОК ТОВАРОВ ====================
@router.callback_query(F.data == "product_list", IsAdmin())
async def product_list(callback: CallbackQuery, state: FSMContext):
    """Показать список товаров с фото (по одному на страницу)"""
    products = await get_all_products()

    if not products:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")]
            ]
        )
        await callback.message.edit_text(
            "📭 Товаров пока нет.",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return

    await state.update_data(
        admin_products=products,
        admin_page=0,
        admin_last_photo_message_id=None,
    )
    await show_admin_product(callback.message, state, 0)
    await callback.answer()


async def show_admin_product(message: Message, state: FSMContext, page: int):
    """Показать один товар для админа с фото"""
    data = await state.get_data()
    products = data.get("admin_products", [])
    last_photo_message_id = data.get("admin_last_photo_message_id")

    if not products or page >= len(products):
        await message.answer("❌ Товары не найдены.")
        return

    product = products[page]
    total = len(products)

    quantity = product[5]
    stock_status = f"📦 В наличии: {quantity} шт."

    text = (
        f"📦 <b>Товар {page + 1} из {total}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{product[0]}</code>\n"
        f"📌 Название: <b>{escape_html(product[1])}</b>\n"
        f"📝 Описание: {escape_html(product[2][:100] + ('...' if len(product[2]) > 100 else ''))}\n"
        f"💰 Цена: {product[3]} ₽\n"
        f"🏷️ Категория: {escape_html(product[4])}\n"
        f"{stock_status}\n"
        f"📷 Фото: {'✅ есть' if product[7] else '❌ нет'}"
    )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_product_page_{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="admin_page_info"))
    if page < total - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_product_page_{page + 1}"))

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            nav_buttons if nav_buttons else [],
            [
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_select_{product[0]}"),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_confirm_{product[0]}"),
            ],
            [
                InlineKeyboardButton(text="📋 Текстовый список", callback_data="product_list_text"),
                InlineKeyboardButton(text="➕ Добавить", callback_data="product_add"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")],
        ]
    )

    # Если есть фото — используем edit_message_media
    if product[7]:
        try:
            if last_photo_message_id:
                await message.bot.edit_message_media(
                    chat_id=message.chat.id,
                    message_id=last_photo_message_id,
                    media=InputMediaPhoto(
                        media=product[7],
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=keyboard,
                )
                return
            else:
                photo_msg = await message.answer_photo(
                    photo=product[7],
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
                await state.update_data(admin_last_photo_message_id=photo_msg.message_id)
                try:
                    await message.delete()
                except Exception:
                    pass
                return
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                return
            logger.warning(f"Error editing/sending admin product photo: {e}, fallback to new message")
            photo_msg = await message.answer_photo(
                photo=product[7],
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            await state.update_data(admin_last_photo_message_id=photo_msg.message_id)
            try:
                await message.delete()
            except Exception:
                pass
            return

    # Если фото нет — текстовый вариант
    if last_photo_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_photo_message_id)
        except Exception:
            pass
        await state.update_data(admin_last_photo_message_id=None)

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("admin_product_page_"), IsAdmin())
async def admin_product_page(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы в админ-списке товаров"""
    page = int(callback.data.split("_")[3])
    await show_admin_product(callback.message, state, page)
    await callback.answer()


@router.callback_query(F.data == "admin_page_info", IsAdmin())
async def admin_page_info(callback: CallbackQuery):
    """Информация о странице"""
    await callback.answer("Страница товара", show_alert=True)


@router.callback_query(F.data == "product_list_text", IsAdmin())
async def product_list_text(callback: CallbackQuery, state: FSMContext):
    """Показать текстовый список всех товаров (без фото)"""
    data = await state.get_data()
    products = data.get("admin_products", [])

    if not products:
        await callback.message.edit_text("📭 Товаров нет.")
        await callback.answer()
        return

    text = "📦 <b>Список товаров:</b>\n"
    text += "━━━━━━━━━━━━━━━━━\n\n"

    for product in products:
        quantity = product[5]
        text += (
            f"🔹 <b>{escape_html(product[1])}</b>\n"
            f"   🆔 ID: <code>{product[0]}</code>\n"
            f"   🏷️ {escape_html(product[4])} | 💰 {product[3]} ₽\n"
            f"   📦 В наличии: {quantity} шт.\n"
            f"   📷 {'🖼️ есть' if product[7] else '❌ нет'}\n"
            f"   ─────────────\n"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖼️ Вернуться к просмотру с фото", callback_data="product_list")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


# ==================== ДОБАВЛЕНИЕ ТОВАРА (FSM) ====================
@router.callback_query(F.data == "product_add", IsAdmin())
async def product_add_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление товара"""
    await state.set_state(AdminProductState.adding_name)
    await state.update_data(product_data={})

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")]
        ]
    )

    try:
        await callback.message.edit_text(
            "📝 <b>Добавление товара</b>\n\n"
            "Введите <b>название</b> товара (манка):",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"product_add_start edit failed: {e}, sending new")
        await callback.message.answer(
            "📝 <b>Добавление товара</b>\n\n"
            "Введите <b>название</b> товара (манка):",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@router.message(StateFilter(AdminProductState.adding_name), F.text)
async def product_add_name(message: Message, state: FSMContext):
    """Ввод названия товара"""
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❌ Название слишком короткое. Введите минимум 2 символа.")
        return

    data = await state.get_data()
    product_data = data.get("product_data", {})
    product_data["name"] = name
    await state.update_data(product_data=product_data)
    await state.set_state(AdminProductState.adding_description)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")]
        ]
    )

    await message.answer(
        "📝 Введите <b>описание</b> товара:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


@router.message(StateFilter(AdminProductState.adding_description), F.text)
async def product_add_description(message: Message, state: FSMContext):
    """Ввод описания товара"""
    description = message.text.strip()
    if len(description) < 3:
        await message.answer("❌ Описание слишком короткое. Введите минимум 3 символа.")
        return

    data = await state.get_data()
    product_data = data.get("product_data", {})
    product_data["description"] = description
    await state.update_data(product_data=product_data)
    await state.set_state(AdminProductState.adding_price)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")]
        ]
    )

    await message.answer(
        "💰 Введите <b>цену</b> товара (в рублях, только цифры):",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


@router.message(StateFilter(AdminProductState.adding_price), F.text)
async def product_add_price(message: Message, state: FSMContext):
    """Ввод цены товара"""
    if not message.text.isdigit():
        await message.answer("❌ Введите корректную цену (только цифры).")
        return

    price = int(message.text)
    if price < 1:
        await message.answer("❌ Цена должна быть больше 0.")
        return

    data = await state.get_data()
    product_data = data.get("product_data", {})
    product_data["price"] = price
    await state.update_data(product_data=product_data)
    await state.set_state(AdminProductState.adding_category)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🦆 Goose", callback_data="category_goose")],
            [InlineKeyboardButton(text="🦆 Duck", callback_data="category_duck")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")],
        ]
    )

    await message.answer(
        "🏷️ <b>Выберите категорию товара:</b>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(
    StateFilter(AdminProductState.adding_category),
    F.data.startswith("category_"),
    IsAdmin(),
)
async def product_add_category_callback(callback: CallbackQuery, state: FSMContext):
    """Выбор категории через callback"""
    category_map = {"goose": "гусь", "duck": "утка"}
    key = callback.data.split("_")[1]
    category = category_map.get(key, key)

    data = await state.get_data()
    product_data = data.get("product_data", {})
    product_data["category"] = category
    await state.update_data(product_data=product_data)
    await state.set_state(AdminProductState.adding_quantity)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")]
        ]
    )

    await callback.message.edit_text(
        f"📦 Введите <b>количество</b> товара в наличии (цифрой):\n\n"
        f"🏷️ Категория: {category}",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.message(StateFilter(AdminProductState.adding_quantity), F.text)
async def product_add_quantity(message: Message, state: FSMContext):
    """Ввод количества товара"""
    if not message.text.isdigit():
        await message.answer("❌ Введите корректное количество (только цифры).")
        return

    quantity = int(message.text)
    if quantity < 0:
        await message.answer("❌ Количество не может быть отрицательным.")
        return

    data = await state.get_data()
    product_data = data.get("product_data", {})
    product_data["quantity"] = quantity
    await state.update_data(product_data=product_data)
    await state.set_state(AdminProductState.adding_photo)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Пропустить", callback_data="photo_skip")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")],
        ]
    )

    await message.answer(
        f"📸 <b>Добавьте фото товара</b> (опционально)\n\n"
        f"Отправьте фото или нажмите «Пропустить»:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(
    StateFilter(AdminProductState.adding_photo),
    F.data == "photo_skip",
    IsAdmin(),
)
async def product_add_photo_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить добавление фото"""
    await save_product(callback.message, state, callback)
    await callback.answer()


@router.message(StateFilter(AdminProductState.adding_photo), F.photo, IsAdmin())
async def product_add_photo(message: Message, state: FSMContext):
    """Получение фото товара"""
    photo = message.photo[-1]
    file_id = photo.file_id

    data = await state.get_data()
    product_data = data.get("product_data", {})
    product_data["image_file_id"] = file_id
    await state.update_data(product_data=product_data)

    await save_product(message, state)


async def save_product(message: Message, state: FSMContext, callback: CallbackQuery = None):
    """Сохранить товар в БД"""
    data = await state.get_data()
    product_data = data.get("product_data", {})

    try:
        await add_product(
            name=product_data.get("name"),
            description=product_data.get("description"),
            price=product_data.get("price"),
            category=product_data.get("category"),
            quantity=product_data.get("quantity", 0),
            ozon_url=None,
            image_file_id=product_data.get("image_file_id"),
        )

        text = (
            f"✅ <b>Товар добавлен!</b>\n\n"
            f"📝 <b>Название:</b> {escape_html(product_data.get('name'))}\n"
            f"💰 <b>Цена:</b> {product_data.get('price')} ₽\n"
            f"🏷️ <b>Категория:</b> {escape_html(product_data.get('category'))}\n"
            f"📦 <b>В наличии:</b> {product_data.get('quantity', 0)} шт.\n"
        )
        if product_data.get("image_file_id"):
            text += "🖼️ <b>Фото:</b> добавлено\n"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📋 Список товаров", callback_data="product_list")],
                [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_back_to_panel")],
            ]
        )

        if callback:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

        await state.clear()
        await state.set_state(AdminProductState.selecting_action)

    except Exception as e:
        logger.error(f"Error adding product: {e}", exc_info=True)
        error_text = "❌ Ошибка при добавлении товара. Попробуйте позже."
        if callback:
            await callback.message.edit_text(error_text, parse_mode=ParseMode.HTML)
        else:
            await message.answer(error_text, parse_mode=ParseMode.HTML)


# ==================== РЕДАКТИРОВАНИЕ ТОВАРА ====================
@router.callback_query(F.data == "product_edit", IsAdmin())
async def product_edit_start(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование товара"""
    products = await get_all_products()

    if not products:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")]
            ]
        )
        await callback.message.edit_text(
            "📭 Нет товаров для редактирования.",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for product in products:
        keyboard.inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {escape_html(product[1])} (ID: {product[0]})",
                    callback_data=f"edit_select_{product[0]}",
                )
            ]
        )
    keyboard.inline_keyboard.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")]
    )

    await callback.message.edit_text(
        "✏️ <b>Редактирование товара</b>\n\n"
        "Выберите товар для редактирования:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_select_"), IsAdmin())
async def product_edit_select(callback: CallbackQuery, state: FSMContext):
    """Выбор товара для редактирования"""
    product_id = int(callback.data.split("_")[2])
    product = await get_product_by_id(product_id)

    if not product:
        await callback.message.edit_text("❌ Товар не найден.")
        await callback.answer()
        return

    await state.update_data(editing_product_id=product_id)
    await state.set_state(AdminProductState.editing_field)

    text = (
        f"✏️ <b>Редактирование товара</b>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{product[0]}</code>\n"
        f"📌 <b>Название:</b> {escape_html(product[1])}\n"
        f"📝 <b>Описание:</b> {escape_html(product[2][:50] + ('...' if len(product[2]) > 50 else ''))}\n"
        f"💰 <b>Цена:</b> {product[3]} ₽\n"
        f"🏷️ <b>Категория:</b> {escape_html(product[4])}\n"
        f"📦 <b>В наличии:</b> {product[5]} шт.\n"
        f"📷 <b>Фото:</b> {'✅ есть' if product[7] else '❌ нет'}\n\n"
        f"Выберите поле для изменения:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Название", callback_data="edit_field_name")],
            [InlineKeyboardButton(text="📝 Описание", callback_data="edit_field_description")],
            [InlineKeyboardButton(text="💰 Цена", callback_data="edit_field_price")],
            [InlineKeyboardButton(text="🏷️ Категория", callback_data="edit_field_category")],
            [InlineKeyboardButton(text="📦 Количество", callback_data="edit_field_quantity")],
            [InlineKeyboardButton(text="📷 Изменить фото", callback_data="edit_field_photo")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="product_edit")],
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        data = await state.get_data()
        last_photo_message_id = data.get("admin_last_photo_message_id")
        if last_photo_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=last_photo_message_id,
                )
                await state.update_data(admin_last_photo_message_id=None)
            except Exception:
                pass

        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    await callback.answer()


# ==================== РЕДАКТИРОВАНИЕ ФОТО ====================
@router.callback_query(F.data == "edit_field_photo", IsAdmin())
async def edit_field_photo(callback: CallbackQuery, state: FSMContext):
    """Запрос нового фото"""
    await callback.answer()
    await state.set_state(AdminProductEditState.photo)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить (оставить текущее)", callback_data="edit_photo_skip")],
            [InlineKeyboardButton(text="⬅️ Назад к редактированию", callback_data="edit_photo_cancel")],
        ]
    )

    await callback.message.edit_text(
        "📷 <b>Редактирование фото</b>\n\n"
        "Отправьте новое фото для товара.\n"
        "Или нажмите «Пропустить», чтобы оставить текущее фото.",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "edit_photo_skip", IsAdmin())
async def edit_photo_skip(callback: CallbackQuery, state: FSMContext):
    """Пропуск редактирования фото"""
    await callback.answer()
    await state.clear()

    products = await get_all_products()
    if products:
        await state.update_data(
            admin_products=products,
            admin_page=0,
            admin_last_photo_message_id=None,
        )
        await show_admin_product(callback.message, state, 0)
    else:
        await callback.message.edit_text("✅ Редактирование фото отменено.")
        await admin_products_menu(callback, state)


@router.callback_query(F.data == "edit_photo_cancel", IsAdmin())
async def edit_photo_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена редактирования фото - возврат к редактированию товара"""
    await callback.answer()

    data = await state.get_data()
    product_id = data.get("editing_product_id")

    if product_id:
        await state.set_state(AdminProductState.editing_field)
        product = await get_product_by_id(product_id)

        if product:
            text = (
                f"✏️ <b>Редактирование товара</b>\n"
                f"━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 ID: <code>{product[0]}</code>\n"
                f"📌 <b>Название:</b> {escape_html(product[1])}\n"
                f"📝 <b>Описание:</b> {escape_html(product[2][:50] + ('...' if len(product[2]) > 50 else ''))}\n"
                f"💰 <b>Цена:</b> {product[3]} ₽\n"
                f"🏷️ <b>Категория:</b> {escape_html(product[4])}\n"
                f"📦 <b>В наличии:</b> {product[5]} шт.\n"
                f"📷 <b>Фото:</b> {'✅ есть' if product[7] else '❌ нет'}\n\n"
                f"Выберите поле для изменения:"
            )

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📝 Название", callback_data="edit_field_name")],
                    [InlineKeyboardButton(text="📝 Описание", callback_data="edit_field_description")],
                    [InlineKeyboardButton(text="💰 Цена", callback_data="edit_field_price")],
                    [InlineKeyboardButton(text="🏷️ Категория", callback_data="edit_field_category")],
                    [InlineKeyboardButton(text="📦 Количество", callback_data="edit_field_quantity")],
                    [InlineKeyboardButton(text="📷 Изменить фото", callback_data="edit_field_photo")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="product_edit")],
                ]
            )

            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            return

    await admin_products_menu(callback, state)



@router.message(StateFilter(AdminProductEditState.photo), F.photo)
async def edit_photo_process(message: Message, state: FSMContext):
    """Обновление фото товара"""
    data = await state.get_data()
    product_id = data.get("editing_product_id")
    if not product_id:
        await message.answer("❌ Ошибка: товар не найден.")
        await state.clear()
        return
    image_file_id = message.photo[-1].file_id
    try:
        await update_product_image(product_id, image_file_id)
        await state.clear()
        await message.answer("✅ <b>Фото товара обновлено!</b>", parse_mode=ParseMode.HTML)
        products = await get_all_products()
        if products:
            await state.update_data(admin_products=products, admin_page=0, admin_last_photo_message_id=None)
            await show_admin_product(message, state, 0)
        else:
            await admin_products_menu(message, state)
    except Exception as e:
        logger.error(f"Error updating product photo: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обновлении фото. Попробуйте позже.", parse_mode=ParseMode.HTML)


@router.message(StateFilter(AdminProductEditState.photo))
async def edit_photo_invalid(message: Message, state: FSMContext):
    """Обработка не-фото в состоянии редактирования фото"""
    await message.answer(
        "❌ Пожалуйста, отправьте <b>фото</b> для товара.\n"
        "Или нажмите кнопку «Пропустить», чтобы оставить текущее фото.",
        parse_mode=ParseMode.HTML,
    )


# ==================== РЕДАКТИРОВАНИЕ ПОЛЕЙ ====================
@router.callback_query(
    StateFilter(AdminProductState.editing_field),
    F.data.startswith("edit_field_"),
    IsAdmin(),
)
async def product_edit_field(callback: CallbackQuery, state: FSMContext):
    """Выбор поля для редактирования"""
    field = callback.data.split("_")[2]
    field_names = {
        "name": "название",
        "description": "описание",
        "price": "цену",
        "category": "категорию",
        "quantity": "количество",
    }

    await state.update_data(editing_field=field)
    await state.set_state(AdminProductState.editing_value)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="product_edit")]
        ]
    )

    await callback.message.edit_text(
        f"✏️ Введите новое <b>{field_names.get(field, field)}</b>:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.message(StateFilter(AdminProductState.editing_value), F.text)
async def product_edit_value(message: Message, state: FSMContext):
    """Ввод нового значения"""
    data = await state.get_data()
    product_id = data.get("editing_product_id")
    field = data.get("editing_field")

    if not product_id or not field:
        await message.answer("❌ Ошибка. Попробуйте снова.")
        await state.clear()
        return

    value = message.text.strip()
    product = await get_product_by_id(product_id)

    if not product:
        await message.answer("❌ Товар не найден.")
        await state.clear()
        return

    try:
        current_image = product[7] if product and len(product) > 7 else None

        update_data = {
            "name": product[1],
            "description": product[2],
            "price": product[3],
            "category": product[4],
            "quantity": product[5],
            "ozon_url": product[6],
            "image_file_id": current_image,
        }

        if field == "price":
            if not value.isdigit() or int(value) < 1:
                await message.answer("❌ Введите корректную цену (только цифры, больше 0).")
                return
            update_data["price"] = int(value)
        elif field == "quantity":
            if not value.isdigit():
                await message.answer("❌ Введите корректное количество (только цифры).")
                return
            update_data["quantity"] = int(value)
        elif field == "name":
            if len(value) < 2:
                await message.answer("❌ Название слишком короткое.")
                return
            update_data["name"] = value
        elif field == "description":
            if len(value) < 3:
                await message.answer("❌ Описание слишком короткое.")
                return
            update_data["description"] = value
        elif field == "category":
            if len(value) < 2:
                await message.answer("❌ Категория слишком короткая.")
                return
            update_data["category"] = value

        await update_product(
            product_id=product_id,
            name=update_data["name"],
            description=update_data["description"],
            price=update_data["price"],
            category=update_data["category"],
            quantity=update_data["quantity"],
            ozon_url=update_data["ozon_url"],
            image_file_id=update_data["image_file_id"],
        )

        await message.answer(
            f"✅ <b>Товар обновлён!</b>\n\n"
            f"🔹 <b>{escape_html(update_data['name'])}</b>\n"
            f"💰 {update_data['price']} ₽\n"
            f"🏷️ {escape_html(update_data['category'])}\n"
            f"📦 В наличии: {update_data['quantity']} шт.",
            parse_mode=ParseMode.HTML,
        )

        await state.clear()
        await state.set_state(AdminProductState.selecting_action)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📦 Продолжить управление", callback_data="admin_products")],
                [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_back_to_panel")],
            ]
        )
        await message.answer(
            "Выберите дальнейшее действие:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )

    except Exception as e:
        logger.error(f"Error updating product: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обновлении товара. Попробуйте позже.")


# ==================== УДАЛЕНИЕ ТОВАРА ====================
@router.callback_query(F.data == "product_delete", IsAdmin())
async def product_delete_start(callback: CallbackQuery, state: FSMContext):
    """Начать удаление товара"""
    products = await get_all_products()

    if not products:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")]
            ]
        )
        await callback.message.edit_text(
            "📭 Нет товаров для удаления.",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for product in products:
        keyboard.inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"🗑️ {escape_html(product[1])} (ID: {product[0]})",
                    callback_data=f"delete_confirm_{product[0]}",
                )
            ]
        )
    keyboard.inline_keyboard.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")]
    )

    await callback.message.edit_text(
        "🗑️ <b>Удаление товара</b>\n\n"
        "Выберите товар для удаления:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_confirm_"), IsAdmin())
async def product_delete_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления товара"""
    product_id = int(callback.data.split("_")[2])
    product = await get_product_by_id(product_id)

    if not product:
        await callback.message.edit_text("❌ Товар не найден.")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_yes_{product_id}")],
            [InlineKeyboardButton(text="❌ Нет, отменить", callback_data="product_delete")],
        ]
    )

    text = (
        f"🗑️ <b>Подтвердите удаление</b>\n\n"
        f"🔹 <b>{escape_html(product[1])}</b>\n"
        f"💰 {product[3]} ₽\n"
        f"🏷️ {escape_html(product[4])}\n"
        f"📦 В наличии: {product[5]} шт.\n\n"
        f"Вы уверены, что хотите удалить этот товар?"
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    await callback.answer()


@router.callback_query(F.data.startswith("delete_yes_"), IsAdmin())
async def product_delete_yes(callback: CallbackQuery, state: FSMContext):
    """Удаление товара с проверкой на активные заказы"""
    product_id = int(callback.data.split("_")[2])

    result = await delete_product(product_id)

    if not result["success"]:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="product_delete")]
            ]
        )
        await callback.message.edit_text(
            f"❌ {result['message']}",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"✅ <b>Товар удалён!</b>\n\n"
        f"Товар с ID <code>{product_id}</code> успешно удалён.",
        parse_mode=ParseMode.HTML,
    )

    await state.clear()
    await state.set_state(AdminProductState.selecting_action)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Продолжить управление", callback_data="admin_products")],
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_back_to_panel")],
        ]
    )
    await callback.message.answer(
        "Выберите дальнейшее действие:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )

    await callback.answer()


# ==================== СПИСОК УДАЛЁННЫХ ТОВАРОВ ====================
@router.callback_query(F.data == "deleted_products_list", IsAdmin())
async def deleted_products_list(callback: CallbackQuery, state: FSMContext):
    """Показать список удалённых (is_active=0) товаров"""
    products = await get_deleted_products()

    if not products:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")]
            ]
        )
        await callback.message.edit_text(
            "📭 Нет удалённых товаров.",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return

    await state.update_data(
        deleted_products=products,
        deleted_page=0,
        deleted_last_photo_message_id=None,
    )
    await show_deleted_product(callback.message, state, 0)
    await callback.answer()


async def show_deleted_product(message: Message, state: FSMContext, page: int):
    """Показать один удалённый товар с возможностью восстановления"""
    data = await state.get_data()
    products = data.get("deleted_products", [])
    last_photo_message_id = data.get("deleted_last_photo_message_id")

    if not products or page >= len(products):
        await message.answer("❌ Товары не найдены.")
        return

    product = products[page]
    total = len(products)

    quantity = product[5]
    text = (
        f"🗑 <b>Удалённый товар {page + 1} из {total}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{product[0]}</code>\n"
        f"📌 Название: <b>{escape_html(product[1])}</b>\n"
        f"📝 Описание: {escape_html(product[2][:100] + ('...' if len(product[2]) > 100 else ''))}\n"
        f"💰 Цена: {product[3]} ₽\n"
        f"🏷️ Категория: {escape_html(product[4])}\n"
        f"📦 В наличии: {quantity} шт.\n"
        f"📷 Фото: {'✅ есть' if product[7] else '❌ нет'}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Этот товар скрыт из каталога."
    )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"deleted_page_{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="deleted_page_info"))
    if page < total - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"deleted_page_{page + 1}"))

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            nav_buttons if nav_buttons else [],
            [InlineKeyboardButton(text="♻️ Восстановить", callback_data=f"restore_confirm_{product[0]}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")],
        ]
    )

    # Если есть фото — используем edit_message_media
    if product[7]:
        try:
            if last_photo_message_id:
                await message.bot.edit_message_media(
                    chat_id=message.chat.id,
                    message_id=last_photo_message_id,
                    media=InputMediaPhoto(
                        media=product[7],
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=keyboard,
                )
                return
            else:
                photo_msg = await message.answer_photo(
                    photo=product[7],
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
                await state.update_data(deleted_last_photo_message_id=photo_msg.message_id)
                try:
                    await message.delete()
                except Exception:
                    pass
                return
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                return
            logger.warning(f"Error editing/sending deleted product photo: {e}, fallback to new message")
            photo_msg = await message.answer_photo(
                photo=product[7],
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            await state.update_data(deleted_last_photo_message_id=photo_msg.message_id)
            try:
                await message.delete()
            except Exception:
                pass
            return

    # Если фото нет — текстовый вариант
    if last_photo_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_photo_message_id)
        except Exception:
            pass
        await state.update_data(deleted_last_photo_message_id=None)

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("deleted_page_"), IsAdmin())
async def deleted_page_callback(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы в списке удалённых товаров"""
    page = int(callback.data.split("_")[2])
    await show_deleted_product(callback.message, state, page)
    await callback.answer()


@router.callback_query(F.data == "deleted_page_info", IsAdmin())
async def deleted_page_info(callback: CallbackQuery):
    """Информация о странице удалённых товаров"""
    await callback.answer("Страница удалённых товаров", show_alert=True)


@router.callback_query(F.data.startswith("restore_confirm_"), IsAdmin())
async def restore_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение восстановления товара"""
    product_id = int(callback.data.split("_")[2])
    product = await get_product_by_id(product_id)

    if not product:
        await callback.message.edit_text("❌ Товар не найден.")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, восстановить", callback_data=f"restore_yes_{product_id}")],
            [InlineKeyboardButton(text="❌ Нет, отменить", callback_data="deleted_products_list")],
        ]
    )

    text = (
        f"♻️ <b>Восстановление товара</b>\n\n"
        f"🔹 <b>{escape_html(product[1])}</b>\n"
        f"💰 {product[3]} ₽\n"
        f"🏷️ {escape_html(product[4])}\n"
        f"📦 В наличии: {product[5]} шт.\n\n"
        f"Вы уверены, что хотите восстановить этот товар в каталоге?"
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    await callback.answer()


@router.callback_query(F.data.startswith("restore_yes_"), IsAdmin())
async def restore_yes(callback: CallbackQuery, state: FSMContext):
    """Восстановление товара"""
    product_id = int(callback.data.split("_")[2])

    success = await restore_product(product_id)

    if success:
        await callback.message.edit_text(
            f"✅ <b>Товар восстановлен!</b>\n\n"
            f"Товар с ID <code>{product_id}</code> снова доступен в каталоге.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка при восстановлении товара.",
            parse_mode=ParseMode.HTML,
        )

    await state.clear()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Продолжить управление", callback_data="admin_products")],
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_back_to_panel")],
        ]
    )
    await callback.message.answer(
        "Выберите дальнейшее действие:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )

    await callback.answer()