# ==================== ИМПОРТЫ РОУТЕРОВ ====================
from .admin import admin_router
from .admin_broadcast import router as admin_broadcast_router
from .admin_products import router as products_router
from .callbacks import router as callbacks_router
from .fallback import router as fallback_router
from .navigation import router as navigation_router
from .profile import router as profile_router
from .profile_orders import router as profile_orders_router
from .router import router as user_router

# ==================== ЭКСПОРТЫ ====================
__all__ = [
    "user_router",
    "admin_router",
    "admin_broadcast_router",
    "callbacks_router",
    "fallback_router",
    "navigation_router",
    "profile_router",
    "profile_orders_router",
    "products_router",
]
