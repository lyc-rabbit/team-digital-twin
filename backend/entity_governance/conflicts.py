"""ConflictDetector —— 强冲突禁止自动合并。"""

from .normalizer import normalize_text, url_key
from .types import PERSON_ID_KEYS


def detect_conflicts(left: dict, right: dict, entity_type: str, neighbors_left=None, neighbors_right=None) -> list:
    """返回冲突列表。非空则 FORCE_REVIEW。"""
    conflicts = []
    a, b = left or {}, right or {}

    type_a = a.get("type") or a.get("entity_type")
    type_b = b.get("type") or b.get("entity_type")
    if type_a and type_b and type_a != type_b:
        conflicts.append({
            "code": "TYPE_MISMATCH",
            "message": f"实体类型不同：{type_a} vs {type_b}",
            "severity": "high",
        })

    url_a = url_key(a.get("url") or a.get("repo") or a.get("repository"))
    url_b = url_key(b.get("url") or b.get("repo") or b.get("repository"))
    if url_a and url_b and url_a == url_b and type_a and type_b and type_a != type_b:
        conflicts.append({
            "code": "SAME_URL_DIFFERENT_TYPE",
            "message": "同一 URL / 仓库但实体类型不同",
            "severity": "high",
        })

    if entity_type == "PERSON":
        conflicts.extend(_person_conflicts(a, b))
    elif entity_type == "PROJECT":
        conflicts.extend(_project_conflicts(a, b, neighbors_left, neighbors_right))
    elif entity_type == "EVENT":
        conflicts.extend(_event_conflicts(a, b))
    elif entity_type == "RESOURCE":
        conflicts.extend(_resource_conflicts(a, b))

    return conflicts


def _ids_of(node, keys):
    out = {}
    for k in keys:
        v = node.get(k)
        if v and str(v).strip():
            out[k] = str(v).strip().lower()
    return out


def _person_conflicts(a, b):
    conflicts = []
    ia, ib = _ids_of(a, PERSON_ID_KEYS), _ids_of(b, PERSON_ID_KEYS)
    for key in ("employee_id", "enterprise_id", "id"):
        if ia.get(key) and ib.get(key) and ia[key] != ib[key]:
            # 两个都有正式工号且不同 —— 强冲突
            if key in ("employee_id", "enterprise_id") or (
                key == "id" and ia.get("employee_id") and ib.get("employee_id")
            ):
                conflicts.append({
                    "code": "DIFFERENT_EMPLOYEE_ID",
                    "message": f"{key} 不同：{ia.get(key)} vs {ib.get(key)}",
                    "severity": "high",
                })
    for key in ("email", "enterprise_wechat", "github_account"):
        if ia.get(key) and ib.get(key) and ia[key] != ib[key]:
            # 账号不同不一定冲突（一人多邮箱），但若工号也不同则升级
            if ia.get("employee_id") and ib.get("employee_id") and ia["employee_id"] != ib["employee_id"]:
                conflicts.append({
                    "code": "DIFFERENT_ACCOUNT",
                    "message": f"{key} 与工号均不一致",
                    "severity": "high",
                })
    return conflicts


def _owner_ids(node, neighbors):
    owners = set()
    if node.get("owner"):
        owners.add(normalize_text(node.get("owner")))
    if node.get("owner_id"):
        owners.add(str(node.get("owner_id")))
    for e in neighbors or []:
        if e.get("relation") == "OWNER":
            owners.add(e.get("source"))
    return {x for x in owners if x}


def _project_conflicts(a, b, n_a, n_b):
    conflicts = []
    pid_a = str(a.get("project_id") or "").strip()
    pid_b = str(b.get("project_id") or "").strip()
    owners_a = _owner_ids(a, n_a)
    owners_b = _owner_ids(b, n_b)
    if pid_a and pid_b and pid_a == pid_b and owners_a and owners_b and owners_a.isdisjoint(owners_b):
        conflicts.append({
            "code": "SAME_PROJECT_ID_DIFFERENT_OWNER",
            "message": "同一项目 ID 但负责人完全不同",
            "severity": "high",
        })
    # 名称几乎一样但负责人、时间窗都完全不同
    time_a = _time_span(a)
    time_b = _time_span(b)
    if owners_a and owners_b and owners_a.isdisjoint(owners_b) and _disjoint_time(time_a, time_b):
        conflicts.append({
            "code": "DIFFERENT_OWNER_AND_TIME",
            "message": "负责人完全不同且项目时间完全不重叠",
            "severity": "high",
        })
    return conflicts


def _resource_conflicts(a, b):
    conflicts = []
    url_a = url_key(a.get("url") or a.get("repo") or a.get("repository"))
    url_b = url_key(b.get("url") or b.get("repo") or b.get("repository"))
    cat_a = normalize_text(a.get("category") or a.get("type"))
    cat_b = normalize_text(b.get("category") or b.get("type"))
    if url_a and url_b and url_a == url_b and cat_a and cat_b and cat_a != cat_b:
        conflicts.append({
            "code": "SAME_URL_DIFFERENT_CATEGORY",
            "message": "同一 URL 但资源类别不同",
            "severity": "medium",
        })
    from organization_graph.ontology.resources import is_resource_hierarchy_pair
    if is_resource_hierarchy_pair(a, b):
        conflicts.append({
            "code": "RESOURCE_HIERARCHY",
            "message": "总类资源与明细资源不是同一实体",
            "severity": "high",
        })
    return conflicts


def _event_conflicts(a, b):
    conflicts = []
    ta = (a.get("time") or a.get("event_time") or "")[:16]
    tb = (b.get("time") or b.get("event_time") or "")[:16]
    if ta and tb and ta != tb:
        conflicts.append({
            "code": "EVENT_TIME_MISMATCH",
            "message": f"事件时间不同：{ta} vs {tb}",
            "severity": "high",
        })
    type_a = normalize_text(a.get("event_type") or a.get("category"))
    type_b = normalize_text(b.get("event_type") or b.get("category"))
    if type_a and type_b and type_a != type_b:
        conflicts.append({
            "code": "EVENT_TYPE_MISMATCH",
            "message": "事件类型不同",
            "severity": "high",
        })
    return conflicts


def _time_span(node):
    start = (node.get("start_date") or node.get("start") or node.get("time") or "")[:10]
    end = (node.get("end_date") or node.get("end") or start)[:10]
    return start, end


def _disjoint_time(span_a, span_b):
    a0, a1 = span_a
    b0, b1 = span_b
    if not (a0 and b0 and a1 and b1):
        return False
    return a1 < b0 or b1 < a0
