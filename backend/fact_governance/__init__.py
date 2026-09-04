"""事实治理：Fact → 图谱实例/关系 → 派生分析结果。不允许原地修改事实。"""

from .api import router
from .repository import get_fact_store

__all__ = ["router", "get_fact_store"]
