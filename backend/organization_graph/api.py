"""organization-graph-service HTTP API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import service


router = APIRouter(tags=["organization-graph"])


class ExtractRequest(BaseModel):
    text: str
    source_type: Optional[str] = "document"


class ApplyExtractRequest(BaseModel):
    text: Optional[str] = ""
    source_type: Optional[str] = "document"
    entities: Optional[list] = None
    relations: Optional[list] = None


class EventUpdateRequest(BaseModel):
    name: str
    time: Optional[str] = None
    description: Optional[str] = None


@router.get("/api/v1/graph/status")
def graph_status():
    return service.graph_status()


@router.get("/api/v1/graph")
def get_graph(
    types: Optional[str] = Query(None, description="逗号分隔节点类型"),
    relations: Optional[str] = Query(None, description="逗号分隔关系类型"),
    includeMerged: bool = Query(False),
    asOf: Optional[str] = Query(None, description="YYYY-MM-DD 历史快照"),
    includeHistory: bool = Query(False),
):
    node_types = [x.strip() for x in types.split(",") if x.strip()] if types else None
    rels = [x.strip() for x in relations.split(",") if x.strip()] if relations else None
    return service.get_graph(
        node_types, rels,
        include_merged=includeMerged,
        as_of=asOf,
        include_history=includeHistory,
    )


@router.post("/api/v1/graph/rebuild")
def rebuild_graph():
    return {"status": "success", **service.rebuild_graph()}


@router.get("/api/v1/person/{person_id}/network")
def person_network(person_id: str):
    data = service.person_network(person_id)
    if not data:
        raise HTTPException(status_code=404, detail="人员不存在于影响力图谱")
    return data


@router.get("/api/v1/person/{person_id}/leadership-profile")
def leadership_profile(person_id: str):
    data = service.leadership_profile(person_id)
    if not data:
        raise HTTPException(status_code=404, detail="人员不存在于影响力图谱")
    return data


@router.get("/api/v1/influence/ranking")
def influence_ranking(
    asOf: Optional[str] = Query(None),
    dateFrom: Optional[str] = Query(None),
    dateTo: Optional[str] = Query(None),
):
    return service.influence_ranking(as_of=asOf, date_from=dateFrom, date_to=dateTo)


@router.get("/api/v1/community")
def community():
    return service.get_communities()


@router.get("/api/v1/risk")
def risk():
    return service.get_risks()


@router.post("/api/v1/extract")
def extract(req: ExtractRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="文本不能为空")
    return service.extract_preview(req.text.strip(), req.source_type or "document")


@router.post("/api/v1/extract/apply")
def extract_apply(req: ApplyExtractRequest):
    if not (req.relations or req.entities):
        raise HTTPException(status_code=400, detail="没有可写入的抽取结果")
    return service.apply_confirmed_extraction(
        {"entities": req.entities or [], "relations": req.relations or []},
        text=req.text or "",
        source_type=req.source_type or "document",
    )


@router.get("/api/v1/extract/history")
def extract_history(limit: int = Query(20)):
    return service.extraction_history(limit)


@router.post("/api/v1/graph/event")
def event_update(req: EventUpdateRequest):
    if not req.name.strip() and not (req.description or "").strip():
        raise HTTPException(status_code=400, detail="事件名称或描述不能为空")
    return service.apply_event_update(req.name, req.time, req.description)
