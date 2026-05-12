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
            # Index UNIQUE : passage de (name) seul à (name, city) — autorise multi-implantation
            old_idx = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_target_companies_name'"
            ).fetchone()
            if old_idx:
                conn.execute("DROP INDEX idx_target_companies_name")
        # Étape 2 : appliquer le schéma complet (CREATE IF NOT EXISTS + indexes)
        conn.executescript(schema)


def normalize_for_dedup(text: str | None) -> str:
    """Normalise une string pour la clé de dédup (titre+entreprise+ville)."""
    if not text:
        return ""
    import re
    s = str(text).strip().lower()
    s = re.sub(r"[\s\W]+", " ", s)
    return s.strip()


def normalize_city_for_dedup(city: str | None) -> str:
    """Normalise une ville pour le dédup.

    Cas gérés :
    - "Paris" / "75 - Paris" / "75 paris" / "PARIS" → "paris"
    - "31 - Toulouse" / "Toulouse (31), France" → "toulouse"
    - "Pau (Bordes)" → "pau" (parenthèses retirées)
    - "Paris, France" / "Paris (France)" → "paris"
    - "" / None → ""
    """
    if not city:
        return ""
    import re
    s = str(city).strip().lower()
    # Vire les parenthèses et leur contenu (Pau (Bordes) → Pau)
    s = re.sub(r"\([^)]*\)", " ", s)
    # Normalise espaces et ponctuation
    s = re.sub(r"[\s\W]+", " ", s).strip()
    # Vire les codes département en début (75 paris → paris, 75 - paris → paris)
    s = re.sub(r"^\d{2,3}\s+", "", s)
    # Vire les suffixes inutiles (paris france → paris)
    s = re.sub(r"\s+france\b.*$", "", s)
    return s.strip()


def make_dedup_key(
    title: str | None,
    company: str | None,
    city: str | None = None,
) -> str:
    """Clé de dédup pour une offre.

    Capture (titre, entreprise, ville) — la ville est essentielle car la même
    offre Capgemini "AI Engineer" peut exister à Paris ET Toulouse en tant que
    DEUX postes distincts. Sans la ville, on jetterait l'un comme doublon.

    La ville est normalisée pour matcher les variantes :
        "Paris" == "75 - Paris" == "Paris, France"
    """
    parts = [
        normalize_for_dedup(title),
        normalize_for_dedup(company),
        normalize_city_for_dedup(city),
    ]
    return "|".join(parts)
