"""新人地图 HTTP API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import service


router = APIRouter(prefix="/api/newcomers", tags=["newcomers"])


class CreateNewcomerRequest(BaseModel):
    employee_id: str
    entry_date: Optional[str] = None
    current_role: Optional[str] = None
    current_role_id: Optional[str] = None
    target_role_id: Optional[str] = None
    compete_in_ranking: Optional[bool] = False


class TargetRoleRequest(BaseModel):
    target_role_id: Optional[str] = None
    compete_in_ranking: Optional[bool] = None


class GuideSaveRequest(BaseModel):
    content: Optional[dict] = None
    status: Optional[str] = None


class TaskUpdateRequest(BaseModel):
    status: Optional[str] = None
    blocked_reason: Optional[str] = None
    help_requested: Optional[bool] = None
    task_name: Optional[str] = None
    description: Optional[str] = None
    estimated_hours: Optional[float] = None
    due_at: Optional[str] = None
    review_required: Optional[bool] = None
    ai_allowed: Optional[bool] = None
    task_level: Optional[str] = None


class TaskCompleteRequest(BaseModel):
    note: Optional[str] = ""


@router.get("")
def list_newcomers():
    return service.list_overview()


@router.get("/interventions")
def interventions():
    return service.list_interventions()


@router.post("/interventions/{intervention_id}/resolve")
def resolve_intervention(intervention_id: str):
    return service.resolve_intervention(intervention_id)


@router.post("")
def create_newcomer(req: CreateNewcomerRequest):
    try:
        return service.create_newcomer(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{employee_id}")
def get_newcomer(employee_id: str):
    detail = service.get_detail(employee_id)
    if not detail:
        raise HTTPException(status_code=404, detail="新人不存在")
    return detail


@router.put("/{employee_id}/target-role")
def set_target_role(employee_id: str, req: TargetRoleRequest):
    try:
        detail = service.set_target_role(
            employee_id, req.target_role_id, req.compete_in_ranking,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not detail:
        raise HTTPException(status_code=404, detail="新人不存在")
    return detail


@router.get("/{employee_id}/onboarding-guide")
def get_guide(employee_id: str):
    guide = service.get_guide(employee_id)
    if guide is None and not service.get_detail(employee_id):
        raise HTTPException(status_code=404, detail="新人不存在")
    return {"guide": guide}


@router.put("/{employee_id}/onboarding-guide")
def save_guide(employee_id: str, req: GuideSaveRequest):
    guide = service.save_guide(employee_id, req.content, req.status)
    if not guide:
        raise HTTPException(status_code=404, detail="新人不存在")
    return {"guide": guide}


@router.post("/{employee_id}/onboarding-guide/generate")
def generate_guide(employee_id: str):
    st = service.start_generate_guide(employee_id)
    if not st:
        raise HTTPException(status_code=404, detail="新人不存在")
    return st


@router.post("/{employee_id}/onboarding-guide/publish")
def publish_guide(employee_id: str):
    try:
        detail = service.publish_guide(employee_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not detail:
        raise HTTPException(status_code=404, detail="新人不存在")
    return detail


@router.get("/{employee_id}/tasks")
def list_tasks(employee_id: str):
    detail = service.get_detail(employee_id)
    if not detail:
        raise HTTPException(status_code=404, detail="新人不存在")
    return {"tasks": detail["tasks"]}


@router.post("/{employee_id}/tasks/recommend")
def recommend_tasks(employee_id: str):
    st = service.start_recommend_tasks(employee_id)
    if not st:
        raise HTTPException(status_code=404, detail="新人不存在")
    return st


@router.get("/{employee_id}/analysis/status")
def analysis_status(employee_id: str, kind: str = "guide"):
    from . import repository as repo
    nc = repo.get_newcomer_by_employee(employee_id) or repo.get_newcomer(employee_id)
    if not nc:
        raise HTTPException(status_code=404, detail="新人不存在")
    return service.get_analysis_status(kind, nc["id"])
