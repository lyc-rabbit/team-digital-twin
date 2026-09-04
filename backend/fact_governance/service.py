"""事实治理业务：确认写图、删除失效下游、禁止原地修改。"""

import re

from database import get_all_members
from organization_graph.ontology.nodes import node_template
from organization_graph.ontology.relations import relation_template
from organization_graph.repository.facade import get_facade
from timeutil import now_iso

from .conflicts import apply_conflict_flags, find_conflicts
from .extractor import extract_facts
from .repository import get_fact_store
from .types import (
    DERIVED_DELETED,
    DERIVED_INVALID,
    DERIVED_STALE,
    GRAPH_OBJECT_TYPE,
    IMPACT_BY_KIND,
    IMPACT_LABEL,
    IMPACT_MUST_DELETE,
    IMPACT_NONE,
    IMPACT_STALE,
    KIND_DAILY_REPORT,
    KIND_GRAPH_NODE,
    KIND_GRAPH_RELATION,
    KIND_INFLUENCE,
    KIND_LABEL,
    KIND_PERSON_NETWORK,
    KIND_PROMOTION,
    KIND_ROLE_RANKING,
    KIND_TEAM_SITUATION,
    LINK_DIRECT,
    LINK_INDIRECT,
    METHOD_MANUAL,
    SOURCE_MANUAL,
    STATUS_CONFIRMED,
    STATUS_DELETED,
    STATUS_EXTRACTED,
    STATUS_REJECTED,
    STATUS_SUPERSEDED,
    graph_relation_of,
    ontology_relation_of,
)


def _graph():
    return get_facade()


def overview():
    imported = ingest_legacy()
    data = get_fact_store().overview()
    data["legacy"] = imported
    return data


def list_facts(status=None, q=None, page=1, page_size=80):
    return get_fact_store().list_facts(status=status, q=q, page=page, page_size=page_size)


def get_fact(fact_id):
    store = get_fact_store()
    fact = store.get_fact(fact_id)
    if not fact:
        raise ValueError("事实不存在")
    fact["lineage"] = store.lineage_tree(fact_id)
    fact["impact"] = impact_preview(fact_id)
    return fact


def create_fact(payload, sources=None, created_by="user"):
    store = get_fact_store()
    rec = {
        "subject": (payload.get("subject") or "").strip(),
        "predicate": (payload.get("predicate") or "").strip(),
        "object": (payload.get("object") or "").strip(),
        "fact_type": payload.get("fact_type") or "RELATION",
        "subject_type": payload.get("subject_type") or "",
        "object_type": payload.get("object_type") or "",
        "ontology_relation": payload.get("ontology_relation") or ontology_relation_of(payload.get("predicate")),
        "valid_from": payload.get("valid_from") or "",
        "valid_to": payload.get("valid_to") or "",
        "confidence": payload.get("confidence") if payload.get("confidence") is not None else 1.0,
        "extract_method": payload.get("extract_method") or METHOD_MANUAL,
        "extract_model": payload.get("extract_model") or "",
        "extract_job_id": payload.get("extract_job_id") or "",
        "supersedes": payload.get("supersedes") or "",
        "created_by": created_by,
        "extract_raw": payload.get("extract_raw") or {},
        "origin_key": payload.get("origin_key") or "",
        "status": payload.get("status") or STATUS_EXTRACTED,
    }
    if not rec["subject"] or not rec["predicate"] or not rec["object"]:
        raise ValueError("主体、谓词、客体都不能为空")
    srcs = sources if sources is not None else [{
        "source_type": payload.get("source_type") or SOURCE_MANUAL,
        "title": payload.get("source_title") or "人工录入",
        "page": payload.get("page") or "",
        "source_text": payload.get("source_text") or "",
        "source_ref": payload.get("source_ref") or "",
        "locator": payload.get("locator") or "",
    }]
    fact = store.insert_fact(rec, srcs)
    apply_conflict_flags(store, fact)
    return store.get_fact(fact["fact_id"])


