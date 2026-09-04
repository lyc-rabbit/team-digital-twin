"""P2 模拟实验室 HTTP API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_member

from . import repository as repo
from . import growth as growth_mod
from . import mentoring
from . import training
from . import org
from . import social
from . import leadership
from . import policy
from . import scenarios

router = APIRouter(tags=["twin"])


class SimulateIn(BaseModel):
    scenario: Optional[str] = None
    question: Optional[str] = None
    person_id: Optional[str] = None
    manager_id: Optional[str] = None
    mentor_id: Optional[str] = None
    mentee_id: Optional[str] = None
    mentee_ids: Optional[list[str]] = None
    reportee_ids: Optional[list[str]] = None
    project_id: Optional[str] = None
    target_id: Optional[str] = None
    person_a: Optional[str] = None
    person_b: Optional[str] = None
    days: Optional[int] = 90
    role_id: Optional[str] = "developer"
    from_level: Optional[str] = "L1"
    to_level: Optional[str] = "L2"
    add_newcomers: Optional[int] = 10
    add_seniors: Optional[int] = 2
    add_managers: Optional[int] = 1
    hire_count: Optional[int] = 10
    mix: Optional[dict] = None
    trees: Optional[list] = None
    custom: Optional[str] = None


class ActualIn(BaseModel):
    days_to_target: Optional[float] = None
    readiness: Optional[float] = None
    days: Optional[float] = None
    score: Optional[float] = None
    note: Optional[str] = None


class PolicyIn(BaseModel):
    id: Optional[str] = None
    category: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[str] = None


class PolicyOutcomeIn(BaseModel):
    metric: str
    before_value: Optional[float] = None
    after_value: Optional[float] = None
    note: Optional[str] = ""


def _need_member(person_id):
    if not person_id or not get_member(person_id):
        raise HTTPException(status_code=404, detail="成员不存在")


@router.get("/api/twin/bootstrap")
def twin_bootstrap():
    return scenarios.bootstrap()


@router.post("/api/twin/simulate")
def twin_simulate(req: SimulateIn):
    try:
        return scenarios.run(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/twin/simulations")
def twin_sim_list(limit: int = Query(40)):
    return {"items": repo.list_simulations(limit)}


@router.get("/api/twin/simulations/{sid}")
def twin_sim_detail(sid: str):
    item = repo.get_simulation(sid)
    if not item:
        raise HTTPException(status_code=404, detail="推演不存在")
    return item


@router.get("/api/twin/predictions")
def twin_pred_list(person_id: Optional[str] = None, kind: Optional[str] = None):
    return {"items": repo.list_predictions(person_id, kind)}


@router.post("/api/twin/predictions/{pid}/actual")
def twin_pred_actual(pid: str, req: ActualIn):
    item = repo.record_actual(pid, {k: v for k, v in req.model_dump().items() if v is not None})
    if not item:
        raise HTTPException(status_code=404, detail="预测不存在")
    return item


@router.get("/api/twin/growth/{person_id}")
def twin_growth(person_id: str, days: int = Query(90)):
    _need_member(person_id)
    return growth_mod.predict_growth(person_id, days)


@router.get("/api/twin/path/{person_id}")
def twin_path(person_id: str):
    _need_member(person_id)
    return {
        "path": leadership.cadre_path(person_id),
        "type": leadership.management_type(person_id),
        "style": leadership.management_style(person_id),
        "growth": growth_mod.predict_growth(person_id, 90),
    }


@router.post("/api/twin/mentoring")
def twin_mentoring(req: SimulateIn):
    data = mentoring.simulate_span(req.manager_id or req.person_id, req.reportee_ids or req.mentee_ids or [])
    if not data:
        raise HTTPException(status_code=404, detail="管理者不存在")
    return data


@router.post("/api/twin/match")
def twin_match(req: SimulateIn):
    data = mentoring.match_mentor(req.manager_id or req.mentor_id, req.mentee_id)
    if not data:
        raise HTTPException(status_code=404, detail="成员不存在")
    return data


@router.post("/api/twin/training/plan")
def twin_plan(req: SimulateIn):
    return training.generate_plan(
        req.person_id or req.mentee_id, req.mentor_id or req.manager_id,
        req.role_id or "developer", req.from_level or "L1", req.to_level or "L2", req.days or 60,
    )


@router.get("/api/twin/training/optimize/{person_id}")
def twin_optimize(person_id: str):
    _need_member(person_id)
    return training.optimize_plan(person_id)


@router.post("/api/twin/training/compare")
def twin_compare(req: SimulateIn):
    return training.compare_schemes(req.person_id or req.mentee_id, req.mentor_id or req.manager_id)


@router.post("/api/twin/training/cohort")
def twin_cohort(req: SimulateIn):
    return training.simulate_cohort(req.hire_count or 10, req.mix)


@router.post("/api/twin/org/expand")
def twin_expand(req: SimulateIn):
    return org.expand(req.add_newcomers or 10, req.add_seniors or 2, req.add_managers or 1)


@router.get("/api/twin/org/pipeline")
def twin_pipeline():
    return org.pipeline()


@router.get("/api/twin/org/structures")
def twin_structures():
    trees = org.default_structures()
    return {"trees": trees, **org.compare_structures(trees)}


@router.post("/api/twin/org/structures")
def twin_structures_compare(req: SimulateIn):
    trees = req.trees or org.default_structures()
    return {"trees": trees, **org.compare_structures(trees)}


@router.get("/api/twin/org/departure/{person_id}")
def twin_departure(person_id: str):
    _need_member(person_id)
    return org.departure(person_id)


@router.get("/api/twin/org/knowledge/{person_id}")
def twin_knowledge(person_id: str):
    _need_member(person_id)
    return org.knowledge_map(person_id)


@router.get("/api/twin/org/informal")
def twin_informal():
    return social.informal_groups()


@router.post("/api/twin/org/conflict")
def twin_conflict(req: SimulateIn):
    data = social.predict_conflict(req.person_a, req.person_b)
    if not data:
        raise HTTPException(status_code=400, detail="需要两名成员")
    return data


@router.get("/api/twin/leadership/auth/{person_id}")
def twin_auth(person_id: str, project_id: Optional[str] = None):
    _need_member(person_id)
    return leadership.auth_if_own_project(person_id, project_id)


@router.get("/api/twin/policies")
def twin_policies():
    return policy.catalog()


@router.post("/api/twin/policies")
def twin_policy_save(req: PolicyIn):
    return repo.upsert_policy(req.model_dump())


@router.get("/api/twin/policies/{pid}")
def twin_policy_one(pid: str):
    data = policy.evaluate_policy(pid)
    if not data:
        raise HTTPException(status_code=404, detail="制度不存在")
    return data


@router.post("/api/twin/policies/{pid}/outcome")
def twin_policy_outcome(pid: str, req: PolicyOutcomeIn):
    if not repo.get_policy(pid):
        raise HTTPException(status_code=404, detail="制度不存在")
    repo.add_policy_outcome(pid, req.metric, req.before_value, req.after_value, req.note or "")
    return policy.evaluate_policy(pid)
