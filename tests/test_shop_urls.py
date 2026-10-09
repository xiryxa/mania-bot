"""Минимальные тесты для защитной проверки URL в карточке товара"""
import pytest
from handlers.shop import _is_valid_url_for_tg


class TestIsValidUrlForTg:
    """Проверка функции _is_valid_url_for_tg"""

    @pytest.mark.parametrize("url", [
        "https://www.ozon.ru/product/12345/",
        "https://ozon.ru/product/some-product-123",
        "http://m.ozon.ru/product/test",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "http://youtube.com/watch?v=test123",
        "https://m.youtube.com/",
    ])
    def test_valid_urls(self, url):
        assert _is_valid_url_for_tg(url) is True

    @pytest.mark.parametrize("url", [
        "https://fakeozon.ru/product/123",          # поддельный домен
        "https://youtube.com.example.org/",          # домен первого уровня с нашим именем
        "https://ozon.ru.example.org/",              # аналогично
        "ftp://ozon.ru/product/123",                 # неподдерживаемая схема
        "javascript:alert(1)",                       # XSS-попытка
        "",                                          # пустая строка
        "   ",                                       # только пробелы
        None,                                        # None
        123,                                         # не строка
        "https://",                                  # нет хоста
        "http://localhost",                          # localhost запрещён
        "http://localhost:8000",                     # localhost с портом запрещён
        "http://ozon.ru:abc",                        # некорректный порт (строка)
        "http://ozon.ru:99999",                      # некорректный порт (>65535)
        "https://www.ozon.ru/product/123 abc",  # пробел внутри URL
        "https://attacker@youtube.com/",  # пользовательские данные в URL
    ])
    def test_invalid_urls(self, url):
        assert _is_valid_url_for_tg(url) is False
