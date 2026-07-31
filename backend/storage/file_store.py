"""Project-scoped filesystem layout."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from backend.config import settings


class FileStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(settings.data_dir) / "projects"
        self.root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        path = self.root / project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def sources_dir(self, project_id: str) -> Path:
        path = self.project_dir(project_id) / "sources"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def source_dir(self, project_id: str, source_id: str) -> Path:
        path = self.sources_dir(project_id) / source_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def pages_dir(self, project_id: str, source_id: str) -> Path:
        path = self.source_dir(project_id, source_id) / "pages"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_upload(
        self,
        project_id: str,
        filename: str,
        data: bytes,
        source_id: str | None = None,
    ) -> tuple[str, Path]:
        sid = source_id or f"SRC-{uuid.uuid4().hex[:10].upper()}"
        dest_dir = self.source_dir(project_id, sid)
        # Keep original extension
        suffix = Path(filename).suffix or ".bin"
        dest = dest_dir / f"original{suffix}"
        dest.write_bytes(data)
        return sid, dest

    def page_image_path(
        self, project_id: str, source_id: str, page_number: int
    ) -> Path:
        return self.pages_dir(project_id, source_id) / f"page-{page_number:04d}.png"

    def remove_source(self, project_id: str, source_id: str) -> None:
        path = self.source_dir(project_id, source_id)
        if path.exists():
            shutil.rmtree(path)