def confirm_fact(fact_id, operator="user"):
    store = get_fact_store()
    fact = store.get_fact(fact_id)
    if not fact:
        raise ValueError("事实不存在")
    if fact["status"] in (STATUS_DELETED, STATUS_REJECTED, STATUS_SUPERSEDED):
        raise ValueError("终态事实不能确认")
    others = [f for f in store.list_active_facts() if f["fact_id"] != fact_id]
    if find_conflicts(fact, others):
        apply_conflict_flags(store, fact)
        raise ValueError("存在未解决冲突，请先处理冲突或修改时间后再确认")

    graph = _graph()
    rel = graph_relation_of(fact.get("ontology_relation") or fact.get("predicate"))
    obj_type = (fact.get("object_type") or "").strip() or GRAPH_OBJECT_TYPE.get(rel) or "Person"
    sub_id = _align_entity(graph, fact["subject"], fact.get("subject_type") or "Person")
    obj_id = _align_entity(graph, fact["object"], obj_type)
    props = relation_template(sub_id, obj_id, rel, inferred=False, semantic=True, strength=float(fact.get("confidence") or 0.7))["properties"]
    props.update({
        "fact_id": fact_id,
        "confirmed": True,
        "predicate": fact["predicate"],
        "valid_from": fact.get("valid_from") or "",
        "valid_to": fact.get("valid_to") or "",
        "evidence_fact": fact_id,
    })
    graph.upsert_edge(sub_id, obj_id, rel, props, record_history=False)
    edge_id = f"{sub_id}|{rel}|{obj_id}"
    _bind_lineage(store, fact, sub_id, obj_id, rel, edge_id)
    store.resolve_conflicts_for(fact_id)
    store.update_fact_status(fact_id, STATUS_CONFIRMED, ontology_relation=rel)
    return get_fact(fact_id)


def reject_fact(fact_id, reason="", operator="user"):
    store = get_fact_store()
    fact = store.get_fact(fact_id)
    if not fact:
        raise ValueError("事实不存在")
    store.resolve_conflicts_for(fact_id)
    return store.update_fact_status(fact_id, STATUS_REJECTED, delete_reason=reason)


def impact_preview(fact_id):
    store = get_fact_store()
    deps = store.list_dependencies(fact_id)
    groups = {k: [] for k in ("must_delete", "recompute", "stale", "none")}
    if not deps:
        groups["none"].append({"kind": KIND_DAILY_REPORT, "title": "日报 / 项目基础信息", "label": IMPACT_LABEL[IMPACT_NONE]})
    for d in deps:
        level = IMPACT_BY_KIND.get(d.get("kind"), IMPACT_STALE)
        item = {
            "derived_id": d["derived_id"],
            "kind": d.get("kind"),
            "kind_label": KIND_LABEL.get(d.get("kind"), d.get("kind")),
            "title": d.get("title") or d.get("object_id"),
            "link_kind": d.get("link_kind"),
            "label": IMPACT_LABEL.get(level, level),
            "level": level,
        }
        groups.setdefault(level, []).append(item)
    direct = [d for d in deps if d.get("link_kind") == LINK_DIRECT]
    indirect = [d for d in deps if d.get("link_kind") == LINK_INDIRECT]
    return {
        "fact_id": fact_id,
        "downstream_count": len(deps),
        "direct_count": len(direct),
        "indirect_count": len(indirect),
        "groups": groups,
        "tree": store.lineage_tree(fact_id),
    }


def delete_fact(fact_id, options=None, operator="user"):
    """软删除。默认：删事实 + 删仅由此事实支撑的直接关系 + 下游标 STALE。不自动重算。"""
    options = options or {}
    store = get_fact_store()
    fact = store.get_fact(fact_id)
    if not fact:
        raise ValueError("事实不存在")
    if fact["status"] == STATUS_DELETED:
        return {"fact": fact, "already_deleted": True}

    do_fact = options.get("delete_fact", True)
    do_direct = options.get("delete_direct_relations", True)
    do_stale = options.get("stale_downstream", True)
    auto_rebuild = options.get("auto_rebuild", False)
    reason = options.get("reason") or "用户删除"
    impact = impact_preview(fact_id)
    actions = {"relations_removed": [], "stale": [], "rebuild_tasks": []}

    if do_direct:
        graph = _graph()
        for b in fact.get("relation_bindings") or []:
            edge_id = b.get("graph_edge_id")
            if not edge_id:
                continue
            supporters = [
                x for x in store.relation_bindings_for_edge(edge_id)
                if x.get("fact_id") != fact_id and x.get("fact_status") == STATUS_CONFIRMED
            ]
            if supporters:
                continue
            parts = edge_id.split("|")
            if len(parts) == 3:
                graph.delete_edge(parts[0], parts[2], parts[1])
                actions["relations_removed"].append(edge_id)
            for d in store.list_dependencies(fact_id):
                if d.get("kind") == KIND_GRAPH_RELATION and d.get("object_id") == edge_id:
                    store.mark_derived(d["derived_id"], DERIVED_DELETED, f"事实 {fact_id} 删除")

    if do_stale:
        for d in store.list_dependencies(fact_id):
            if d.get("kind") == KIND_GRAPH_RELATION:
                continue
            store.mark_derived(d["derived_id"], DERIVED_STALE if d.get("link_kind") == LINK_INDIRECT else DERIVED_INVALID, f"事实 {fact_id} 删除")
            actions["stale"].append(d["derived_id"])
            tid = store.add_rebuild_task(fact_id, d["derived_id"], d.get("kind"), d.get("title"))
            actions["rebuild_tasks"].append(tid)

    store.resolve_conflicts_for(fact_id)
    updated = fact
    if do_fact:
        updated = store.update_fact_status(
            fact_id, STATUS_DELETED, deleted_by=operator, delete_reason=reason,
        )

    rebuilt = []
    if auto_rebuild:
        rebuilt = _run_rebuild(actions["rebuild_tasks"])

    return {
        "fact": updated,
        "impact": impact,
        "actions": actions,
        "auto_rebuild": auto_rebuild,
        "rebuilt": rebuilt,
    }


