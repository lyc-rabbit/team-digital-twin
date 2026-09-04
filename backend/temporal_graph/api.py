"""时态图谱 HTTP API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import query, service
from .events import apply_event
from .repository import get_temporal_store
from .types import TEMPORAL_EVENT_TYPES

router = APIRouter(tags=["temporal-graph"])


class TemporalEventIn(BaseModel):
    event_type: str
    event_time: str
    person_id: Optional[str] = None
    other_person_id: Optional[str] = None
    project_id: Optional[str] = None
    resource_id: Optional[str] = None
    department_id: Optional[str] = None
    role_id: Optional[str] = None
    skill_id: Optional[str] = None
    description: Optional[str] = ""
    operator: Optional[str] = ""


@router.get("/api/temporal/overview")
def overview():
    return service.overview()


@router.get("/api/temporal/event-types")
def event_types():
    return {"items": list(TEMPORAL_EVENT_TYPES)}


@router.get("/api/temporal/snapshot")
def get_snapshot(asOf: str = Query(..., description="YYYY-MM-DD")):
    return query.snapshot(asOf)


@router.get("/api/temporal/facts")
def facts(
    subjectId: Optional[str] = None,
    objectId: Optional[str] = None,
    predicate: Optional[str] = None,
    asOf: Optional[str] = None,
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    openOnly: bool = False,
):
    store = get_temporal_store()
    if asOf:
        items = store.facts_as_of(asOf, predicate=predicate)
        if subjectId:
            items = [f for f in items if f["subject_id"] == subjectId]
        if objectId:
            items = [f for f in items if f["object_id"] == objectId]
        return {"items": items}
    if dateFrom or dateTo:
        items = store.facts_overlapping(dateFrom, dateTo, subjectId, objectId, predicate)
        return {"items": items}
    return {
        "items": store.list_facts(
            subject_id=subjectId, object_id=objectId, predicate=predicate, open_only=openOnly,
        )
    }


@router.get("/api/temporal/range")
def range_query(objectId: str, dateFrom: str, dateTo: str, predicates: Optional[str] = None):
    preds = [x.strip() for x in predicates.split(",") if x.strip()] if predicates else ["OWNER", "WORKS_ON"]
    return query.range_participants(objectId, dateFrom, dateTo, preds)


@router.get("/api/temporal/person/{person_id}/timeline")
def person_tl(person_id: str):
    data = query.person_timeline(person_id)
    return data


@router.get("/api/temporal/project/{project_id}/timeline")
def project_tl(project_id: str):
    return query.project_timeline(project_id)


@router.post("/api/temporal/events")
def create_event(req: TemporalEventIn):
    try:
        return apply_event(
            req.event_type,
            req.event_time,
            person_id=req.person_id,
            other_person_id=req.other_person_id,
            project_id=req.project_id,
            resource_id=req.resource_id,
            department_id=req.department_id,
            role_id=req.role_id,
            skill_id=req.skill_id,
            description=req.description or "",
            operator=req.operator or "",
        )
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/temporal/events")
def list_events(limit: int = 50, entityId: Optional[str] = None):
    return {"items": get_temporal_store().list_events(limit=limit, entity_id=entityId)}


@router.get("/api/temporal/influence")
def temporal_influence(
    asOf: Optional[str] = None,
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
):
    from organization_graph.builder import GraphBuilder
    GraphBuilder().ensure_built()
    from organization_graph.repository.facade import get_facade
    graph = get_facade()
    nodes = graph.list_nodes()
    edges = graph.list_edges()
    scores, meta = service.influence_window(nodes, edges, dateFrom, dateTo, asOf)
    ranking = sorted(scores.values(), key=lambda x: x["influence_score"], reverse=True)
    return {"ranking": ranking, "meta": meta}


@router.post("/api/temporal/sync")
def sync():
    from organization_graph.repository.store import get_sqlite_store
    return service.sync_after_rebuild(get_sqlite_store())
