"""Source API routes."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.api.deps import get_source_service
from backend.domain.enums import SourceRole

router = APIRouter(tags=["sources"])


class RoleBody(BaseModel):
    role: SourceRole


@router.post("/api/projects/{project_id}/sources")
async def upload_source(
    project_id: str,
    file: UploadFile = File(...),
    role: str = Form(default="EVIDENCE_SOURCE"),
):
    data = await file.read()
    filename = file.filename or "upload.bin"
    try:
        return get_source_service().upload(
            project_id, filename, data, role=role
        )
    except KeyError:
        raise HTTPException(404, "Project not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/projects/{project_id}/sources")
def list_sources(project_id: str):
    return get_source_service().list(project_id)


@router.get("/api/sources/{source_id}")
def get_source(source_id: str):
    try:
        return get_source_service().get(source_id)
    except KeyError:
        raise HTTPException(404, "Source not found") from None


@router.patch("/api/sources/{source_id}/role")
def patch_role(source_id: str, body: RoleBody):
    try:
        return get_source_service().set_role(source_id, body.role.value)
    except KeyError:
        raise HTTPException(404, "Source not found") from None


@router.post("/api/sources/{source_id}/process")
def process_source(source_id: str):
    try:
        return get_source_service().process(source_id)
    except KeyError:
        raise HTTPException(404, "Source not found") from None
    except Exception as e:
        raise HTTPException(500, f"Processing failed: {e}") from e


@router.get("/api/sources/{source_id}/pages")
def list_pages(source_id: str):
    return get_source_service().list_pages(source_id)


@router.get("/api/sources/{source_id}/pages/{page_number}")
def get_page(source_id: str, page_number: int):
    try:
        return get_source_service().get_page(source_id, page_number)
    except KeyError:
        raise HTTPException(404, "Page not found") from None


@router.get("/api/projects/{project_id}/search")
def search_project(
    project_id: str,
    q: str = Query(min_length=1),
    source_id: str | None = None,
):
    source_ids = [source_id] if source_id else None
    return get_source_service().search(project_id, q, source_ids=source_ids)
