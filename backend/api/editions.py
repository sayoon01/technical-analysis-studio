"""Edition and section API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_edition_service

router = APIRouter(tags=["editions-sections"])


class ProduceBody(BaseModel):
    parent_edition_id: str | None = None
    new_source_ids: list[str] | None = None
    resume_edition_id: str | None = None


class ImpactBody(BaseModel):
    parent_edition_id: str
    new_source_ids: list[str] | None = None


@router.post("/api/projects/{project_id}/editions")
def create_and_produce(project_id: str, body: ProduceBody | None = None):
    try:
        parent = body.parent_edition_id if body else None
        new_ids = body.new_source_ids if body else None
        resume_id = body.resume_edition_id if body else None
        return get_edition_service().produce(
            project_id,
            parent_edition_id=parent,
            new_source_ids=new_ids,
            resume_edition_id=resume_id,
        )
    except KeyError:
        raise HTTPException(404, "Project not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/projects/{project_id}/impact/preview")
def preview_impact(project_id: str, body: ImpactBody):
    try:
        return get_edition_service().preview_impact(
            project_id,
            body.parent_edition_id,
            new_source_ids=body.new_source_ids,
        )
    except KeyError:
        raise HTTPException(404, "Not found") from None


@router.get("/api/projects/{project_id}/editions")
def list_editions(project_id: str):
    return get_edition_service().list_editions(project_id)


@router.get("/api/editions/{edition_id}")
def get_edition(edition_id: str):
    try:
        return get_edition_service().get_edition(edition_id)
    except KeyError:
        raise HTTPException(404, "Edition not found") from None


@router.post("/api/editions/{edition_id}/produce")
def produce_edition(edition_id: str):
    try:
        edition = get_edition_service().get_edition(edition_id)
        return get_edition_service().produce(edition["project_id"])
    except KeyError:
        raise HTTPException(404, "Edition not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/editions/{edition_id}/resume")
def resume_edition(edition_id: str):
    """Continue writing an interrupted edition (skip completed DRAFT sections)."""
    try:
        return get_edition_service().resume(edition_id)
    except KeyError:
        raise HTTPException(404, "Edition not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/editions/{edition_id}/diff/{other_edition_id}")
def diff_editions(edition_id: str, other_edition_id: str):
    try:
        return get_edition_service().diff_editions(edition_id, other_edition_id)
    except KeyError:
        raise HTTPException(404, "Edition not found") from None


@router.get("/api/editions/{edition_id}/sections")
def list_sections(edition_id: str):
    return get_edition_service().list_sections(edition_id)


@router.get("/api/sections/{section_id}")
def get_section(section_id: str):
    try:
        return get_edition_service().get_section(section_id)
    except KeyError:
        raise HTTPException(404, "Section not found") from None


@router.get("/api/sections/{section_id}/evidence")
def get_section_evidence(section_id: str):
    try:
        return get_edition_service().get_section_evidence(section_id)
    except KeyError:
        raise HTTPException(404, "Section not found") from None


@router.get("/api/sections/{section_id}/versions")
def list_versions(section_id: str):
    try:
        return get_edition_service().list_versions(section_id)
    except KeyError:
        raise HTTPException(404, "Section not found") from None


@router.post("/api/sections/{section_id}/regenerate")
def regenerate(section_id: str):
    try:
        section = get_edition_service().get_section(section_id)
        edition = get_edition_service().get_edition(section["edition_id"])
        return get_edition_service().regenerate_section(
            edition["project_id"], section_id
        )
    except KeyError:
        raise HTTPException(404, "Section not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/sections/{section_id}/research")
def research_only(section_id: str):
    return regenerate(section_id)


@router.get("/api/claims/{claim_id}/locations")
def claim_locations(claim_id: str):
    try:
        return get_edition_service().resolve_claim_location(claim_id)
    except KeyError:
        raise HTTPException(404, "Claim not found") from None
