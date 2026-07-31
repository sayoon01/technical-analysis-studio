"""Project API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.deps import get_plan_service, get_project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectBody(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class PatchProjectBody(BaseModel):
    name: str | None = None
    description: str | None = None
    stage: str | None = None


@router.post("")
def create_project(body: CreateProjectBody):
    return get_project_service().create(body.name, body.description)


@router.get("")
def list_projects():
    return get_project_service().list()


@router.get("/{project_id}")
def get_project(project_id: str):
    try:
        return get_project_service().get(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found") from None


@router.patch("/{project_id}")
def patch_project(project_id: str, body: PatchProjectBody):
    try:
        return get_project_service().patch(
            project_id,
            name=body.name,
            description=body.description,
            stage=body.stage,
        )
    except KeyError:
        raise HTTPException(404, "Project not found") from None


@router.get("/{project_id}/status")
def project_status(project_id: str):
    try:
        return get_plan_service().generation_status(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found") from None
