"""Tests de `backend.matching.is_batch_applied` et `list_pending/applied_batches`.

Fix audit user : cli.py list-batches affichait les batches déjà appliqués
comme "à scorer" alors qu'il n'y avait plus rien à faire.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def temp_db_with_offers(tmp_path, monkeypatch):
    """DB temporaire avec 3 offres dont 2 scorées."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.db.DB_PATH", db_file)
    from backend.db import db as _db, init_schema
    init_schema()
    with _db() as conn:
        # 3 offres dont 1 sans score
        conn.executemany(
            "INSERT INTO offers (id, title, dedup_key, match_score) VALUES (?, ?, ?, ?)",
            [
                (1, "Job 1", "j1|", 75),
                (2, "Job 2", "j2|", 60),
                (3, "Job 3", "j3|", None),  # pas encore scorée
            ],
        )
    yield tmp_path


@pytest.fixture
def temp_batches_dir(tmp_path, monkeypatch):
    """Surcharge le BATCHES_DIR vers un tmp."""
    batches_dir = tmp_path / "batches"
    batches_dir.mkdir()
    monkeypatch.setattr("backend.matching.BATCHES_DIR", batches_dir)
    return batches_dir


class TestIsBatchApplied:
    def test_all_offers_scored_returns_true(self, temp_db_with_offers, temp_batches_dir):
        from backend.matching import is_batch_applied
        batch = temp_batches_dir / "2026-05-13_to_score.json"
        # Batch avec uniquement les offres déjà scorées (id 1 et 2)
        batch.write_text(json.dumps({
            "offers": [{"id": 1, "title": "Job 1"}, {"id": 2, "title": "Job 2"}],
            "count": 2,
        }), encoding="utf-8")
        assert is_batch_applied(batch) is True

    def test_one_offer_unscored_returns_false(self, temp_db_with_offers, temp_batches_dir):
        from backend.matching import is_batch_applied
        batch = temp_batches_dir / "2026-05-13_to_score.json"
        batch.write_text(json.dumps({
            "offers": [{"id": 1}, {"id": 3}],  # id 3 pas scoré
            "count": 2,
        }), encoding="utf-8")
        assert is_batch_applied(batch) is False

    def test_empty_batch_returns_true(self, temp_db_with_offers, temp_batches_dir):
        """Batch vide = rien à faire = considéré 'applied'."""
        from backend.matching import is_batch_applied
        batch = temp_batches_dir / "empty.json"
        batch.write_text(json.dumps({"offers": [], "count": 0}), encoding="utf-8")
        assert is_batch_applied(batch) is True

    def test_nonexistent_file_returns_false(self, temp_db_with_offers, temp_batches_dir):
        from backend.matching import is_batch_applied
        assert is_batch_applied(Path("/does/not/exist.json")) is False

    def test_malformed_json_returns_false(self, temp_db_with_offers, temp_batches_dir):
        from backend.matching import is_batch_applied
        batch = temp_batches_dir / "bad.json"
        batch.write_text("not valid json", encoding="utf-8")
        assert is_batch_applied(batch) is False


class TestListPendingApplied:
    def test_list_pending_excludes_applied(self, temp_db_with_offers, temp_batches_dir):
        from backend.matching import list_applied_batches, list_pending_batches

        # Batch 1 : tout scoré (id 1+2) → applied
        b1 = temp_batches_dir / "2026-05-12_to_score.json"
        b1.write_text(json.dumps({"offers": [{"id": 1}, {"id": 2}], "count": 2}), encoding="utf-8")

        # Batch 2 : contient id 3 (pas scoré) → pending
        b2 = temp_batches_dir / "2026-05-13_to_score.json"
        b2.write_text(json.dumps({"offers": [{"id": 3}], "count": 1}), encoding="utf-8")

        pending = list_pending_batches()
        applied = list_applied_batches()

        assert b1 in applied
        assert b1 not in pending
        assert b2 in pending
        assert b2 not in applied

    def test_latest_pending_batch(self, temp_db_with_offers, temp_batches_dir):
        from backend.matching import latest_pending_batch

        b1 = temp_batches_dir / "2026-05-12_to_score.json"
        b1.write_text(json.dumps({"offers": [{"id": 1}], "count": 1}), encoding="utf-8")
        b2 = temp_batches_dir / "2026-05-13_to_score.json"
        b2.write_text(json.dumps({"offers": [{"id": 3}], "count": 1}), encoding="utf-8")

        # Seul b2 est pending (b1 est applied car id 1 a match_score=75)
        assert latest_pending_batch() == b2


class TestExportBatch:
    def test_export_specific_offer_ids_only(self, temp_db_with_offers, temp_batches_dir):
        from backend.matching import export_batch_to_score

        path = export_batch_to_score(offer_ids=[1, 3])
        raw = json.loads(path.read_text(encoding="utf-8"))

        assert raw["count"] == 2
        assert [offer["id"] for offer in raw["offers"]] == [1, 3]


