# ==================== ИМПОРТЫ ====================
import logging
from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from db import (
    check_and_notify_low_stock,
    create_order_and_decrease_stock,
    escape_html,
    get_product_by_id,
    get_product_stock,
    get_user_by_telegram_id,
    LOW_STOCK_THRESHOLD,
)
from forms.users import OrderState

# ==================== НАСТРОЙКА ====================
logger = logging.getLogger(__name__)
router = Router()


# ==================== ОФОРМЛЕНИЕ ЗАКАЗА (FSM) ====================
@router.callback_query(F.data.startswith("order_product_"))
async def order_product_callback(callback: CallbackQuery, state: FSMContext):
    """Выбор товара для заказа"""
    user_id = callback.from_user.id
    user = await get_user_by_telegram_id(user_id)
    if not user:
        try:
            await callback.message.edit_text(
                "❌ Вы не зарегистрированы!\n\n"
                "Пожалуйста, сначала пройдите регистрацию через /register,\n"
                "а затем оформите заказ заново.",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"order_product_callback edit failed: {e}, sending new")
            await callback.message.answer(
                "❌ Вы не зарегистрированы!\n\n"
                "Пожалуйста, сначала пройдите регистрацию через /register,\n"
                "а затем оформите заказ заново.",
                parse_mode=ParseMode.HTML,
            )
        await callback.answer()
        return

    product_id = int(callback.data.split("_")[2])
    product = await get_product_by_id(product_id)
    if not product:
        try:
            await callback.message.edit_text("❌ Товар не найден.")
        except Exception as e:
            logger.warning(f"order_product_callback edit failed: {e}, sending new")
            await callback.message.answer("❌ Товар не найден.")
        await callback.answer()
        return

    await state.update_data(product_id=product_id, quantity=1)
    await state.set_state(OrderState.quantity)
    await show_quantity_selector(callback.message, state)
    await callback.answer()


