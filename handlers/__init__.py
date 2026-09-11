# ==================== ИМПОРТЫ РОУТЕРОВ ====================
from .admin import admin_router
from .admin_products import router as products_router
from .callbacks import router as callbacks_router
from .fallback import router as fallback_router
from .navigation import router as navigation_router
from .router import router as user_router

# ==================== ЭКСПОРТЫ ====================
__all__ = [
    "user_router",
    "admin_router",
    "callbacks_router",
    "fallback_router",
    "navigation_router",
    "products_router",
]
