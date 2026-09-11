# ==================== ИМПОРТЫ ====================
import html
import logging
from datetime import datetime, timezone

import aiosqlite
import pytz
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ==================== НАСТРОЙКА ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE = "users.sqlite"


# ==================== ИНИЦИАЛИЗАЦИЯ БД ====================
async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        # ---------- Таблица пользователей ----------
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                fullname TEXT,
                phone TEXT,
                email TEXT,
                city TEXT,
                address TEXT,
                username TEXT
            )
        """)

        # ---------- Таблица товаров ----------
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price INTEGER,
                category TEXT,
                quantity INTEGER DEFAULT 0,
                ozon_url TEXT,
                image_file_id TEXT,
                sort_order INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        """)

        # ---------- Таблица заказов ----------
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                quantity INTEGER DEFAULT 1,
                delivery_method TEXT,
                delivery_address TEXT,
                comment TEXT,
                tracking_number TEXT,
                status TEXT DEFAULT 'новый',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)

        # ---------- Миграции ----------
        cursor = await db.execute("PRAGMA table_info(products)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "is_active" not in column_names:
            await db.execute("ALTER TABLE products ADD COLUMN is_active INTEGER DEFAULT 1")
            logger.info("✅ Добавлено поле is_active в таблицу products")

        cursor = await db.execute("PRAGMA table_info(orders)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "tracking_number" not in column_names:
            await db.execute("ALTER TABLE orders ADD COLUMN tracking_number TEXT")
            logger.info("✅ Добавлено поле tracking_number в таблицу orders")

        if "unit_price" not in column_names:
            await db.execute("ALTER TABLE orders ADD COLUMN unit_price INTEGER")
            logger.info("✅ Добавлено поле unit_price в таблицу orders")

        cursor = await db.execute("PRAGMA table_info(products)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "low_stock_notified" not in column_names:
            await db.execute("ALTER TABLE products ADD COLUMN low_stock_notified INTEGER DEFAULT 0")
            logger.info("✅ Добавлено поле low_stock_notified в таблицу products")

        cursor = await db.execute("PRAGMA table_info(users)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "created_at" not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP")
            logger.info("✅ Добавлено поле created_at в таблицу users")

        await db.commit()
        logger.info("✅ База данных инициализирована/обновлена")


# ==================== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ====================
async def get_user_by_telegram_id(telegram_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id, fullname, phone, email, city, address, username, created_at "
            "FROM users WHERE id = ?",
            (telegram_id,),
        )
        return await cursor.fetchone()


async def add_user(
    telegram_id: int,
    fullname: str,
    phone: str,
    email: str,
    city: str,
    address: str = None,
    username: str = None,
    created_at: str = None,
):
    if created_at is None:
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "INSERT INTO users (id, fullname, phone, email, city, address, username, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (telegram_id, fullname, phone, email, city, address, username, created_at),
        )
        await db.commit()


async def update_user(
    telegram_id: int,
    fullname: str,
    phone: str,
    email: str,
    city: str,
    address: str = None,
    username: str = None,
):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "UPDATE users SET fullname = ?, phone = ?, email = ?, city = ?, address = ?, username = ? "
            "WHERE id = ?",
            (fullname, phone, email, city, address, username, telegram_id),
        )
        await db.commit()


async def get_users():
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id, fullname, phone, email, city, address, username, created_at "
            "FROM users ORDER BY id"
        )
        return await cursor.fetchall()


async def get_user_count():
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        result = await cursor.fetchone()
        return result[0] if result else 0


# ==================== РАБОТА С ТОВАРАМИ ====================
async def get_products():
    """Получить активные товары в наличии (quantity > 0)"""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT * FROM products WHERE quantity > 0 AND is_active = 1"
        )
        return await cursor.fetchall()


async def get_all_products():
    """Получить все активные товары"""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id, name, description, price, category, quantity, ozon_url, image_file_id "
            "FROM products WHERE is_active = 1 ORDER BY sort_order ASC, id ASC"
        )
        return await cursor.fetchall()


