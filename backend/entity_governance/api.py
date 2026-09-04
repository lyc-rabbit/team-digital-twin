"""Entity Governance / Entity Resolution HTTP API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import service
from .types import ENTITY_TYPES

router = APIRouter(tags=["entity-governance"])


class DetectIn(BaseModel):
    entityTypes: Optional[list[str]] = None
    force: Optional[bool] = True
    autoMerge: Optional[bool] = True


class MergeIn(BaseModel):
    sourceEntityId: str
    targetEntityId: str
    reason: Optional[str] = ""
    candidateId: Optional[str] = None
    operator: Optional[str] = "user"


class RejectIn(BaseModel):
    candidateId: str
    reason: Optional[str] = "不是同一实体"
    operator: Optional[str] = "user"


class SkipIn(BaseModel):
    candidateId: str
    operator: Optional[str] = "user"


class AliasIn(BaseModel):
    entityId: str
    value: str
    source: Optional[str] = "manual"


class ResolveIn(BaseModel):
    entityType: str
    name: str
    attributes: Optional[dict] = None
    source: Optional[dict] = None
    preferredId: Optional[str] = None


@router.get("/api/entity-governance/overview")
def overview():
    return service.get_overview()


@router.post("/api/entity-governance/detect")
def detect(req: DetectIn):
    types = req.entityTypes or list(ENTITY_TYPES)
    return service.detect_duplicates(
        entity_types=types,
        force=bool(req.force),
        auto_merge=bool(req.autoMerge),
    )


@router.get("/api/entity-governance/detect/status")
def detect_status():
    return service.get_detect_status()


@router.get("/api/entity-governance/candidates")
def candidates(
    status: Optional[str] = Query("all"),
    entityType: Optional[str] = None,
    minScore: Optional[float] = None,
    page: int = Query(1),
    pageSize: int = Query(50),
):
    return service.list_candidates(
        status=status,
        entity_type=entityType,
        min_score=minScore,
        page=page,
        page_size=pageSize,
    )


@router.get("/api/entity-governance/candidates/{candidate_id}")
def candidate_detail(candidate_id: str):
    data = service.get_candidate_detail(candidate_id)
    if not data:
        raise HTTPException(status_code=404, detail="候选不存在")
    return data


@router.post("/api/entity-governance/merge")
def merge(req: MergeIn):
    try:
        return service.merge_entities(
            req.sourceEntityId,
            req.targetEntityId,
            reason=req.reason or "人工确认同一实体",
            operator=req.operator or "user",
            candidate_id=req.candidateId,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/entity-governance/reject")
def reject(req: RejectIn):
    try:
        return service.reject_candidate(req.candidateId, reason=req.reason or "", operator=req.operator or "user")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/entity-governance/skip")
def skip(req: SkipIn):
    try:
        return service.skip_candidate(req.candidateId, operator=req.operator or "user")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/entity-governance/unmerge/{merge_id}")
def unmerge(merge_id: str, operator: str = Query("user")):
    try:
        return service.unmerge(merge_id, operator=operator)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/entity-governance/merges")
def merges(includeUnmerged: bool = Query(True), limit: int = Query(100)):
    return {"items": service.list_merges(include_unmerged=includeUnmerged, limit=limit)}


@router.get("/api/entity-governance/merges/{merge_id}")
def merge_detail(merge_id: str):
    data = service.get_merge(merge_id)
    if not data:
        raise HTTPException(status_code=404, detail="合并记录不存在")
    return data


@router.post("/api/entity-governance/aliases")
def aliases(req: AliasIn):
    try:
        return service.add_alias(req.entityId, req.value, source=req.source or "manual")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/entity-resolution/resolve")
def resolve(req: ResolveIn):
    if not (req.name or "").strip():
        raise HTTPException(status_code=400, detail="name 不能为空")
    return service.resolve_entity(
        req.entityType,
        req.name.strip(),
        attributes=req.attributes or {},
        source=req.source or {},
        preferred_id=req.preferredId,
        create_if_new=True,
    )
