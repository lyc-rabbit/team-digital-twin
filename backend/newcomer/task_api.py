from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from . import service as nc_service

task_router = APIRouter(prefix="/api/newcomer-tasks", tags=["newcomers"])


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


@task_router.put("/{task_id}")
def update_task(task_id: str, req: TaskUpdateRequest):
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    result = nc_service.update_task(task_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="任务不存在")
    return result


@task_router.post("/{task_id}/complete")
def complete_task(task_id: str, req: TaskCompleteRequest = TaskCompleteRequest()):
    detail = nc_service.complete_task(task_id, req.note or "")
    if not detail:
        raise HTTPException(status_code=404, detail="任务不存在")
    return detail
