import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.validators import validate_fullname, validate_phone

def test_validate_fullname_valid():
    assert validate_fullname("Иван Петров") == (True, "")
    assert validate_fullname("Иван Иванович Петров") == (True, "")

def test_validate_fullname_invalid():
    assert validate_fullname("Иван")[0] is False
    assert validate_fullname("И П")[0] is False

def test_validate_phone_valid():
    assert validate_phone("+79035289413") == (True, "")
    assert validate_phone("+7 903 528-94-13") == (True, "")

def test_validate_phone_invalid():
    assert validate_phone("89035289413")[0] is False  # без +
    assert validate_phone("+7903")[0] is False        # слишком короткий
    assert validate_phone("+7903528941a")[0] is False # содержит буквы