class TestExportBatchExcludesArchived:
    """Garde-fou audit user (19 mai 2026) : `filter_non_alternance_offers`
    peut archiver (`is_active=0`) certaines des `new_ids` du scrape juste
    avant la génération du batch. Sans ce filtre par défaut, on enverrait
    au LLM des offres qu'on vient de rejeter."""

    @pytest.fixture
    def temp_db_mixed_active(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        monkeypatch.setattr("backend.db.DB_PATH", db_file)
        from backend.db import db as _db, init_schema
        init_schema()
        with _db() as conn:
            # 3 offres : 2 actives (id 1, 3), 1 archivée (id 2)
            conn.executemany(
                "INSERT INTO offers (id, title, dedup_key, is_active) VALUES (?, ?, ?, ?)",
                [
                    (1, "Active 1", "a1|", 1),
                    (2, "Archived",  "a2|", 0),
                    (3, "Active 2", "a3|", 1),
                ],
            )
        yield tmp_path

    def test_offer_ids_default_excludes_archived(
        self, temp_db_mixed_active, temp_batches_dir
    ):
        """Combo scénario réel : run_full_scrape passe new_ids=[1,2,3], mais
        2 a été archivée par filter_alternance → batch contient juste 1 et 3."""
        from backend.matching import export_batch_to_score
        path = export_batch_to_score(offer_ids=[1, 2, 3])
        raw = json.loads(path.read_text(encoding="utf-8"))
        ids = [o["id"] for o in raw["offers"]]
        assert 1 in ids
        assert 3 in ids
        assert 2 not in ids, (
            f"Bug audit : l'offre archivée (is_active=0) ne doit PAS être "
            f"exportée par défaut. ids retournés : {ids}"
        )

    def test_only_unscored_default_excludes_archived(
        self, temp_db_mixed_active, temp_batches_dir
    ):
        """Path `only_unscored=True` (sans offer_ids) doit aussi exclure les
        archivées."""
        from backend.matching import export_batch_to_score
        path = export_batch_to_score()  # only_unscored=True par défaut
        raw = json.loads(path.read_text(encoding="utf-8"))
        ids = [o["id"] for o in raw["offers"]]
        # Toutes les 3 ont match_score=NULL donc all eligibles, mais
        # l'archivée doit être filtrée.
        assert 1 in ids
        assert 3 in ids
        assert 2 not in ids

    def test_include_archived_true_brings_them_back(
        self, temp_db_mixed_active, temp_batches_dir
    ):
        """Escape hatch : `include_archived=True` exporte aussi les archivées."""
        from backend.matching import export_batch_to_score
        path = export_batch_to_score(
            offer_ids=[1, 2, 3], include_archived=True
        )
        raw = json.loads(path.read_text(encoding="utf-8"))
        ids = sorted(o["id"] for o in raw["offers"])
        assert ids == [1, 2, 3]


class TestParseScoresFileValidation:
    """Audit user (19 mai 2026) : `for item in raw['scores']` lève un TypeError
    opaque sur `null`/wrong type. Le caller CLI ne catche que `ValueError`."""

    def _write(self, tmp_path: Path, payload) -> Path:
        p = tmp_path / "scores.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    def test_scores_null_raises_value_error(self, tmp_path):
        from backend.matching import parse_scores_file
        p = self._write(tmp_path, {"scores": None})
        with pytest.raises(ValueError, match="doit être une liste"):
            parse_scores_file(p)

    def test_scores_string_raises_value_error(self, tmp_path):
        from backend.matching import parse_scores_file
        p = self._write(tmp_path, {"scores": "abc"})
        with pytest.raises(ValueError, match="doit être une liste"):
            parse_scores_file(p)

    def test_scores_dict_raises_value_error(self, tmp_path):
        from backend.matching import parse_scores_file
        p = self._write(tmp_path, {"scores": {"foo": "bar"}})
        with pytest.raises(ValueError, match="doit être une liste"):
            parse_scores_file(p)

    def test_scores_int_raises_value_error(self, tmp_path):
        from backend.matching import parse_scores_file
        p = self._write(tmp_path, {"scores": 42})
        with pytest.raises(ValueError, match="doit être une liste"):
            parse_scores_file(p)

    def test_item_not_dict_raises_value_error(self, tmp_path):
        """`scores` est bien une liste mais un item est `null` / une string."""
        from backend.matching import parse_scores_file
        p = self._write(tmp_path, {"scores": [None, "string-item", 42]})
        with pytest.raises(ValueError, match="doit être un dict"):
            parse_scores_file(p)

    def test_empty_scores_list_returns_empty(self, tmp_path):
        """`scores: []` est valide → 0 score à appliquer."""
        from backend.matching import parse_scores_file
        p = self._write(tmp_path, {"scores": []})
        assert parse_scores_file(p) == []
