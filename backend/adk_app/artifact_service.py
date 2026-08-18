from __future__ import annotations

from pathlib import Path

from google.adk.artifacts.file_artifact_service import FileArtifactService

from backend.config import settings


def artifact_root() -> Path:
    root = (settings.data_dir.resolve() / "adk_artifacts").resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise RuntimeError(f"Artifact root is not a directory: {root}")
    return root


def build_artifact_service() -> FileArtifactService:
    return FileArtifactService(artifact_root())
