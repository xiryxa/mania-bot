# ==================== ИМПОРТЫ ====================
import html
import logging
from datetime import datetime, timezone
import html as _html_lib
import re as _re_lib
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
        db.row_factory = aiosqlite.Row
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
        
        # ---------- Таблица подписок на появление товара ----------
        await db.execute("""
            CREATE TABLE IF NOT EXISTS product_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                UNIQUE(user_id, product_id)
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

        # Миграция для снепшота данных пользователя в заказе
        if "order_fullname" not in column_names:
            await db.execute("ALTER TABLE orders ADD COLUMN order_fullname TEXT")
            logger.info("✅ Добавлено поле order_fullname в таблицу orders")

        if "order_phone" not in column_names:
            await db.execute("ALTER TABLE orders ADD COLUMN order_phone TEXT")
            logger.info("✅ Добавлено поле order_phone в таблицу orders")

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
        db.row_factory = aiosqlite.Row
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
        db.row_factory = aiosqlite.Row
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
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE users SET fullname = ?, phone = ?, email = ?, city = ?, address = ?, username = ? "
            "WHERE id = ?",
            (fullname, phone, email, city, address, username, telegram_id),
        )
        await db.commit()


async def get_users():
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, fullname, phone, email, city, address, username, created_at "
            "FROM users ORDER BY id"
        )
        return await cursor.fetchall()


async def get_user_count():
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        result = await cursor.fetchone()
        return result[0] if result else 0
    
    
async def get_all_user_ids() -> list[int]:
    """
    Получить список Telegram ID всех зарегистрированных пользователей.
    Используется для массовой рассылки.
    """
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id FROM users ORDER BY id")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

# ==================== РАБОТА С ТОВАРАМИ ====================
async def get_products():
    """Получить все активные товары (включая те, у которых quantity == 0)"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE is_active = 1"
        )
        return await cursor.fetchall()


async def get_all_products():
    """Получить все активные товары"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, description, price, category, quantity, ozon_url, image_file_id "
            "FROM products WHERE is_active = 1 ORDER BY sort_order ASC, id ASC"
        )
        return await cursor.fetchall()


async def get_product_by_id(product_id: int):
    """Получить товар по ID"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, description, price, category, quantity, ozon_url, image_file_id "
            "FROM products WHERE id = ?",
            (product_id,),
        )
        return await cursor.fetchone()


async def get_product_stock(product_id: int) -> int:
    """Получить количество товара на складе"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
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
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "UPDATE products SET quantity = quantity - ? "
            "WHERE id = ? AND quantity >= ?",
            (quantity, product_id, quantity),
        )
        await db.commit()
        return cursor.rowcount == 1


async def get_products_by_category(category: str) -> list:
    """Получить активные товары по категории (включая те, у которых quantity == 0)"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, description, price, category, image_file_id, quantity "
            "FROM products WHERE category = ? AND is_active = 1 "
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
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT
                orders.id,
                orders.order_fullname,
                orders.order_phone,
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
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT
                orders.id,
                orders.user_id,
                orders.order_fullname,
                orders.order_phone,
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
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id),
        )
        await db.commit()
        
        
