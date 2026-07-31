"""Initialize SQLite schema from migrations/001_init.sql."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "backend" / "storage" / "migrations" / "001_init.sql"
DB_PATH = ROOT / "data" / "tas.db"


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    sql = SQL.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(sql)
        conn.commit()
        print(f"Initialized {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
