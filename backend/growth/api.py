"""P0 成长数据链 HTTP API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_member

from . import repository as repo
from . import service
from . import scores
from . import cadre
from . import upward
from .standards import get_role_standards, COMMUNICATION_CAPABILITY
from .taxonomy import list_taxonomy, get_template
from . import suggest as tag_suggest

router = APIRouter(tags=["growth"])


class EventLogIn(BaseModel):
    event_time: Optional[str] = None
    event_type: Optional[str] = None
    event_tag: Optional[str] = None
    involved_members: Optional[list[str]] = None
    subjects: Optional[list[dict]] = None
    related_persons: Optional[list[str]] = None
    related_project_id: Optional[str] = None
    related_stage_id: Optional[str] = None
    related_role_id: Optional[str] = None
    related_newcomer_id: Optional[str] = None
    created_by: Optional[str] = None
    source: Optional[str] = "manual"
    background: Optional[str] = ""
    facts: Optional[str] = ""
    expected: Optional[str] = ""
    difference: Optional[str] = ""
    actions: Optional[str] = ""
    result: Optional[str] = ""
    evidence: Optional[str] = ""
    judgement: Optional[str] = ""
    attempts: Optional[str] = ""
    help_request: Optional[str] = ""
    extra_fields: Optional[dict] = None
    summary: Optional[str] = ""
    scene: Optional[str] = None
    target_person_id: Optional[str] = None


class StageRecordIn(BaseModel):
    stage_goal: Optional[str] = None
    role_requirements: Optional[str] = None
    stage_tasks: Optional[list] = None
    human_ai_division: Optional[list] = None
    self_eval: Optional[str] = None
    mentor_eval: Optional[str] = None
    result: Optional[str] = None
    capability_changes: Optional[list] = None
    passed: Optional[bool] = None


class UpwardReportIn(BaseModel):
    manager_id: Optional[str] = None
    project_id: Optional[str] = None
    extra_notes: Optional[str] = ""


class EventSuggestIn(BaseModel):
    text: str
    created_by: Optional[str] = None
    event_time: Optional[str] = None


class ProjectGrowthIn(BaseModel):
    project_role: Optional[str] = None
    responsibility: Optional[str] = None
    key_decisions: Optional[str] = None
    risk_handling: Optional[str] = None
    resource_coordination: Optional[str] = None
    collaboration: Optional[str] = None
    newcomer_training: Optional[str] = None
    outcome: Optional[str] = None
    retrospective: Optional[str] = None


@router.get("/api/events/taxonomy")
def event_taxonomy():
    return list_taxonomy()


@router.get("/api/events/template")
def event_template(event_type: str = Query(""), event_tag: str = Query("")):
    return get_template(event_type, event_tag)


@router.post("/api/events/suggest-tags")
def suggest_event_tags(req: EventSuggestIn):
    try:
        return tag_suggest.suggest_tags(req.text, req.created_by or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/events/structured")
def log_structured(req: EventLogIn):
    try:
        return {"status": "success", **service.log_structured_event(req.model_dump())}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/events/{event_id}/chain")
def event_chain(event_id: int):
    detail = service.event_detail_bundle(event_id)
    if not detail:
        raise HTTPException(status_code=404, detail="事件不存在")
    return detail


@router.get("/api/relationships/score")
def relationship_score(
    from_id: str = Query(...),
    to_id: str = Query(...),
    dimension: str = Query("trust"),
):
    return scores.score_detail(from_id, to_id, dimension)


@router.get("/api/relationships/pair")
def relationship_pair(from_id: str = Query(...), to_id: str = Query(...)):
    return scores.pair_overview(from_id, to_id)


@router.get("/api/relationships/evidence/{evidence_id}")
def relationship_evidence_item(evidence_id: int):
    item = scores.evidence_item(evidence_id)
    if not item:
        raise HTTPException(status_code=404, detail="证据不存在")
    return item


@router.get("/api/growth/standards/{role_id}")
def role_standards(role_id: str):
    data = get_role_standards(role_id)
    data["communication"] = COMMUNICATION_CAPABILITY
    return data


@router.get("/api/growth/cadre")
def cadre_list():
    return {"profiles": cadre.list_profiles()}


@router.get("/api/growth/cadre/{person_id}")
def cadre_detail(person_id: str):
    profile = cadre.build_profile(person_id)
    if not profile:
        raise HTTPException(status_code=404, detail="成员不存在")
    return profile


@router.get("/api/growth/upward/{person_id}")
def upward_detail(person_id: str, manager_id: Optional[str] = Query(None)):
    archive = upward.build_archive(person_id, manager_id)
    if not archive:
        raise HTTPException(status_code=404, detail="成员不存在")
    return archive


@router.get("/api/growth/upward/{person_id}/facts")
def upward_facts(
    person_id: str,
    manager_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
):
    if not get_member(person_id):
        raise HTTPException(status_code=404, detail="成员不存在")
    return upward.collect_report_facts(person_id, manager_id, project_id)


@router.post("/api/growth/upward/{person_id}/report")
def upward_report(person_id: str, req: UpwardReportIn):
    if not get_member(person_id):
        raise HTTPException(status_code=404, detail="成员不存在")
    return upward.generate_report(
        person_id,
        req.manager_id,
        req.project_id,
        req.extra_notes or "",
    )


@router.get("/api/growth/promotion/{person_id}")
def promotion_growth(person_id: str):
    data = cadre.promotion_assessment(person_id)
    if not data:
        raise HTTPException(status_code=404, detail="成员不存在")
    return data


@router.get("/api/newcomers/{employee_id}/stages")
def newcomer_stages(employee_id: str):
    from newcomer.repository import get_newcomer_by_employee, get_newcomer
    nc = get_newcomer_by_employee(employee_id) or get_newcomer(employee_id)
    if not nc:
        raise HTTPException(status_code=404, detail="新人不存在")
    return {
        "newcomer_id": nc["id"],
        "stages": service.list_stage_bundle(nc["id"], nc.get("target_role_id")),
    }


@router.put("/api/newcomers/{employee_id}/stages/{stage_id}")
def save_newcomer_stage(employee_id: str, stage_id: str, req: StageRecordIn):
    from newcomer.repository import get_newcomer_by_employee, get_newcomer
    nc = get_newcomer_by_employee(employee_id) or get_newcomer(employee_id)
    if not nc:
        raise HTTPException(status_code=404, detail="新人不存在")
    rec = service.save_stage_record(nc["id"], stage_id, req.model_dump())
    return {"record": rec}


@router.get("/api/projects/{project_id}/growth-evidence")
def list_project_growth(project_id: str):
    return {"items": repo.list_project_growth(project_id=project_id)}


@router.put("/api/projects/{project_id}/growth-evidence/{person_id}")
def save_project_growth(project_id: str, person_id: str, req: ProjectGrowthIn):
    item = repo.upsert_project_growth(project_id, person_id, req.model_dump())
    return {"item": item}


@router.post("/api/projects/{project_id}/growth-evidence/{person_id}/to-event")
def project_growth_to_event(project_id: str, person_id: str, created_by: Optional[str] = Query(None)):
    try:
        return {"status": "success", **service.project_growth_to_event(project_id, person_id, created_by)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
