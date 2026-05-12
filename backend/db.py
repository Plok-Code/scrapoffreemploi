"""Connexion SQLite + helpers."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "app.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Connexion SQLite avec row_factory dict-like et FK on."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db():
    """Context manager : commit auto en sortie OK, rollback sur exception."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    """Crée les tables si elles n'existent pas. Idempotent."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with db() as conn:
        conn.executescript(schema)


def normalize_for_dedup(text: str | None) -> str:
    """Normalise une string pour la clé de dédup (titre+entreprise)."""
    if not text:
        return ""
    import re
    s = str(text).strip().lower()
    s = re.sub(r"[\s\W]+", " ", s)
    return s.strip()


def make_dedup_key(title: str | None, company: str | None) -> str:
    return f"{normalize_for_dedup(title)}|{normalize_for_dedup(company)}"
