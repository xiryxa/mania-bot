import logging
import logging.handlers
import os

def setup_logger():
    """
    Настройка логгера с ротацией файлов.
    - Логи пишутся в logs/mania_bot.log (макс. 5 МБ, 3 backup файла)
    - WARNING и выше дублируются в консоль, INFO фильтруется от спама aiogram.event
    """
    # 1. Вычисляем АБСОЛЮТНЫЙ путь до папки logs относительно этого файла
    # __file__ = .../mania-bot/utils/logger.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir) # Поднимаемся в корень mania-bot
    log_dir = os.path.join(project_root, "logs")
    log_file = os.path.join(log_dir, "mania_bot.log")
    
    # Создаём директорию, если её нет
    os.makedirs(log_dir, exist_ok=True)
    
    # Основной (корневой) логгер
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Формат логов
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # RotatingFileHandler: запись в файл с ротацией
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 МБ
        backupCount=3,             # Хранить 3 старых файла
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # ConsoleHandler: вывод в консоль
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Фильтр, чтобы не спамить в консоль каждым обновлением от aiogram
    class NoAiogramEventFilter(logging.Filter):
        def filter(self, record):
            if record.levelno >= logging.WARNING:
                return True
            if not record.name.startswith("aiogram.event"):
                return True
            return False

    console_handler.addFilter(NoAiogramEventFilter())
    
    # Очищаем старые хендлеры, если логгер инициализировался ранее
    if logger.hasHandlers():
        logger.handlers.clear()
        
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # ЯВНАЯ ПРОВЕРКА: пишем тестовое сообщение, чтобы гарантировать запись в файл
    # и выводим путь в консоль, чтобы ты точно знал, где искать файл
    logger.info(f"📂 Логи успешно инициализированы. Файл: {log_file}")
    
    return logger