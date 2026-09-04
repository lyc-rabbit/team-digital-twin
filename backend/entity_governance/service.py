"""统一实体层服务：解析、检测、合并、撤销、影响力重算。"""

import json
import re
import threading
import uuid
from copy import deepcopy

from timeutil import now_iso

from organization_graph.algorithms.influence import compute_influence
from organization_graph.ontology.nodes import node_template
from organization_graph.ontology.resources import is_resource_hierarchy_pair
from organization_graph.repository.facade import get_facade

from .conflicts import detect_conflicts
from .matcher import EntityMatchEngine, build_alias_index
from .normalizer import normalize_text
from .repository import get_gov_store
from .survivorship import merge_fields, recommend_canonical
from .types import (
    CANDIDATE_AUTO_MERGED,
    CANDIDATE_MERGED,
    CANDIDATE_PENDING,
    CANDIDATE_REJECTED,
    DECISION_AUTO_MATCH,
    DECISION_FORCE_REVIEW,
    DECISION_MATCH,
    DECISION_NEW,
    DECISION_REVIEW,
    DEFAULT_SOURCE_BY_CONTEXT,
    ENTITY_TYPES,
    GOVERNANCE_RELATIONS,
    ID_PREFIX,
    LIFECYCLE_CANONICAL,
    LIFECYCLE_MERGED,
    LIFECYCLE_NEW,
    NO_AUTO_MERGE_TYPES,
    REVIEW_THRESHOLD,
    STATUS_ACTIVE,
    STATUS_MERGED,
    to_entity_type,
    to_graph_type,
)

REL_MERGED_INTO = "MERGED_INTO"

_lock = threading.RLock()
_detect_state = {"running": False, "progress": "", "last_result": None}


def _now():
    return now_iso()


def _store():
    return get_facade()


def _gov():
    return get_gov_store()


def make_entity_id(entity_type, name):
    raw = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", (name or "").strip()).strip("_")
    raw = raw.lower() or "unknown"
    prefix = ID_PREFIX.get(entity_type, "node")
    return f"{prefix}_{raw}"[:80]


def follow_canonical(entity_id):
    gov = _gov()
    seen = set()
    current = entity_id
    while current and current not in seen:
        seen.add(current)
        rec = gov.get_entity(current)
        if not rec:
            node = _store().get_node(current)
            if node and (node.get("entity_status") or STATUS_ACTIVE) == STATUS_MERGED:
                current = node.get("canonical_entity_id") or current
                continue
            return current
        if rec.get("status") == STATUS_MERGED and rec.get("canonical_entity_id"):
            current = rec["canonical_entity_id"]
            continue
        return rec["entity_id"]
    return current


def sync_graph_node_to_registry(node, source="graph"):
    if not node or not node.get("id"):
        return None
    gov = _gov()
    etype = to_entity_type(node.get("type"))
    existing = gov.get_entity(node["id"])
    payload = {
        "entity_id": node["id"],
        "entity_type": etype,
        "canonical_name": node.get("name") or node["id"],
        "status": node.get("entity_status") or (existing or {}).get("status") or STATUS_ACTIVE,
        "lifecycle": (existing or {}).get("lifecycle") or LIFECYCLE_CANONICAL,
        "source_count": (existing or {}).get("source_count") or 1,
        "confidence": (existing or {}).get("confidence") or 1.0,
        "canonical_source": (existing or {}).get("canonical_source") or source,
        "canonical_entity_id": node.get("canonical_entity_id") or (existing or {}).get("canonical_entity_id"),
        "metadata": {
            **((existing or {}).get("metadata") or {}),
            "graph_type": node.get("type"),
        },
    }
    rec = gov.upsert_entity(payload)
    gov.add_alias(node["id"], etype, node.get("name") or node["id"], source="sync")
    return rec


def bootstrap_from_graph():
    nodes = _list_graph_nodes(include_merged=True)
    count = 0
    for node in nodes:
        if not node.get("type"):
            continue
        sync_graph_node_to_registry(node, source="graph_bootstrap")
        count += 1
    return {"synced": count}


def _list_graph_nodes(include_merged=False):
    store = _store()
    try:
        return store.list_nodes(include_merged=include_merged)
    except TypeError:
        nodes = store.list_nodes()
        if include_merged:
            return nodes
        return [n for n in nodes if (n.get("entity_status") or STATUS_ACTIVE) == STATUS_ACTIVE]


def _list_graph_edges(include_merged=False):
    store = _store()
    try:
        return store.list_edges(include_merged=include_merged)
    except TypeError:
        return _filter_edges(store.list_edges(), include_merged)


