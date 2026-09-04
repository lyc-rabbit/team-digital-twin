"""P0 事件录入编排：结构化保存 → 证据分析 → 兼容旧关系增量。"""

from timeutil import now_iso
from database import (
    get_all_members,
    get_event_detail,
    insert_relationship_log,
    insert_emotion_log,
    delete_relationship_logs_by_event,
    delete_emotion_logs_by_event,
)
from llm_client import extract_event, is_mock_mode, last_call_degraded
from newcomer.repository import get_newcomer, get_newcomer_by_employee
from newcomer.templates import STAGES, CAPABILITIES, ROLE_CAPABILITIES

from . import repository as repo
from .analyzer import analyze_event, persist_analysis
from .standards import human_ai_for_role, get_role_standards
from .taxonomy import compose_summary, get_template, type_label, tag_label


TRUST_DIMS = {"trust", "professional_trust", "independence", "delivery_trust"}


def _collect_involved(payload):
    ids = []
    for mid in payload.get("involved_members") or []:
        if mid and mid not in ids:
            ids.append(mid)
    created = payload.get("created_by")
    if created and created not in ids:
        ids.append(created)
    for s in payload.get("subjects") or []:
        pid = s.get("person_id") if isinstance(s, dict) else s
        if pid and pid not in ids:
            ids.append(pid)
    for pid in payload.get("related_persons") or []:
        if pid and pid not in ids:
            ids.append(pid)
    return ids


def _normalize_subjects(payload, involved):
    subjects = payload.get("subjects") or []
    out = []
    for s in subjects:
        if isinstance(s, dict) and s.get("person_id"):
            out.append({"person_id": s["person_id"], "role": s.get("role") or "target"})
        elif isinstance(s, str):
            out.append({"person_id": s, "role": "target"})
    if not out and payload.get("target_person_id"):
        out.append({"person_id": payload["target_person_id"], "role": "target"})
    if not out:
        created = payload.get("created_by")
        for mid in involved:
            if mid != created:
                out.append({"person_id": mid, "role": "target"})
                break
        if not out and involved:
            out.append({"person_id": involved[0], "role": "target"})
    return out


def _extra_fields(payload):
    extra = dict(payload.get("extra_fields") or {})
    for k in ("attempts", "help_request"):
        if payload.get(k) and k not in extra:
            extra[k] = payload[k]
    return extra


def log_structured_event(payload):
    involved = _collect_involved(payload)
    if not involved:
        raise ValueError("请至少选择一名涉及成员")
    extra = _extra_fields(payload)
    raw = compose_summary({**payload, "extra_fields": extra, "involved_members": involved})
    if not raw.strip():
        raise ValueError("请按描述框架填写事件内容")
    subjects = _normalize_subjects(payload, involved)
    scene = payload.get("scene") or tag_label(payload.get("event_type"), payload.get("event_tag")) or type_label(payload.get("event_type"))

    event_id = repo.insert_structured_event({
        **payload,
        "involved_members": involved,
        "subjects": subjects,
        "related_persons": payload.get("related_persons") or [],
        "raw_summary": raw,
        "scene": scene,
        "extra_fields": extra,
        "source": payload.get("source") or "manual",
        "confidence": payload.get("confidence") or 0.85,
    })

    members = get_all_members()
    members_info = [{"id": m["id"], "name": m["name"], "role": m["role"]} for m in members]
    parsed = extract_event(raw, members_info)
    repo.update_event_structured(
        event_id,
        parsed_task=parsed.get("task"),
        scene=parsed.get("scene") or scene,
        confidence=parsed.get("confidence") or 0.8,
    )

    event = repo.get_event(event_id)
    analysis = persist_analysis(event_id, analyze_event(event))
    _write_compat_logs(event_id, analysis, parsed)

    if event.get("related_newcomer_id"):
        _touch_stage_record(event)

    try:
        from temporal_graph.events import apply_from_team_event
        apply_from_team_event(repo.get_event(event_id))
    except Exception:
        pass

    facts_out = {"created": 0}
    try:
        from fact_governance.bridge import ingest_from_logged_event
        facts_out = ingest_from_logged_event(
            repo.get_event(event_id), analysis=analysis, parsed=parsed,
        )
    except Exception as exc:
        facts_out = {"created": 0, "error": str(exc)}

    return {
        "event_id": event_id,
        "event": repo.get_event(event_id),
        "mock_mode": is_mock_mode(),
        "degraded": last_call_degraded(),
        "analysis": analysis,
        "facts": facts_out,
        "parsed_analysis": {
            "task": parsed.get("task"),
            "scene": parsed.get("scene") or scene,
            "emotions": parsed.get("emotions") or [],
            "relations": parsed.get("relations") or [],
            "confidence": parsed.get("confidence") or 0.8,
            "relationship_evidence": analysis.get("relationship_evidence") or [],
            "capability_evidence": analysis.get("capability_evidence") or [],
            "structured_problem": analysis.get("structured_problem"),
        },
    }


