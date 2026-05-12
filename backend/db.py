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
    """Crée les tables si elles n'existent pas. Idempotent.

    Inclut une mini-migration : ajoute les colonnes manquantes AVANT d'exécuter
    le schéma (les nouveaux index référencent ces colonnes).
    """
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with db() as conn:
        # Étape 1 : migrations conditionnelles si la table existe déjà
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='offers'"
        ).fetchone()
        if table_exists:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(offers)").fetchall()}
            if "is_active" not in cols:
                conn.execute("ALTER TABLE offers ADD COLUMN is_active INTEGER DEFAULT 1")
                conn.execute("UPDATE offers SET is_active = 1 WHERE is_active IS NULL")
            if "last_checked_at" not in cols:
                conn.execute("ALTER TABLE offers ADD COLUMN last_checked_at TEXT")
        # Migration target_companies (colonnes city + source ajoutées après v1)
        target_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='target_companies'"
        ).fetchone()
        if target_table:
            tc_cols = {r["name"] for r in conn.execute("PRAGMA table_info(target_companies)").fetchall()}
            if "city" not in tc_cols:
                conn.execute("ALTER TABLE target_companies ADD COLUMN city TEXT")
            if "source" not in tc_cols:
                conn.execute("ALTER TABLE target_companies ADD COLUMN source TEXT")
                conn.execute("UPDATE target_companies SET source = 'xlsx historique' WHERE source IS NULL")
        # Étape 2 : appliquer le schéma complet (CREATE IF NOT EXISTS + indexes)
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