def _filter_edges(edges, include_merged=False):
    if include_merged:
        return edges
    inactive = {
        n["id"]
        for n in _list_graph_nodes(include_merged=True)
        if (n.get("entity_status") or STATUS_ACTIVE) == STATUS_MERGED
    }
    out = []
    for e in edges:
        if e.get("relation") in GOVERNANCE_RELATIONS:
            continue
        if (e.get("properties") or {}).get("entity_status") == STATUS_MERGED:
            continue
        if e.get("source") in inactive or e.get("target") in inactive:
            continue
        out.append(e)
    return out


def resolve_entity(entity_type, name, attributes=None, source=None, preferred_id=None, create_if_new=True):
    """Normalize → Alias → Recall → Match。LLM 不决定是否同一实体。"""
    with _lock:
        return _resolve_unlocked(entity_type, name, attributes, source, preferred_id, create_if_new)


def _resolve_unlocked(entity_type, name, attributes=None, source=None, preferred_id=None, create_if_new=True):
    gov = _gov()
    store = _store()
    etype = to_entity_type(entity_type)
    gtype = to_graph_type(etype)
    name = (name or "").strip()
    attributes = dict(attributes or {})
    source = source or {}
    source_type = source.get("type") or "event"
    norm = normalize_text(name)

    alias = gov.find_alias(etype, norm) if norm else None
    if alias:
        cid = follow_canonical(alias["entity_id"])
        rec = gov.get_entity(cid)
        if rec and rec.get("status") == STATUS_ACTIVE:
            gov.add_alias(cid, etype, name, source=source_type)
            rec["source_count"] = int(rec.get("source_count") or 1) + 1
            gov.upsert_entity(rec)
            _append_evidence(cid, source, name)
            return {
                "decision": DECISION_MATCH,
                "canonical_entity_id": cid,
                "canonical_name": rec.get("canonical_name"),
                "score": 1.0,
                "via": "alias",
                "entity_type": etype,
            }

    if preferred_id:
        existing_node = store.get_node(preferred_id)
        if existing_node:
            cid = follow_canonical(preferred_id)
            sync_graph_node_to_registry(store.get_node(cid) or existing_node, source=source_type)
            gov.add_alias(cid, etype, name, source=source_type)
            return {
                "decision": DECISION_MATCH,
                "canonical_entity_id": cid,
                "canonical_name": (store.get_node(cid) or existing_node).get("name") or name,
                "score": 1.0,
                "via": "preferred_id",
                "entity_type": etype,
            }

    incoming = {
        "id": preferred_id or make_entity_id(etype, name),
        "type": gtype,
        "name": name,
        **attributes,
    }
    pool = [n for n in _list_graph_nodes() if n.get("type") == gtype]
    engine = EntityMatchEngine(store)
    alias_index = build_alias_index(gov.list_aliases(entity_type=etype))
    recalled = engine.recall(incoming, pool, alias_index)

    best = None
    for other in recalled:
        result = engine.match(incoming, other)
        if not best or result["score"] > best["score"]:
            best = result
            best["candidate_entity_id"] = other["id"]
            best["candidate_name"] = other.get("name")

    if best and best["decision"] == DECISION_AUTO_MATCH and etype not in NO_AUTO_MERGE_TYPES:
        cid = follow_canonical(best["candidate_entity_id"])
        rec = gov.get_entity(cid) or sync_graph_node_to_registry(store.get_node(cid), source_type)
        gov.add_alias(cid, etype, name, source=source_type)
        if rec:
            rec["source_count"] = int(rec.get("source_count") or 1) + 1
            gov.upsert_entity(rec)
        _append_evidence(cid, source, name)
        return {
            "decision": DECISION_MATCH,
            "canonical_entity_id": cid,
            "canonical_name": (rec or {}).get("canonical_name") or name,
            "score": best["score"],
            "via": "auto_match",
            "field_scores": best.get("field_scores"),
            "entity_type": etype,
        }

    if not create_if_new:
        return {
            "decision": DECISION_NEW if not best or best["score"] < REVIEW_THRESHOLD else DECISION_REVIEW,
            "canonical_entity_id": None,
            "score": (best or {}).get("score") or 0,
            "best": best,
            "entity_type": etype,
        }

    new_id = _unique_id(etype, name, preferred_id)
    graph_node = node_template(gtype, new_id, name, **attributes)
    graph_node["entity_status"] = STATUS_ACTIVE
    graph_node["canonical_entity_id"] = new_id
    store.upsert_node(graph_node)
    gov.upsert_entity({
        "entity_id": new_id,
        "entity_type": etype,
        "canonical_name": name,
        "status": STATUS_ACTIVE,
        "lifecycle": LIFECYCLE_NEW if not best else LIFECYCLE_CANONICAL,
        "source_count": 1,
        "canonical_source": DEFAULT_SOURCE_BY_CONTEXT.get(source_type, source_type),
        "canonical_entity_id": new_id,
        "metadata": {"graph_type": gtype},
    })
    gov.add_alias(new_id, etype, name, source=source_type)
    _append_evidence(new_id, source, name)

    decision = DECISION_NEW
    if best and best["score"] >= REVIEW_THRESHOLD:
        decision = DECISION_FORCE_REVIEW if best["decision"] == DECISION_FORCE_REVIEW else DECISION_REVIEW
        gov.upsert_candidate({
            **best,
            "entity_a_id": new_id,
            "entity_b_id": best["candidate_entity_id"],
            "status": CANDIDATE_PENDING,
        })

    return {
        "decision": decision,
        "canonical_entity_id": new_id,
        "canonical_name": name,
        "score": (best or {}).get("score") or 0.0,
        "via": "created",
        "candidate": best,
        "entity_type": etype,
    }