async def get_product_by_id(product_id: int):
    """Получить товар по ID"""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id, name, description, price, category, quantity, ozon_url, image_file_id "
            "FROM products WHERE id = ?",
            (product_id,),
        )
        return await cursor.fetchone()


async def get_product_stock(product_id: int) -> int:
    """Получить количество товара на складе"""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT quantity FROM products WHERE id = ?",
            (product_id,),
        )
        result = await cursor.fetchone()
        return result[0] if result else 0


async def decrease_product_stock(product_id: int, quantity: int) -> bool:
    """
    Уменьшить количество товара на складе.
    Атомарный UPDATE с проверкой остатка.
    Возвращает True, если списание прошло успешно.
    """
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "UPDATE products SET quantity = quantity - ? "
            "WHERE id = ? AND quantity >= ?",
            (quantity, product_id, quantity),
        )
        await db.commit()
        return cursor.rowcount == 1


async def get_products_by_category(category: str) -> list:
    """Получить активные товары по категории (только те, у которых quantity > 0)"""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id, name, description, price, category, image_file_id, quantity "
            "FROM products WHERE category = ? AND quantity > 0 AND is_active = 1 "
            "ORDER BY sort_order ASC, id ASC",
            (category,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": row[3],
                "category": row[4],
                "image_file_id": row[5],
                "quantity": row[6],
            }
            for row in rows
        ]


# ==================== РАБОТА С ЗАКАЗАМИ ====================


async def get_orders():
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT
                orders.id,
                users.fullname,
                users.phone,
                users.email,
                users.city,
                users.address,
                products.name,
                orders.quantity,
                orders.delivery_method,
                orders.delivery_address,
                orders.status,
                orders.tracking_number,
                orders.created_at,
                orders.unit_price,
                orders.comment
            FROM orders
            LEFT JOIN users ON orders.user_id = users.id
            LEFT JOIN products ON orders.product_id = products.id
            ORDER BY orders.created_at DESC
        """)
        return await cursor.fetchall()




async def get_order_by_id(order_id: int):
    """Получить заказ по ID с данными пользователя и товара"""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT
                orders.id,
                orders.user_id,
                users.fullname,
                users.phone,
                users.email,
                users.city,
                products.name,
                orders.quantity,
                orders.delivery_method,
                orders.delivery_address,
                orders.status,
                orders.created_at,
                orders.tracking_number,
                orders.unit_price,
                orders.comment,
                orders.product_id  
            FROM orders
            LEFT JOIN users ON orders.user_id = users.id
            LEFT JOIN products ON orders.product_id = products.id
            WHERE orders.id = ?
        """, (order_id,))
        return await cursor.fetchone()


async def update_order_status(order_id: int, status: str):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id),
        )
        await db.commit()


async def update_order_comment(order_id: int, comment: str):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "UPDATE orders SET comment = ? WHERE id = ?",
            (comment, order_id),
        )
        await db.commit()


async def get_orders_count(status_filter: str = None) -> int:
    """Получить количество заказов с фильтром"""
    async with aiosqlite.connect(DATABASE) as db:
        if status_filter == "active":
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE status IN (?, ?, ?)",
                ("новый", "в обработке", "отправлен"),
            )
        elif status_filter == "completed":
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE status IN (?, ?)",
                ("доставлен", "отменён"),
            )
        else:
            cursor = await db.execute("SELECT COUNT(*) FROM orders")

        result = await cursor.fetchone()
        return result[0] if result else 0



async def get_user_orders_count(user_id: int) -> int:
    """Получить количество заказов пользователя"""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = ?",
            (user_id,),
        )
        result = await cursor.fetchone()
        return result[0] if result else 0


