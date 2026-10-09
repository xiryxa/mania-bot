"""Минимальные тесты для защитной проверки URL в карточке товара"""
import pytest
from handlers.shop import _is_valid_url_for_tg


class TestIsValidUrlForTg:
    """Проверка функции _is_valid_url_for_tg"""

    # Корректные URL
    @pytest.mark.parametrize("url", [
        "https://www.ozon.ru/product/12345/",
        "https://ozon.ru/product/some-product-123",
        "http://ozon.ru/product/test",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtube.com/watch?v=test123",
        "http://localhost/test",
    ])
    def test_valid_urls(self, url):
        assert _is_valid_url_for_tg(url) is True

    # Некорректные URL
    @pytest.mark.parametrize("url", [
        "https://jshsksksksoeijd",           # нет точки в домене
        "http://localhost",                    # localhost без пути — допустим, но проверим
        "not-a-url",                          # вообще не URL
        "ftp://ozon.ru/product/123",          # неподдерживаемая схема
        "",                                   # пустая строка
        None,                                 # None
        123,                                  # не строка
        "https://",                           # нет хоста
        "javascript:alert(1)",                # XSS-попытка
    ])
    def test_invalid_urls(self, url):
        # localhost без точки тоже должен проходить (есть в логике функции)
        if url == "http://localhost":
            assert _is_valid_url_for_tg(url) is True
        else:
            assert _is_valid_url_for_tg(url) is False