def _unique_id(etype, name, preferred_id=None):
    store = _store()
    gov = _gov()
    base = preferred_id or make_entity_id(etype, name)
    existing = store.get_node(base)
    if not existing:
        rec = gov.get_entity(base)
        if rec and rec.get("status") == STATUS_MERGED:
            return follow_canonical(base)
        return base
    if normalize_text(existing.get("name")) == normalize_text(name):
        return follow_canonical(base)
    for i in range(2, 30):
        cid = f"{base}_{i}"
        if not store.get_node(cid) and not gov.get_entity(cid):
            return cid
    return f"{base}_{uuid.uuid4().hex[:6]}"


def _append_evidence(entity_id, source, snippet):
    if not source:
        return
    _gov().add_evidence(
        entity_id,
        source_type=source.get("type") or "unknown",
        source_id=str(source.get("id") or ""),
        snippet=(snippet or "")[:200],
    )


def detect_duplicates(entity_types=None, force=True, auto_merge=True, operator="system"):
    global _detect_state
    with _lock:
        if _detect_state["running"]:
            return {"status": "running", "progress": _detect_state.get("progress")}
        _detect_state = {"running": True, "progress": "启动检测", "last_result": None}
    try:
        result = _detect_unlocked(entity_types, force, auto_merge, operator)
        _detect_state["last_result"] = result
        return result
    finally:
        _detect_state["running"] = False


