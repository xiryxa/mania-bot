# ==================== ИМПОРТЫ ====================
import asyncio
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
from handlers.admin import render_admin_banner
from db import (
    add_product,
    delete_product,
    escape_html,
    get_all_products,
    get_deleted_products,
    get_product_by_id,
    restore_product,
    update_product,
    update_product_image,
    CAPTION_LIMIT,
    visible_len,
    truncate_plain
)
from filters import IsAdmin
from forms.users import AdminProductEditState, AdminProductState
from config import CATEGORY_MAP, ADMIN_NAV_BANNER_ID

# ==================== НАСТРОЙКА ====================
logger = logging.getLogger(__name__)
router = Router()


# ==================== ХЕЛПЕР: безопасное редактирование сообщения ====================
async def safe_edit(callback: CallbackQuery, text: str, keyboard=None, parse_mode: str = ParseMode.HTML):
    """
    Пытается отредактировать сообщение callback'а. Если не удалось (например,
    сообщение — фото), отправляет новое сообщение.
    """
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=parse_mode)
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode=parse_mode)


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

    await render_admin_banner(callback.message, "📦 <b>Управление товарами</b>\n\nВыберите действие:", keyboard)
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
        await safe_edit(callback, "📭 Товаров пока нет.", keyboard)
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

    if not products or page >= len(products):
        await message.answer("❌ Товары не найдены.")
        return

    product = products[page]
    total = len(products)

    quantity = product["quantity"]
    stock_status = f"📦 В наличии: {quantity} шт."

    # Безопасный caption: описание обрезается с учётом бюджета каркаса
    head = (
        f"📦 <b>Товар {page + 1} из {total}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{product['id']}</code>\n"
        f" Название: <b>{escape_html(product['name'])}</b>\n"
        f" Описание: "
    )
    tail = (
        f"\n💰 Цена: {product['price']} ₽\n"
        f"🏷️ Категория: {escape_html(product['category'])}\n"
        f"{stock_status}\n"
        f"📷 Фото: {'✅ есть' if product['image_file_id'] else '❌ нет'}"
    )

    budget = CAPTION_LIMIT - visible_len(head + tail) - 4
    text = head + escape_html(truncate_plain(product['description'], budget)) + tail

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"product_page_admin_{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="page_info_admin_"))
    if page < total - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"product_page_admin_{page + 1}"))

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            nav_buttons if nav_buttons else [],
            [
                InlineKeyboardButton(text="️✏️ Редактировать", callback_data=f"edit_select_{product['id']}_list_{page}"),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_confirm_{product['id']}_from_list_{page}"),
            ],
            [
                InlineKeyboardButton(text="📝 Текстовый список", callback_data="product_list_text"),
                InlineKeyboardButton(text="➕ Добавить", callback_data="product_add"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")],
        ]
    )

    # Если есть фото — используем edit_message_media
    if product['image_file_id']:
        try:
            # Сначала пытаемся отредактировать текущее сообщение
            await message.bot.edit_message_media(
                chat_id=message.chat.id,
                message_id=message.message_id,
                media=InputMediaPhoto(
                    media=product['image_file_id'],
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
            return
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                return
            # Если не удалось (например, сообщение текстовое), отправляем новое фото
            logger.warning(f"Error editing admin product photo: {e}, sending new")
            photo_msg = await message.answer_photo(
                photo=product['image_file_id'],
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

    # Если фото нет — используем баннер
    await render_admin_banner(message, text, keyboard)


@router.callback_query(F.data.startswith("product_page_admin_"), IsAdmin())
async def admin_product_page(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы в админ-списке товаров"""
    page = int(callback.data.split("_")[3])
    await show_admin_product(callback.message, state, page)
    await callback.answer()


@router.callback_query(F.data == "page_info_admin_", IsAdmin())
async def page_info_admin(callback: CallbackQuery):
    """Информация о странице"""
    await callback.answer("Страница товара", show_alert=True)


@router.callback_query(F.data == "product_list_text", IsAdmin())
async def product_list_text(callback: CallbackQuery, state: FSMContext):
    """Показать текстовый список всех товаров с пагинацией"""
    data = await state.get_data()
    products = data.get("admin_products", [])

    if not products:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="product_list")],
            ]
        )
        await render_admin_banner(callback.message, "📭 Товаров нет.", keyboard)
        await callback.answer()
        return

    # Инициализируем страницу текстового списка
    await state.update_data(admin_text_page=0)
    await show_admin_product_text(callback.message, state, 0)
    await callback.answer()

async def show_admin_product_text(message: Message, state: FSMContext, page: int):
    """Показать страницу текстового списка товаров (8 товаров на страницу)"""
    data = await state.get_data()
    products = data.get("admin_products", [])

    if not products:
        await message.answer("❌ Товары не найдены.")
        return

    items_per_page = 8
    total_pages = (len(products) + items_per_page - 1) // items_per_page

    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(products))
    page_products = products[start_idx:end_idx]

    text = f" <b>Список товаров (стр. {page + 1} из {total_pages})</b>\n"
    text += "━━━━━━━━━━━━━━━━━\n\n"

    for product in page_products:
        quantity = product["quantity"]
        text += (
            f" <b>{escape_html(product['name'])}</b>\n"
            f"   🆔 ID: <code>{product['id']}</code>\n"
            f"   🏷️ {escape_html(product['category'])} | 💰 {product['price']} ₽\n"
            f"    В наличии: {quantity} шт.\n"
            f"   📷 {'🖼️ есть' if product['image_file_id'] else '❌ нет'}\n"
            f"   ─────────────\n"
        )

    # Кнопки пагинации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"product_text_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"product_text_page_{page + 1}"))

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            nav_buttons if nav_buttons else [],
            [InlineKeyboardButton(text="🖼️ Вернуться к просмотру с фото", callback_data="product_list")],
        ]
    )

    await render_admin_banner(message, text, keyboard)

@router.callback_query(F.data.startswith("product_text_page_"), IsAdmin())
async def product_text_page_callback(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы текстового списка"""
    page = int(callback.data.split("_")[3])
    await show_admin_product_text(callback.message, state, page)
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

    text = (
        "📝 <b>Добавление товара</b>\n\n"
        "Введите <b>название</b> товара (манка):"
    )

    try:
        await callback.bot.edit_message_media(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            media=InputMediaPhoto(
                media=ADMIN_NAV_BANNER_ID,
                caption=text,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=keyboard,
        )
        add_bot_message_id = callback.message.message_id
    except Exception as e:
        error_text = str(e).lower()
        if "message is not modified" in error_text:
            add_bot_message_id = callback.message.message_id
        else:
            try:
                await callback.message.delete()
            except Exception:
                pass
            new_msg = await callback.message.answer_photo(
                photo=ADMIN_NAV_BANNER_ID,
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            add_bot_message_id = new_msg.message_id

    await state.update_data(add_bot_message_id=add_bot_message_id)
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

    text = "📝 Введите <b>описание</b> товара:"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")]]
    )

    await message.delete()
    await _update_add_flow_message(message.bot, message.chat.id, data.get("add_bot_message_id"), text, keyboard, state)
    await state.update_data(product_data=product_data)
    await state.set_state(AdminProductState.adding_description)


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

    text = "💰 Введите <b>цену</b> товара (в рублях, только цифры):"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")]]
    )

    await message.delete()
    await _update_add_flow_message(message.bot, message.chat.id, data.get("add_bot_message_id"), text, keyboard, state)
    await state.update_data(product_data=product_data)
    await state.set_state(AdminProductState.adding_price)


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

    text = "🏷️ <b>Выберите категорию товара:</b>"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🦆 Goose", callback_data="category_goose")],
            [InlineKeyboardButton(text="🦆 Duck", callback_data="category_duck")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")],
        ]
    )

    await message.delete()
    await _update_add_flow_message(message.bot, message.chat.id, data.get("add_bot_message_id"), text, keyboard, state)
    await state.update_data(product_data=product_data)
    await state.set_state(AdminProductState.adding_category)


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

    text = (
        "📸 <b>Добавьте фото товара</b>\n\n"
        "Отправьте фото или нажмите «Пропустить»:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Пропустить", callback_data="photo_skip")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")],
        ]
    )

    await message.delete()
    await _update_add_flow_message(message.bot, message.chat.id, data.get("add_bot_message_id"), text, keyboard, state)
    await state.update_data(product_data=product_data)
    await state.set_state(AdminProductState.adding_photo)


# Вспомогательная функция внутри файла (добавь её перед product_add_name или в начало файла после импортов)
async def _update_add_flow_message(bot, chat_id: int, msg_id: int, text: str, keyboard, state: FSMContext):
    """Редактирует сообщение добавления или создает новое, если старое удалено"""
    try:
        await bot.edit_message_media(
            chat_id=chat_id,
            message_id=msg_id,
            media=InputMediaPhoto(
                media=ADMIN_NAV_BANNER_ID,
                caption=text,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=keyboard,
        )
    except Exception:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
        new_msg = await bot.send_photo(
            chat_id=chat_id,
            photo=ADMIN_NAV_BANNER_ID,
            caption=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await state.update_data(add_bot_message_id=new_msg.message_id)


@router.callback_query(
    StateFilter(AdminProductState.adding_category),
    F.data.startswith("category_"),
    IsAdmin(),
)
async def product_add_category_callback(callback: CallbackQuery, state: FSMContext):
    """Выбор категории через callback"""
    key = callback.data.split("_")[1]
    category = CATEGORY_MAP.get(key, key)

    data = await state.get_data()
    product_data = data.get("product_data", {})
    product_data["category"] = category
    await state.update_data(product_data=product_data)
    await state.set_state(AdminProductState.adding_quantity)

    text = f"📦 Введите <b>количество</b> товара в наличии (цифрой):\n\n🏷️ Категория: {category}"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_products")]
        ]
    )

    msg_id = data.get("add_bot_message_id")
    try:
        await callback.bot.edit_message_media(
            chat_id=callback.message.chat.id,
            message_id=msg_id,
            media=InputMediaPhoto(
                media=ADMIN_NAV_BANNER_ID,
                caption=text,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=keyboard,
        )
    except Exception:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=msg_id)
        except Exception:
            pass
        new_msg = await callback.message.answer_photo(
            photo=ADMIN_NAV_BANNER_ID,
            caption=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await state.update_data(add_bot_message_id=new_msg.message_id)

    await callback.answer()


async def save_product(message: Message, state: FSMContext, callback: CallbackQuery = None):
    """Сохранить товар в БД"""
    data = await state.get_data()
    product_data = data.get("product_data", {})
    msg_id = data.get("add_bot_message_id")

    # Определяем chat_id и bot в зависимости от того, откуда вызвана функция
    chat_id = message.chat.id if message else callback.message.chat.id
    bot = message.bot if message else callback.bot

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

        # Показываем фото товара, если оно есть, иначе баннер
        photo_to_show = product_data.get("image_file_id") or ADMIN_NAV_BANNER_ID

        try:
            await bot.edit_message_media(
                chat_id=chat_id,
                message_id=msg_id,
                media=InputMediaPhoto(
                    media=photo_to_show,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
        except Exception:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_to_show,
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )

        await state.clear()
        await state.set_state(AdminProductState.selecting_action)

    except Exception as e:
        logger.error(f"Error adding product: {e}", exc_info=True)
        error_text = "❌ Ошибка при добавлении товара. Попробуйте позже."
        if callback:
            await callback.message.answer(error_text, parse_mode=ParseMode.HTML)
        else:
            await message.answer(error_text, parse_mode=ParseMode.HTML)




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

    try:
        await message.delete()
    except Exception:
        pass

    await save_product(message, state)


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
        await safe_edit(callback, "📭 Нет товаров для редактирования.", keyboard)
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for product in products:
        keyboard.inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {escape_html(product['name'])} (ID: {product['id']})",
                    callback_data=f"edit_select_{product['id']}",
                )
            ]
        )
    keyboard.inline_keyboard.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")]
    )

    await render_admin_banner(callback.message, "✏️ <b>Редактирование товара</b>\n\nВыберите товар для редактирования:", keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("edit_select_"), IsAdmin())