def supersede_fact(fact_id, payload, operator="user"):
    """不允许 Edit：旧事实 SUPERSEDED，新建事实。"""
    store = get_fact_store()
    old = store.get_fact(fact_id)
    if not old:
        raise ValueError("事实不存在")
    delete_fact(fact_id, {
        "delete_fact": False,
        "delete_direct_relations": True,
        "stale_downstream": True,
        "auto_rebuild": False,
        "reason": "被新事实替代",
    }, operator=operator)
    payload = dict(payload or {})
    payload["supersedes"] = fact_id
    if not payload.get("subject"):
        payload["subject"] = old["subject"]
    if not payload.get("object"):
        payload["object"] = old["object"]
    sources = old.get("sources") or []
    new_fact = create_fact(payload, sources=[{
        "source_type": s.get("source_type"),
        "source_ref": s.get("source_ref"),
        "title": s.get("title"),
        "page": s.get("page"),
        "source_text": s.get("source_text") or f"替代 {fact_id}",
        "locator": s.get("locator"),
    } for s in sources] or None, created_by=operator)
    store.update_fact_status(fact_id, STATUS_SUPERSEDED, superseded_by=new_fact["fact_id"], deleted_by=operator, delete_reason="被新事实替代")
    return {"old": store.get_fact(fact_id), "new": new_fact}


def run_extract(text, source_title="", source_type="document", page="", members=None, created_by="user"):
    store = get_fact_store()
    members = members if members is not None else get_all_members()
    job = store.insert_job({
        "source_type": source_type,
        "source_title": source_title or "未命名文档",
        "source_text": text or "",
        "status": "running",
        "model": "",
    })
    result = extract_facts(text, members, source_type=source_type)
    created = []
    seen = store.origin_keys()
    for item in result.get("facts") or []:
        pred = graph_relation_of(item.get("predicate") or item.get("ontology_relation"))
        subj = (item.get("subject") or "").strip()
        obj = (item.get("object") or "").strip()
        key = f"extract:{source_type}:{subj}|{pred}|{obj}" if subj and obj and pred else ""
        if key and key in seen:
            continue
        fact = create_fact({
            **item,
            "predicate": pred or item.get("predicate"),
            "ontology_relation": pred or item.get("ontology_relation"),
            "extract_job_id": job["job_id"],
            "extract_method": result.get("method") or "llm_extract",
            "extract_model": result.get("model") or "",
            "source_type": source_type,
            "source_title": source_title or "未命名文档",
            "source_text": item.get("source_text") or (text or "")[:400],
            "page": page,
            "origin_key": key,
        }, created_by=created_by)
        created.append(fact)
        if key:
            seen.add(key)
    store.update_job(job["job_id"], status="done", model=result.get("model") or "", fact_count=len(created))
    return {
        "job": store.get_job(job["job_id"]),
        "facts": created,
        "degraded": result.get("degraded"),
        "mock_mode": result.get("mock_mode"),
    }


def list_jobs():
    return {"items": get_fact_store().list_jobs()}


def list_conflicts():
    return {"items": get_fact_store().list_conflicts()}


def list_rebuild_tasks():
    return {"items": get_fact_store().list_rebuild_tasks()}


