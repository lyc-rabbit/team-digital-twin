"""知识图谱语义治理（本体层 + 关系推理 + 语义重构建议）。

不删除已有节点，不修改节点 type。实体治理负责 SAME_AS，本模块负责 IS_A / PART_OF。
"""

from .api import router

__all__ = ["router"]