async def update_order_status_atomic(order_id: int, new_status: str) -> dict:
    """
    Атомарно изменяет статус заказа и корректирует остатки на складе.
    Возвращает dict: {"success": bool, "message": str, "old_status": str, "new_status": str}
    """
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        # 1. Получаем текущее состояние заказа
        cursor = await db.execute(
            "SELECT status, product_id, quantity FROM orders WHERE id = ?",
            (order_id,)
        )
        order = await cursor.fetchone()
        
        if not order:
            return {"success": False, "message": "Заказ не найден"}
        
        current_status, product_id, quantity = order
        
        # Защита от повторного выполнения (idempotency)
        if current_status == new_status:
            return {"success": True, "message": "Статус не изменился", "old_status": current_status, "new_status": new_status}
        
        restocked = False
        
        if new_status == "отменён" and current_status != "отменён":
            # Возврат на склад при отмене
            if product_id and quantity > 0:
                cursor = await db.execute("SELECT quantity FROM products WHERE id = ?", (product_id,))
                stock_res = await cursor.fetchone()
                old_quantity = stock_res[0] if stock_res else 0
                
                await db.execute(
                    "UPDATE products SET quantity = quantity + ? WHERE id = ?",
                    (quantity, product_id)
                )
                logger.info(f"✅ Stock returned for cancelled order #{order_id} (product {product_id}, qty {quantity})")
                
                if old_quantity == 0 and (old_quantity + quantity) > 0:
                    restocked = True
                
        elif current_status == "отменён" and new_status != "отменён":
            # Повторное списание при восстановлении из отменённых
            if product_id and quantity > 0:
                cursor = await db.execute(
                    "SELECT quantity FROM products WHERE id = ?",
                    (product_id,)
                )
                stock_res = await cursor.fetchone()
                current_stock = stock_res[0] if stock_res else 0
                
                if current_stock < quantity:
                    return {
                        "success": False, 
                        "message": f"Недостаточно товара на складе. Доступно: {current_stock} шт., требуется: {quantity} шт.",
                        "old_status": current_status
                    }
                
                await db.execute(
                    "UPDATE products SET quantity = quantity - ? WHERE id = ?",
                    (quantity, product_id)
                )
                logger.info(f"✅ Stock decreased for restored order #{order_id} (product {product_id}, qty {quantity})")
        
        # 3. Финальное обновление статуса
        await db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (new_status, order_id)
        )
        await db.commit()
        
        return {
            "success": True, 
            "message": "Успешно", 
            "old_status": current_status, 
            "new_status": new_status,
            "restocked": restocked,
            "product_id": product_id
        }


async def update_order_comment(order_id: int, comment: str):
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE orders SET comment = ? WHERE id = ?",
            (comment, order_id),
        )
        await db.commit()


async def get_orders_count(status_filter: str = None) -> int:
    """Получить количество заказов с фильтром"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
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
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        # 1. Получаем текущие данные пользователя для снепшота
        cursor = await db.execute(
            "SELECT fullname, phone FROM users WHERE id = ?",
            (user_id,),
        )
        user_data = await cursor.fetchone()
        order_fullname = user_data[0] if user_data and user_data[0] else "Не указано"
        order_phone = user_data[1] if user_data and user_data[1] else "Не указано"

        # 2. Получаем цену товара (для записи в orders.unit_price)
        cursor = await db.execute(
            "SELECT price FROM products WHERE id = ?",
            (product_id,),
        )
        result = await cursor.fetchone()

        if not result:
            return {"success": False, "message": "Товар не найден.", "order_id": None}

        unit_price = result[0]

        # 3. Атомарное списание остатка с проверкой
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

        # 4. Сохраняем заказ с новыми полями снепшота
        await db.execute(
            "INSERT INTO orders "
            "(user_id, product_id, quantity, delivery_method, delivery_address, comment, unit_price, order_fullname, order_phone) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, product_id, quantity, delivery_method, delivery_address, comment, unit_price, order_fullname, order_phone),
        )

        # 5. Получаем ID созданного заказа
        cursor = await db.execute("SELECT last_insert_rowid()")
        order_id_row = await cursor.fetchone()
        order_id = order_id_row[0] if order_id_row else None

        # 6. Обновляем адрес пользователя
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
        db.row_factory = aiosqlite.Row
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
) -> dict:
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT quantity FROM products WHERE id = ?",
            (product_id,),
        )
        result = await cursor.fetchone()
        old_quantity = result[0] if result else 0

        await db.execute(
            "UPDATE products SET "
            "name = ?, description = ?, price = ?, category = ?, "
            "image_file_id = ?, ozon_url = ?, quantity = ? "
            "WHERE id = ?",
            (name, description, price, category, image_file_id, ozon_url, quantity, product_id),
        )

        if quantity > LOW_STOCK_THRESHOLD and old_quantity <= LOW_STOCK_THRESHOLD:
            await db.execute(
                "UPDATE products SET low_stock_notified = 0 WHERE id = ?",
                (product_id,),
            )

        await db.commit()
        
        # Проверяем переход 0 -> >0
        restocked = (old_quantity == 0 and quantity > 0)
        return {"success": True, "restocked": restocked, "product_id": product_id}


async def delete_product(product_id: int) -> dict:
    """
    Мягкое удаление товара: помечаем как неактивный (is_active = 0).
    Заказы остаются в истории.

    Возвращает:
    {'success': True/False, 'message': str, 'active_orders': int}
    """
    has_active, count = await check_product_has_active_orders(product_id)

    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
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
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, description, price, category, quantity, ozon_url, image_file_id "
            "FROM products WHERE is_active = 0 ORDER BY id DESC"
        )
        return await cursor.fetchall()


async def restore_product(product_id: int) -> bool:
    """Восстановить скрытый товар"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
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
        db.row_factory = aiosqlite.Row
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
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE orders SET tracking_number = ? WHERE id = ?",
            (tracking_number, order_id),
        )
        await db.commit()
        
        
