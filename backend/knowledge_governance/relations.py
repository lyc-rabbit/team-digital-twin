"""图谱语义关系：在已有边上增强，不替换原关系。"""

from organization_graph.ontology.relations import (
    REL_BELONGS_TO,
    REL_CONTROL,
    REL_HAS_RESOURCE,
    REL_HAS_SUB_RESOURCE,
    REL_OWNER,
    REL_WORKS_ON,
    RELATION_TYPES,
    relation_template,
)

REL_IS_A = "IS_A"
REL_PART_OF = "PART_OF"
REL_USES = "USES"
REL_DEPENDS_ON = "DEPENDS_ON"
REL_CONTRIBUTE_TO = "CONTRIBUTE_TO"
REL_CONTROL_KEY = "CONTROL_KEY_RESOURCE"
REL_MANAGES = "MANAGES"

SEMANTIC_RELATIONS = (
    REL_IS_A,
    REL_PART_OF,
    REL_USES,
    REL_DEPENDS_ON,
    REL_CONTRIBUTE_TO,
    REL_CONTROL_KEY,
    REL_MANAGES,
)

ALL_RELATIONS = tuple(dict.fromkeys(list(RELATION_TYPES) + list(SEMANTIC_RELATIONS)))

# 推理匹配时，把已有操作关系当成语义关系的证据
RELATION_EQUIV = {
    REL_USES: (REL_USES, REL_HAS_RESOURCE),
    REL_IS_A: (REL_IS_A,),
    REL_PART_OF: (REL_PART_OF,),
    REL_MANAGES: (REL_MANAGES, REL_CONTROL),
    REL_WORKS_ON: (REL_WORKS_ON,),
    REL_BELONGS_TO: (REL_BELONGS_TO,),
}

INFERRED_FLAG = "inferred"


def semantic_edge(source, target, relation, **props):
    props = dict(props or {})
    props.setdefault("semantic", True)
    return relation_template(source, target, relation, **props)
