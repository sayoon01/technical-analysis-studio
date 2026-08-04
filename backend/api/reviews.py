"""Review API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.deps import get_review_service

router = APIRouter(tags=["reviews"])


@router.post("/api/editions/{edition_id}/review")
def review_edition(edition_id: str):
    try:
        return get_review_service().review_edition(edition_id)
    except KeyError:
        raise HTTPException(404, "Edition not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/editions/{edition_id}/review/full")
def review_full_report(edition_id: str):
    try:
        return get_review_service().review_full_report(edition_id)
    except KeyError:
        raise HTTPException(404, "Edition not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/sections/{section_id}/review")
def review_section(section_id: str):
    try:
        return get_review_service().review_section(section_id)
    except KeyError:
        raise HTTPException(404, "Section not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/sections/{section_id}/reviews")
def list_reviews(section_id: str):
    try:
        return get_review_service().list_section_reviews(section_id)
    except KeyError:
        raise HTTPException(404, "Section not found") from None


@router.get("/api/sections/{section_id}/issues")
def list_issues(section_id: str):
    try:
        return get_review_service().open_issues(section_id)
    except KeyError:
        raise HTTPException(404, "Section not found") from None


@router.get("/api/editions/{edition_id}/reviews/full")
def list_full_reviews(edition_id: str):
    try:
        return get_review_service().list_full_report_reviews(edition_id)
    except KeyError:
        raise HTTPException(404, "Edition not found") from None