def _detect_unlocked(entity_types, force, auto_merge, operator):
    gov = _gov()
    store = _store()
    bootstrap_from_graph()
    types = [to_entity_type(t) for t in (entity_types or ENTITY_TYPES)]
    if force:
        gov.clear_pending_candidates(types)

    engine = EntityMatchEngine(store)
    alias_index = build_alias_index(gov.list_aliases())
    influence_before = _influence_map()

    scanned = 0
    written = 0
    auto_merged = 0
    review_n = 0
    conflict_n = 0
    seen_pairs = set()
    nodes_by_type = {}
    for node in _list_graph_nodes():
        et = to_entity_type(node.get("type"))
        if et in types:
            nodes_by_type.setdefault(et, []).append(node)
            scanned += 1

    for etype, pool in nodes_by_type.items():
        _detect_state["progress"] = f"匹配 {etype}（{len(pool)}）"
        for entity in pool:
            if (entity.get("entity_status") or STATUS_ACTIVE) == STATUS_MERGED:
                continue
            recalled = engine.recall(entity, pool, alias_index)
            for other in recalled:
                if (other.get("entity_status") or STATUS_ACTIVE) == STATUS_MERGED:
                    continue
                pair = tuple(sorted([entity["id"], other["id"]]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                if etype == "RESOURCE" and is_resource_hierarchy_pair(entity, other):
                    continue
                result = engine.match(entity, other)
                if result["score"] < REVIEW_THRESHOLD:
                    continue
                status = CANDIDATE_PENDING
                merge_id = None
                if (
                    auto_merge
                    and result["decision"] == DECISION_AUTO_MATCH
                    and etype not in NO_AUTO_MERGE_TYPES
                    and not result.get("conflicts")
                ):
                    rec = recommend_canonical(
                        entity, other,
                        store.neighbors(entity["id"]),
                        store.neighbors(other["id"]),
                    )
                    target_id = rec["entity_id"]
                    source_id = other["id"] if target_id == entity["id"] else entity["id"]
                    try:
                        merged = merge_entities(
                            source_id, target_id,
                            reason="自动合并：高置信且无强冲突",
                            operator=operator,
                            score=result["score"],
                            evidence=result.get("evidence"),
                            skip_lock=True,
                        )
                        status = CANDIDATE_AUTO_MERGED
                        auto_merged += 1
                        merge_id = merged.get("merge_id")
                    except Exception as exc:
                        result["conflicts"] = list(result.get("conflicts") or []) + [{
                            "code": "AUTO_MERGE_FAILED",
                            "message": str(exc),
                            "severity": "medium",
                        }]
                        result["decision"] = DECISION_FORCE_REVIEW
                cand = gov.upsert_candidate({
                    **result,
                    "status": status,
                    "operator": operator,
                    "merge_id": merge_id,
                })
                written += 1
                if result["decision"] == DECISION_FORCE_REVIEW:
                    conflict_n += 1
                elif status == CANDIDATE_PENDING:
                    review_n += 1
                if cand and merge_id:
                    gov.update_candidate(cand["candidate_id"], status=status, merge_id=merge_id)

    influence_after = _write_influence()
    delta = _influence_delta(influence_before, influence_after)
    overview = get_overview()
    summary = {
        "status": "success",
        "scanned": scanned,
        "candidate_pairs": written,
        "auto_merged": auto_merged,
        "review": review_n,
        "conflicts": conflict_n,
        "high_confidence": auto_merged,
        "influence_delta": delta,
        "overview": overview,
    }
    gov.set_meta("last_detect", json.dumps(summary, ensure_ascii=False))
    gov.set_meta("last_detect_at", _now())
    _detect_state["progress"] = "完成"
    return summary


def get_detect_status():
    return {
        "running": _detect_state.get("running"),
        "progress": _detect_state.get("progress"),
        "last_result": _detect_state.get("last_result") or _loads_meta_detect(),
    }


def _loads_meta_detect():
    raw = _gov().get_meta("last_detect")
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def list_candidates(**kwargs):
    data = _gov().list_candidates(**kwargs)
    store = _store()
    for item in data["items"]:
        a = store.get_node(item["entity_a_id"])
        b = store.get_node(item["entity_b_id"])
        item["entity_a"] = _public_node(a) if a else {"id": item["entity_a_id"]}
        item["entity_b"] = _public_node(b) if b else {"id": item["entity_b_id"]}
        item["recommended_canonical"] = (
            recommend_canonical(a or {}, b or {}, store.neighbors(item["entity_a_id"]), store.neighbors(item["entity_b_id"]))
            if a and b else None
        )
    return data


def get_candidate_detail(candidate_id):
    gov = _gov()
    cand = gov.get_candidate(candidate_id)
    if not cand:
        return None
    store = _store()
    a = store.get_node(cand["entity_a_id"])
    b = store.get_node(cand["entity_b_id"])
    n_a = store.neighbors(cand["entity_a_id"]) if a else []
    n_b = store.neighbors(cand["entity_b_id"]) if b else []
    return {
        **cand,
        "entityA": _public_node(a, extra=True) if a else None,
        "entityB": _public_node(b, extra=True) if b else None,
        "neighborsA": _public_edges(n_a),
        "neighborsB": _public_edges(n_b),
        "aliasesA": gov.list_aliases(entity_id=cand["entity_a_id"]),
        "aliasesB": gov.list_aliases(entity_id=cand["entity_b_id"]),
        "recommended_canonical": recommend_canonical(a or {}, b or {}, n_a, n_b) if a and b else None,
        "evidenceA": gov.list_evidence(cand["entity_a_id"]),
        "evidenceB": gov.list_evidence(cand["entity_b_id"]),
    }


def merge_entities(
    source_entity_id, target_entity_id, reason="", operator="user",
    score=None, evidence=None, candidate_id=None, skip_lock=False,
):
    if source_entity_id == target_entity_id:
        raise ValueError("不能把实体合并到自身")
    if skip_lock:
        return _merge_unlocked(source_entity_id, target_entity_id, reason, operator, score, evidence, candidate_id)
    with _lock:
        return _merge_unlocked(source_entity_id, target_entity_id, reason, operator, score, evidence, candidate_id)


def _merge_unlocked(source_entity_id, target_entity_id, reason, operator, score, evidence, candidate_id):
    store = _store()
    gov = _gov()
    source = store.get_node(source_entity_id)
    target = store.get_node(target_entity_id)
    if not source or not target:
        raise ValueError("实体不存在于图谱")
    if source.get("type") != target.get("type"):
        raise ValueError("不同类型实体不能合并")
    if (source.get("entity_status") or STATUS_ACTIVE) == STATUS_MERGED:
        raise ValueError("源实体已经合并")
    if (target.get("entity_status") or STATUS_ACTIVE) == STATUS_MERGED:
        raise ValueError("目标实体不是 ACTIVE Canonical，请选择主实体")

    n_source = store.neighbors(source_entity_id)
    n_target = store.neighbors(target_entity_id)
    conflicts = detect_conflicts(source, target, to_entity_type(source.get("type")), n_source, n_target)
    influence_before = _influence_map()

    snapshot = {
        "source_node": deepcopy(source),
        "target_node": deepcopy(target),
        "source_edges": deepcopy(n_source),
        "target_edges": deepcopy(n_target),
        "created_aliases": [],
        "rewired_edge_ids": [],
        "created_edge_ids": [],
        "merged_edge_ids": [],
    }

    incoming_source = source.get("canonical_source") or "event"
    merged_node, field_log = merge_fields(target, source, incoming_source)
    merged_node["name"] = target.get("name")
    merged_node["id"] = target_entity_id
    merged_node["type"] = target.get("type")
    merged_node["entity_status"] = STATUS_ACTIVE
    merged_node["canonical_entity_id"] = target_entity_id
    merged_node["source_count"] = int(target.get("source_count") or 1) + int(source.get("source_count") or 1)
    store.upsert_node(merged_node)

    etype = to_entity_type(target.get("type"))
    from .normalizer import normalize_text
    src_norm = normalize_text(source.get("name") or "")
    existed_alias = gov.find_alias(etype, src_norm) if src_norm else True
    alias = gov.add_alias(target_entity_id, etype, source.get("name"), source="merge")
    if alias and not existed_alias:
        snapshot["created_aliases"].append(alias.get("alias_id"))
    gov.reassign_aliases(source_entity_id, target_entity_id)
    gov.reassign_evidence(source_entity_id, target_entity_id)

    for edge in n_source:
        props = dict(edge.get("properties") or {})
        old_id = edge.get("id") or f"{edge['source']}|{edge['relation']}|{edge['target']}"
        if edge.get("relation") in GOVERNANCE_RELATIONS:
            _mark_edge_merged(store, edge)
            snapshot["merged_edge_ids"].append(old_id)
            continue
        new_src = target_entity_id if edge["source"] == source_entity_id else edge["source"]
        new_tgt = target_entity_id if edge["target"] == source_entity_id else edge["target"]
        if new_src == new_tgt:
            _mark_edge_merged(store, edge)
            snapshot["merged_edge_ids"].append(old_id)
            continue
        new_props = dict(props)
        ids = list(new_props.get("source_relationship_ids") or [])
        if old_id not in ids:
            ids.append(old_id)
        new_props["source_relationship_ids"] = ids[:30]
        new_props["entity_status"] = STATUS_ACTIVE
        evid = list(new_props.get("evidence") or [])
        existing = store.get_edge(f"{new_src}|{edge['relation']}|{new_tgt}")
        if existing:
            merged_props = dict(existing.get("properties") or {})
            merged_props.update({k: v for k, v in new_props.items() if v not in (None, "", [], {})})
            try:
                merged_props["strength"] = max(
                    float(merged_props.get("strength") or 0),
                    float(new_props.get("strength") or 0),
                )
            except (TypeError, ValueError):
                pass
            ev = list(merged_props.get("evidence") or [])
            for item in evid:
                if item not in ev:
                    ev.append(item)
            merged_props["evidence"] = ev[:20]
            src_ids = list(merged_props.get("source_relationship_ids") or [])
            for x in ids:
                if x not in src_ids:
                    src_ids.append(x)
            merged_props["source_relationship_ids"] = src_ids[:30]
            merged_props["entity_status"] = STATUS_ACTIVE
            store.upsert_edge(new_src, new_tgt, edge["relation"], merged_props, record_history=False)
            snapshot["rewired_edge_ids"].append(f"{new_src}|{edge['relation']}|{new_tgt}")
        else:
            store.upsert_edge(new_src, new_tgt, edge["relation"], new_props, record_history=False)
            snapshot["created_edge_ids"].append(f"{new_src}|{edge['relation']}|{new_tgt}")
        _mark_edge_merged(store, edge)
        snapshot["merged_edge_ids"].append(old_id)

    merge_batch_id = f"batch_{uuid.uuid4().hex[:10]}"
    source_node = dict(source)
    source_node["entity_status"] = STATUS_MERGED
    source_node["canonical_entity_id"] = target_entity_id
    source_node["merge_batch_id"] = merge_batch_id
    source_node["merged_at"] = _now()
    store.upsert_node(source_node)
    store.upsert_edge(
        source_entity_id, target_entity_id, REL_MERGED_INTO,
        {"entity_status": STATUS_ACTIVE, "operator": operator, "reason": reason, "score": score or 0},
        record_history=False,
    )

    gov.upsert_entity({
        "entity_id": target_entity_id,
        "entity_type": etype,
        "canonical_name": merged_node.get("name"),
        "status": STATUS_ACTIVE,
        "lifecycle": LIFECYCLE_CANONICAL,
        "source_count": merged_node.get("source_count") or 1,
        "canonical_entity_id": target_entity_id,
    })
    gov.upsert_entity({
        "entity_id": source_entity_id,
        "entity_type": etype,
        "canonical_name": source.get("name"),
        "status": STATUS_MERGED,
        "lifecycle": LIFECYCLE_MERGED,
        "canonical_entity_id": target_entity_id,
        "merge_batch_id": merge_batch_id,
        "merged_at": _now(),
    })
    snapshot["field_log"] = field_log

    influence_after = _write_influence()
    delta = _influence_delta(influence_before, influence_after)
    merge_rec = gov.insert_merge({
        "source_entity_id": source_entity_id,
        "target_entity_id": target_entity_id,
        "operator": operator,
        "reason": reason or "人工确认同一实体",
        "score": score,
        "evidence": evidence or [{"conflicts": conflicts}, {"fields": field_log}],
        "candidate_id": candidate_id,
        "snapshot": snapshot,
        "influence_before": influence_before,
        "influence_after": influence_after,
        "influence_delta": delta,
    })
    status = CANDIDATE_AUTO_MERGED if operator == "system" else CANDIDATE_MERGED
    if candidate_id:
        gov.update_candidate(candidate_id, status=status, merge_id=merge_rec["merge_id"], operator=operator, reason=reason)
    else:
        pair = gov.get_candidate_pair(source_entity_id, target_entity_id)
        if pair:
            gov.update_candidate(pair["candidate_id"], status=status, merge_id=merge_rec["merge_id"], operator=operator, reason=reason)

    return {
        "merge_id": merge_rec["merge_id"],
        "canonical_entity_id": target_entity_id,
        "canonical_name": merged_node.get("name"),
        "source_entity_id": source_entity_id,
        "aliases": [a["value"] for a in gov.list_aliases(entity_id=target_entity_id)],
        "influence_delta": delta,
        "conflicts": conflicts,
        "field_log": field_log,
    }


def _mark_edge_merged(store, edge):
    props = dict(edge.get("properties") or {})
    props["entity_status"] = STATUS_MERGED
    store.upsert_edge(edge["source"], edge["target"], edge["relation"], props, record_history=False)


def unmerge(merge_id, operator="user"):
    with _lock:
        return _unmerge_unlocked(merge_id, operator)


def _unmerge_unlocked(merge_id, operator):
    gov = _gov()
    store = _store()
    rec = gov.get_merge(merge_id)
    if not rec:
        raise ValueError("合并记录不存在")
    if rec.get("unmerged"):
        raise ValueError("该合并已经撤销")
    snap = rec.get("snapshot") or {}
    source_node = snap.get("source_node")
    target_node = snap.get("target_node")
    if not source_node or not target_node:
        raise ValueError("快照不完整，无法撤销（不会新建节点冒充原实体）")

    current_source = store.get_node(rec["source_entity_id"])
    if current_source and (current_source.get("entity_status") or STATUS_ACTIVE) == STATUS_ACTIVE:
        raise ValueError("源实体已是独立实体，无需撤销")
    current_target = store.get_node(rec["target_entity_id"])
    if current_target and (current_target.get("entity_status") or STATUS_ACTIVE) == STATUS_MERGED:
        raise ValueError("主实体随后又被合并，请先撤销后续合并")

    restored_source = dict(source_node)
    restored_source["entity_status"] = STATUS_ACTIVE
    restored_source["canonical_entity_id"] = restored_source.get("id")
    restored_source.pop("merge_batch_id", None)
    restored_source.pop("merged_at", None)
    store.upsert_node(restored_source)

    restored_target = dict(target_node)
    restored_target["entity_status"] = STATUS_ACTIVE
    restored_target["canonical_entity_id"] = restored_target.get("id")
    store.upsert_node(restored_target)

    for edge in (snap.get("source_edges") or []) + (snap.get("target_edges") or []):
        props = dict(edge.get("properties") or {})
        props["entity_status"] = STATUS_ACTIVE
        store.upsert_edge(edge["source"], edge["target"], edge["relation"], props, record_history=False)

    for eid in snap.get("created_edge_ids") or []:
        parts = str(eid).split("|")
        if len(parts) == 3:
            existing = store.get_edge(eid)
            if existing:
                props = dict(existing.get("properties") or {})
                props["entity_status"] = STATUS_MERGED
                store.upsert_edge(parts[0], parts[2], parts[1], props, record_history=False)

    for edge in store.list_edges(
        relation=REL_MERGED_INTO,
        source=rec["source_entity_id"],
        target=rec["target_entity_id"],
        include_merged=True,
    ):
        _mark_edge_merged(store, edge)

    gov.delete_aliases(snap.get("created_aliases") or [])
    etype = to_entity_type(source_node.get("type"))
    gov.upsert_entity({
        "entity_id": rec["source_entity_id"],
        "entity_type": etype,
        "canonical_name": source_node.get("name"),
        "status": STATUS_ACTIVE,
        "lifecycle": LIFECYCLE_CANONICAL,
        "canonical_entity_id": rec["source_entity_id"],
        "merge_batch_id": None,
        "merged_at": None,
    })
    gov.upsert_entity({
        "entity_id": rec["target_entity_id"],
        "entity_type": etype,
        "canonical_name": target_node.get("name"),
        "status": STATUS_ACTIVE,
        "lifecycle": LIFECYCLE_CANONICAL,
        "canonical_entity_id": rec["target_entity_id"],
    })
    gov.add_alias(rec["source_entity_id"], etype, source_node.get("name"), source="unmerge")
    gov.mark_unmerged(merge_id, operator)
    if rec.get("candidate_id"):
        gov.update_candidate(rec["candidate_id"], status=CANDIDATE_PENDING, operator=operator, reason="已撤销合并")

    influence = _write_influence()
    return {
        "merge_id": merge_id,
        "restored_entity_id": rec["source_entity_id"],
        "canonical_entity_id": rec["target_entity_id"],
        "influence": influence,
    }


def reject_candidate(candidate_id, reason="", operator="user"):
    cand = _gov().get_candidate(candidate_id)
    if not cand:
        raise ValueError("候选不存在")
    _gov().update_candidate(candidate_id, status=CANDIDATE_REJECTED, operator=operator, reason=reason or "不是同一实体")
    return _gov().get_candidate(candidate_id)


def skip_candidate(candidate_id, operator="user"):
    cand = _gov().get_candidate(candidate_id)
    if not cand:
        raise ValueError("候选不存在")
    _gov().update_candidate(candidate_id, status="skipped", operator=operator, reason="暂不处理")
    return _gov().get_candidate(candidate_id)


def add_alias(entity_id, value, source="manual"):
    node = _store().get_node(entity_id)
    rec = _gov().get_entity(entity_id)
    if not node and not rec:
        raise ValueError("实体不存在")
    etype = (rec or {}).get("entity_type") or to_entity_type((node or {}).get("type"))
    cid = follow_canonical(entity_id)
    alias = _gov().add_alias(cid, etype, value, source=source)
    if not alias:
        raise ValueError("别名无效或已占用")
    return alias


def list_merges(include_unmerged=True, limit=100):
    return _gov().list_merges(include_unmerged=include_unmerged, limit=limit)


def get_merge(merge_id):
    rec = _gov().get_merge(merge_id)
    if not rec:
        return None
    store = _store()
    rec["source_entity"] = _public_node(store.get_node(rec["source_entity_id"]), extra=True)
    rec["target_entity"] = _public_node(store.get_node(rec["target_entity_id"]), extra=True)
    return rec


def get_overview():
    gov = _gov()
    store = _store()
    bootstrap_from_graph()
    nodes = _list_graph_nodes(include_merged=True)
    active = [n for n in nodes if (n.get("entity_status") or STATUS_ACTIVE) == STATUS_ACTIVE]
    merged = [n for n in nodes if (n.get("entity_status") or STATUS_ACTIVE) == STATUS_MERGED]
    counts = gov.candidate_counts()
    pending = 0
    auto_n = 0
    conflict_n = 0
    done_n = 0
    for row in counts:
        n = int(row.get("c") or 0)
        if row.get("decision") == DECISION_FORCE_REVIEW and row.get("status") == CANDIDATE_PENDING:
            conflict_n += n
        if row.get("status") == CANDIDATE_PENDING:
            pending += n
        if row.get("status") == CANDIDATE_AUTO_MERGED:
            auto_n += n
        if row.get("status") in (CANDIDATE_MERGED, CANDIDATE_AUTO_MERGED, CANDIDATE_REJECTED):
            done_n += n
    total = len(nodes) or 1
    duplicate_rate = round(len(merged) / total, 4)
    resolved = len(active) + len(merged)
    auto_merges, false_merges = gov.auto_merge_stats()
    cand_total = sum(int(r.get("c") or 0) for r in counts) or 1
    return {
        "total_entities": len(nodes),
        "canonical_entities": len(active),
        "alias_count": gov.count_aliases(),
        "merged_count": len(merged),
        "pending_review": pending,
        "auto_merged": auto_n,
        "conflicts": conflict_n,
        "processed": done_n,
        "duplicate_rate": duplicate_rate,
        "duplicate_rate_pct": round(duplicate_rate * 100, 1),
        "resolution_rate": round(resolved / total, 4),
        "auto_resolution_rate": round(auto_merges / max(auto_merges + done_n - auto_n, 1), 4) if (auto_merges or done_n) else 0,
        "conflict_rate": round(conflict_n / cand_total, 4),
        "false_merge_rate": round(false_merges / auto_merges, 4) if auto_merges else 0.0,
        "graph_stats": store.stats(),
        "last_detect_at": gov.get_meta("last_detect_at"),
        "by_type": _count_by_type(active),
    }


def _count_by_type(nodes):
    out = {}
    for n in nodes:
        t = n.get("type") or "Unknown"
        out[t] = out.get(t, 0) + 1
    return out


def _influence_map():
    nodes = _list_graph_nodes()
    edges = _list_graph_edges()
    raw = compute_influence(nodes, edges)
    return {
        pid: {
            "id": pid,
            "name": info.get("name"),
            "influence_score": info.get("influence_score"),
            "connections": info.get("connections"),
            "degree": info.get("degree"),
            "betweenness": info.get("betweenness"),
            "pagerank": info.get("pagerank"),
        }
        for pid, info in raw.items()
    }


def _write_influence():
    store = _store()
    inf = _influence_map()
    for pid, info in inf.items():
        node = store.get_node(pid)
        if node:
            node["influence_score"] = info["influence_score"]
            store.upsert_node(node)
    return inf


def _influence_delta(before, after):
    items = []
    ids = set(before) | set(after)
    for pid in ids:
        b = (before.get(pid) or {}).get("influence_score")
        a = (after.get(pid) or {}).get("influence_score")
        if b is None and a is None:
            continue
        if b == a:
            continue
        bc = (before.get(pid) or {}).get("connections") or 0
        ac = (after.get(pid) or {}).get("connections") or 0
        name = (after.get(pid) or before.get(pid) or {}).get("name") or pid
        reasons = []
        if ac != bc:
            reasons.append(f"关系数量{ac - bc:+d}")
        items.append({
            "id": pid,
            "name": name,
            "before": b,
            "after": a,
            "delta": (a or 0) - (b or 0),
            "connections_before": bc,
            "connections_after": ac,
            "reason": "；".join(reasons) or "实体合并后中心性重算",
        })
    items.sort(key=lambda x: abs(x.get("delta") or 0), reverse=True)
    return items[:30]


def _public_node(node, extra=False):
    if not node:
        return None
    base = {
        "id": node.get("id"),
        "type": node.get("type"),
        "name": node.get("name"),
        "entity_status": node.get("entity_status") or STATUS_ACTIVE,
        "canonical_entity_id": node.get("canonical_entity_id") or node.get("id"),
        "department": node.get("department"),
        "position": node.get("position"),
        "owner": node.get("owner"),
        "status": node.get("status"),
        "time": node.get("time"),
        "domain": node.get("domain"),
        "category": node.get("category"),
        "url": node.get("url") or node.get("repo"),
        "description": node.get("description"),
        "influence_score": node.get("influence_score"),
        "source_count": node.get("source_count"),
        "updated_at": node.get("updated_at"),
    }
    if extra:
        skip = set(base) | {"metadata"}
        base["attributes"] = {k: v for k, v in node.items() if k not in skip}
    return base


def _public_edges(edges):
    out = []
    for e in edges or []:
        if e.get("relation") in GOVERNANCE_RELATIONS:
            continue
        out.append({
            "id": e.get("id"),
            "source": e.get("source"),
            "target": e.get("target"),
            "relation": e.get("relation"),
            "properties": e.get("properties") or {},
        })
    return out