async def create_order_and_decrease_stock(
    user_id: int,
    product_id: int,
    quantity: int,
    delivery_method: str,
    delivery_address: str,
    comment: str = None,
) -> dict:
    """
    Создаёт заказ, обновляет адрес пользователя и списывает остаток.
    Всё в одной транзакции.
    
    Списание остатка — атомарный UPDATE с условием quantity >= ?, 
    защищено от race condition.
    """
    async with aiosqlite.connect(DATABASE) as db:
        # 1. Получаем цену товара (для записи в orders.unit_price)
        cursor = await db.execute(
            "SELECT price FROM products WHERE id = ?",
            (product_id,),
        )
        result = await cursor.fetchone()

        if not result:
            return {"success": False, "message": "Товар не найден.", "order_id": None}

        unit_price = result[0]

        # 2. Атомарное списание остатка с проверкой
        cursor = await db.execute(
            "UPDATE products SET quantity = quantity - ? "
            "WHERE id = ? AND quantity >= ?",
            (quantity, product_id, quantity),
        )

        if cursor.rowcount != 1:
            # Товара не хватило — узнаём актуальный остаток для сообщения
            cursor = await db.execute(
                "SELECT quantity FROM products WHERE id = ?",
                (product_id,),
            )
            stock_row = await cursor.fetchone()
            current_stock = stock_row[0] if stock_row else 0
            return {
                "success": False,
                "message": f"Недостаточно товара на складе. Доступно: {current_stock} шт.",
                "order_id": None,
            }

        # 3. Сохраняем заказ
        await db.execute(
            "INSERT INTO orders "
            "(user_id, product_id, quantity, delivery_method, delivery_address, comment, unit_price) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, product_id, quantity, delivery_method, delivery_address, comment, unit_price),
        )

        # 4. Получаем ID созданного заказа
        cursor = await db.execute("SELECT last_insert_rowid()")
        order_id_row = await cursor.fetchone()
        order_id = order_id_row[0] if order_id_row else None

        # 5. Обновляем адрес пользователя
        await db.execute(
            "UPDATE users SET address = ? WHERE id = ?",
            (delivery_address, user_id),
        )

        await db.commit()

        return {"success": True, "message": "Заказ оформлен.", "order_id": order_id}


# ==================== РАБОТА С ТОВАРАМИ (АДМИН) ====================
async def add_product(
    name: str,
    description: str,
    price: int,
    category: str,
    quantity: int = 0,
    ozon_url: str = None,
    image_file_id: str = None,
):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "INSERT INTO products "
            "(name, description, price, category, image_file_id, ozon_url, quantity) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, description, price, category, image_file_id, ozon_url, quantity),
        )
        await db.commit()


async def update_product(
    product_id: int,
    name: str,
    description: str,
    price: int,
    category: str,
    quantity: int,
    image_file_id: str = None,
    ozon_url: str = None,
):
    async with aiosqlite.connect(DATABASE) as db:
        # Получаем текущее количество
        cursor = await db.execute(
            "SELECT quantity FROM products WHERE id = ?",
            (product_id,),
        )
        result = await cursor.fetchone()
        old_quantity = result[0] if result else 0

        # Обновляем товар
        await db.execute(
            "UPDATE products SET "
            "name = ?, description = ?, price = ?, category = ?, "
            "image_file_id = ?, ozon_url = ?, quantity = ? "
            "WHERE id = ?",
            (name, description, price, category, image_file_id, ozon_url, quantity, product_id),
        )

        # Если количество пополнилось выше порога — сбрасываем флаг уведомления
        if quantity > LOW_STOCK_THRESHOLD and old_quantity <= LOW_STOCK_THRESHOLD:
            await db.execute(
                "UPDATE products SET low_stock_notified = 0 WHERE id = ?",
                (product_id,),
            )

        await db.commit()


async def delete_product(product_id: int) -> dict:
    """
    Мягкое удаление товара: помечаем как неактивный (is_active = 0).
    Заказы остаются в истории.

    Возвращает:
    {'success': True/False, 'message': str, 'active_orders': int}
    """
    has_active, count = await check_product_has_active_orders(product_id)

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "UPDATE products SET is_active = 0 WHERE id = ?",
            (product_id,),
        )
        await db.commit()

    if has_active:
        return {
            "success": True,
            "message": f"Товар скрыт из каталога. Есть {count} незавершённых заказов с этим товаром.",
            "active_orders": count,
        }
    else:
        return {"success": True, "message": "Товар скрыт из каталога.", "active_orders": 0}


