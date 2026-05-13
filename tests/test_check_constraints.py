"""Tests des CHECK constraints SQLite (migration 002).

Vérifie que :
- Les valeurs valides (cf `backend/models.py:VALID_*`) sont acceptées.
- Les valeurs invalides sont rejetées avec `sqlite3.IntegrityError`
  (`CHECK constraint failed: ...`).
- Les bornes numériques (`match_score ∈ [0,100]`, `score_* ∈ [0,20]`,
  `is_active ∈ {0,1}`) sont enforced côté DB.
- Le filet ne casse PAS les opérations légitimes existantes.

Synchro : si tu modifies les VALID_* dans `models.py`, ajoute ici les
nouveaux cas de test ET crée une nouvelle migration `00X_*.sql` pour
mettre à jour les CHECK en DB.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.models import (
    MATCH_LABELS,
    VALID_COMPANY_STATUSES,
    VALID_PRIORITIES,
    VALID_REMOTE,
    VALID_STATUSES,
)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """DB temporaire avec toutes les migrations appliquées."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.db.DB_PATH", db_file)
    from backend.db import init_schema
    init_schema()
    return db_file


def _raw_insert_offers(db_file, **fields):
    """Insère directement via sqlite3 (bypass queries.py)
    pour tester que le CHECK SQL agit en filet de défense."""
    conn = sqlite3.connect(db_file)
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" * len(fields))
    sql = f"INSERT INTO offers ({cols}) VALUES ({placeholders})"  # nosec B608
    try:
        conn.execute(sql, tuple(fields.values()))
        conn.commit()
    finally:
        conn.close()


def _raw_insert_target_companies(db_file, **fields):
    conn = sqlite3.connect(db_file)
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" * len(fields))
    sql = f"INSERT INTO target_companies ({cols}) VALUES ({placeholders})"  # nosec B608
    try:
        conn.execute(sql, tuple(fields.values()))
        conn.commit()
    finally:
        conn.close()


class TestOffersStatus:
    def test_null_status_allowed(self, temp_db):
        _raw_insert_offers(temp_db, title="t", status=None)

    @pytest.mark.parametrize("s", VALID_STATUSES)
    def test_valid_status_accepted(self, temp_db, s):
        _raw_insert_offers(temp_db, title="t", status=s)

    @pytest.mark.parametrize("s", ["BOGUS", "postule", "Postulé ", " Postulé"])
    def test_invalid_status_rejected(self, temp_db, s):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            _raw_insert_offers(temp_db, title="t", status=s)


class TestOffersPriority:
    @pytest.mark.parametrize("p", [None, *VALID_PRIORITIES])
    def test_valid_priority_accepted(self, temp_db, p):
        _raw_insert_offers(temp_db, title="t", priority=p)

    @pytest.mark.parametrize("p", ["High", "haute", "URGENT"])
    def test_invalid_priority_rejected(self, temp_db, p):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            _raw_insert_offers(temp_db, title="t", priority=p)


class TestOffersRemote:
    @pytest.mark.parametrize("r", [None, *VALID_REMOTE])
    def test_valid_remote_accepted(self, temp_db, r):
        _raw_insert_offers(temp_db, title="t", remote=r)

    @pytest.mark.parametrize("r", ["Yes", "Remote", "Télétravail"])
    def test_invalid_remote_rejected(self, temp_db, r):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            _raw_insert_offers(temp_db, title="t", remote=r)


class TestOffersMatchLabel:
    @pytest.mark.parametrize("label", [None, *MATCH_LABELS])
    def test_valid_label_accepted(self, temp_db, label):
        _raw_insert_offers(temp_db, title="t", match_label=label)

    @pytest.mark.parametrize("label", ["Best", "top", "Excellent"])
    def test_invalid_label_rejected(self, temp_db, label):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            _raw_insert_offers(temp_db, title="t", match_label=label)


class TestOffersScoreBounds:
    @pytest.mark.parametrize("s", [0, 1, 50, 99, 100])
    def test_valid_match_score_accepted(self, temp_db, s):
        _raw_insert_offers(temp_db, title="t", match_score=s)

    @pytest.mark.parametrize("s", [-1, 101, 150, 9999])
    def test_invalid_match_score_rejected(self, temp_db, s):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            _raw_insert_offers(temp_db, title="t", match_score=s)

    @pytest.mark.parametrize("axis", [
        "score_pipeline", "score_exploration", "score_modelisation",
        "score_deploiement", "score_cadrage",
    ])
    @pytest.mark.parametrize("v", [0, 5, 10, 15, 20])
    def test_valid_axis_score_accepted(self, temp_db, axis, v):
        _raw_insert_offers(temp_db, title="t", **{axis: v})

    @pytest.mark.parametrize("axis", [
        "score_pipeline", "score_exploration", "score_modelisation",
        "score_deploiement", "score_cadrage",
    ])
    @pytest.mark.parametrize("v", [-1, 21, 50, 100])
    def test_invalid_axis_score_rejected(self, temp_db, axis, v):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            _raw_insert_offers(temp_db, title="t", **{axis: v})


class TestOffersIsActive:
    @pytest.mark.parametrize("v", [0, 1])
    def test_valid_is_active_accepted(self, temp_db, v):
        _raw_insert_offers(temp_db, title="t", is_active=v)

    @pytest.mark.parametrize("v", [-1, 2, 99])
    def test_invalid_is_active_rejected(self, temp_db, v):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            _raw_insert_offers(temp_db, title="t", is_active=v)


class TestTargetCompaniesConstraints:
    @pytest.mark.parametrize("p", [None, *VALID_PRIORITIES])
    def test_valid_priority(self, temp_db, p):
        _raw_insert_target_companies(temp_db, name="x", priority=p)

    @pytest.mark.parametrize("p", ["Urgent", "low"])
    def test_invalid_priority(self, temp_db, p):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            _raw_insert_target_companies(temp_db, name="x", priority=p)

    @pytest.mark.parametrize("s", [None, *VALID_COMPANY_STATUSES])
    def test_valid_status(self, temp_db, s):
        _raw_insert_target_companies(temp_db, name="x", status=s)

    @pytest.mark.parametrize("s", ["Pending", "Postulé"])  # "Postulé" valid pour offers mais PAS pour companies
    def test_invalid_status(self, temp_db, s):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            _raw_insert_target_companies(temp_db, name="x", status=s)


class TestNonRegression:
    """L'app continue de fonctionner comme avant — pas de side-effect."""

    def test_queries_insert_offer_still_works(self, temp_db):
        from backend.queries import insert_offer
        offer_id, was_new = insert_offer({
            "title": "ML Engineer Alternance",
            "company": "Acme",
            "city": "Paris",
            "url": "http://example.com/1",
            "status": "Postulé",
            "match_score": 75,
            "score_pipeline": 12,
            "remote": "Hybride",
            "priority": "Haute",
        })
        assert offer_id is not None
        assert was_new is True

    def test_queries_update_offer_still_works(self, temp_db):
        from backend.queries import insert_offer, update_offer
        offer_id, _ = insert_offer({
            "title": "Test",
            "url": "http://example.com/upd",
        })
        ok = update_offer(offer_id, {"status": "Entretien", "priority": "Haute"})
        assert ok is True
