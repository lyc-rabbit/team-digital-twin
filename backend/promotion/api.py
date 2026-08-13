"""晋升推演 HTTP API。"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import service
from .templates import list_templates


router = APIRouter(prefix="/api/promotion", tags=["promotion"])


class CustomRequirement(BaseModel):
    name: str
    weight: float


class CreateSimulationRequest(BaseModel):
    name: Optional[str] = None
    target_role_id: Optional[str] = None
    target_role_name: Optional[str] = None
    department: Optional[str] = None
    candidate_scope: Optional[list[str]] = None
    style_id: Optional[str] = "tech_expert"
    leadership_style: Optional[dict] = None
    custom_requirements: Optional[list[CustomRequirement]] = None
    layer_weights: Optional[dict] = None


class UpdateWeightsRequest(BaseModel):
    layer_weights: Optional[dict] = None
    custom_requirements: Optional[list[CustomRequirement]] = None
    sub_weights: Optional[dict] = None


@router.get("/templates")
def templates():
    return list_templates()


@router.get("/simulations")
def list_simulations():
    return {"simulations": service.list_simulations()}


@router.post("/simulations")
def create_simulation(req: CreateSimulationRequest):
    try:
        sim = service.create_simulation(req.model_dump())
        return {"status": "running", "simulation": sim}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/simulations/{sim_id}")
def get_simulation(sim_id: str):
    detail = service.get_simulation_detail(sim_id)
    if not detail:
        raise HTTPException(status_code=404, detail="推演任务不存在")
    return detail


@router.get("/simulations/{sim_id}/status")
def get_status(sim_id: str):
    st = service.get_status(sim_id)
    if not st:
        raise HTTPException(status_code=404, detail="推演任务不存在")
    return st


@router.put("/simulations/{sim_id}/weights")
def update_weights(sim_id: str, req: UpdateWeightsRequest):
    custom = None
    if req.custom_requirements is not None:
        custom = [c.model_dump() for c in req.custom_requirements]
    try:
        detail = service.update_weights(
            sim_id,
            layer_weights=req.layer_weights,
            custom_requirements=custom,
            sub_weights=req.sub_weights,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not detail:
        raise HTTPException(status_code=404, detail="推演任务不存在")
    return {"status": "success", "message": "已按新权重重算，未重新调用 AI", **detail}


@router.post("/simulations/{sim_id}/cancel")
def cancel_simulation(sim_id: str):
    st = service.cancel_simulation(sim_id)
    if not st:
        raise HTTPException(status_code=404, detail="推演任务不存在")
    return {"status": "cancelled", "simulation": st}


@router.delete("/simulations/{sim_id}")
def delete_simulation(sim_id: str):
    if not service.delete_simulation(sim_id):
        raise HTTPException(status_code=404, detail="推演任务不存在")
    return {"status": "success"}