async def get_deleted_products():
    """Получить все удалённые (скрытые) товары (is_active = 0)"""
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT id, name, description, price, category, quantity, ozon_url, image_file_id "
            "FROM products WHERE is_active = 0 ORDER BY id DESC"
        )
        return await cursor.fetchall()


async def restore_product(product_id: int) -> bool:
    """Восстановить скрытый товар"""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "UPDATE products SET is_active = 1 WHERE id = ?",
            (product_id,),
        )
        await db.commit()
        return True


async def check_product_has_active_orders(product_id: int) -> tuple[bool, int]:
    """
    Проверяет, есть ли у товара незавершённые заказы.
    Возвращает: (есть_ли_активные, количество_активных)
    """
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM orders "
            "WHERE product_id = ? AND status NOT IN ('доставлен', 'отменён')",
            (product_id,),
        )
        result = await cursor.fetchone()
        count = result[0] if result else 0
        return (count > 0, count)


# ==================== ОБНОВЛЕНИЕ ЗАКАЗОВ ====================
async def update_order_tracking_number(order_id: int, tracking_number: str):
    """Обновить трек-номер заказа"""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "UPDATE orders SET tracking_number = ? WHERE id = ?",
            (tracking_number, order_id),
        )
        await db.commit()
        
        
async def update_product_image(product_id: int, image_file_id: str) -> bool:
    """Обновить фото товара"""
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            "UPDATE products SET image_file_id = ? WHERE id = ?",
            (image_file_id, product_id),
        )
        await db.commit()
        return True


async def return_stock_on_cancel(order_id: int) -> bool:
    """
    Вернуть товар на склад при отмене заказа.
    Возвращает True, если успешно.
    """
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT product_id, quantity FROM orders WHERE id = ?",
            (order_id,),
        )
        result = await cursor.fetchone()
        if not result:
            logger.warning(f"Order {order_id} not found for stock return")
            return False

        product_id, quantity = result

        if not product_id:
            logger.warning(f"Order {order_id} has no product_id")
            return False

        await db.execute(
            "UPDATE products SET quantity = quantity + ? WHERE id = ?",
            (quantity, product_id),
        )
        await db.commit()
        logger.info(f"✅ Returned {quantity} units to stock for product {product_id} (order {order_id})")
        return True