async def update_product_image(product_id: int, image_file_id: str) -> bool:
    """Обновить фото товара"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE products SET image_file_id = ? WHERE id = ?",
            (image_file_id, product_id),
        )
        await db.commit()
        return True



async def get_orders_paginated(status_filter: str = None, offset: int = 0, limit: int = 5):
    """
    Получить заказы с пагинацией и фильтром по статусу
    status_filter: None — все, 'active' — новый + в обработке + отправлен, 'completed' — доставлен + отменён
    """
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        if status_filter == "active":
            where_clause = "WHERE orders.status IN ('новый', 'в обработке', 'отправлен')"
        elif status_filter == "completed":
            where_clause = "WHERE orders.status IN ('доставлен', 'отменён')"
        else:
            where_clause = ""

        cursor = await db.execute(f"""
            SELECT
                orders.id,
                orders.order_fullname,
                orders.order_phone,
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
        db.row_factory = aiosqlite.Row
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
        db.row_factory = aiosqlite.Row
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


# ==================== БЕЗОПАСНЫЙ CAPTION (лимит Telegram) ====================
CAPTION_LIMIT = 1024  # лимит Telegram для caption (после парсинга сущностей)
_TAG_RE = _re_lib.compile(r"</?[a-zA-Z][^>]*>")


def visible_len(html_text: str) -> int:
    """Длина текста так, как её считает Telegram: после парсинга сущностей и без тегов."""
    return len(_html_lib.unescape(_TAG_RE.sub("", html_text)))