SKIP_RELATIONS = frozenset({"MERGED_INTO", "ALIAS_OF"})


def ingest_legacy():
    """把已有图谱边、时态事实灌进事实层。幂等，不重复导入。"""
    store = get_fact_store()
    seen = store.origin_keys()
    graph = _graph()
    try:
        nodes = {n["id"]: n for n in graph.list_nodes(include_merged=True)}
    except TypeError:
        nodes = {n["id"]: n for n in graph.list_nodes()}
    try:
        edges = graph.list_edges(include_merged=False)
    except TypeError:
        edges = graph.list_edges()

    imported, skipped = 0, 0
    new_facts = []

    for e in edges:
        rel = e.get("relation") or ""
        if rel in SKIP_RELATIONS:
            skipped += 1
            continue
        src, tgt = e.get("source"), e.get("target")
        if not src or not tgt or src == tgt:
            skipped += 1
            continue
        key = f"graph:{src}|{rel}|{tgt}"
        if key in seen:
            skipped += 1
            continue
        src_n = nodes.get(src) or {}
        tgt_n = nodes.get(tgt) or {}
        props = e.get("properties") or {}
        inferred = bool(props.get("inferred")) and not props.get("confirmed")
        status = STATUS_EXTRACTED if inferred else STATUS_CONFIRMED
        evidence = props.get("explanation") or ""
        if isinstance(props.get("evidence"), list) and props["evidence"]:
            evidence = evidence or " ".join(str(x) for x in props["evidence"][:3])
        fact = store.insert_fact({
            "subject": src_n.get("name") or src,
            "predicate": rel,
            "object": tgt_n.get("name") or tgt,
            "subject_type": src_n.get("type") or "",
            "object_type": tgt_n.get("type") or "",
            "ontology_relation": rel,
            "fact_type": "RELATION",
            "valid_from": props.get("valid_from") or "",
            "valid_to": props.get("valid_to") or "",
            "status": status,
            "confidence": float(props.get("strength") or 0.7),
            "extract_method": "legacy_graph",
            "created_by": "system",
            "origin_key": key,
            "extra": {"origin": "graph", "edge_id": e.get("id") or key[6:]},
        }, sources=[{
            "source_type": "graph",
            "title": "已有知识图谱关系",
            "source_text": evidence or f"{src_n.get('name') or src} {rel} {tgt_n.get('name') or tgt}",
            "source_ref": e.get("id") or "",
        }])
        _bind_lineage(store, fact, src, tgt, rel, e.get("id") or f"{src}|{rel}|{tgt}")
        seen.add(key)
        imported += 1
        new_facts.append(fact)

    try:
        from temporal_graph.repository import get_temporal_store
        tfacts = get_temporal_store().list_facts()
    except Exception:
        tfacts = []
    for tf in tfacts or []:
        key = f"temporal:{tf.get('id')}"
        if key in seen:
            skipped += 1
            continue
        src, rel, tgt = tf.get("subject_id"), tf.get("predicate"), tf.get("object_id")
        gkey = f"graph:{src}|{rel}|{tgt}"
        if gkey in seen and not tf.get("valid_to"):
            skipped += 1
            continue
        src_n = nodes.get(src) or {}
        tgt_n = nodes.get(tgt) or {}
        ev = tf.get("evidence") if isinstance(tf.get("evidence"), dict) else {}
        fact = store.insert_fact({
            "subject": src_n.get("name") or src,
            "predicate": rel,
            "object": tgt_n.get("name") or tgt,
            "subject_type": src_n.get("type") or "",
            "object_type": tgt_n.get("type") or "",
            "ontology_relation": rel,
            "valid_from": tf.get("valid_from") or "",
            "valid_to": tf.get("valid_to") or "",
            "status": STATUS_CONFIRMED,
            "confidence": float(tf.get("confidence") or 0.7),
            "extract_method": "legacy_temporal",
            "created_by": "system",
            "origin_key": key,
            "extra": {"origin": "temporal", "temporal_id": tf.get("id"), "source_event_id": tf.get("source_event_id")},
        }, sources=[{
            "source_type": "event" if tf.get("source_event_id") else "graph",
            "title": "时态事实",
            "source_ref": tf.get("source_event_id") or "",
            "source_text": (ev or {}).get("explanation") or "",
        }])
        _bind_lineage(store, fact, src, tgt, rel, f"{src}|{rel}|{tgt}")
        seen.add(key)
        imported += 1
        new_facts.append(fact)

    for fact in new_facts:
        apply_conflict_flags(store, store.get_fact(fact["fact_id"]))

    return {"imported": imported, "skipped": skipped}


