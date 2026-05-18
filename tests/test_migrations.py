"""Tests du runner de migrations versionnées (`backend._migrations`).

Couvre :
- Application sur DB vide (création + tracking)
- Application sur DB pré-existante (CREATE IF NOT EXISTS → no-op + tracking)
- Idempotence (2e run = no-op)
- Tracking via `schema_migrations`
- `current_schema_version()` retourne la plus haute version appliquée
- Ordre d'application par version (001 avant 002 avant 010)
- Fichier mal nommé ignoré (warning logué, pas d'exception)
- Rollback si une migration échoue (transaction)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """DB SQLite temporaire isolée du `data/app.db` réel."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.db.DB_PATH", db_file)
    yield db_file


@pytest.fixture
def isolated_migrations(tmp_path, monkeypatch):
    """Dossier `migrations/` temporaire pour injecter des migrations de test.

    Crée `tmp_path/migrations/` et patche `MIGRATIONS_DIR` pour pointer dessus.
    Retourne le Path du dossier — les tests y écrivent les .sql voulus.
    """
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    monkeypatch.setattr("backend._migrations.MIGRATIONS_DIR", mig_dir)
    return mig_dir


class TestApplyMigrationsRealFiles:
    """Tests avec les VRAIES migrations du projet (`backend/migrations/`)."""

    def test_fresh_db_applies_initial(self, temp_db):
        from backend._migrations import apply_migrations, current_schema_version
        assert current_schema_version() == 0
        applied = apply_migrations()
        assert len(applied) >= 1
        assert applied[0].version == 1
        assert applied[0].name == "initial"
        assert current_schema_version() >= 1

    def test_creates_offers_table(self, temp_db):
        from backend._migrations import apply_migrations
        apply_migrations()
        # La table doit exister + avoir les colonnes attendues
        conn = sqlite3.connect(temp_db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(offers)").fetchall()}
        conn.close()
        assert "id" in cols
        assert "title" in cols
        assert "is_active" in cols
        assert "dedup_key" in cols

    def test_creates_target_companies_table(self, temp_db):
        from backend._migrations import apply_migrations
        apply_migrations()
        conn = sqlite3.connect(temp_db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(target_companies)").fetchall()}
        conn.close()
        assert "name" in cols
        assert "city" in cols  # ajouté dans le baseline 001
        assert "source" in cols

    def test_idempotent_second_call(self, temp_db):
        """Ré-appeler `apply_migrations()` sur une DB à jour est un no-op."""
        from backend._migrations import apply_migrations
        first = apply_migrations()
        second = apply_migrations()
        assert len(first) >= 1
        assert second == []  # rien à appliquer

    def test_init_schema_alias(self, temp_db):
        """`db.init_schema()` doit déclencher les migrations (alias clean)."""
        from backend.db import init_schema
        from backend._migrations import current_schema_version
        init_schema()
        assert current_schema_version() >= 1

    def test_existing_schema_no_double_apply(self, temp_db):
        """Cas du user en place : sa DB a déjà toutes les tables et colonnes
        (schéma 001 complet). Quand on rebranche le runner de migrations,
        001 est appliquée comme no-op (CREATE IF NOT EXISTS) puis marquée
        appliquée — les données existantes sont préservées.
        """
        # Pré-crée le schéma complet équivalent à 001 (sans la table
        # schema_migrations, qui est ajoutée par le runner).
        mig_path = Path(__file__).resolve().parent.parent / "backend" / "migrations" / "001_initial.sql"
        sql = mig_path.read_text(encoding="utf-8")
        conn = sqlite3.connect(temp_db)
        conn.executescript(sql)
        # Insère une row pour vérifier qu'on ne la perd pas
        conn.execute(
            "INSERT INTO offers (title, company, url) VALUES (?, ?, ?)",
            ("pre-existing", "Acme", "http://pre/1"),
        )
        conn.commit()
        conn.close()

        from backend._migrations import apply_migrations, current_schema_version
        applied = apply_migrations()
        # 001 est marquée appliquée (même si SQL no-op)
        assert any(m.version == 1 for m in applied)
        assert current_schema_version() >= 1

        # La row pré-existante n'a pas été perdue
        conn = sqlite3.connect(temp_db)
        n = conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
        conn.close()
        assert n == 1


class TestMigrationFileDiscovery:
    """Tests du parsing/tri des fichiers de migration (avec dossier injecté)."""

    def test_sort_by_version_numeric(self, temp_db, isolated_migrations):
        # Crée 3 migrations dans le désordre lexicographique : 002, 010, 003
        (isolated_migrations / "010_zzz.sql").write_text(
            "CREATE TABLE ten (id INTEGER);", encoding="utf-8"
        )
        (isolated_migrations / "002_b.sql").write_text(
            "CREATE TABLE two (id INTEGER);", encoding="utf-8"
        )
        (isolated_migrations / "003_c.sql").write_text(
            "CREATE TABLE three (id INTEGER);", encoding="utf-8"
        )
        from backend._migrations import apply_migrations
        applied = apply_migrations()
        # Ordre attendu : 002, 003, 010 (numérique, pas lexicographique)
        assert [m.version for m in applied] == [2, 3, 10]
        assert [m.name for m in applied] == ["b", "c", "zzz"]

    def test_bad_filename_ignored(self, temp_db, isolated_migrations):
        """Un fichier .sql mal nommé est ignoré (warning logué) sans casser."""
        (isolated_migrations / "001_initial.sql").write_text(
            "CREATE TABLE okay (id INTEGER);", encoding="utf-8"
        )
        # Nom non conforme — pas de préfixe numérique
        (isolated_migrations / "bad_name.sql").write_text(
            "CREATE TABLE bad (id INTEGER);", encoding="utf-8"
        )
        from backend._migrations import apply_migrations
        applied = apply_migrations()
        # Seule la migration bien nommée est appliquée
        assert [m.version for m in applied] == [1]

    def test_duplicate_version_raises(self, temp_db, isolated_migrations):
        """Deux fichiers avec la même version → RuntimeError clair."""
        (isolated_migrations / "002_one.sql").write_text(
            "CREATE TABLE a (id INTEGER);", encoding="utf-8"
        )
        (isolated_migrations / "002_two.sql").write_text(
            "CREATE TABLE b (id INTEGER);", encoding="utf-8"
        )
        from backend._migrations import apply_migrations
        with pytest.raises(RuntimeError, match="dupliquée pour la version 2"):
            apply_migrations()


class TestMigrationFailureRollback:
    """Une migration SQL invalide doit rollback la transaction."""

    def test_invalid_sql_rolls_back(self, temp_db, isolated_migrations):
        """Migration v1 OK puis v2 cassée → v1 reste appliquée, v2 absente."""
        (isolated_migrations / "001_ok.sql").write_text(
            "CREATE TABLE t1 (id INTEGER);", encoding="utf-8"
        )
        (isolated_migrations / "002_broken.sql").write_text(
            "THIS IS NOT VALID SQL;", encoding="utf-8"
        )

        from backend._migrations import apply_migrations, current_schema_version
        with pytest.raises(sqlite3.OperationalError):
            apply_migrations()

        # v1 est appliquée
        assert current_schema_version() == 1

        # v2 NON tracked (rollback OK)
        conn = sqlite3.connect(temp_db)
        applied = {
            row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        conn.close()
        assert 1 in applied
        assert 2 not in applied

    def test_multi_ddl_with_error_in_middle_rolls_back_partial(
        self, temp_db, isolated_migrations
    ):
        """Le test critique du bug rollback (audit user, 19 mai 2026).

        Avant le fix `autocommit=False`, `Connection.executescript()` émettait
        un COMMIT implicite avant de lancer le script, ce qui rendait le
        rollback impossible : les CREATE TABLE exécutés avant l'erreur SQL
        restaient persistés.

        Ici : une migration enchaîne 2 CREATE TABLE valides, puis du SQL
        invalide. Vérifie qu'AUCUNE des 2 premières tables ne persiste
        après le rollback. Si ce test échoue, la transaction de migration
        n'est PAS atomique → risque de DB à moitié migrée.
        """
        (isolated_migrations / "001_multi_ddl_broken.sql").write_text(
            """
            CREATE TABLE t_part1 (id INTEGER);
            CREATE TABLE t_part2 (id INTEGER);
            CRAP_INVALID_SQL_BOOM;
            CREATE TABLE t_part3 (id INTEGER);
            """,
            encoding="utf-8",
        )

        from backend._migrations import apply_migrations, current_schema_version
        with pytest.raises(sqlite3.OperationalError):
            apply_migrations()

        # Aucune migration appliquée (schema_migrations vide en tant que tx)
        assert current_schema_version() == 0

        # Aucune des 3 tables ne doit persister (rollback complet)
        conn = sqlite3.connect(temp_db)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        for t in ("t_part1", "t_part2", "t_part3"):
            assert t not in tables, (
                f"BUG rollback : table {t!r} persiste après l'erreur SQL. "
                f"Tables présentes : {tables}. "
                f"Cause probable : Connection.executescript() en mode "
                f"LEGACY_TRANSACTION_CONTROL fait un COMMIT implicite. "
                f"Fix : utiliser sqlite3.connect(..., autocommit=False) "
                f"pour la connexion de migration."
            )

    def test_multi_migration_atomicity(self, temp_db, isolated_migrations):
        """v1 OK (commited) → v2 multi-DDL avec erreur (rollback complet).

        Vérifie que v1 reste appliquée et que les DDL de v2 (avant l'erreur)
        ne fuient PAS dans la DB.
        """
        (isolated_migrations / "001_ok.sql").write_text(
            "CREATE TABLE v1_persisted (id INTEGER);", encoding="utf-8"
        )
        (isolated_migrations / "002_partial.sql").write_text(
            """
            CREATE TABLE v2_should_not_exist (id INTEGER);
            CREATE TABLE v2_neither (id INTEGER);
            BROKEN_SYNTAX_HERE;
            """,
            encoding="utf-8",
        )

        from backend._migrations import apply_migrations, current_schema_version
        with pytest.raises(sqlite3.OperationalError):
            apply_migrations()

        # v1 OK
        assert current_schema_version() == 1
        conn = sqlite3.connect(temp_db)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        # v1 persistée
        assert "v1_persisted" in tables
        # v2 entièrement rollbackée
        assert "v2_should_not_exist" not in tables
        assert "v2_neither" not in tables


class TestSchemaMigrationsTable:
    """La table de tracking elle-même."""

    def test_table_columns(self, temp_db):
        from backend._migrations import apply_migrations
        apply_migrations()
        conn = sqlite3.connect(temp_db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(schema_migrations)").fetchall()}
        conn.close()
        assert cols == {"version", "name", "applied_at"}

    def test_applied_at_is_set(self, temp_db):
        from backend._migrations import apply_migrations
        apply_migrations()
        conn = sqlite3.connect(temp_db)
        row = conn.execute(
            "SELECT version, name, applied_at FROM schema_migrations WHERE version = 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 1
        assert row[1] == "initial"
        assert row[2] is not None  # timestamp non null


class TestCurrentSchemaVersion:
    def test_returns_zero_on_empty_db(self, temp_db):
        from backend._migrations import current_schema_version
        # Aucune migration appliquée → 0 (et la table est créée au passage)
        assert current_schema_version() == 0

    def test_returns_max_version_after_apply(self, temp_db):
        from backend._migrations import apply_migrations, current_schema_version
        apply_migrations()
        v = current_schema_version()
        assert v >= 1
