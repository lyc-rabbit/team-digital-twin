from .api import router
from .repository import init_tables

init_tables()

__all__ = ["router"]
