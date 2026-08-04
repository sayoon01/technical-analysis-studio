"""Export API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.api.deps import get_export_service

router = APIRouter(tags=["exports"])


@router.post("/api/editions/{edition_id}/exports")
def create_export(edition_id: str):
    try:
        return get_export_service().export_edition(edition_id)
    except KeyError:
        raise HTTPException(404, "Edition not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Export failed: {e}") from e


@router.get("/api/editions/{edition_id}/export-readiness")
def export_readiness(edition_id: str):
    try:
        return get_export_service().export_readiness(edition_id)
    except KeyError:
        raise HTTPException(404, "Edition not found") from None


@router.get("/api/editions/{edition_id}/exports")
def list_exports(edition_id: str):
    return get_export_service().list_exports(edition_id)


@router.get("/api/exports/{export_id}/download")
def download_export(export_id: str):
    try:
        path = get_export_service().download_path(export_id)
    except KeyError:
        raise HTTPException(404, "Export not found") from None
    except FileNotFoundError:
        raise HTTPException(404, "File missing") from None
    return FileResponse(path, filename=path.name)
