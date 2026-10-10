"""Минимальные тесты для защитной проверки URL в карточке товара"""
import pytest
from handlers.shop import _is_valid_url_for_tg


class TestIsValidUrlForTg:
    """Проверка функции _is_valid_url_for_tg"""

    @pytest.mark.parametrize("url", [
        "https://www.ozon.ru/product/12345/",
        "https://youtube.com/watch?v=123",
        "https://youtu.be/123",
        "http://example.com",
        "https://example.com/path?query=1",
        "https://example.org/product/123",          # произвольный внешний домен
        "https://www.ozon.ru/",                     # реальная ссылка на Ozon
    ])
    def test_valid_urls(self, url):
        assert _is_valid_url_for_tg(url) is True

    @pytest.mark.parametrize("url", [
        "ftp://ozon.ru/product/123",                 # неподдерживаемая схема
        "javascript:alert(1)",                       # XSS-попытка
        "",                                          # пустая строка
        "   ",                                       # только пробелы
        None,                                        # None
        123,                                         # не строка
        "https://",                                  # нет хоста
        "http://ozon.ru:abc",                        # некорректный порт (строка)
        "http://ozon.ru:99999",                      # некорректный порт (>65535)
        "https://attacker@youtube.com/",             # пользовательские данные в URL
    ])
    def test_invalid_urls(self, url):
        assert _is_valid_url_for_tg(url) is False
