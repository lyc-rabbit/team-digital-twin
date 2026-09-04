"""把记事件、图谱抽取接到事实层。不自动确认（抽取 UI 已确认的除外）。"""

import json

from database import get_all_members

from .repository import get_fact_store
from .service import confirm_fact, create_fact, _align_entity
from .types import GRAPH_OBJECT_TYPE, SOURCE_EVENT, STATUS_EXTRACTED, graph_relation_of

DIM_TO_PRED = {
    "trust": "TRUST",
    "professional_trust": "TRUST",
    "delivery_trust": "TRUST",
    "risk_trust": "TRUST",
    "autonomy_trust": "TRUST",
    "management_trust": "TRUST",
    "independence": "TRUST",
    "sentiment": "COLLABORATE_WITH",
    "communication": "COLLABORATE_WITH",
    "mentoring": "MENTOR",
    "management": "MANAGEMENT_RESPONSIBILITY",
    "professional": "COLLABORATE_WITH",
    "problem_solving": "COLLABORATE_WITH",
    "problem_definition": "COLLABORATE_WITH",
}

TAG_TO_PRED = {
    "协作": "COLLABORATE_WITH",
    "合作": "COLLABORATE_WITH",
    "信任": "TRUST",
    "冲突": "CONFLICT",
    "分歧": "CONFLICT",
    "指导": "MENTOR",
    "培养": "MENTOR",
    "汇报": "REPORT_TO",
    "负责": "ORG_RESPONSIBILITY",
}


def _names():
    return {m["id"]: m.get("name") or m["id"] for m in (get_all_members() or [])}


def _day(value):
    s = str(value or "").replace(" ", "T")
    return s[:10] if s else ""


def _as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def ingest_from_logged_event(event, analysis=None, parsed=None):
    """日历/记录事件保存后：生成待确认 Fact，不写图谱。"""
    if not event:
        return {"created": 0, "facts": []}
    event_id = event.get("id") or event.get("event_id")
    if not event_id:
        return {"created": 0, "facts": []}
    names = _names()
    store = get_fact_store()
    seen = store.origin_keys()
    created = []
    when = _day(event.get("event_time"))
    title = event.get("scene") or event.get("event_tag") or f"事件 #{event_id}"
    raw = (event.get("raw_summary") or event.get("facts") or "")[:500]
    involved = _as_list(event.get("involved_members"))
    source_title = f"事件 · {title}"

    triples = []
    for rel in (analysis or {}).get("relationship_evidence") or []:
        a, b = rel.get("from_member_id"), rel.get("to_member_id")
        pred = graph_relation_of(DIM_TO_PRED.get(rel.get("dimension") or "", "") or "COLLABORATE_WITH")
        if a and b and a != b:
            triples.append((a, pred, b, rel.get("reason") or raw, 0.8))
    for rel in (parsed or {}).get("relations") or []:
        a, b = rel.get("from"), rel.get("to")
        tag = (rel.get("tag") or "").strip()
        pred = graph_relation_of(TAG_TO_PRED.get(tag) or tag or "COLLABORATE_WITH")
        if a and b and a != b:
            triples.append((a, pred, b, tag or raw, float(rel.get("confidence") or 0.7)))

    proj = event.get("related_project_id")
    if proj:
        for pid in involved:
            if pid:
                triples.append((pid, "WORKS_ON", proj, raw, 0.75))

    uniq = {}
    for item in triples:
        uniq[item[:3]] = item

    for subj_id, pred, obj_id, text, conf in uniq.values():
        key = f"event:{event_id}:{subj_id}|{pred}|{obj_id}"
        if key in seen:
            continue
        sub_name = names.get(subj_id, subj_id)
        obj_name = names.get(obj_id, obj_id)
        obj_type = GRAPH_OBJECT_TYPE.get(pred) or "Person"
        try:
            fact = create_fact({
                "subject": sub_name,
                "predicate": pred,
                "object": obj_name,
                "subject_type": "Person",
                "object_type": obj_type,
                "ontology_relation": pred,
                "valid_from": when,
                "confidence": conf,
                "extract_method": "event_log",
                "source_type": SOURCE_EVENT,
                "source_title": source_title,
                "source_text": text or raw,
                "source_ref": str(event_id),
                "origin_key": key,
            }, created_by=event.get("created_by") or "user")
            created.append(fact)
            seen.add(key)
        except Exception:
            continue
    return {"created": len(created), "facts": created, "event_id": event_id}


def ingest_confirmed_graph_relations(relations, text="", source_type="document", source_title="", entities=None):
    """关系网抽取：用户已确认 → 登记 Fact 并 confirm 写图。"""
    store = get_fact_store()
    confirmed, pending, skipped = [], [], []
    title = source_title or "LLM 关系抽取"
    snippet = (text or "")[:400]
    types = {}
    for ent in entities or []:
        name = (ent.get("name") or ent.get("id") or "").strip()
        if name:
            types[name] = ent.get("type") or "Person"
    for rel in relations or []:
        src = (rel.get("source") or "").strip()
        tgt = (rel.get("target") or "").strip()
        pred = graph_relation_of((rel.get("relation") or "").strip())
        if not src or not tgt or not pred:
            continue
        key = f"extract:{source_type}:{src}|{pred}|{tgt}"
        existing = store.get_by_origin_key(key)
        if existing:
            if existing.get("status") == STATUS_EXTRACTED:
                try:
                    confirmed.append(confirm_fact(existing["fact_id"]))
                except ValueError:
                    pending.append(existing)
            else:
                skipped.append(key)
            continue
        try:
            fact = create_fact({
                "subject": src,
                "predicate": pred,
                "object": tgt,
                "subject_type": types.get(src) or "Person",
                "object_type": types.get(tgt) or GRAPH_OBJECT_TYPE.get(pred) or "Person",
                "ontology_relation": pred,
                "confidence": float(rel.get("confidence") or 0.7),
                "extract_method": "graph_extract",
                "source_type": source_type,
                "source_title": title,
                "source_text": snippet or f"{src} {pred} {tgt}",
                "origin_key": key,
            }, created_by="extract")
        except Exception:
            continue
        try:
            confirmed.append(confirm_fact(fact["fact_id"]))
        except ValueError:
            pending.append(fact)
    if entities:
        from organization_graph.repository.facade import get_facade
        graph = get_facade()
        for ent in entities:
            name = (ent.get("name") or "").strip()
            if not name:
                continue
            try:
                _align_entity(graph, name, ent.get("type") or "Person")
            except Exception:
                continue
    return {
        "confirmed": len(confirmed),
        "pending": len(pending),
        "skipped": len(skipped),
        "facts": confirmed + pending,
        "applied": {"nodes": 0, "edges": len(confirmed)},
    }
