"""项目中心 HTTP API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import repository as repo
from . import service


router = APIRouter(prefix="/api/projects", tags=["project-center"])


class StageIn(BaseModel):
    name: str
    description: Optional[str] = ""
    status: Optional[str] = None
    progress: Optional[float] = None
    owner_id: Optional[str] = ""
    planned_start_date: Optional[str] = ""
    planned_end_date: Optional[str] = ""
    sort_order: Optional[int] = None


class MemberIn(BaseModel):
    user_id: Optional[str] = None
    member_id: Optional[str] = None
    role: Optional[str] = "其他"
    responsibility: Optional[str] = ""
    participation_level: Optional[str] = "主要"


class ProjectCreate(BaseModel):
    name: str
    description: str
    owner_id: str
    status: Optional[str] = "open"
    type: Optional[str] = ""
    priority: Optional[str] = ""
    business: Optional[str] = ""
    tags: Optional[list[str]] = None
    start_date: Optional[str] = ""
    end_date: Optional[str] = ""
    members: Optional[list[MemberIn]] = None
    stages: list[StageIn]


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    business: Optional[str] = None
    tags: Optional[list[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    current_stage_id: Optional[str] = None
    force: Optional[bool] = False
    operator_id: Optional[str] = ""


class StageUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[float] = None
    owner_id: Optional[str] = None
    planned_start_date: Optional[str] = None
    planned_end_date: Optional[str] = None
    actual_start_date: Optional[str] = None
    actual_end_date: Optional[str] = None
    sort_order: Optional[int] = None


class StageComplete(BaseModel):
    summary: Optional[str] = ""
    operator_id: Optional[str] = ""


class ActivityIn(BaseModel):
    content: str
    type: Optional[str] = "note"
    stage_id: Optional[str] = ""
    source: Optional[str] = "MANUAL"
    operator_id: Optional[str] = ""


class MilestoneIn(BaseModel):
    name: str
    description: Optional[str] = ""
    stage_id: Optional[str] = ""
    owner_id: Optional[str] = ""
    planned_date: Optional[str] = ""
    status: Optional[str] = "not_started"
    importance: Optional[str] = "normal"


class MilestoneUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    stage_id: Optional[str] = None
    owner_id: Optional[str] = None
    planned_date: Optional[str] = None
    actual_date: Optional[str] = None
    status: Optional[str] = None
    importance: Optional[str] = None


class RiskIn(BaseModel):
    title: str
    description: Optional[str] = ""
    type: Optional[str] = "其他"
    level: Optional[str] = "medium"
    probability: Optional[str] = ""
    impact: Optional[str] = ""
    owner_id: Optional[str] = ""
    mitigation: Optional[str] = ""
    status: Optional[str] = "open"


class RiskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    level: Optional[str] = None
    probability: Optional[str] = None
    impact: Optional[str] = None
    owner_id: Optional[str] = None
    mitigation: Optional[str] = None
    status: Optional[str] = None


class ObjectiveIn(BaseModel):
    title: str
    description: Optional[str] = ""
    status: Optional[str] = "not_started"


class KrIn(BaseModel):
    name: str
    target_value: Optional[str] = ""
    current_value: Optional[str] = ""
    unit: Optional[str] = ""
    status: Optional[str] = "not_started"


class RelationIn(BaseModel):
    target_project_id: str
    relation_type: Optional[str] = "关联"
    description: Optional[str] = ""


@router.get("")
def list_projects(
    owner_id: Optional[str] = None,
    status: Optional[str] = None,
    type: Optional[str] = Query(None, alias="type"),
    priority: Optional[str] = None,
    current_stage: Optional[str] = None,
    risk_level: Optional[str] = None,
    sort: Optional[str] = "updated_at",
    viewer_id: Optional[str] = None,
    member_id: Optional[str] = None,
    mine: Optional[str] = None,
    include_archived: bool = False,
    archived_only: bool = False,
):
    return {
        "projects": service.list_projects({
            "owner_id": owner_id,
            "status": status,
            "type": type,
            "priority": priority,
            "current_stage": current_stage,
            "risk_level": risk_level,
            "sort": sort,
            "viewer_id": viewer_id,
            "member_id": member_id,
            "mine": mine,
            "include_archived": include_archived,
            "archived_only": archived_only,
        })
    }


@router.post("")
def create_project(req: ProjectCreate):
    try:
        data = req.model_dump()
        data["stages"] = [s for s in data.get("stages") or [] if (s.get("name") or "").strip()]
        return service.create_project(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{project_id}")
def get_project(project_id: str):
    item = service.get_project(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    return item


@router.put("/{project_id}")
def update_project(project_id: str, req: ProjectUpdate):
    try:
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        force = bool(data.pop("force", False))
        item = service.update_project(project_id, data, force=force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    return item


@router.delete("/{project_id}")
def delete_project(project_id: str):
    if not repo.delete_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"status": "success"}


@router.get("/{project_id}/stages")
def list_stages(project_id: str):
    item = service.get_project(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"stages": item.get("stages") or []}


@router.post("/{project_id}/stages")
def add_stage(project_id: str, req: StageIn):
    if not repo.get_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    if not (req.name or "").strip():
        raise HTTPException(status_code=400, detail="阶段名称为必填")
    repo.add_stage(project_id, req.model_dump())
    return service.get_project(project_id)


@router.put("/{project_id}/stages/{stage_id}")
def update_stage(project_id: str, stage_id: str, req: StageUpdate):
    data = req.model_dump(exclude_unset=True)
    try:
        item = service.update_stage(project_id, stage_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not item:
        raise HTTPException(status_code=404, detail="阶段不存在")
    return item


@router.post("/{project_id}/stages/{stage_id}/complete")
def complete_stage(project_id: str, stage_id: str, req: StageComplete = StageComplete()):
    try:
        return service.complete_stage(project_id, stage_id, req.summary or "", req.operator_id or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{project_id}/members")
def list_members(project_id: str):
    item = service.get_project(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"members": item.get("members") or []}


@router.post("/{project_id}/members")
def add_member(project_id: str, req: MemberIn):
    uid = req.user_id or req.member_id
    if not uid:
        raise HTTPException(status_code=400, detail="请选择成员")
    if not repo.get_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    data = req.model_dump()
    data["user_id"] = uid
    item = repo.add_member(project_id, data)
    repo.add_activity(project_id, {
        "type": "member",
        "content": f"加入成员 {uid}（{req.role or '其他'}）",
        "source": "SYSTEM",
        "operator_id": uid,
    })
    return item


@router.delete("/{project_id}/members/{member_id}")
def delete_member(project_id: str, member_id: str):
    repo.delete_member(project_id, member_id)
    return {"status": "success"}


@router.get("/{project_id}/milestones")
def list_milestones(project_id: str):
    item = repo.get_project(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"milestones": item.get("milestones") or []}


@router.post("/{project_id}/milestones")
def add_milestone(project_id: str, req: MilestoneIn):
    if not repo.get_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return repo.add_milestone(project_id, req.model_dump())


@router.put("/{project_id}/milestones/{milestone_id}")
def update_milestone(project_id: str, milestone_id: str, req: MilestoneUpdate):
    item = repo.update_milestone(milestone_id, {k: v for k, v in req.model_dump().items() if v is not None})
    if not item:
        raise HTTPException(status_code=404, detail="里程碑不存在")
    return item


@router.get("/{project_id}/risks")
def list_risks(project_id: str):
    item = repo.get_project(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"risks": item.get("risks") or []}


@router.post("/{project_id}/risks")
def add_risk(project_id: str, req: RiskIn):
    if not repo.get_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return repo.add_risk(project_id, req.model_dump())


@router.put("/{project_id}/risks/{risk_id}")
def update_risk(project_id: str, risk_id: str, req: RiskUpdate):
    item = repo.update_risk(risk_id, {k: v for k, v in req.model_dump().items() if v is not None})
    if not item:
        raise HTTPException(status_code=404, detail="风险不存在")
    return item


@router.get("/{project_id}/activities")
def list_activities(project_id: str):
    item = service.get_project(project_id)
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"activities": item.get("activities") or []}


@router.post("/{project_id}/activities")
def add_activity(project_id: str, req: ActivityIn):
    if not (req.content or "").strip():
        raise HTTPException(status_code=400, detail="动态内容不能为空")
    if not repo.get_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return repo.add_activity(project_id, req.model_dump())


@router.post("/{project_id}/objectives")
def add_objective(project_id: str, req: ObjectiveIn):
    if not repo.get_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return repo.add_objective(project_id, req.model_dump())


@router.post("/{project_id}/objectives/{objective_id}/krs")
def add_kr(project_id: str, objective_id: str, req: KrIn):
    return repo.add_kr(objective_id, req.model_dump())


@router.post("/{project_id}/relations")
def add_relation(project_id: str, req: RelationIn):
    if not repo.get_project(project_id) or not repo.get_project(req.target_project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return repo.add_relation({
        "source_project_id": project_id,
        **req.model_dump(),
    })


@router.delete("/{project_id}/relations/{relation_id}")
def delete_relation(project_id: str, relation_id: str):
    repo.delete_relation(relation_id)
    return {"status": "success"}