async def show_quantity_selector(message: Message, state: FSMContext):
    """Показать счётчик количества"""
    data = await state.get_data()
    quantity = data.get("quantity", 1)
    product_id = data.get("product_id")
    product = await get_product_by_id(product_id)
    current_stock = await get_product_stock(product_id)

    text = (
        f"🔹 <b>{escape_html(product[1])}</b>\n"
        f"💰 {product[3]} ₽\n"
        f"📦 Доступно: <b>{current_stock}</b> шт.\n\n"
        f"📦 <b>Количество:</b> {quantity} шт."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➖", callback_data="qty_minus"),
                InlineKeyboardButton(text=f"{quantity}", callback_data="qty_display"),
                InlineKeyboardButton(text="➕", callback_data="qty_plus"),
            ],
            [
                InlineKeyboardButton(text="✅ Далее", callback_data="qty_confirm"),
                InlineKeyboardButton(text="⬅️ Отмена", callback_data="order_cancel"),
            ],
        ]
    )

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"show_quantity_selector edit failed: {e}, sending new")
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("qty_"))
async def quantity_control(callback: CallbackQuery, state: FSMContext):
    """Управление количеством: ➖, ➕, ✅ Далее"""
    action = callback.data
    data = await state.get_data()
    quantity = data.get("quantity", 1)
    product_id = data.get("product_id")

    if action == "qty_minus":
        quantity = max(1, quantity - 1)
        await state.update_data(quantity=quantity)
        await show_quantity_selector(callback.message, state)

    elif action == "qty_back":
        await show_quantity_selector(callback.message, state)

    elif action == "qty_plus":
        if quantity >= 99:
            await callback.answer("❌ Максимум 99 шт.", show_alert=True)
            return
        quantity += 1
        await state.update_data(quantity=quantity)
        await show_quantity_selector(callback.message, state)

    elif action == "qty_display":
        await callback.answer(f"Количество: {quantity} шт.", show_alert=True)

    elif action == "qty_confirm":
        if quantity < 1:
            await callback.answer("❌ Минимум 1 шт.", show_alert=True)
            return

        current_stock = await get_product_stock(product_id)

        if current_stock < quantity:
            product = await get_product_by_id(product_id)
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад к выбору количества", callback_data="qty_back")]
                ]
            )
            try:
                await callback.message.edit_text(
                    f"❌ <b>Недостаточно товара на складе!</b>\n\n"
                    f"📦 Товар: {escape_html(product[1])}\n"
                    f"📦 Доступно: <b>{current_stock}</b> шт.\n"
                    f"🛒 Запрошено: <b>{quantity}</b> шт.\n\n"
                    f"Пожалуйста, уменьшите количество или выберите другой товар.",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.warning(f"qty_confirm edit error: {e}")
                await callback.message.answer(
                    f"❌ <b>Недостаточно товара на складе!</b>\n\n"
                    f"📦 Товар: {escape_html(product[1])}\n"
                    f"📦 Доступно: <b>{current_stock}</b> шт.\n"
                    f"🛒 Запрошено: <b>{quantity}</b> шт.\n\n"
                    f"Пожалуйста, уменьшите количество или выберите другой товар.",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
            await callback.answer()
            return

        await state.update_data(quantity=quantity)
        await ask_delivery_method(callback.message, state)

    await callback.answer()


async def ask_delivery_method(message: Message, state: FSMContext):
    """Спросить способ доставки с подробным описанием"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📮 Почта России", callback_data="delivery_post")],
            [InlineKeyboardButton(text="🚚 СДЭК", callback_data="delivery_cdek")],
            [InlineKeyboardButton(text="🚚 Яндекс Доставка", callback_data="delivery_yandex")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="order_cancel")],
        ]
    )

    text = (
        "🚚 <b>Выберите способ доставки:</b>\n\n"
        "📮 <b>Почта России</b> — доступна по всей стране.\n"
        "• Отправка по номеру телефона (нужно согласие получателя).\n"
        "• Получение по паспорту или СМС-коду в отделении.\n"
        "• Срок хранения — 15 дней.\n"
        "Срок: 5–14 дней.\n"
        '<a href="https://www.pochta.ru/support">📄 Подробнее о правилах</a>\n\n'
        "🚚 <b>СДЭК</b> — быстрая доставка по городам.\n"
        "• Получение в пункте выдачи по паспорту или СДЭК ID.\n"
        "• Рекомендуем проверять товар при получении.\n"
        "Срок: 2–5 рабочих дней.\n"
        '<a href="https://www.cdek.ru/ru/faq/">📄 Подробнее о правилах</a>\n\n'
        "🚚 <b>Яндекс Доставка</b> — курьерская доставка до двери.\n"
        "• Курьер приедет по указанному адресу.\n"
        "• Отслеживание статуса доставки в реальном времени.\n"
        "• Быстрая и надёжная доставка по городам России.\n"
        "Срок: 1–3 дня.\n"
        '<a href="https://yandex.ru/delivery">📄 Подробнее о правилах</a>'
    )

    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"ask_delivery_method edit failed: {e}, sending new")
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    await state.set_state(OrderState.delivery_method)


@router.callback_query(F.data.startswith("delivery_"))
async def order_delivery(callback: CallbackQuery, state: FSMContext):
    """Выбор способа доставки"""
    method = callback.data.split("_")[1]
    method_names = {
        "post": "Почта России",
        "cdek": "СДЭК",
        "yandex": "Яндекс Доставка",
    }

    # Ссылки на карты ПВЗ только для Почты и СДЭК
    map_links = {
        "post": "https://yandex.ru/maps/?text=Почта%20России&mode=search",
        "cdek": "https://yandex.ru/maps/?text=CDEK&mode=search",
        # Яндекс Доставка — курьер, карта не нужна
    }

    address_examples = {
        "post": "г. Уткинск, ул. Охотничья, д. 7, индекс 123456",
        "cdek": "г. Уткинск, ул. Свистковая, д. 5, ПВЗ СДЭК",
        "yandex": "г. Уткинск, ул. Охотничья, д. 7, кв. 12",
    }

    address_prompts = {
        "post": "Укажите полный адрес с почтовым индексом.",
        "cdek": "Укажите адрес пункта выдачи СДЭК.",
        "yandex": "Укажите полный адрес для курьерской доставки (улица, дом, квартира, подъезд).",
    }

    delivery_method = method_names.get(method, method)
    await state.update_data(delivery_method=delivery_method)
    await state.set_state(OrderState.address)

    # Формируем клавиатуру: кнопка с картой только для Почты и СДЭК
    keyboard_buttons = []
    if method in map_links:
        keyboard_buttons.append(
            [InlineKeyboardButton(text="🗺️ Посмотреть пункты выдачи на карте", url=map_links[method])]
        )
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="order_cancel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    example_address = address_examples.get(method, "")
    prompt = address_prompts.get(method, "")

    # Текст сообщения
    text = (
        f"📍 <b>Укажите адрес доставки</b>\n\n"
        f"Вы выбрали: <b>{delivery_method}</b>\n\n"
        f"{prompt}\n\n"
    )

    if method != "yandex":
        text += "Чтобы найти ближайший пункт выдачи, нажмите на кнопку ниже.\n"
    text += "Затем укажите точный адрес в сообщении.\n\n"
    text += f"<i>Пример:</i>\n"
    text += f"<code>{example_address}</code>"

    try:
        sent_message = await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        await state.update_data(prompt_message_id=sent_message.message_id)
    except Exception as e:
        logger.warning(f"order_delivery edit failed: {e}, sending new")
        sent_message = await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        await state.update_data(prompt_message_id=sent_message.message_id)
    await callback.answer()


@router.message(StateFilter(OrderState.address), F.text)
async def order_address(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_telegram_id(user_id)
    if not user:
        await message.answer(
            "❌ Вы не зарегистрированы!\n\n"
            "Пожалуйста, сначала пройдите регистрацию через /register,\n"
            "а затем оформите заказ заново.",
            parse_mode=ParseMode.HTML,
        )
        await state.clear()
        return

    address = message.text.strip()
    if len(address) < 5:
        await message.answer("❌ Слишком короткий адрес. Введите полный адрес (минимум 5 символов):")
        return

    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except Exception:
            pass
        await state.update_data(prompt_message_id=None)

    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(delivery_address=address, user=user)
    await ask_comment(message, state)


async def ask_comment(message: Message, state: FSMContext):
    """Запрос комментария к заказу"""
    await state.set_state(OrderState.comment)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Пропустить", callback_data="comment_skip")]
        ]
    )

    text = (
        "📝 <b>Комментарий к заказу</b>\n\n"
        "Если у вас есть особые пожелания по доставке, "
        "времени, способу связи или что-то ещё — напишите здесь.\n\n"
        "Если ничего не нужно — нажмите «Пропустить»."
    )

    try:
        sent_msg = await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        await state.update_data(comment_message_id=sent_msg.message_id)
    except Exception:
        sent_msg = await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        await state.update_data(comment_message_id=sent_msg.message_id)


@router.callback_query(StateFilter(OrderState.comment), F.data == "comment_skip")
async def comment_skip(callback: CallbackQuery, state: FSMContext):
    """Пропустить комментарий"""
    await callback.answer()

    data = await state.get_data()
    comment_message_id = data.get("comment_message_id")
    if comment_message_id:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=comment_message_id)
        except Exception:
            pass

    await state.update_data(comment=None)
    # Передаём user_id явно — callback.message.from_user это бот, а не пользователь
    await create_order_from_state(callback.message, state, user_id=callback.from_user.id)


async def create_order_from_state(message: Message, state: FSMContext, user_id: int = None):
    """Создать заказ из данных в состоянии и отправить уведомление админу"""
    data = await state.get_data()
    user = data.get("user")
    if not user:
        await message.answer(
            "❌ Ошибка: пользователь не найден. Пожалуйста, зарегистрируйтесь через /register и попробуйте снова.",
            parse_mode=ParseMode.HTML,
        )
        await state.clear()
        return

    # Если user_id не передан явно — берём из message (для message-хэндлеров).
    # Для callback-хэндлеров user_id передаётся явно из callback.from_user.id,
    # потому что callback.message.from_user — это бот, а не пользователь.
    if user_id is None:
        user_id = message.from_user.id

    product_id = data.get("product_id")
    requested_quantity = data.get("quantity", 1)
    address = data.get("delivery_address")
    delivery_method = data.get("delivery_method")
    comment = data.get("comment")

    result = await create_order_and_decrease_stock(
        user_id=user_id,
        product_id=product_id,
        quantity=requested_quantity,
        delivery_method=delivery_method,
        delivery_address=address,
        comment=comment,
    )

    if not result["success"]:
        await message.answer(f"❌ {result['message']}", parse_mode=ParseMode.HTML)
        if "Недостаточно" in result["message"]:
            await state.set_state(OrderState.quantity)
            await show_quantity_selector(message, state)
        return

    await state.clear()

    try:
        await message.delete()
    except Exception:
        pass

    prompt_message_id = data.get("prompt_message_id")
    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except Exception as e:
            logger.warning(f"Failed to delete prompt message: {e}")

    try:
        product = await get_product_by_id(product_id)

        from handlers.admin import ADMIN_IDS

        admin_chat_id = ADMIN_IDS[0] if ADMIN_IDS else user_id

        new_stock = await get_product_stock(product_id)
        product_price = product[3] if product else 0
        total_price = requested_quantity * product_price

        admin_text = (
            f"🆕 <b>Новый заказ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>Клиент:</b> {escape_html(user[1])}\n"
            f"📞 <b>Телефон:</b> {escape_html(user[2])}\n"
            f"📧 <b>Email:</b> {escape_html(user[3] or 'не указан')}\n"
            f"🏙️ <b>Город:</b> {escape_html(user[4] or 'не указан')}\n"
            f"🛒 <b>Товар:</b> {escape_html(product[1])}\n"
            f"📦 <b>Количество:</b> {requested_quantity}\n"
            f"💰 <b>Цена за шт.:</b> {product_price} ₽\n"
            f"💵 <b>Сумма:</b> {total_price} ₽\n"
            f"🚚 <b>Доставка:</b> {delivery_method}\n"
            f"📍 <b>Адрес:</b> {escape_html(address)}\n"
        )
        if comment:
            admin_text += f"📝 <b>Комментарий:</b> {escape_html(comment)}\n"
        admin_text += f"📊 <b>Остаток на складе:</b> {new_stock} шт.\n"
        admin_text += f"━━━━━━━━━━━━━━━━━━━━━"

        await message.bot.send_message(chat_id=admin_chat_id, text=admin_text, parse_mode=ParseMode.HTML)

        if new_stock == 0:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✏️ Перейти к редактированию", callback_data=f"edit_select_{product_id}")],
                    [InlineKeyboardButton(text="📦 Управление товарами", callback_data="admin_products")],
                ]
            )
            await message.bot.send_message(
                chat_id=admin_chat_id,
                text=(
                    f"⚠️ <b>Товар закончился на складе!</b>\n\n"
                    f"📦 <b>Товар:</b> {escape_html(product[1])}\n"
                    f"🆔 ID: <code>{product_id}</code>\n\n"
                    f"Чтобы изменить количество, перейдите в редактирование товара."
                ),
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )

        if new_stock > 0 and new_stock <= LOW_STOCK_THRESHOLD:
            await check_and_notify_low_stock(
                product_id=product_id,
                product_name=product[1] if product else "товар",
                new_stock=new_stock,
                bot=message.bot,
                admin_chat_id=admin_chat_id,
            )

    except Exception as e:
        logger.error(f"Failed to send notification to admin: {e}", exc_info=True)

    await message.answer(
        "✅ <b>Заказ оформлен!</b>\n\n"
        "В ближайшее время с вами свяжется оператор для подтверждения.\n\n"
        "Проследить статус заказа можно в вашем профиле (/profile).\n\n"
        "🦆 <i>Приманивайте и будьте с Манией!</i>",
        parse_mode=ParseMode.HTML,
    )


@router.message(StateFilter(OrderState.comment), F.text)
async def process_comment(message: Message, state: FSMContext):
    comment = message.text.strip()
    if len(comment) > 500:
        await message.answer("❌ Комментарий слишком длинный. Максимум 500 символов.")
        return

    data = await state.get_data()
    comment_message_id = data.get("comment_message_id")
    if comment_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=comment_message_id)
        except Exception:
            pass

    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(comment=comment)
    # Передаём user_id явно — для консистентности с comment_skip
    await create_order_from_state(message, state, user_id=message.from_user.id)


@router.callback_query(F.data == "order_cancel")
async def order_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена заказа"""
    await state.clear()
    try:
        await callback.message.edit_text("❌ Заказ отменён.")
    except Exception as e:
        logger.warning(f"order_cancel edit failed: {e}")
        await callback.message.answer("❌ Заказ отменён.")
    await callback.answer()