def reanalyze_structured(event_id):
    event = repo.get_event(event_id)
    if not event:
        raise ValueError(f"事件不存在: {event_id}")
    members = get_all_members()
    members_info = [{"id": m["id"], "name": m["name"], "role": m["role"]} for m in members]
    parsed = extract_event(event.get("raw_summary") or "", members_info)
    repo.update_event_structured(
        event_id,
        parsed_task=parsed.get("task"),
        scene=parsed.get("scene") or event.get("scene"),
        confidence=parsed.get("confidence"),
    )
    event = repo.get_event(event_id)
    analysis = persist_analysis(event_id, analyze_event(event))
    delete_relationship_logs_by_event(event_id)
    delete_emotion_logs_by_event(event_id)
    _write_compat_logs(event_id, analysis, parsed)
    facts_out = {"created": 0}
    try:
        from fact_governance.bridge import ingest_from_logged_event
        facts_out = ingest_from_logged_event(event, analysis=analysis, parsed=parsed)
    except Exception as exc:
        facts_out = {"created": 0, "error": str(exc)}
    return {
        "event_id": event_id,
        "mock_mode": is_mock_mode(),
        "degraded": last_call_degraded(),
        "facts": facts_out,
        "analysis": analysis,
        "parsed_analysis": {
            "task": parsed.get("task"),
            "scene": parsed.get("scene") or event.get("scene"),
            "emotions": parsed.get("emotions") or [],
            "relations": parsed.get("relations") or [],
            "confidence": parsed.get("confidence") or 0.8,
            "relationship_evidence": analysis.get("relationship_evidence") or [],
            "capability_evidence": analysis.get("capability_evidence") or [],
        },
    }


def _write_compat_logs(event_id, analysis, parsed):
    pair_trust = {}
    pair_senti = {}
    pair_tag = {}
    for rel in analysis.get("relationship_evidence") or []:
        key = (rel["from_member_id"], rel["to_member_id"])
        dim = rel.get("dimension")
        delta = int(rel.get("delta") or 0)
        if dim in TRUST_DIMS or dim == "trust":
            pair_trust[key] = pair_trust.get(key, 0) + delta
        elif dim == "sentiment":
            pair_senti[key] = pair_senti.get(key, 0) + delta
        else:
            pair_trust[key] = pair_trust.get(key, 0) + (1 if delta > 0 else (-1 if delta < 0 else 0))
        pair_tag[key] = rel.get("reason") or pair_tag.get(key) or ""

    for rel in parsed.get("relations") or []:
        key = (rel.get("from"), rel.get("to"))
        if not key[0] or not key[1] or key[0] == key[1]:
            continue
        if key not in pair_trust:
            pair_trust[key] = int(rel.get("trust_delta") or 0)
            pair_senti[key] = pair_senti.get(key, 0) + int(rel.get("sentiment_delta") or 0)
            pair_tag[key] = rel.get("tag") or pair_tag.get(key) or ""

    keys = set(pair_trust) | set(pair_senti)
    for key in keys:
        insert_relationship_log(
            event_id, key[0], key[1],
            int(pair_trust.get(key, 0)),
            int(pair_senti.get(key, 0)),
            pair_tag.get(key) or "",
        )

    for emo in parsed.get("emotions") or []:
        if emo.get("member_id"):
            insert_emotion_log(event_id, emo["member_id"], emo.get("emotion") or "平静", emo.get("intensity", 5))


