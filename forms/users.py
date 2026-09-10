# ==================== ИМПОРТЫ ====================
from aiogram.fsm.state import State, StatesGroup


# ==================== СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЯ ====================
class Form(StatesGroup):
    """FSM для регистрации пользователя"""
    name = State()
    phone = State()
    email = State()
    city = State()


class UpdateState(StatesGroup):
    """FSM для обновления данных пользователя"""
    name = State()
    phone = State()
    email = State()
    city = State()


class ProfileState(StatesGroup):
    """FSM для просмотра профиля"""
    viewing = State()


# ==================== СОСТОЯНИЯ ЗАКАЗА ====================
class OrderState(StatesGroup):
    """FSM для оформления заказа"""
    product = State()          # выбор товара
    quantity = State()         # количество
    delivery_method = State()  # способ доставки
    address = State()          # ввод адреса
    comment = State()          # комментарий к заказу


# ==================== СОСТОЯНИЯ АДМИНА ====================
class AdminState(StatesGroup):
    """FSM для админ-панели"""
    in_panel = State()


class AdminOrdersState(StatesGroup):
    """FSM для управления заказами"""
    viewing_active = State()
    viewing_all = State()
    page = State()
    status_filter = State()
    adding_tracking = State()


class AdminProductState(StatesGroup):
    """FSM для управления товарами"""
    selecting_action = State()   # выбрать действие (добавить/редактировать/удалить)
    adding_name = State()        # ввод названия
    adding_description = State() # ввод описания
    adding_price = State()       # ввод цены
    adding_category = State()    # ввод категории
    adding_photo = State()       # загрузка фото
    adding_quantity = State()    # количество
    editing_select = State()     # выбор товара для редактирования
    editing_field = State()      # выбор поля для редактирования
    editing_value = State()      # новое значение поля
    deleting_confirm = State()   # подтверждение удаления


class AdminProductEditState(StatesGroup):
    """Состояния для редактирования товара"""
    photo = State()


class AddProductSteps(StatesGroup):
    """FSM для добавления товара админом"""
    name = State()
    description = State()
    price = State()
    category = State()
    photo = State()
    confirm = State()