async def get_orders_paginated(status_filter: str = None, offset: int = 0, limit: int = 5):
    """
    Получить заказы с пагинацией и фильтром по статусу
    status_filter: None — все, 'active' — новый + в обработке + отправлен, 'completed' — доставлен + отменён
    """
    async with aiosqlite.connect(DATABASE) as db:
        if status_filter == "active":
            where_clause = "WHERE orders.status IN ('новый', 'в обработке', 'отправлен')"
        elif status_filter == "completed":
            where_clause = "WHERE orders.status IN ('доставлен', 'отменён')"
        else:
            where_clause = ""

        cursor = await db.execute(f"""
            SELECT
                orders.id,
                users.fullname,
                users.phone,
                users.email,
                users.city,
                products.name,
                orders.quantity,
                orders.delivery_method,
                orders.delivery_address,
                orders.status,
                orders.created_at,
                orders.tracking_number,
                orders.product_id,
                orders.unit_price,
                orders.comment
            FROM orders
            LEFT JOIN users ON orders.user_id = users.id
            LEFT JOIN products ON orders.product_id = products.id
            {where_clause}
            ORDER BY orders.created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        return await cursor.fetchall()


# ==================== СТАТИСТИКА ПО ПОЛЬЗОВАТЕЛЯМ ====================
async def get_user_orders_count_by_status(user_id: int, statuses: list) -> int:
    """Получить количество заказов пользователя с определёнными статусами"""
    async with aiosqlite.connect(DATABASE) as db:
        placeholders = ",".join(["?"] * len(statuses))
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM orders WHERE user_id = ? AND status IN ({placeholders})",
            (user_id, *statuses),
        )
        result = await cursor.fetchone()
        return result[0] if result else 0


async def get_user_orders_paginated_by_status(
    user_id: int,
    statuses: list = None,
    offset: int = 0,
    limit: int = 5,
):
    """Получить заказы пользователя с фильтром по статусам"""
    async with aiosqlite.connect(DATABASE) as db:
        if statuses:
            placeholders = ",".join(["?"] * len(statuses))
            query = f"""
                SELECT
                    orders.id,
                    products.name,
                    orders.quantity,
                    orders.delivery_method,
                    orders.delivery_address,
                    orders.status,
                    orders.comment,
                    orders.created_at,
                    orders.product_id,
                    orders.unit_price,
                    orders.tracking_number
                FROM orders
                LEFT JOIN products ON orders.product_id = products.id
                WHERE orders.user_id = ? AND orders.status IN ({placeholders})
                ORDER BY orders.created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor = await db.execute(query, (user_id, *statuses, limit, offset))
        else:
            cursor = await db.execute("""
                SELECT
                    orders.id,
                    products.name,
                    orders.quantity,
                    orders.delivery_method,
                    orders.delivery_address,
                    orders.status,
                    orders.comment,
                    orders.created_at,
                    orders.product_id,
                    orders.unit_price,
                    orders.tracking_number
                FROM orders
                LEFT JOIN products ON orders.product_id = products.id
                WHERE orders.user_id = ?
                ORDER BY orders.created_at DESC
                LIMIT ? OFFSET ?
            """, (user_id, limit, offset))

        return await cursor.fetchall()


# ==================== УТИЛИТЫ ====================
async def notify_user_safe(bot, chat_id: int, text: str, **kwargs) -> bool:
    """Отправить сообщение, не поднимая исключение наверх. True/False по результату."""
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", **kwargs)
        return True
    except Exception as e:
        logger.warning(f"Failed to notify {chat_id}: {e}")
        return False


def escape_html(text):
    """Экранирует HTML-символы в тексте"""
    if text is None:
        return ""
    return html.escape(str(text))


def format_moscow_time(timestamp_str: str) -> str:
    if not timestamp_str:
        return "неизвестно"

    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    utc_dt = pytz.UTC.localize(dt)
    moscow_tz = pytz.timezone("Europe/Moscow")
    moscow_time = utc_dt.astimezone(moscow_tz)

    return moscow_time.strftime("%d.%m.%Y %H:%M") + " (МСК)"


# ==================== НИЗКИЙ ОСТАТОК ====================
LOW_STOCK_THRESHOLD = 2


async def check_and_notify_low_stock(
    product_id: int,
    product_name: str,
    new_stock: int,
    bot,
    admin_chat_id: int,
) -> bool:
    """
    Проверяет, нужно ли уведомить о низком остатке.
    Возвращает True, если уведомление было отправлено.
    """
    if new_stock > LOW_STOCK_THRESHOLD:
        return False

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
            "SELECT low_stock_notified FROM products WHERE id = ?",
            (product_id,),
        )
        result = await cursor.fetchone()

        if not result:
            return False

        already_notified = result[0]

        if already_notified:
            return False

        await db.execute(
            "UPDATE products SET low_stock_notified = 1 WHERE id = ?",
            (product_id,),
        )
        await db.commit()

    from handlers.admin import ADMIN_IDS

    if admin_chat_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Перейти к редактированию", callback_data=f"edit_select_{product_id}")],
                [InlineKeyboardButton(text="📦 Управление товарами", callback_data="admin_products")],
            ]
        )

        await bot.send_message(
            chat_id=admin_chat_id,
            text=(
                f"⚠️ <b>Осталось мало товара!</b>\n\n"
                f"📦 <b>Товар:</b> {escape_html(product_name)}\n"
                f"🆔 ID: <code>{product_id}</code>\n"
                f"📊 <b>Остаток:</b> {new_stock} шт.\n\n"
                f"Рекомендуется пополнить склад, пока товар не закончился."
            ),
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )

        logger.info(f"⚠️ Low stock notification sent for product {product_id} (stock: {new_stock})")
        return True

    return False


