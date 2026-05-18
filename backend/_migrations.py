"""Runner de migrations SQLite versionnées.

Architecture
------------
- `backend/migrations/{NNN}_{descripteur}.sql` : fichiers SQL numérotés.
- `schema_migrations` (table) : track les versions appliquées
  (`version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT`).
- `apply_migrations()` : crée la table si manquante, itère sur les fichiers
  triés par version, applique en transaction ceux absents de
  `schema_migrations`, log chaque application.

Pour une DB existante (à jour côté schéma) : les `CREATE TABLE IF NOT EXISTS`
de `001_initial.sql` sont no-op, puis 001 est marquée appliquée. Les futures
migrations (002+) seront appliquées normalement.

Pour une DB neuve : 001 crée toutes les tables, puis sera marquée appliquée.

Voir `backend/migrations/__init__.py` pour les conventions de nommage.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import NamedTuple

from backend._logging import logger

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# `001_initial.sql` → version=1, name="initial"
_MIGRATION_FILENAME_RE = re.compile(r"^(\d+)_(.+)\.sql$")


class MigrationFile(NamedTuple):
    version: int
    name: str
    path: Path

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def _list_migrations() -> list[MigrationFile]:
    """Liste les fichiers de migration disponibles, triés par version."""
    if not MIGRATIONS_DIR.exists():
        return []
    found: list[MigrationFile] = []
    for path in MIGRATIONS_DIR.iterdir():
        if not path.is_file() or path.suffix != ".sql":
            continue
        m = _MIGRATION_FILENAME_RE.match(path.name)
        if not m:
            logger.warning(
                "Migration ignorée — nom non conforme (attendu `NNN_<name>.sql`) : {f}",
                f=path.name,
            )
            continue
        version = int(m.group(1))
        name = m.group(2)
        found.append(MigrationFile(version=version, name=name, path=path))
    found.sort(key=lambda m: m.version)
    # Détection des doublons / trous
    seen: set[int] = set()
    for mig in found:
        if mig.version in seen:
            raise RuntimeError(
                f"Migration dupliquée pour la version {mig.version} : {mig.path.name}"
            )
        seen.add(mig.version)
    return found


def _ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    """Crée la table de tracking si elle n'existe pas."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] if hasattr(row, "keys") else row[0] for row in rows}


def apply_migrations(conn_factory=None) -> list[MigrationFile]:
    """Applique toutes les migrations en attente.

    Args:
        conn_factory: callable retournant une sqlite3.Connection. Si None,
            utilise `backend.db.get_connection`. Permet l'injection en test
            (pointer sur une DB temporaire).

    Returns:
        Liste des migrations appliquées dans CE run (vide si rien à faire).

    Comportement :
    - Chaque migration est appliquée dans sa propre transaction (commit
      explicite après `executescript` + `INSERT INTO schema_migrations`).
    - Si une migration échoue (exception SQL), la transaction est rollback
      et l'exception remonte — les migrations suivantes ne sont PAS tentées.
    - Idempotente : ré-appeler `apply_migrations()` sur une DB à jour est un
      no-op.
    """
    if conn_factory is None:
        # Import tardif pour éviter une boucle d'import (db importe _migrations).
        from backend.db import get_connection
        conn_factory = get_connection

    migrations = _list_migrations()
    if not migrations:
        logger.warning("Aucune migration trouvée dans {d}", d=MIGRATIONS_DIR)
        return []

    applied_in_this_run: list[MigrationFile] = []

    # Première connexion : init de schema_migrations + récup des versions
    conn = conn_factory()
    try:
        _ensure_schema_migrations_table(conn)
        conn.commit()
        applied = _get_applied_versions(conn)
    finally:
        conn.close()

    pending = [m for m in migrations if m.version not in applied]
    if not pending:
        logger.debug(
            "Aucune migration en attente ({n} déjà appliquées)", n=len(applied)
        )
        return []

    logger.info(
        "Application de {n} migration(s) en attente : versions={v}",
        n=len(pending),
        v=[m.version for m in pending],
    )

    for mig in pending:
        # CRITICAL : la connexion de migration doit être ouverte en
        # `autocommit=False` (PEP 249 transaction control).
        #
        # En mode LEGACY_TRANSACTION_CONTROL (défaut Python 3.13),
        # `Connection.executescript()` émet un **COMMIT implicite avant** de
        # lancer le script (cf docs sqlite3). Un `BEGIN` explicite posé juste
        # avant est donc commité immédiatement, et tout DDL exécuté à
        # l'intérieur du script ne peut PLUS être rollback en cas d'erreur
        # — d'où risque de migration à moitié appliquée.
        #
        # Avec `autocommit=False`, une transaction est implicitement ouverte
        # avant la 1re statement et reste vivante pendant tout le script :
        # `conn.rollback()` annule TOUTES les DDL si la moindre échoue.
        conn = _open_migration_connection()
        try:
            conn.executescript(mig.sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (mig.version, mig.name),
            )
            conn.commit()
            applied_in_this_run.append(mig)
            logger.info(
                "Migration appliquée : v{v} ({n})", v=mig.version, n=mig.name
            )
        except Exception:
            conn.rollback()
            logger.exception(
                "Échec migration v{v} ({n}) — rollback", v=mig.version, n=mig.name
            )
            raise
        finally:
            conn.close()

    return applied_in_this_run


def _open_migration_connection() -> sqlite3.Connection:
    """Ouvre une connexion SQLite dédiée aux migrations (`autocommit=False`).

    Lit `DB_PATH` au moment de l'appel pour rester compatible avec les tests
    qui monkeypatchent `backend.db.DB_PATH` vers un tmp_path.
    """
    from backend.db import DB_PATH

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, autocommit=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def current_schema_version(conn_factory=None) -> int:
    """Retourne la plus haute version appliquée, ou 0 si rien."""
    if conn_factory is None:
        from backend.db import get_connection
        conn_factory = get_connection

    conn = conn_factory()
    try:
        # `schema_migrations` peut ne pas exister sur une DB jamais initialisée
        _ensure_schema_migrations_table(conn)
        conn.commit()
        row = conn.execute(
            "SELECT MAX(version) AS v FROM schema_migrations"
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return 0
    v = row["v"] if hasattr(row, "keys") else row[0]
    return int(v) if v is not None else 0