def truncate_plain(text, max_len: int) -> str:
    """Обрезать plain-текст по видимым символам ДО escape_html. Добавляет '...' только при обрезке."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max(0, max_len)].rstrip() + "..."


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
        db.row_factory = aiosqlite.Row
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


# ==================== ЛОГИКА СТАТУСОВ ЗАКАЗОВ ====================
def get_status_notification_text(
    old_status: str | None, 
    new_status: str, 
    order_id: int, 
    product_name: str, 
    delivery_method: str, 
    delivery_address: str
) -> str | None:
    """
    Возвращает текст уведомления о смене статуса.
    Без выдумывания причин — только констатация факта (per Claude's review).
    """
    if not old_status:
        old_status = "новый"
    if old_status == new_status:
        return None

    product = escape_html(product_name or "товар")
    delivery = escape_html(delivery_method or "не указан")
    address = escape_html(delivery_address or "не указан")
    new_status_escaped = escape_html(str(new_status))

    # 1. Движение ВПЕРЁД (стандартные сообщения)
    if new_status == "в обработке" and old_status == "новый":
        return f"🔄 Ваш заказ #{order_id} принят в обработку! Мы уже готовим «{product}» к отправке."
    
    if new_status == "отправлен" and old_status == "в обработке":
        return f"📦 Ваш заказ #{order_id} отправлен!\n🚚 Способ доставки: {delivery}\n📍 Адрес: {address}"
    
    if new_status == "доставлен" and old_status == "отправлен":
        return f"✅ Заказ #{order_id} доставлен! Спасибо за покупку 🦆\nБудем рады видеть вас снова."
    
    if new_status == "отменён" and old_status in ["новый", "в обработке", "отправлен"]:
        return f"❌ Заказ #{order_id} отменён. Если это ошибка — напишите нам, контакты в разделе /about."

    # 2. ОТКАТЫ НАЗАД (нейтральная констатация факта + ссылка на /about)
    if old_status == "отправлен" and new_status in ["в обработке", "новый"]:
        return f"ℹ️ Ваш заказ #{order_id} вернулся в стадию обработки. Продолжается подготовка к отправке.\nПо всем вопросам — контакты в /about."
    
    if old_status == "доставлен" and new_status in ["отправлен", "в обработке", "новый"]:
        return f"ℹ️ Статус вашего заказа #{order_id} изменён на «{new_status_escaped}».\nПо всем вопросам — контакты в /about."
    
    if old_status == "в обработке" and new_status == "новый":
        return f"ℹ️ Ваш заказ #{order_id} вернулся в статус «Новый». Продолжается проверка.\nПо всем вопросам — контакты в /about."

    # 3. ВОССТАНОВЛЕНИЕ из "отменён" (позитивный факт — заказ снова активен)
    if old_status == "отменён" and new_status in ["новый", "в обработке", "отправлен"]:
        return f"✅ Ваш заказ #{order_id} снова в работе. Текущий статус: «{new_status_escaped}».\nПо всем вопросам — контакты в /about."

    # 4. Fallback для любых других переходов
    return f"ℹ️ Статус вашего заказа #{order_id} обновлён: «{new_status_escaped}».\nПо всем вопросам — контакты в /about."


async def clear_order_tracking_number(order_id: int):
    """Очищает трек-номер заказа (используется при откате статуса из 'отправлен')"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE orders SET tracking_number = NULL WHERE id = ?",
            (order_id,),
        )
        await db.commit()
        logger.info(f"🧹 DB: Tracking number cleared for order #{order_id}")
        

# ==================== ПОДПИСКИ НА ТОВАРЫ ====================
async def subscribe_to_product(user_id: int, product_id: int) -> dict:
    """
    Подписать пользователя на уведомление о появлении товара.
    Возвращает dict: {"success": bool, "message": str}
    """
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute(
                "INSERT INTO product_subscriptions (user_id, product_id) VALUES (?, ?)",
                (user_id, product_id)
            )
            await db.commit()
            return {"success": True, "message": "Подписка создана"}
        except aiosqlite.IntegrityError:
            return {"success": False, "message": "Вы уже подписаны на этот товар"}


async def unsubscribe_from_product(user_id: int, product_id: int) -> bool:
    """Отписать пользователя от товара"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "DELETE FROM product_subscriptions WHERE user_id = ? AND product_id = ?",
            (user_id, product_id)
        )
        await db.commit()
        return True


async def get_product_subscribers(product_id: int) -> list[int]:
    """Получить список user_id подписчиков на товар"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id FROM product_subscriptions WHERE product_id = ?",
            (product_id,)
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def delete_subscription(user_id: int, product_id: int) -> bool:
    """Удалить подписку (используется после успешной отправки уведомления)"""
    async with aiosqlite.connect(DATABASE) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "DELETE FROM product_subscriptions WHERE user_id = ? AND product_id = ?",
            (user_id, product_id)
        )
        await db.commit()
        return True