async def product_edit_select(callback: CallbackQuery, state: FSMContext):
    """Выбор товара для редактирования"""
    parts = callback.data.split("_")
    product_id = int(parts[2])

    if len(parts) > 3 and parts[3] == "list":
        return_callback = f"product_page_admin_{parts[4]}"
    else:
        return_callback = "product_edit"

    product = await get_product_by_id(product_id)

    if not product:
        await safe_edit(callback, "❌ Товар не найден.")
        await callback.answer()
        return

    await state.update_data(
        editing_product_id=product_id,
        edit_return_callback=return_callback
    )
    await state.set_state(AdminProductState.editing_field)

    # Безопасный caption: описание обрезается с учётом бюджета каркаса
    head = (
        f"✏️ <b>Редактирование товара</b>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{product['id']}</code>\n"
        f"📌 <b>Название:</b> {escape_html(product['name'])}\n"
        f"📝 <b>Описание:</b> "
    )
    tail = (
        f"\n💰 <b>Цена:</b> {product['price']} ₽\n"
        f"🏷️ <b>Категория:</b> {escape_html(product['category'])}\n"
        f"📦 <b>В наличии:</b> {product['quantity']} шт.\n"
        f"📷 <b>Фото:</b> {'✅ есть' if product['image_file_id'] else '❌ нет'}\n\n"
        f"Выберите поле для изменения:"
    )

    budget = CAPTION_LIMIT - visible_len(head + tail) - 4
    text = head + escape_html(truncate_plain(product['description'], budget)) + tail

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Название", callback_data="edit_field_name")],
            [InlineKeyboardButton(text="📝 Описание", callback_data="edit_field_description")],
            [InlineKeyboardButton(text="💰 Цена", callback_data="edit_field_price")],
            [InlineKeyboardButton(text="🏷️ Категория", callback_data="edit_field_category")],
            [InlineKeyboardButton(text="📦 Количество", callback_data="edit_field_quantity")],
            [InlineKeyboardButton(text="📷 Изменить фото", callback_data="edit_field_photo")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=return_callback)],
        ]
    )

    # Если у товара есть фото — показываем его (паттерн из show_admin_product)
    if product['image_file_id']:
        try:
            await callback.message.bot.edit_message_media(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                media=InputMediaPhoto(
                    media=product['image_file_id'],
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
            await state.update_data(edit_bot_message_id=callback.message.message_id)
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                await callback.answer()
                return
            logger.warning(f"product_edit_select: edit_message_media failed: {e}, sending new photo")
            try:
                await callback.message.delete()
            except Exception:
                pass
            new_msg = await callback.message.answer_photo(
                photo=product['image_file_id'],
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            await state.update_data(edit_bot_message_id=new_msg.message_id)
    else:
        await render_admin_banner(callback.message, text, keyboard)
        await state.update_data(edit_bot_message_id=callback.message.message_id)

    await callback.answer()


# ==================== РЕДАКТИРОВАНИЕ ФОТО ====================
@router.callback_query(F.data == "edit_field_photo", IsAdmin())
async def edit_field_photo(callback: CallbackQuery, state: FSMContext):
    """Запрос нового фото"""
    await callback.answer()
    await state.set_state(AdminProductEditState.photo)

    data = await state.get_data()
    product_id = data.get("editing_product_id")
    product = await get_product_by_id(product_id)
    edit_bot_message_id = data.get("edit_bot_message_id")

    text = (
        "📷 <b>Редактирование фото</b>\n\n"
        "Отправьте новое фото для товара."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к редактированию", callback_data="edit_photo_back")]
        ]
    )

    if product and product['image_file_id'] and edit_bot_message_id:
        try:
            await callback.bot.edit_message_media(
                chat_id=callback.message.chat.id,
                message_id=edit_bot_message_id,
                media=InputMediaPhoto(
                    media=product['image_file_id'],
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                return
            logger.warning(f"edit_field_photo: edit_message_media failed: {e}, sending new photo")
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=edit_bot_message_id,
                )
            except Exception:
                pass
            new_msg = await callback.message.answer_photo(
                photo=product['image_file_id'],
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            await state.update_data(edit_bot_message_id=new_msg.message_id)
    else:
        await render_admin_banner(callback.message, text, keyboard)
        await state.update_data(edit_bot_message_id=callback.message.message_id)


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
        await safe_edit(callback, "✅ Редактирование фото отменено.")
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
                f"🆔 ID: <code>{product['id']}</code>\n"
                f"📌 <b>Название:</b> {escape_html(product['name'])}\n"
                f"📝 <b>Описание:</b> {escape_html(product['description'][:50] + ('...' if len(product['description']) > 50 else ''))}\n"
                f"💰 <b>Цена:</b> {product['price']} ₽\n"
                f"🏷️ <b>Категория:</b> {escape_html(product['category'])}\n"
                f"📦 <b>В наличии:</b> {product['quantity']} шт.\n"
                f"📷 <b>Фото:</b> {'✅ есть' if product['image_file_id'] else '❌ нет'}\n\n"
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

            await safe_edit(callback, text, keyboard)
            return

    await admin_products_menu(callback, state)


@router.message(StateFilter(AdminProductEditState.photo), F.photo)
async def edit_photo_process(message: Message, state: FSMContext):
    """Обновление фото товара"""
    data = await state.get_data()
    product_id = data.get("editing_product_id")
    edit_bot_message_id = data.get("edit_bot_message_id")

    if not product_id:
        await message.answer("❌ Ошибка: товар не найден.")
        await state.clear()
        return

    image_file_id = message.photo[-1].file_id

    try:
        await update_product_image(product_id, image_file_id)

        try:
            await message.delete()
        except Exception:
            pass

        await state.set_state(AdminProductState.editing_field)

        product = await get_product_by_id(product_id)

        head = (
            f"✏️ <b>Редактирование товара</b>\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 ID: <code>{product['id']}</code>\n"
            f"📌 <b>Название:</b> {escape_html(product['name'])}\n"
            f"📝 <b>Описание:</b> "
        )
        tail = (
            f"\n💰 <b>Цена:</b> {product['price']} ₽\n"
            f"🏷️ <b>Категория:</b> {escape_html(product['category'])}\n"
            f"📦 <b>В наличии:</b> {product['quantity']} шт.\n"
            f"📷 <b>Фото:</b> ✅ есть\n\n"
            f"Выберите поле для изменения:"
        )

        budget = CAPTION_LIMIT - visible_len(head + tail) - 4
        text = head + escape_html(truncate_plain(product['description'], budget)) + tail

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Название", callback_data="edit_field_name")],
                [InlineKeyboardButton(text="📝 Описание", callback_data="edit_field_description")],
                [InlineKeyboardButton(text="💰 Цена", callback_data="edit_field_price")],
                [InlineKeyboardButton(text="🏷️ Категория", callback_data="edit_field_category")],
                [InlineKeyboardButton(text="📦 Количество", callback_data="edit_field_quantity")],
                [InlineKeyboardButton(text="📷 Изменить фото", callback_data="edit_field_photo")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=data.get("edit_return_callback", "product_edit"))],
            ]
        )

        if edit_bot_message_id:
            try:
                await message.bot.edit_message_media(
                    chat_id=message.chat.id,
                    message_id=edit_bot_message_id,
                    media=InputMediaPhoto(
                        media=image_file_id,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=keyboard,
                )
            except Exception as e:
                error_text = str(e).lower()
                if "message is not modified" in error_text:
                    pass
                else:
                    logger.warning(f"edit_photo_process: edit_message_media failed: {e}, sending new photo")
                    try:
                        await message.bot.delete_message(
                            chat_id=message.chat.id,
                            message_id=edit_bot_message_id,
                        )
                    except Exception:
                        pass
                    new_msg = await message.answer_photo(
                        photo=image_file_id,
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML,
                    )
                    await state.update_data(edit_bot_message_id=new_msg.message_id)
        else:
            await render_admin_banner(message, text, keyboard)

        notification_msg = await message.answer("✅ Фото обновлено!")
        await asyncio.sleep(3)
        try:
            await notification_msg.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error updating product photo: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обновлении фото. Попробуйте позже.", parse_mode=ParseMode.HTML)


@router.callback_query(StateFilter(AdminProductEditState.photo), F.data == "edit_photo_back", IsAdmin())
async def edit_photo_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к редактированию товара из состояния изменения фото"""
    await callback.answer()

    data = await state.get_data()
    product_id = data.get("editing_product_id")
    edit_bot_message_id = data.get("edit_bot_message_id")
    return_callback = data.get("edit_return_callback", "product_edit")

    await state.set_state(AdminProductState.editing_field)

    product = await get_product_by_id(product_id)

    head = (
        f"✏️ <b>Редактирование товара</b>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{product['id']}</code>\n"
        f"📌 <b>Название:</b> {escape_html(product['name'])}\n"
        f"📝 <b>Описание:</b> "
    )
    tail = (
        f"\n💰 <b>Цена:</b> {product['price']} ₽\n"
        f"🏷️ <b>Категория:</b> {escape_html(product['category'])}\n"
        f"📦 <b>В наличии:</b> {product['quantity']} шт.\n"
        f"📷 <b>Фото:</b> {'✅ есть' if product['image_file_id'] else '❌ нет'}\n\n"
        f"Выберите поле для изменения:"
    )

    budget = CAPTION_LIMIT - visible_len(head + tail) - 4
    text = head + escape_html(truncate_plain(product['description'], budget)) + tail

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Название", callback_data="edit_field_name")],
            [InlineKeyboardButton(text="📝 Описание", callback_data="edit_field_description")],
            [InlineKeyboardButton(text="💰 Цена", callback_data="edit_field_price")],
            [InlineKeyboardButton(text="🏷️ Категория", callback_data="edit_field_category")],
            [InlineKeyboardButton(text="📦 Количество", callback_data="edit_field_quantity")],
            [InlineKeyboardButton(text="📷 Изменить фото", callback_data="edit_field_photo")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=return_callback)],
        ]
    )

    if product['image_file_id'] and edit_bot_message_id:
        try:
            await callback.bot.edit_message_media(
                chat_id=callback.message.chat.id,
                message_id=edit_bot_message_id,
                media=InputMediaPhoto(
                    media=product['image_file_id'],
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                return
            logger.warning(f"edit_photo_back: edit_message_media failed: {e}, sending new photo")
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=edit_bot_message_id,
                )
            except Exception:
                pass
            new_msg = await callback.message.answer_photo(
                photo=product['image_file_id'],
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            await state.update_data(edit_bot_message_id=new_msg.message_id)
    else:
        await render_admin_banner(callback.message, text, keyboard)
        await state.update_data(edit_bot_message_id=callback.message.message_id)


@router.message(StateFilter(AdminProductEditState.photo))
async def edit_photo_invalid(message: Message, state: FSMContext):
    """Обработка не-фото в состоянии редактирования фото"""
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(
        "❌ Пожалуйста, отправьте <u><b>фото</b></u> для товара.",
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

    data = await state.get_data()
    product_id = data.get("editing_product_id")
    product = await get_product_by_id(product_id) if product_id else None

    if field == "category":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🦆 Гусь", callback_data="edit_category_goose")],
                [InlineKeyboardButton(text="🦆 Утка", callback_data="edit_category_duck")],
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"edit_select_{product_id}")],
            ]
        )
        text = "🏷️ <b>Выберите новую категорию товара:</b>"
    else:
        field_names = {
            "name": "название",
            "description": "описание",
            "price": "цену",
            "quantity": "количество",
        }
        await state.update_data(editing_field=field)
        await state.set_state(AdminProductState.editing_value)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"edit_select_{product_id}")]
            ]
        )
        text = f"✏️ Введите новое <b>{field_names.get(field, field)}</b>:"

    if product and product['image_file_id']:
        try:
            await callback.bot.edit_message_media(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                media=InputMediaPhoto(
                    media=product['image_file_id'],
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
            await state.update_data(edit_bot_message_id=callback.message.message_id)
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                await callback.answer()
                return
            logger.warning(f"product_edit_field: edit_message_media failed: {e}, sending new photo")
            try:
                await callback.message.delete()
            except Exception:
                pass
            new_msg = await callback.message.answer_photo(
                photo=product['image_file_id'],
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            await state.update_data(edit_bot_message_id=new_msg.message_id)
    else:
        await render_admin_banner(callback.message, text, keyboard)
        await state.update_data(edit_bot_message_id=callback.message.message_id)

    await callback.answer()


@router.callback_query(
    StateFilter(AdminProductState.editing_field),
    F.data.startswith("edit_category_"),
    IsAdmin(),
)
async def product_edit_category_select(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора категории при редактировании через инлайн-кнопки"""
    key = callback.data.split("_")[2]
    new_category = CATEGORY_MAP.get(key, key)
    data = await state.get_data()
    product_id = data.get("editing_product_id")
    return_callback = data.get("edit_return_callback", "product_edit")
    if not product_id:
        await callback.answer("❌ Ошибка: товар не найден.")
        return
    product = await get_product_by_id(product_id)
    if not product:
        await callback.answer("❌ Товар не найден.")
        return
    try:
        await update_product(
            product_id=product_id,
            name=product['name'],
            description=product['description'],
            price=product['price'],
            category=new_category,
            quantity=product['quantity'],
            ozon_url=product['ozon_url'],
            image_file_id=product['image_file_id'],
        )
        await state.set_state(AdminProductState.editing_field)
        head = (
            f"✏️ <b>Редактирование товара</b>\n"
            f"━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 ID: <code>{product['id']}</code>\n"
            f"📌 <b>Название:</b> {escape_html(product['name'])}\n"
            f"📝 <b>Описание:</b> "
        )
        tail = (
            f"\n💰 <b>Цена:</b> {product['price']} ₽\n"
            f"🏷️ <b>Категория:</b> {escape_html(new_category)}\n"
            f"📦 <b>В наличии:</b> {product['quantity']} шт.\n"
            f"📷 <b>Фото:</b> {'✅ есть' if product['image_file_id'] else '❌ нет'}\n\n"
            f"Выберите поле для изменения:"
        )

        budget = CAPTION_LIMIT - visible_len(head + tail) - 4
        text = head + escape_html(truncate_plain(product['description'], budget)) + tail

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Название", callback_data="edit_field_name")],
                [InlineKeyboardButton(text="📝 Описание", callback_data="edit_field_description")],
                [InlineKeyboardButton(text="💰 Цена", callback_data="edit_field_price")],
                [InlineKeyboardButton(text="🏷️ Категория", callback_data="edit_field_category")],
                [InlineKeyboardButton(text="📦 Количество", callback_data="edit_field_quantity")],
                [InlineKeyboardButton(text="📷 Изменить фото", callback_data="edit_field_photo")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=return_callback)],
            ]
        )

        if product['image_file_id']:
            try:
                await callback.bot.edit_message_media(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    media=InputMediaPhoto(
                        media=product['image_file_id'],
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=keyboard,
                )
            except Exception as e:
                error_text = str(e).lower()
                if "message is not modified" in error_text:
                    await callback.answer("✅ Категория обновлена!")
                    return
                logger.warning(f"product_edit_category_select: edit_message_media failed: {e}, sending new photo")
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                await callback.message.answer_photo(
                    photo=product['image_file_id'],
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
        else:
            await render_admin_banner(callback.message, text, keyboard)
        await callback.answer("✅ Категория обновлена!")
    except Exception as e:
        logger.error(f"Error updating product category: {e}", exc_info=True)


@router.message(StateFilter(AdminProductState.editing_value), F.text)
async def product_edit_value(message: Message, state: FSMContext):
    """Ввод нового значения"""
    data = await state.get_data()
    product_id = data.get("editing_product_id")
    field = data.get("editing_field")
    edit_bot_message_id = data.get("edit_bot_message_id")

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
        current_image = product['image_file_id']

        update_data = {
            "name": product['name'],
            "description": product['description'],
            "price": product['price'],
            "category": product['category'],
            "quantity": product['quantity'],
            "ozon_url": product['ozon_url'],
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

        result = await update_product(
            product_id=product_id,
            name=update_data["name"],
            description=update_data["description"],
            price=update_data["price"],
            category=update_data["category"],
            quantity=update_data["quantity"],
            ozon_url=update_data["ozon_url"],
            image_file_id=update_data["image_file_id"],
        )

        try:
            await message.delete()
        except Exception:
            pass

        if result.get("success"):
            if result.get("restocked") and result.get("product_id"):
                from utils.notifications import notify_back_in_stock
                await notify_back_in_stock(result["product_id"], message.bot)

            await state.set_state(AdminProductState.editing_field)

            field_names = {
                "name": "Название",
                "description": "Описание",
                "price": "Цена",
                "quantity": "Количество",
                "category": "Категория",
            }
            field_ru = field_names.get(field, field)

            head = (
                f"✏️ <b>Редактирование товара</b>\n"
                f"━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 ID: <code>{product['id']}</code>\n"
                f"📌 <b>Название:</b> {escape_html(update_data['name'])}\n"
                f"📝 <b>Описание:</b> "
            )
            tail = (
                f"\n💰 <b>Цена:</b> {update_data['price']} ₽\n"
                f"🏷️ <b>Категория:</b> {escape_html(update_data['category'])}\n"
                f"📦 <b>В наличии:</b> {update_data['quantity']} шт.\n"
                f"📷 <b>Фото:</b> {'✅ есть' if current_image else '❌ нет'}\n\n"
                f"Выберите поле для изменения:"
            )

            budget = CAPTION_LIMIT - visible_len(head + tail) - 4
            text = head + escape_html(truncate_plain(update_data['description'], budget)) + tail

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📝 Название", callback_data="edit_field_name")],
                    [InlineKeyboardButton(text="📝 Описание", callback_data="edit_field_description")],
                    [InlineKeyboardButton(text="💰 Цена", callback_data="edit_field_price")],
                    [InlineKeyboardButton(text="🏷️ Категория", callback_data="edit_field_category")],
                    [InlineKeyboardButton(text="📦 Количество", callback_data="edit_field_quantity")],
                    [InlineKeyboardButton(text="📷 Изменить фото", callback_data="edit_field_photo")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"product_page_admin_{data.get('admin_page', 0)}" if data.get('edit_return_callback', '').startswith('product_page_admin_') else "product_edit")],
                ]
            )

            if edit_bot_message_id and current_image:
                try:
                    await message.bot.edit_message_media(
                        chat_id=message.chat.id,
                        message_id=edit_bot_message_id,
                        media=InputMediaPhoto(
                            media=current_image,
                            caption=text,
                            parse_mode=ParseMode.HTML,
                        ),
                        reply_markup=keyboard,
                    )
                except Exception as e:
                    error_text = str(e).lower()
                    if "message is not modified" in error_text:
                        pass
                    else:
                        logger.warning(f"product_edit_value: edit_message_media failed: {e}, sending new photo")
                        try:
                            await message.bot.delete_message(
                                chat_id=message.chat.id,
                                message_id=edit_bot_message_id,
                            )
                        except Exception:
                            pass
                        new_msg = await message.answer_photo(
                            photo=current_image,
                            caption=text,
                            reply_markup=keyboard,
                            parse_mode=ParseMode.HTML,
                        )
                        await state.update_data(edit_bot_message_id=new_msg.message_id)
            elif edit_bot_message_id:
                try:
                    await message.bot.edit_message_media(
                        chat_id=message.chat.id,
                        message_id=edit_bot_message_id,
                        media=InputMediaPhoto(
                            media=ADMIN_NAV_BANNER_ID,
                            caption=text,
                            parse_mode=ParseMode.HTML,
                        ),
                        reply_markup=keyboard,
                    )
                except Exception as e:
                    error_text = str(e).lower()
                    if "message is not modified" in error_text:
                        pass
                    else:
                        logger.warning(f"product_edit_value: edit_message_media (banner) failed: {e}, sending new")
                        try:
                            await message.bot.delete_message(
                                chat_id=message.chat.id,
                                message_id=edit_bot_message_id,
                            )
                        except Exception:
                            pass
                        new_msg = await message.answer_photo(
                            photo=ADMIN_NAV_BANNER_ID,
                            caption=text,
                            reply_markup=keyboard,
                            parse_mode=ParseMode.HTML,
                        )
                        await state.update_data(edit_bot_message_id=new_msg.message_id)
            else:
                await render_admin_banner(message, text, keyboard)

            notification_msg = await message.answer(f"✅ {field_ru} обновлено!")
            await asyncio.sleep(3)
            try:
                await notification_msg.delete()
            except Exception:
                pass
        else:
            await message.answer("❌ Ошибка при обновлении товара.")

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
        await safe_edit(callback, "📭 Нет товаров для удаления.", keyboard)
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for product in products:
        keyboard.inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"🗑️ {escape_html(product['name'])} (ID: {product['id']})",
                    callback_data=f"delete_confirm_{product['id']}",
                )
            ]
        )
    keyboard.inline_keyboard.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")]
    )

    await render_admin_banner(callback.message, "🗑️ <b>Удаление товара</b>\n\nВыберите товар для удаления:", keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("delete_confirm_"), IsAdmin())
