"""知识图谱语义治理 HTTP API。LLM 不在此路径写图谱。"""

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from . import service
from .llm import explain_inference
from .repository import get_kg_store

router = APIRouter(tags=["knowledge-governance"])


class TypeIn(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    parent_id: Optional[str] = None
    description: Optional[str] = ""
    type_schema: Optional[dict] = None


class MergeTypeIn(BaseModel):
    sourceId: str
    targetId: str


class RuleStatusIn(BaseModel):
    status: str


class RuleIn(BaseModel):
    id: Optional[str] = None
    name: str
    condition: list
    action: dict
    description: Optional[str] = ""
    status: Optional[str] = "ACTIVE"


class RollbackIn(BaseModel):
    revisionId: str


class ExplainIn(BaseModel):
    chain: list
    conclusion: str


class WorkItemPatch(BaseModel):
    proposed: Optional[dict] = None


class BatchIds(BaseModel):
    ids: list[str]


class RelationIn(BaseModel):
    id: Optional[str] = None
    name: str
    source_type: str
    target_type: str
    description: Optional[str] = ""
    rule: Optional[dict] = None


class ConstraintIn(BaseModel):
    id: Optional[str] = None
    name: str
    kind: str
    object_type: Optional[str] = ""
    property: Optional[str] = ""
    message: Optional[str] = ""
    expression: Optional[dict] = None
    status: Optional[str] = "ACTIVE"


class PropertiesIn(BaseModel):
    properties: list


class ClassifyIn(BaseModel):
    nodeId: str
    typeId: Optional[str] = None
    ontologyType: Optional[str] = None


@router.get("/api/knowledge-governance/overview")
def overview():
    return service.overview()


@router.get("/api/knowledge-governance/analyze")
def analyze(publish: bool = Query(False), force: bool = Query(False)):
    if publish:
        return service.propose_semantics(source="analyze", force=force)
    return service.analyze()


@router.post("/api/knowledge-governance/analyze/publish")
def analyze_publish(force: bool = Query(False)):
    return service.propose_semantics(source="analyze", force=force)


@router.get("/api/knowledge-governance/ontology/draft")
def draft():
    return service.ontology_draft()


@router.post("/api/knowledge-governance/ontology/apply")
def apply_draft():
    return service.apply_ontology_draft()


@router.get("/api/knowledge-governance/ontology/types")
def types():
    return service.type_tree()


@router.post("/api/knowledge-governance/ontology/types")
def create_type(req: TypeIn):
    if not req.name:
        raise HTTPException(400, "类型名必填")
    payload = req.model_dump()
    if payload.get("type_schema") is not None:
        payload["schema"] = payload["type_schema"]
    return service.upsert_type(payload)


@router.put("/api/knowledge-governance/ontology/types/{tid}")
def update_type(tid: str, req: TypeIn):
    existing = get_kg_store().get_type(tid)
    if not existing:
        raise HTTPException(404, "类型不存在")
    payload = req.model_dump(exclude_unset=True)
    payload["id"] = tid
    payload["name"] = payload.get("name") or existing["name"]
    if "parent_id" not in payload:
        payload["parent_id"] = existing.get("parent_id")
    if "description" not in payload:
        payload["description"] = existing.get("description")
    if payload.get("type_schema") is not None:
        payload["schema"] = payload["type_schema"]
    return service.upsert_type(payload)


@router.delete("/api/knowledge-governance/ontology/types/{tid}")
def delete_type(tid: str):
    try:
        return service.delete_ontology_type(tid)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/knowledge-governance/ontology/types/merge")
def merge_types(req: MergeTypeIn):
    try:
        return service.merge_types(req.sourceId, req.targetId)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/knowledge-governance/ontology/schema")
def compiled_schema():
    return service.compiled_schema()


@router.put("/api/knowledge-governance/ontology/types/{tid}/properties")
def save_properties(tid: str, req: PropertiesIn):
    try:
        return service.save_type_properties(tid, req.properties)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/knowledge-governance/ontology/relations")
def ontology_relations():
    return {"items": get_kg_store().list_ontology_relations()}


@router.post("/api/knowledge-governance/ontology/relations")
def upsert_relation(req: RelationIn):
    try:
        return service.save_ontology_relation(req.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/api/knowledge-governance/ontology/relations/{rid}")
def delete_relation(rid: str):
    try:
        return service.delete_ontology_relation(rid)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/knowledge-governance/ontology/constraints")
def constraints():
    return service.compiled_schema()


@router.post("/api/knowledge-governance/ontology/constraints")
def upsert_constraint(req: ConstraintIn):
    try:
        return service.save_constraint(req.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/api/knowledge-governance/ontology/constraints/{cid}")
def delete_constraint(cid: str):
    try:
        return service.delete_constraint(cid)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/knowledge-governance/rules")
def rules():
    return {"items": get_kg_store().list_rules(include_inactive=True)}


@router.post("/api/knowledge-governance/rules")
def upsert_rule(req: RuleIn):
    kg = get_kg_store()
    kg.snapshot(reason="upsert-rule")
    return kg.upsert_rule(req.model_dump())


@router.post("/api/knowledge-governance/rules/{rid}/status")
def set_rule_status(rid: str, req: RuleStatusIn):
    kg = get_kg_store()
    kg.snapshot(reason="rule-status")
    rec = kg.set_rule_status(rid, req.status)
    if not rec:
        raise HTTPException(404, "规则不存在")
    return rec


@router.post("/api/knowledge-governance/enhance")
def enhance():
    return service.propose_semantics(source="analyze")


@router.post("/api/knowledge-governance/apply-confirmed")
def apply_confirmed():
    return service.apply_confirmed()


@router.get("/api/knowledge-governance/inferred")
def inferred(limit: int = 80):
    return {"items": service.list_inferred(limit=limit)}


@router.post("/api/knowledge-governance/explain")
def explain(req: ExplainIn):
    return {"explanation": explain_inference(req.chain, req.conclusion)}


@router.get("/api/knowledge-governance/work-items")
def work_items(
    status: Optional[str] = Query("open"),
    type: Optional[str] = None,
    problem_code: Optional[str] = Query(None, alias="problemCode"),
    page: int = 1,
    pageSize: int = 80,
):
    return get_kg_store().list_work_items(
        status=status or "open",
        suggestion_type=type,
        problem_code=problem_code,
        page=page,
        page_size=pageSize,
    )


@router.post("/api/knowledge-governance/work-items/accept-batch")
def accept_batch(req: BatchIds):
    results = []
    for sid in req.ids or []:
        try:
            results.append({"id": sid, "ok": True, "item": service.accept_work_item(sid)})
        except Exception as e:
            results.append({"id": sid, "ok": False, "error": str(e)})
    return {"results": results}


@router.post("/api/knowledge-governance/work-items/classify")
def classify_ticket(req: ClassifyIn):
    try:
        return service.classify_instance_ticket(
            req.nodeId, type_id=req.typeId, ontology_type=req.ontologyType,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/api/knowledge-governance/work-items/classify/{node_id}")
def classify_ticket_path(node_id: str):
    try:
        return service.classify_instance_ticket(node_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/api/knowledge-governance/instances/{node_id}")
def instance_detail(node_id: str):
    try:
        return service.instance_detail(node_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.delete("/api/knowledge-governance/instances/{node_id}")
def retire_instance(node_id: str):
    try:
        return service.retire_instance(node_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch("/api/knowledge-governance/work-items/{sid}")
def patch_item(sid: str, req: WorkItemPatch):
    if req.proposed is None:
        raise HTTPException(400, "proposed 必填")
    try:
        return service.patch_work_item(sid, req.proposed)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/knowledge-governance/work-items/{sid}/accept")
def accept_item(sid: str, req: WorkItemPatch = Body(default_factory=WorkItemPatch)):
    try:
        return service.accept_work_item(sid, proposed=req.proposed)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/knowledge-governance/work-items/{sid}/reject")
def reject_item(sid: str):
    try:
        return service.reject_work_item(sid)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/api/knowledge-governance/work-items/{sid}/defer")
def defer_item(sid: str):
    try:
        return service.defer_work_item(sid)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/api/knowledge-governance/suggestions")
def suggestions(status: Optional[str] = "open"):
    mapped = "open" if status in ("pending", "open", None) else status
    return get_kg_store().list_work_items(status=mapped)


@router.post("/api/knowledge-governance/suggestions/{sid}/accept")
def accept(sid: str):
    try:
        return service.accept_work_item(sid)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/knowledge-governance/suggestions/{sid}/ignore")
def ignore(sid: str):
    try:
        return service.reject_work_item(sid)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/api/knowledge-governance/revisions")
def revisions():
    return {"items": get_kg_store().list_revisions(30)}


@router.post("/api/knowledge-governance/rollback")
def rollback(req: RollbackIn):
    try:
        return service.rollback_ontology(req.revisionId)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
