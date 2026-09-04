"""事件驱动：关闭旧事实、打开新事实，不删除历史。"""

from timeutil import parse_day, today

from .repository import get_temporal_store
from .types import (
    EVT_JOIN_COMPANY,
    EVT_LEAVE_COMPANY,
    EVT_PROJECT_COMPLETE,
    EVT_PROJECT_OWNER_CHANGE,
    EVT_PROJECT_PHASE_CHANGE,
    EVT_PROJECT_START,
    EVT_RESOURCE_ACQUIRE,
    EVT_RESOURCE_RELEASE,
    EVT_RESOURCE_TRANSFER,
    EVT_ROLE_CHANGE,
    EVT_TRANSFER,
    EXCLUSIVE_BY_SOURCE,
    EXCLUSIVE_BY_TARGET,
    LEAVE_CLOSE_PREDICATES,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_INACTIVE,
    REL_BELONGS_TO,
    REL_CONTROL,
    REL_HAS_ROLE,
    REL_OWNER,
    REL_REPORT_TO,
    REL_WORKS_ON,
)
from organization_graph.ontology.relations import REL_HAS_KNOWLEDGE


def infer_event_type(event_type="", event_tag="", summary=""):
    text = f"{event_type} {event_tag} {summary or ''}"
    if any(k in text for k in ("离职", "离开公司", "LEAVE")):
        return EVT_LEAVE_COMPANY
    if any(k in text for k in ("入职", "加入公司", "JOIN_COMPANY")):
        return EVT_JOIN_COMPANY
    if any(k in text for k in ("交接", "转交负责", "OWNER_CHANGE")):
        return EVT_PROJECT_OWNER_CHANGE
    if any(k in text for k in ("调动", "转岗", "TRANSFER")):
        return EVT_TRANSFER
    if any(k in text for k in ("角色变化", "换角色", "ROLE_CHANGE")):
        return EVT_ROLE_CHANGE
    if any(k in text for k in ("资源转交", "转交资源")):
        return EVT_RESOURCE_TRANSFER
    if "上线" in text or event_tag == "project_delivery":
        return EVT_PROJECT_PHASE_CHANGE
    return None


