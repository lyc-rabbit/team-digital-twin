"""事实治理 HTTP API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import service

router = APIRouter(tags=["fact-governance"])


class FactIn(BaseModel):
    subject: str
    predicate: str
    object: str
    fact_type: Optional[str] = "RELATION"
    subject_type: Optional[str] = ""
    object_type: Optional[str] = ""
    ontology_relation: Optional[str] = ""
    valid_from: Optional[str] = ""
    valid_to: Optional[str] = ""
    confidence: Optional[float] = 1.0
    source_type: Optional[str] = "manual"
    source_title: Optional[str] = ""
    source_text: Optional[str] = ""
    source_ref: Optional[str] = ""
    page: Optional[str] = ""
    locator: Optional[str] = ""
    created_by: Optional[str] = "user"


class DeleteIn(BaseModel):
    delete_fact: Optional[bool] = True
    delete_direct_relations: Optional[bool] = True
    stale_downstream: Optional[bool] = True
    auto_rebuild: Optional[bool] = False
    reason: Optional[str] = ""
    operator: Optional[str] = "user"


class RejectIn(BaseModel):
    reason: Optional[str] = ""
    operator: Optional[str] = "user"


class ExtractIn(BaseModel):
    text: str
    source_title: Optional[str] = ""
    source_type: Optional[str] = "document"
    page: Optional[str] = ""
    created_by: Optional[str] = "user"


class SupersedeIn(FactIn):
    pass


def _err(e):
    raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/fact-governance/overview")
def overview():
    return service.overview()


@router.get("/api/fact-governance/facts")
def list_facts(
    status: Optional[str] = Query("all"),
    q: Optional[str] = None,
    page: int = Query(1),
    pageSize: int = Query(80),
):
    return service.list_facts(status=status, q=q, page=page, page_size=pageSize)


@router.post("/api/fact-governance/facts")
def create_fact(req: FactIn):
    try:
        return service.create_fact(req.model_dump(), created_by=req.created_by or "user")
    except ValueError as e:
        _err(e)


@router.get("/api/fact-governance/facts/{fact_id}")
def get_fact(fact_id: str):
    try:
        return service.get_fact(fact_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/fact-governance/facts/{fact_id}/confirm")
def confirm_fact(fact_id: str):
    try:
        return service.confirm_fact(fact_id)
    except ValueError as e:
        _err(e)


@router.post("/api/fact-governance/facts/{fact_id}/reject")
def reject_fact(fact_id: str, req: RejectIn = RejectIn()):
    try:
        return service.reject_fact(fact_id, reason=req.reason or "", operator=req.operator or "user")
    except ValueError as e:
        _err(e)


@router.get("/api/fact-governance/facts/{fact_id}/impact")
def impact(fact_id: str):
    try:
        service.get_fact(fact_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return service.impact_preview(fact_id)


@router.post("/api/fact-governance/facts/{fact_id}/delete")
def delete_fact(fact_id: str, req: DeleteIn = DeleteIn()):
    try:
        return service.delete_fact(fact_id, options=req.model_dump(), operator=req.operator or "user")
    except ValueError as e:
        _err(e)


@router.post("/api/fact-governance/facts/{fact_id}/supersede")
def supersede(fact_id: str, req: SupersedeIn):
    try:
        return service.supersede_fact(fact_id, req.model_dump(), operator=req.created_by or "user")
    except ValueError as e:
        _err(e)


@router.post("/api/fact-governance/extract")
def extract(req: ExtractIn):
    if not (req.text or "").strip():
        raise HTTPException(status_code=400, detail="文本不能为空")
    return service.run_extract(
        req.text.strip(),
        source_title=req.source_title or "",
        source_type=req.source_type or "document",
        page=req.page or "",
        created_by=req.created_by or "user",
    )


@router.get("/api/fact-governance/jobs")
def jobs():
    return service.list_jobs()


@router.get("/api/fact-governance/conflicts")
def conflicts():
    return service.list_conflicts()


@router.get("/api/fact-governance/rebuild-tasks")
def rebuild_tasks():
    return service.list_rebuild_tasks()


@router.post("/api/fact-governance/ingest-legacy")
def ingest_legacy():
    return service.ingest_legacy()
