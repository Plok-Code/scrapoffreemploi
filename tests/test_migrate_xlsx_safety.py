"""Tests du garde-fou destructif de `backend.migrate_xlsx`.

Le script `migrate_xlsx` fait `DELETE FROM offers` avant l'import. Pour qu'un
utilisateur ne perde pas 1000+ offres scrapées en relançant le quickstart par
réflexe, `_check_safe_to_wipe` refuse de tourner si la table est déjà peuplée
sauf si `--force` est passé.

On teste le helper directement (pure-function, pas besoin de mocker openpyxl).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.db.DB_PATH", db_file)
    from backend.db import init_schema
    init_schema()
    yield db_file


def _seed_one_offer():
    from backend.db import db
    with db() as conn:
        conn.execute(
            "INSERT INTO offers (title, dedup_key) VALUES ('Existing offer', 'k')"
        )


class TestCheckSafeToWipe:
    def test_empty_db_safe_without_force(self, temp_db):
        """DB vide → OK sans --force (quickstart d'un nouveau user)."""
        from backend.migrate_xlsx import _check_safe_to_wipe
        safe, msg = _check_safe_to_wipe(force=False)
        assert safe is True
        assert msg is None

    def test_empty_db_safe_with_force(self, temp_db):
        """DB vide + --force → OK aussi (idempotent)."""
        from backend.migrate_xlsx import _check_safe_to_wipe
        safe, msg = _check_safe_to_wipe(force=True)
        assert safe is True
        assert msg is None

    def test_populated_db_refused_without_force(self, temp_db):
        """DB peuplée + pas de --force → refus avec message explicite."""
        _seed_one_offer()
        from backend.migrate_xlsx import _check_safe_to_wipe
        safe, msg = _check_safe_to_wipe(force=False)
        assert safe is False
        assert msg is not None
        # Le message doit contenir des indices actionnables pour le user
        assert "1 ligne" in msg or "1 lignes" in msg
        assert "--force" in msg
        assert "DELETE FROM offers" in msg

    def test_populated_db_force_overrides(self, temp_db):
        """DB peuplée + --force → OK explicite."""
        _seed_one_offer()
        from backend.migrate_xlsx import _check_safe_to_wipe
        safe, msg = _check_safe_to_wipe(force=True)
        assert safe is True
        assert msg is None

    def test_run_returns_exit_code_2_on_refusal(self, temp_db, capsys):
        """`run()` retourne le code 2 (distinct de 1=erreur générique) sur refus.

        Le 2 permet à un script wrapper de distinguer "missing xlsx" (1) de
        "DB déjà peuplée, on refuse" (2) et de prendre des actions différentes.
        """
        _seed_one_offer()
        from backend.migrate_xlsx import run
        exit_code = run([])  # pas de --force
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "REFUS" in captured.err
        assert "--force" in captured.err
