"""Connexion SQLite + helpers."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "app.db"


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
    """Initialise / met à jour le schéma DB via le runner de migrations.

    Applique toutes les migrations en attente dans `backend/migrations/`
    (cf `backend/_migrations.py`). Idempotent : sur une DB à jour, c'est
    un no-op (les migrations sont déjà dans `schema_migrations`).

    Appelée au boot de l'app (lifespan dans `backend/main.py`) et au début
    de chaque seed script. Les anciens ALTER TABLE conditionnels qui vivaient
    ici sont désormais formalisés dans les fichiers de migration.
    """
    # Import tardif : `_migrations` importe `db.get_connection` paresseusement
    # via le param `conn_factory`. Pas de cycle direct.
    from backend._migrations import apply_migrations
    apply_migrations()


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
