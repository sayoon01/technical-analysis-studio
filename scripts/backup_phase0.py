"""Phase 0 backup helper.

Creates:
  data/backup/tas-before-adk.db
  data/backup/legacy-mes-output/
"""

from __future__ import annotations

import shutil
from pathlib import Path


def _copy_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    backup_root = data_dir / "backup"
    backup_root.mkdir(parents=True, exist_ok=True)

    _copy_if_exists(data_dir / "tas.db", backup_root / "tas-before-adk.db")

    legacy_out = backup_root / "legacy-mes-output"
    legacy_out.mkdir(parents=True, exist_ok=True)
    _copy_tree_if_exists(data_dir / "exports", legacy_out)

    print(f"backup created at: {backup_root}")


if __name__ == "__main__":
    main()
