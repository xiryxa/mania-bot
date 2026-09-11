# MANIA Bot

Telegram-бот для бренда охотничьих товаров **MANIA** — автоматизация продаж манков, засидок и аксессуаров.

---

## Возможности

- 🛒 **Каталог товаров** с пагинацией и фото, разбит по категориям
- 📦 **Оформление заказа** с выбором способа доставки (Почта России, СДЭК, Яндекс Доставка)
- 👤 **Личный кабинет**: регистрация, редактирование профиля, история заказов с фильтрами
- 🔐 **Админ-панель**: управление заказами, товарами, экспорт заказов в CSV
- 🔄 **Автоматический пересчёт остатков** при отмене и возврате заказа в работу
- ⚠️ **Уведомления о низком остатке** товара администраторам
- 📊 **Отслеживание заказов**: трек-номера, подтверждение получения

---

## Стек

- Python 3.11+
- [Aiogram 3](https://docs.aiogram.dev/) — асинхронный фреймворк для Telegram Bot API
- SQLite + [aiosqlite](https://github.com/omnilib/aiosqlite) — асинхронная работа с БД
- FSM (Finite State Machine) — пошаговые сценарии регистрации и оформления заказа
- [python-dotenv](https://github.com/theskumar/python-dotenv) — переменные окружения из `.env`
- [pytz](https://pythonhosted.org/pytz/) — конвертация времени в московское
- [email-validator](https://github.com/JoshData/python-email-validator) — валидация email

---

## Установка и запуск (локально)

### 1. Клонировать репозиторий

```bash
git clone https://github.com/xiryxa/mania-bot.git
cd mania-bot
```

### 2. Создать и активировать виртуальное окружение

```bash
python -m venv .venv
```

**Windows:**
```bash
.venv\Scripts\activate
```

**Linux / macOS:**
```bash
source .venv/bin/activate
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Настроить переменные окружения

Скопируй `.env.example` в `.env`:

```bash
cp .env.example .env
```

Открой `.env` и заполни:

| Переменная | Что это |
|------------|---------|
| `BOT_TOKEN` | Токен бота от [@BotFather](https://t.me/BotFather) |
| `ADMIN_IDS` | Список Telegram ID администраторов через запятую |
| `ADMIN_USERNAMES` | Список юзернеймов администраторов через запятую (в том же порядке, что `ADMIN_IDS`) |

Свой Telegram ID можно узнать у бота [@userinfobot](https://t.me/userinfobot).

### 5. Запустить бота

```bash
python main.py
```

Если всё настроено верно, в логах появится:
```
INFO:__main__:🤖 Бот запущен! Нажмите Ctrl+C для остановки.
INFO:aiogram.dispatcher:Run polling for bot @... 
```

База данных `users.sqlite` создастся автоматически при первом запуске.

---

## Структура проекта

```
mania-bot/
├── main.py                    # Точка входа: запуск бота, инициализация роутеров
├── config.py                  # Константы проекта (ABOUT_MANIA, CATEGORY_MAP, команды бота)
├── db.py                      # Вся работа с базой данных (aiosqlite)
├── filters.py                 # Фильтр IsAdmin для защиты админских команд
├── requirements.txt           # Зависимости проекта
├── .env.example               # Шаблон переменных окружения
│
├── forms/
│   └── users.py               # FSM-состояния (регистрация, заказ, админ-панель)
│
├── utils/
│   └── validators.py          # Валидаторы ФИО, телефона, города
│
└── handlers/                  # Роутеры
    ├── __init__.py            # Экспорт всех роутеров
    ├── router.py              # Команды /start, /command, /register, /profile
    ├── navigation.py          # Навигация: /about, /help-переходы
    ├── profile.py             # Профиль пользователя и регистрация
    ├── callbacks.py           # Магазин и общие callback-запросы
    ├── shop.py                # Каталог товаров
    ├── admin.py               # Админ-панель: заказы, статистика, экспорт CSV
    ├── admin_products.py      # Управление товарами (CRUD)
    └── fallback.py            # Обработчик неизвестных сообщений
```

---

## Деплой на VPS (Ubuntu 24/7)

### Текущее состояние

⚠️ **Известное ограничение:** сейчас бот запускается вручную через `python main.py` в терминале. При падении процесса или перезагрузке сервера — не поднимается автоматически.

Перед реальным деплоем на VPS нужно настроить автозапуск через **systemd**.

### Рекомендуемый план деплоя (TODO)

1. **Подготовить VPS:** Ubuntu 22.04+, Python 3.11+.
2. **Скопировать проект** на сервер (git clone или rsync).
3. **Создать venv**, установить зависимости.
4. **Настроить `.env`** с реальными боевыми значениями.
5. **Создать systemd-юнит** `/etc/systemd/system/mania-bot.service`:
   - `WorkingDirectory` — папка проекта
   - `ExecStart` — путь к venv python + `main.py`
   - `Restart=always` — автоперезапуск при падении
   - `User` — не root, а отдельный системный пользователь
6. **Включить и запустить сервис:** `systemctl enable mania-bot && systemctl start mania-bot`.
7. **Настроить логирование** в файл (сейчас только stdout).
8. **Настроить бэкап** `users.sqlite` (cron + rsync / файловая копия).

Подробная инструкция будет добавлена в этот раздел перед деплоем.

---

## Лицензия

Проект разрабатывается для коммерческого использования брендом **MANIA**. Все права защищены.

---

## Контакты

- 🌐 Сайт: [maniateam.ru](https://maniateam.ru)
- 📺 YouTube: [@MANIAteam](https://www.youtube.com/@MANIAteam)
- 📞 Телефон (манки): +7 903 528-94-13 (WhatsApp, Viber)
- 📞 Телефон (скрадки): +7 928 041-89-89 (WhatsApp, Viber)
