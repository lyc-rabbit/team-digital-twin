"""团队态势 HTTP API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import repository as repo
from . import pipeline
from .collectors import collect_snapshot


router = APIRouter(prefix="/api/team-situation", tags=["team-situation"])


class AnalyzeRequest(BaseModel):
    idempotency_key: Optional[str] = None


class ContextRequest(BaseModel):
    context_date: Optional[str] = None
    context_type: str
    content: str
    creator_id: Optional[str] = ""


class RiskPatchRequest(BaseModel):
    status: str


class QuestionPatchRequest(BaseModel):
    status: str
    answer: Optional[str] = ""


class ConfigRequest(BaseModel):
    project_weight: Optional[float] = None
    member_weight: Optional[float] = None
    task_weight: Optional[float] = None
    collab_weight: Optional[float] = None
    scheduler_enabled: Optional[bool] = None
    scheduler_hour: Optional[int] = None
    scheduler_minute: Optional[int] = None
    included_member_ids: Optional[list[str]] = None


@router.get("/today")
def today():
    return pipeline.today_payload()


@router.get("/status")
def status():
    return pipeline.get_status()


@router.get("/reports")
def reports(
    date: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    if date:
        item = repo.get_report_by_date(date)
        return {"reports": [item] if item else []}
    return {"reports": repo.list_reports(start_date, end_date)}


@router.get("/members/{member_id}")
def member_situation(member_id: str):
    data = pipeline.member_payload(member_id)
    if not data:
        raise HTTPException(status_code=404, detail="暂无该成员态势，请先生成今日分析")
    return data


@router.get("/projects/{project_id}")
def project_situation(project_id: str):
    data = pipeline.project_payload(project_id)
    if not data:
        raise HTTPException(status_code=404, detail="暂无该项目态势，请先生成今日分析")
    return data


@router.get("/trends")
def trends(range: str = Query("7d", alias="range")):
    return pipeline.trends_payload(range)


@router.post("/analyze")
def analyze(req: AnalyzeRequest = AnalyzeRequest()):
    return pipeline.start_analyze(req.idempotency_key, trigger="manual")


@router.get("/data-snapshot")
def data_snapshot():
    snap = collect_snapshot(days=30)
    return {
        "members": snap["members"],
        "daily_reports": snap["daily_reports"],
        "projects": snap["projects"],
        "tasks": snap["tasks"],
        "roles": snap["roles"],
        "relationships": snap["relationships"],
        "role_competitions": snap["role_competitions"],
    }


@router.post("/context")
def add_context(req: ContextRequest):
    from timeutil import today as beijing_today
    day = (req.context_date or beijing_today())[:10]
    allowed = {"note", "project", "member", "risk", "management", "今日特殊事项", "项目变化", "人员变化", "风险", "管理层信息"}
    ctype = req.context_type if req.context_type in allowed else req.context_type
    if not (req.content or "").strip():
        raise HTTPException(status_code=400, detail="补充内容不能为空")
    repo.add_context(day, ctype, req.content.strip(), req.creator_id or "")
    return {"status": "success", "message": "已记入 Team Context（source=manual）", "date": day}


@router.get("/context")
def list_context(date: Optional[str] = None):
    return {"items": repo.list_context(context_date=date, days=14)}


@router.patch("/risks/{risk_id}")
def patch_risk(risk_id: str, req: RiskPatchRequest):
    if req.status not in ("open", "confirmed", "ignored", "resolved"):
        raise HTTPException(status_code=400, detail="状态无效")
    item = repo.update_risk(risk_id, req.status)
    if not item:
        raise HTTPException(status_code=404, detail="风险不存在")
    return item


@router.patch("/questions/{question_id}")
def patch_question(question_id: str, req: QuestionPatchRequest):
    if req.status not in ("open", "long_term", "temporary", "ignored"):
        raise HTTPException(status_code=400, detail="请选择：长期变化 / 临时变化 / 忽略")
    item = repo.answer_question(question_id, req.status, req.answer or "")
    if not item:
        raise HTTPException(status_code=404, detail="问题不存在")
    return item


@router.get("/config")
def get_config():
    return repo.get_config()


@router.put("/config")
def put_config(req: ConfigRequest):
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    if "included_member_ids" in data:
        ids = [str(x).strip() for x in (data["included_member_ids"] or []) if str(x).strip()]
        if not ids:
            raise HTTPException(status_code=400, detail="请至少勾选一名计入健康度的团队成员")
        data["included_member_ids"] = ids
    return repo.set_config(data)