def _touch_stage_record(event):
    nc = get_newcomer(event.get("related_newcomer_id")) or get_newcomer_by_employee(event.get("related_newcomer_id"))
    if not nc:
        return
    stage_id = event.get("related_stage_id") or nc.get("onboarding_stage") or "onboarding"
    rec = repo.get_stage_record(nc["id"], stage_id)
    if rec:
        return
    role_id = event.get("related_role_id") or nc.get("target_role_id") or "developer"
    stage = next((s for s in STAGES if s["id"] == stage_id), STAGES[0])
    caps = ROLE_CAPABILITIES.get(role_id) or list(CAPABILITIES.keys())
    repo.upsert_stage_record(nc["id"], stage_id, {
        "stage_goal": f"完成「{stage['label']}」阶段目标，留下可核验事实。",
        "role_requirements": "、".join(CAPABILITIES.get(c, c) for c in caps[:6]),
        "human_ai_division": human_ai_for_role(role_id),
        "stage_tasks": [],
        "capability_changes": [],
        "passed": False,
    })


def event_detail_bundle(event_id):
    detail = get_event_detail(event_id)
    event = repo.get_event(event_id)
    if not event:
        return None
    evidences = repo.list_relationship_evidence(event_id=event_id)
    caps = repo.list_capability_evidence(event_id=event_id)
    return {
        **(detail or {}),
        **event,
        "relationship_evidence": evidences,
        "capability_evidence": caps,
        "template": get_template(event.get("event_type"), event.get("event_tag")),
    }


def list_stage_bundle(newcomer_id, target_role_id=None):
    records = {r["stage_id"]: r for r in repo.list_stage_records(newcomer_id)}
    events = repo.list_events({"newcomer_id": newcomer_id, "limit": 300})
    by_stage = {}
    for e in events:
        sid = e.get("related_stage_id") or ""
        by_stage.setdefault(sid, []).append(e)
    out = []
    for s in STAGES:
        rec = records.get(s["id"])
        if not rec:
            rec = {
                "newcomer_id": newcomer_id,
                "stage_id": s["id"],
                "stage_goal": f"完成「{s['label']}」阶段目标",
                "role_requirements": "",
                "stage_tasks": [],
                "human_ai_division": human_ai_for_role(target_role_id or "developer"),
                "self_eval": "",
                "mentor_eval": "",
                "result": "",
                "capability_changes": [],
                "passed": False,
            }
        rec = dict(rec)
        rec["stage_label"] = s["label"]
        rec["events"] = by_stage.get(s["id"]) or []
        rec["standards"] = get_role_standards(target_role_id or "developer")
        out.append(rec)
    return out


def save_stage_record(newcomer_id, stage_id, payload):
    return repo.upsert_stage_record(newcomer_id, stage_id, payload)


def project_growth_to_event(project_id, person_id, created_by=None):
    growth = repo.get_project_growth(project_id, person_id)
    if not growth:
        raise ValueError("请先填写项目成长证据")
    snippets = []
    mapping = [
        ("risk_handling", "项目风险", "project_risk"),
        ("key_decisions", "技术决策", "tech_decision"),
        ("newcomer_training", "培养结果", "development_result"),
        ("outcome", "项目交付", "project_delivery"),
        ("collaboration", "项目推进", "project_progress"),
    ]
    tag = "project_progress"
    title = "项目成长证据"
    body = ""
    for field, label, tid in mapping:
        text = (growth.get(field) or "").strip()
        if text:
            snippets.append(f"【{label}】{text}")
            tag = tid
            title = label
            body = text
    if not snippets:
        raise ValueError("成长证据为空，无法生成事件")
    event_type = "people_development" if tag == "development_result" else "project"
    payload = {
        "event_time": now_iso(),
        "event_type": event_type,
        "event_tag": tag,
        "involved_members": [person_id] + ([created_by] if created_by and created_by != person_id else []),
        "created_by": created_by or person_id,
        "subjects": [{"person_id": person_id, "role": "target"}],
        "related_project_id": project_id,
        "source": "project",
        "facts": body,
        "result": growth.get("outcome") or "",
        "actions": growth.get("key_decisions") or growth.get("risk_handling") or "",
        "evidence": growth.get("retrospective") or "",
        "judgement": growth.get("responsibility") or "",
        "summary": "\n".join(snippets),
        "scene": title,
    }
    result = log_structured_event(payload)
    repo.upsert_project_growth(project_id, person_id, {**growth, "event_id": result["event_id"]})
    return result
