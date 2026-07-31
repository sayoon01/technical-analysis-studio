"""Validate rendered visual artifacts exist and are non-empty."""

from __future__ import annotations

from pathlib import Path


def validate_visual_file(path: Path, *, min_bytes: int = 32) -> bool:
    return path.is_file() and path.stat().st_size >= min_bytes


def count_unrendered(requests: list[dict], rendered_paths: dict[str, Path]) -> int:
    missing = 0
    for req in requests:
        vid = req.get("visual_id")
        path = rendered_paths.get(vid)
        if not path or not validate_visual_file(path):
            missing += 1
    return missing