async def product_delete_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления товара"""
    parts = callback.data.split("_")
    product_id = int(parts[2])

    # Определяем контекст возврата
    if len(parts) > 3 and parts[3] == "from" and parts[4] == "list":
        page = int(parts[5])
        return_callback = f"product_page_admin_{page}"
    else:
        return_callback = "product_delete"

    product = await get_product_by_id(product_id)

    if not product:
        await safe_edit(callback, "❌ Товар не найден.")
        await callback.answer()
        return

    # Сохраняем контекст возврата
    await state.update_data(delete_return_callback=return_callback)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_yes_{product_id}")],
            [InlineKeyboardButton(text="❌ Нет, отменить", callback_data=return_callback)],
        ]
    )

    text = (
        f"🗑️ <b>Подтвердите удаление</b>\n\n"
        f"🔹 <b>{escape_html(product['name'])}</b>\n"
        f"💰 {product['price']} ₽\n"
        f"🏷️ {escape_html(product['category'])}\n"
        f"📦 В наличии: {product['quantity']} шт.\n\n"
        f"Вы уверены, что хотите удалить этот товар?"
    )

    if product['image_file_id']:
        try:
            await callback.bot.edit_message_media(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                media=InputMediaPhoto(
                    media=product['image_file_id'],
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                await callback.answer()
                return
            logger.warning(f"product_delete_confirm: edit_message_media failed: {e}, sending new photo")
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer_photo(
                photo=product['image_file_id'],
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
    else:
        await render_admin_banner(callback.message, text, keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("delete_yes_"), IsAdmin())
async def product_delete_yes(callback: CallbackQuery, state: FSMContext):
    """Удаление товара с проверкой на активные заказы"""
    product_id = int(callback.data.split("_")[2])

    # Получаем данные товара до удаления
    product = await get_product_by_id(product_id)
    if not product:
        await callback.answer("❌ Товар не найден.", show_alert=True)
        return

    # Сохраняем данные для отображения после удаления
    product_name = product['name']
    product_price = product['price']
    product_category = product['category']
    product_image = product['image_file_id']

    # Получаем контекст возврата
    data = await state.get_data()
    return_callback = data.get("delete_return_callback", "admin_products")

    result = await delete_product(product_id)

    if not result["success"]:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="product_delete")]
            ]
        )
        await safe_edit(callback, f"❌ {result['message']}", keyboard)
        await callback.answer()
        return

    # Формируем текст результата
    text = (
        f"✅ <b>Товар удалён</b>\n\n"
        f"🆔 ID: <code>{product_id}</code>\n"
        f"🔹 <b>{escape_html(product_name)}</b>\n"
        f"💰 {product_price} ₽\n"
        f"🏷️ {escape_html(product_category)}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Продолжить управление", callback_data="admin_products")]
        ]
    )

    # Редактируем исходное сообщение подтверждения
    if product_image:
        try:
            await callback.bot.edit_message_media(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                media=InputMediaPhoto(
                    media=product_image,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                await callback.answer()
                return
            logger.warning(f"product_delete_yes: edit_message_media failed: {e}, sending new photo")
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer_photo(
                photo=product_image,
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
    else:
        await render_admin_banner(callback.message, text, keyboard)

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
        await render_admin_banner(callback.message, "📭 Нет удалённых товаров.", keyboard)
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

    if not products or page >= len(products):
        await message.answer("❌ Товары не найдены.")
        return

    product = products[page]
    total = len(products)

    # Добавляем логирование
    logger.info(f"show_deleted_product: page={page}, product_id={product['id']}, has_photo={bool(product['image_file_id'])}, photo_id={product['image_file_id'] if product['image_file_id'] else 'None'}")

    quantity = product['quantity']

    # Безопасный caption: описание обрезается с учётом бюджета каркаса
    head = (
        f"🗑 <b>Удалённый товар {page + 1} из {total}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{product['id']}</code>\n"
        f"📌 Название: <b>{escape_html(product['name'])}</b>\n"
        f"📝 Описание: "
    )
    tail = (
        f"\n💰 Цена: {product['price']} ₽\n"
        f"🏷️ Категория: {escape_html(product['category'])}\n"
        f"📦 В наличии: {quantity} шт.\n"
        f"📷 Фото: {'✅ есть' if product['image_file_id'] else '❌ нет'}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Этот товар скрыт из каталога."
    )

    budget = CAPTION_LIMIT - visible_len(head + tail) - 4
    text = head + escape_html(truncate_plain(product['description'], budget)) + tail

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"deleted_page_{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="deleted_info_btn"))
    if page < total - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"deleted_page_{page + 1}"))

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            nav_buttons if nav_buttons else [],
            [InlineKeyboardButton(text="♻️ Восстановить", callback_data=f"restore_confirm_{product['id']}_from_list_{page}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products")],
        ]
    )

    # Если есть фото — используем edit_message_media
    if product['image_file_id']:
        try:
            logger.info(f"show_deleted_product: пытаемся edit_message_media для product_id={product['id']}")
            await message.bot.edit_message_media(
                chat_id=message.chat.id,
                message_id=message.message_id,
                media=InputMediaPhoto(
                    media=product['image_file_id'],
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
            logger.info(f"show_deleted_product: edit_message_media успешно для product_id={product['id']}")
            return
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                return
            logger.warning(f"show_deleted_product: edit_message_media failed для product_id={product['id']}: {e}, sending new photo")
            photo_msg = await message.answer_photo(
                photo=product['image_file_id'],
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

    # Если фото нет — используем баннер с текстом
    logger.info(f"show_deleted_product: нет фото для product_id={product['id']}, показываем баннер с текстом")
    await render_admin_banner(message, text, keyboard)


@router.callback_query(F.data.startswith("deleted_page_"), IsAdmin())
async def deleted_page_callback(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы в списке удалённых товаров"""
    page = int(callback.data.split("_")[2])
    await show_deleted_product(callback.message, state, page)
    await callback.answer()


