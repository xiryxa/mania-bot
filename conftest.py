import os
import tempfile
import pytest
import pytest_asyncio
import sys

# Добавляем корень проекта в путь, чтобы работал import db
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import db

@pytest.fixture(autouse=True)
def patch_db_path(monkeypatch):
    """Создает временную БД для каждого теста и удаляет её после"""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
    temp_db.close()
    monkeypatch.setattr(db, "DATABASE", temp_db.name)
    yield temp_db.name
    if os.path.exists(temp_db.name):
        os.remove(temp_db.name)

@pytest_asyncio.fixture  # <--- ПРАВИЛЬНЫЙ ДЕКОРАТОР ДЛЯ АСИНХРОННЫХ ФИКСТУР
async def initialized_db(patch_db_path):
    """Инициализирует таблицы во временной БД"""
    await db.init_db()
    yield
