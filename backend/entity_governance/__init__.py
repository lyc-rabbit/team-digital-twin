"""统一实体层（Entity Governance / Entity Resolution）。

组织影响力图谱是第一个消费者；项目中心、日报、新人地图、晋升推演应绑定 canonical_entity_id。
"""

from .api import router
from .scheduler import start_scheduler

__all__ = ["router", "start_scheduler"]