@router.callback_query(F.data == "deleted_info_btn", IsAdmin())
async def deleted_page_info(callback: CallbackQuery):
    """Информация о странице удалённых товаров"""
    await callback.answer("Страница удалённых товаров", show_alert=True)


@router.callback_query(F.data.startswith("restore_confirm_"), IsAdmin())
async def restore_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение восстановления товара"""
    parts = callback.data.split("_")
    product_id = int(parts[2])

    # Определяем контекст возврата
    if len(parts) > 3 and parts[3] == "from" and parts[4] == "list":
        page = int(parts[5])
        return_callback = f"deleted_page_{page}"
    else:
        return_callback = "deleted_products_list"

    product = await get_product_by_id(product_id)

    if not product:
        await safe_edit(callback, "❌ Товар не найден.")
        await callback.answer()
        return

    # Сохраняем контекст возврата
    await state.update_data(restore_return_callback=return_callback)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, восстановить", callback_data=f"restore_yes_{product_id}")],
            [InlineKeyboardButton(text="❌ Нет, отменить", callback_data=return_callback)],
        ]
    )

    text = (
        f"♻️ <b>Восстановление товара</b>\n\n"
        f"🔹 <b>{escape_html(product['name'])}</b>\n"
        f"💰 {product['price']} ₽\n"
        f"🏷️ {escape_html(product['category'])}\n"
        f"📦 В наличии: {product['quantity']} шт.\n\n"
        f"Вы уверены, что хотите восстановить этот товар в каталоге?"
    )

    if product['image_file_id']:
        try:
            await callback.bot.edit_message_media(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                media=InputMediaPhoto(
                    media=product['image_file_id'],
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=keyboard,
            )
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                await callback.answer()
                return
            logger.warning(f"restore_confirm: edit_message_media failed: {e}, sending new photo")
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer_photo(
                photo=product['image_file_id'],
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
    else:
        await render_admin_banner(callback.message, text, keyboard)

    await callback.answer()


@router.callback_query(F.data.startswith("restore_yes_"), IsAdmin())
async def restore_yes(callback: CallbackQuery, state: FSMContext):
    """Восстановление товара"""
    product_id = int(callback.data.split("_")[2])

    # Получаем данные товара до восстановления
    product = await get_product_by_id(product_id)
    if not product:
        await callback.answer("❌ Товар не найден.", show_alert=True)
        return

    product_name = product['name']
    product_category = product['category']
    product_image = product['image_file_id']

    success = await restore_product(product_id)

    if success:
        text = (
            f"✅ <b>Товар восстановлен</b>\n\n"
            f"🆔 ID: <code>{product_id}</code>\n"
            f"🔹 <b>{escape_html(product_name)}</b>\n"
            f"🏷️ {escape_html(product_category)}"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📦 Продолжить управление", callback_data="admin_products")]
            ]
        )

        # Редактируем исходное сообщение подтверждения
        if product_image:
            try:
                await callback.bot.edit_message_media(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    media=InputMediaPhoto(
                        media=product_image,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=keyboard,
                )
            except Exception as e:
                error_text = str(e).lower()
                if "message is not modified" in error_text:
                    await callback.answer()
                    return
                logger.warning(f"restore_yes: edit_message_media failed: {e}, sending new photo")
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                await callback.message.answer_photo(
                    photo=product_image,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
        else:
            await render_admin_banner(callback.message, text, keyboard)
    else:
        await safe_edit(callback, "❌ Ошибка при восстановлении товара.")

    await callback.answer()