def _bind_lineage(store, fact, sub_id, obj_id, rel, edge_id):
    fact_id = fact["fact_id"]
    existing = fact.get("relation_bindings") or []
    if not any(b.get("graph_edge_id") == edge_id for b in existing):
        store.add_entity_binding(fact_id, "subject", fact.get("subject"), fact.get("subject_type"), sub_id)
        store.add_entity_binding(fact_id, "object", fact.get("object"), fact.get("object_type"), obj_id)
        store.add_relation_binding(fact_id, edge_id, rel, sub_id, obj_id)
    d_rel = store.ensure_derived(KIND_GRAPH_RELATION, edge_id, f"{fact.get('subject')} —{fact.get('predicate')}→ {fact.get('object')}")
    d_sub = store.ensure_derived(KIND_GRAPH_NODE, sub_id, fact.get("subject") or sub_id)
    d_obj = store.ensure_derived(KIND_GRAPH_NODE, obj_id, fact.get("object") or obj_id)
    store.add_dependency(fact_id, d_rel, LINK_DIRECT)
    store.add_dependency(fact_id, d_sub, LINK_DIRECT)
    store.add_dependency(fact_id, d_obj, LINK_DIRECT)
    for kind, oid, title in _indirect_consumers(sub_id, obj_id, fact):
        did = store.ensure_derived(kind, oid, title)
        store.add_dependency(fact_id, did, LINK_INDIRECT)


def _align_entity(graph, name, hint_type):
    name = (name or "").strip()
    if not name:
        raise ValueError("实体名为空")
    node = graph.get_node(name)
    if node:
        return node["id"]
    try:
        nodes = graph.list_nodes(include_merged=False)
    except TypeError:
        nodes = graph.list_nodes()
    for n in nodes:
        if (n.get("name") or "") == name:
            return n["id"]
    members = get_all_members() or []
    for m in members:
        if m.get("name") == name:
            nid = m.get("id") or _id_of("Person", name)
            existing = graph.get_node(nid)
            if existing:
                return existing["id"]
            graph.upsert_node(node_template("Person", nid, name, position=m.get("role") or ""))
            return nid
    etype = hint_type if hint_type in (
        "Person", "Project", "Organization", "Task", "Event", "Resource", "Role", "Capability",
        "Department", "InformalGroup", "Knowledge", "Achievement", "Contribution",
        "TrainingAction", "CapabilityEvidence", "ProjectStage",
    ) else "Resource"
    if etype == "Organization":
        etype = "InformalGroup"
    nid = _id_of(etype, name)
    existing = graph.get_node(nid)
    if existing:
        return existing["id"]
    graph.upsert_node(node_template(etype if etype in (
        "Person", "Role", "Department", "Project", "Resource", "Knowledge", "Event", "InformalGroup",
        "Achievement", "Contribution", "TrainingAction", "CapabilityEvidence", "ProjectStage", "Capability",
    ) else "Resource", nid, name))
    return nid


def _id_of(etype, name):
    slug = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", name).strip("_").lower()
    prefix = {
        "Project": "project", "Event": "event", "Resource": "resource",
        "Knowledge": "knowledge", "InformalGroup": "group", "Department": "dept",
        "Role": "role", "Person": "person", "Task": "task", "Capability": "cap",
    }.get(etype, "node")
    return f"{prefix}_{slug}"[:80]


def _indirect_consumers(sub_id, obj_id, fact):
    name = fact.get("subject") or sub_id
    return [
        (KIND_PERSON_NETWORK, sub_id, f"{name} 人物关系网"),
        (KIND_INFLUENCE, "ranking", "影响力排名"),
        (KIND_TEAM_SITUATION, "latest", "团队态势"),
        (KIND_ROLE_RANKING, "ai-native", "角色竞争排名"),
        (KIND_PROMOTION, sub_id, f"{name} 晋升推演"),
        (KIND_DAILY_REPORT, "base", "日报 / 项目基础信息"),
    ]


def _run_rebuild(task_ids):
    """默认不跑。占位：只把任务标为 DONE，真正重算由各模块入口触发。"""
    return [{"task_id": t, "status": "skipped", "note": "未默认自动重算"} for t in task_ids]
