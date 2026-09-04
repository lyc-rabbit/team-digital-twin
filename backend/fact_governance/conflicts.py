"""时间重叠与互斥谓词冲突检测。时间不重叠则不算冲突。"""

from .types import EXCLUSIVE_PREDICATES, STATUS_CONFLICT, STATUS_EXTRACTED, ACTIVE_FACT_STATUSES


def _day(value):
    return str(value or "").replace(" ", "T")[:10]


def intervals_overlap(a_from, a_to, b_from, b_to):
    a0, a1 = _day(a_from), _day(a_to)
    b0, b1 = _day(b_from), _day(b_to)
    if not a0 and not a1 and not b0 and not b1:
        return True
    if a1 and b0 and a1 < b0:
        return False
    if b1 and a0 and b1 < a0:
        return False
    return True


def is_exclusive(predicate):
    p = (predicate or "").strip()
    return p in EXCLUSIVE_PREDICATES or p.upper() in EXCLUSIVE_PREDICATES


def find_conflicts(fact, others):
    """others: 已有活跃事实。返回 [(other, reason), ...]"""
    hits = []
    if not is_exclusive(fact.get("predicate")):
        same_triple = [
            o for o in others
            if o.get("fact_id") != fact.get("fact_id")
            and o.get("subject") == fact.get("subject")
            and o.get("predicate") == fact.get("predicate")
            and o.get("object") == fact.get("object")
            and o.get("status") in ACTIVE_FACT_STATUSES
        ]
        for o in same_triple:
            if intervals_overlap(fact.get("valid_from"), fact.get("valid_to"), o.get("valid_from"), o.get("valid_to")):
                hits.append((o, "同一主谓宾在重叠时间重复出现"))
        return hits
    for o in others:
        if o.get("fact_id") == fact.get("fact_id"):
            continue
        if o.get("status") not in ACTIVE_FACT_STATUSES:
            continue
        if o.get("predicate") != fact.get("predicate"):
            continue
        if o.get("object") != fact.get("object"):
            continue
        if o.get("subject") == fact.get("subject"):
            continue
        if not intervals_overlap(fact.get("valid_from"), fact.get("valid_to"), o.get("valid_from"), o.get("valid_to")):
            continue
        hits.append((
            o,
            f"互斥谓词「{fact.get('predicate')}」在重叠时间内出现不同主体："
            f"{fact.get('subject')} vs {o.get('subject')}",
        ))
    return hits


def apply_conflict_flags(store, fact):
    others = store.list_active_facts()
    hits = find_conflicts(fact, others)
    for other, reason in hits:
        store.add_conflict(fact["fact_id"], other["fact_id"], reason)
        if fact.get("status") == STATUS_EXTRACTED:
            store.update_fact_status(fact["fact_id"], STATUS_CONFLICT)
        if other.get("status") == STATUS_EXTRACTED:
            store.update_fact_status(other["fact_id"], STATUS_CONFLICT)
    return hits
