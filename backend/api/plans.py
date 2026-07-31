"""Analysis / plan / outline API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.deps import get_plan_service

router = APIRouter(tags=["analysis-plans"])


class PatchPlanBody(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    purpose: str | None = None
    target_reader: str | None = None
    report_summary: str | None = None


class PatchOutlineBody(BaseModel):
    nodes: list[dict] = Field(min_length=1)


@router.post("/api/projects/{project_id}/analyze")
def analyze(project_id: str):
    try:
        return get_plan_service().analyze(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/projects/{project_id}/analysis")
def get_analysis(project_id: str):
    try:
        return get_plan_service().get_analysis(project_id)
    except KeyError:
        raise HTTPException(404, "Analysis not found") from None


@router.get("/api/projects/{project_id}/metrics")
def get_metrics(project_id: str):
    return get_plan_service().get_metrics(project_id)


@router.get("/api/projects/{project_id}/evidence-gaps")
def get_gaps(project_id: str):
    return {"evidence_gaps": get_plan_service().get_evidence_gaps(project_id)}


@router.post("/api/projects/{project_id}/plans/generate")
def generate_plan(project_id: str):
    try:
        return get_plan_service().generate_plan(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/projects/{project_id}/plan")
def get_plan(project_id: str):
    try:
        return get_plan_service().get_plan(project_id)
    except KeyError:
        raise HTTPException(404, "Plan not found") from None


@router.patch("/api/projects/{project_id}/plan")
def patch_plan(project_id: str, body: PatchPlanBody):
    try:
        return get_plan_service().patch_plan(
            project_id,
            title=body.title,
            subtitle=body.subtitle,
            purpose=body.purpose,
            target_reader=body.target_reader,
            report_summary=body.report_summary,
        )
    except KeyError:
        raise HTTPException(404, "Plan not found") from None


@router.get("/api/projects/{project_id}/outline")
def get_outline(project_id: str):
    try:
        return get_plan_service().get_outline(project_id)
    except KeyError:
        raise HTTPException(404, "Outline not found") from None


@router.patch("/api/projects/{project_id}/outline")
def patch_outline(project_id: str, body: PatchOutlineBody):
    try:
        return get_plan_service().patch_outline(project_id, body.nodes)
    except KeyError:
        raise HTTPException(404, "Outline not found") from None
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/projects/{project_id}/outline/nodes/{node_id}/recommend")
def recommend_node(project_id: str, node_id: str):
    try:
        return get_plan_service().recommend_node(project_id, node_id)
    except KeyError:
        raise HTTPException(404, "Node not found") from None


@router.post("/api/projects/{project_id}/outline/approve")
def approve_outline(project_id: str):
    try:
        return get_plan_service().approve_outline(project_id)
    except KeyError:
        raise HTTPException(404, "Outline not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
