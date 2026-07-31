"""Source service re-export path used by API (alias file)."""

# Kept for design tree compatibility: SourceService lives with ProjectService.
from backend.services.project_service import ProjectService, SourceService

__all__ = ["ProjectService", "SourceService"]