def apply_event(
    event_type,
    event_time,
    *,
    person_id=None,
    other_person_id=None,
    project_id=None,
    resource_id=None,
    department_id=None,
    role_id=None,
    description="",
    operator="",
    team_event_id="",
    payload=None,
    skill_id=None,
):
    store = get_temporal_store()
    when = parse_day(event_time) or today()
    payload = dict(payload or {})
    payload.update({
        "person_id": person_id,
        "other_person_id": other_person_id,
        "project_id": project_id,
        "resource_id": resource_id,
        "department_id": department_id,
        "role_id": role_id,
        "skill_id": skill_id,
    })
    rec = store.insert_event({
        "event_type": event_type,
        "event_time": when,
        "description": description,
        "operator": operator,
        "team_event_id": team_event_id,
        "payload": payload,
    })
    eid = rec["id"]
    closed, opened = [], []

    def _open(subj, pred, obj, extra=None):
        if not subj or not pred or not obj:
            return None
        existing = store.find_open(subj, pred, obj)
        if existing:
            return existing
        fact = store.insert_fact({
            "subject_id": subj,
            "predicate": pred,
            "object_id": obj,
            "valid_from": when,
            "valid_to": "",
            "source_event_id": eid,
            "source": "event",
            "confidence": 1.0,
            "evidence": extra or {"event_type": event_type, "description": description},
        })
        opened.append(fact)
        return fact

    def _exclusive_open(subj, pred, obj):
        if pred in EXCLUSIVE_BY_TARGET:
            closed.extend(store.close_open_matching(
                predicate=pred, object_id=obj, valid_to=when,
                source_event_id=eid, exclude_subject=subj,
            ))
        if pred in EXCLUSIVE_BY_SOURCE:
            closed.extend(store.close_open_matching(
                predicate=pred, subject_id=subj, valid_to=when,
                source_event_id=eid,
            ))
        return _open(subj, pred, obj)

    if event_type == EVT_JOIN_COMPANY and person_id:
        store.upsert_lifecycle({
            "entity_id": person_id,
            "entity_type": "Person",
            "status": LIFECYCLE_ACTIVE,
            "valid_from": when,
            "valid_to": "",
            "source_event_id": eid,
        })
        _exclusive_open(person_id, REL_BELONGS_TO, department_id)

    elif event_type == EVT_LEAVE_COMPANY and person_id:
        store.upsert_lifecycle({
            "entity_id": person_id,
            "entity_type": "Person",
            "status": LIFECYCLE_INACTIVE,
            "valid_from": (store.get_lifecycle(person_id) or {}).get("valid_from") or when,
            "valid_to": when,
            "source_event_id": eid,
        })
        for pred in LEAVE_CLOSE_PREDICATES:
            closed.extend(store.close_open_matching(
                predicate=pred, subject_id=person_id, valid_to=when, source_event_id=eid,
            ))
        closed.extend(store.close_open_matching(
            predicate=REL_REPORT_TO, object_id=person_id, valid_to=when, source_event_id=eid,
        ))

    elif event_type == EVT_TRANSFER and person_id and department_id:
        _exclusive_open(person_id, REL_BELONGS_TO, department_id)

    elif event_type == EVT_ROLE_CHANGE and person_id and role_id:
        closed.extend(store.close_open_matching(
            predicate=REL_HAS_ROLE, subject_id=person_id, valid_to=when, source_event_id=eid,
        ))
        _open(person_id, REL_HAS_ROLE, role_id)

    elif event_type == EVT_PROJECT_OWNER_CHANGE and project_id:
        new_owner = other_person_id or person_id
        old_owner = person_id if other_person_id else None
        closed.extend(store.close_open_matching(
            predicate=REL_OWNER, object_id=project_id, valid_to=when,
            source_event_id=eid, exclude_subject=new_owner,
        ))
        _open(new_owner, REL_OWNER, project_id)
        _open(new_owner, REL_WORKS_ON, project_id)
        if old_owner and old_owner != new_owner:
            _open(old_owner, REL_WORKS_ON, project_id)  # 仍可能参与；若已开放则复用

    elif event_type == EVT_PROJECT_START and project_id:
        store.upsert_lifecycle({
            "entity_id": project_id,
            "entity_type": "Project",
            "status": LIFECYCLE_ACTIVE,
            "valid_from": when,
            "valid_to": "",
            "source_event_id": eid,
        })
        if person_id:
            _exclusive_open(person_id, REL_OWNER, project_id)
            _open(person_id, REL_WORKS_ON, project_id)

    elif event_type == EVT_PROJECT_COMPLETE and project_id:
        store.upsert_lifecycle({
            "entity_id": project_id,
            "entity_type": "Project",
            "status": LIFECYCLE_INACTIVE,
            "valid_from": (store.get_lifecycle(project_id) or {}).get("valid_from") or when,
            "valid_to": when,
            "source_event_id": eid,
        })
        closed.extend(store.close_open_matching(
            predicate=REL_OWNER, object_id=project_id, valid_to=when, source_event_id=eid,
        ))

    elif event_type == EVT_PROJECT_PHASE_CHANGE and project_id:
        if person_id:
            _open(person_id, REL_WORKS_ON, project_id)

    elif event_type == EVT_RESOURCE_ACQUIRE and person_id and resource_id:
        _open(person_id, REL_CONTROL, resource_id)

    elif event_type == EVT_RESOURCE_TRANSFER and resource_id:
        new_owner = other_person_id or person_id
        closed.extend(store.close_open_matching(
            predicate=REL_CONTROL, object_id=resource_id, valid_to=when,
            source_event_id=eid, exclude_subject=new_owner,
        ))
        _open(new_owner, REL_CONTROL, resource_id)

    elif event_type == EVT_RESOURCE_RELEASE and resource_id:
        closed.extend(store.close_open_matching(
            predicate=REL_CONTROL, object_id=resource_id, valid_to=when, source_event_id=eid,
        ))

    if skill_id and person_id and event_type in (EVT_PROJECT_PHASE_CHANGE, EVT_ROLE_CHANGE, EVT_JOIN_COMPANY):
        _open(person_id, REL_HAS_KNOWLEDGE, skill_id)

    return {"event": rec, "closed": closed, "opened": opened}


def apply_from_team_event(event):
    """从已有 team_events / 结构化事件尽量推导时态动作。不确定则只记账不改关系。"""
    if not event:
        return None
    summary = event.get("raw_summary") or event.get("description") or ""
    inferred = infer_event_type(event.get("event_type") or "", event.get("event_tag") or "", summary)
    if not inferred:
        return None
    involved = event.get("involved_members") or []
    if isinstance(involved, str):
        import json
        try:
            involved = json.loads(involved)
        except Exception:
            involved = []
    subjects = event.get("subjects") or []
    person_id = event.get("target_person_id") or event.get("created_by")
    if subjects:
        s0 = subjects[0]
        person_id = s0.get("person_id") if isinstance(s0, dict) else s0
    related = event.get("related_persons") or []
    other = related[0] if related else (involved[1] if len(involved) > 1 else None)
    return apply_event(
        inferred,
        event.get("event_time") or today(),
        person_id=person_id,
        other_person_id=other,
        project_id=event.get("related_project_id"),
        description=summary[:200],
        team_event_id=event.get("id"),
        payload={"event_tag": event.get("event_tag"), "auto": True},
    )
