# ==================== ИМПОРТЫ ====================
import logging
from aiogram.types import InputMediaPhoto
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from db import escape_html, get_product_by_id, get_products_by_category
from config import CATEGORY_MAP

# ==================== НАСТРОЙКА ====================
logger = logging.getLogger(__name__)
router = Router()


# ==================== ГЛАВНОЕ МЕНЮ /shop ====================
@router.message(Command("shop"))
async def shop_main(message: Message):
    """Главное меню магазина (отправляет новое сообщение)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🦆 Манки", callback_data="shop_category_manks")],
            [InlineKeyboardButton(text="🛖 Засидки", callback_data="shop_category_zasadki")],
            [InlineKeyboardButton(text="👕 Аксессуары", callback_data="shop_category_accessories")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start")],
        ]
    )

    await message.answer(
        "🛒 <b>Добро пожаловать в MANIA!</b>\n\n"
        "Здесь вы можете заказать профессиональные манки для охоты на гуся и утку.\n\n"
        "Выберите категорию:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


# ==================== ВЫБОР КАТЕГОРИИ ====================
@router.callback_query(F.data == "shop_category_manks")
async def shop_manks_menu(callback: CallbackQuery):
    """Выбор типа манка: гусь или утка (редактирует сообщение)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🦢 Гусь", callback_data="shop_subcategory_goose")],
            [InlineKeyboardButton(text="🦆 Утка", callback_data="shop_subcategory_duck")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop_back_to_main")],
        ]
    )

    await callback.message.edit_text(
        "🦆 <b>Выберите тип манка:</b>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data == "shop_category_zasadki")
async def shop_zasadki(callback: CallbackQuery):
    """Засидки - временно недоступны (редактирует сообщение)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop_back_to_main")]
        ]
    )

    await callback.message.edit_text(
        "🛖 <b>Засидки</b>\n\n"
        "К сожалению, на данный момент товаров в этой категории нет.\n"
        "Следите за обновлениями!",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data == "shop_category_accessories")
async def shop_accessories(callback: CallbackQuery):
    """Аксессуары - временно недоступны (редактирует сообщение)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop_back_to_main")]
        ]
    )

    await callback.message.edit_text(
        "👕 <b>Аксессуары</b>\n\n"
        "Раздел аксессуаров скоро появится!\n"
        "Следите за обновлениями.",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


# ==================== СПИСОК ТОВАРОВ В ПОДКАТЕГОРИИ ====================
@router.callback_query(F.data.startswith("shop_subcategory_"))
async def shop_products_list(callback: CallbackQuery, state: FSMContext):
    """
    Показать список товаров в выбранной подкатегории (редактирует сообщение)
    """
    category = callback.data.split("_")[2]

    
    category_ru = CATEGORY_MAP.get(category, category)
    products = await get_products_by_category(category_ru)

    if not products:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop_manks_menu")]
            ]
        )
        await callback.message.edit_text(
            f"📭 Товаров в категории «{category_ru}» пока нет.",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return

    await state.update_data(
        shop_products=products,
        shop_page=0,
        shop_category=category_ru,
        shop_last_photo_message_id=None,
    )

    await show_product_card(callback.message, state, 0)
    await callback.answer()


# ==================== КАРТОЧКА ТОВАРА С ПАГИНАЦИЕЙ ====================
async def show_product_card(
    message: Message,
    state: FSMContext,
    page: int,
):
    """
    Отображение карточки товара с пагинацией
    """
    data = await state.get_data()
    products = data.get("shop_products", [])
    category = data.get("shop_category", "")
    last_photo_message_id = data.get("shop_last_photo_message_id")

    if not products or page >= len(products):
        await message.answer("❌ Товары не найдены.")
        return

    product = products[page]
    total = len(products)

    quantity = product.get("quantity", 0)
    stock_status = f"📦 В наличии: {quantity} шт." if quantity > 0 else "❌ Нет в наличии"

    text = (
        f"🦆 <b>{escape_html(product['name'])}</b>\n\n"
        f"💰 <b>Цена:</b> {product['price']} ₽\n"
        f"🏷️ <b>Категория:</b> {escape_html(product['category'])}\n\n"
        f"📝 {escape_html(product['description'])}\n\n"
        f"{stock_status}"
    )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"shop_product_page_{page - 1}",
            )
        )

    nav_buttons.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total}",
            callback_data="shop_page_info",
        )
    )

    if page < total - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"shop_product_page_{page + 1}",
            )
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            nav_buttons if nav_buttons else [],
            [
                InlineKeyboardButton(
                    text="📩 Заказать",
                    callback_data=f"order_product_{product['id']}",
                ),
                InlineKeyboardButton(
                    text="📋 Список",
                    callback_data="shop_show_list",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к выбору",
                    callback_data="shop_manks_menu",
                )
            ],
        ]
    )

    # Если есть фото — используем edit_message_media
    if product.get("image_file_id"):
        try:
            if last_photo_message_id:
                await message.bot.edit_message_media(
                    chat_id=message.chat.id,
                    message_id=last_photo_message_id,
                    media=InputMediaPhoto(
                        media=product["image_file_id"],
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    ),
                    reply_markup=keyboard,
                )
                return
            else:
                photo_msg = await message.answer_photo(
                    photo=product["image_file_id"],
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
                await state.update_data(shop_last_photo_message_id=photo_msg.message_id)
                try:
                    await message.delete()
                except Exception:
                    pass
                return
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                return
            logger.warning(f"Error editing/sending photo: {e}, fallback to new message")
            photo_msg = await message.answer_photo(
                photo=product["image_file_id"],
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            await state.update_data(shop_last_photo_message_id=photo_msg.message_id)
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
        await state.update_data(shop_last_photo_message_id=None)

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


# ==================== ПАГИНАЦИЯ ====================
@router.callback_query(F.data.startswith("shop_product_page_"))
async def shop_product_page(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы товара (редактирует сообщение)"""
    page = int(callback.data.split("_")[3])
    await show_product_card(callback.message, state, page)
    await callback.answer()


@router.callback_query(F.data == "shop_page_info")
async def shop_page_info(callback: CallbackQuery):
    """Информация о текущей странице"""
    await callback.answer("Страница товара", show_alert=True)


# ==================== СПИСОК ВСЕХ ТОВАРОВ ====================
@router.callback_query(F.data == "shop_show_list")
async def shop_show_list(callback: CallbackQuery, state: FSMContext):
    """Показать список всех товаров в категории (редактирует сообщение)"""
    data = await state.get_data()
    products = data.get("shop_products", [])
    category = data.get("shop_category", "")
    last_photo_message_id = data.get("shop_last_photo_message_id")

    if not products:
        await callback.message.edit_text("📭 Товаров нет.")
        await callback.answer()
        return

    text = f"📋 <b>Товары в категории «{category}»:</b>\n\n"
    for i, product in enumerate(products, 1):
        quantity = product.get("quantity", 0)
        stock = "✅" if quantity > 0 else "❌"
        text += f"{i}. {escape_html(product['name'])} — {product['price']} ₽ {stock} (в наличии: {quantity} шт.)\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к товарам", callback_data="shop_product_page_0")]
        ]
    )

    if last_photo_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=last_photo_message_id,
            )
            await state.update_data(shop_last_photo_message_id=None)
        except Exception:
            pass

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    await callback.answer()


# ==================== НАЗАД В ГЛАВНОЕ МЕНЮ ====================
@router.callback_query(F.data == "shop_back_to_main")
async def shop_back_to_main(callback: CallbackQuery, state: FSMContext = None):
    """Возврат в главное меню магазина из любой точки (редактирует сообщение)"""
    if state:
        data = await state.get_data()
        last_photo_message_id = data.get("shop_last_photo_message_id")

        if last_photo_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=last_photo_message_id,
                )
            except Exception:
                pass

        await state.clear()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🦆 Манки", callback_data="shop_category_manks")],
            [InlineKeyboardButton(text="🛖 Засидки", callback_data="shop_category_zasadki")],
            [InlineKeyboardButton(text="👕 Аксессуары", callback_data="shop_category_accessories")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start")],
        ]
    )

    try:
        await callback.message.edit_text(
            "🛒 <b>Добро пожаловать в MANIA!</b>\n\n"
            "Здесь вы можете заказать профессиональные манки для охоты на гуся и утку.\n\n"
            "Выберите категорию:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "🛒 <b>Добро пожаловать в MANIA!</b>\n\n"
            "Здесь вы можете заказать профессиональные манки для охоты на гуся и утку.\n\n"
            "Выберите категорию:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@router.callback_query(F.data == "shop_manks_menu")
async def shop_manks_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору типа манка (редактирует сообщение)"""
    data = await state.get_data()
    last_photo_message_id = data.get("shop_last_photo_message_id")

    if last_photo_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=last_photo_message_id,
            )
        except Exception:
            pass

    await state.clear()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🦢 Гусь", callback_data="shop_subcategory_goose")],
            [InlineKeyboardButton(text="🦆 Утка", callback_data="shop_subcategory_duck")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop_back_to_main")],
        ]
    )

    try:
        await callback.message.edit_text(
            "🦆 <b>Выберите тип манка:</b>",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "🦆 <b>Выберите тип манка:</b>",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()