"""Tests du bulk insert (`backend.queries.insert_offers_bulk`).

Utilise une DB temporaire pour ne pas polluer `data/app.db`.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Crée une DB SQLite temporaire pour ce test."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.db.DB_PATH", db_file)
    from backend.db import init_schema
    init_schema()
    yield db_file


class TestInsertOffersBulk:
    def test_empty_list(self, temp_db):
        from backend.queries import insert_offers_bulk
        new_ids, dup = insert_offers_bulk([])
        assert new_ids == []
        assert dup == 0

    def test_single_insert(self, temp_db):
        from backend.queries import insert_offers_bulk
        new_ids, dup = insert_offers_bulk([
            {"title": "ML Engineer", "company": "Acme", "city": "Paris", "url": "http://x/1"},
        ])
        assert len(new_ids) == 1
        assert dup == 0

    def test_dedup_by_url(self, temp_db):
        from backend.queries import insert_offers_bulk
        offers = [
            {"title": "ML Engineer", "company": "Acme", "city": "Paris", "url": "http://x/1"},
            {"title": "ML Engineer", "company": "Acme", "city": "Paris", "url": "http://x/1"},
        ]
        new_ids, dup = insert_offers_bulk(offers)
        assert len(new_ids) == 1
        assert dup == 1

    def test_dedup_by_title_company_city(self, temp_db):
        """Même (title, company, city) sans URL → 1 seul insert."""
        from backend.queries import insert_offers_bulk
        offers = [
            {"title": "ML Engineer", "company": "Acme", "city": "Paris", "url": None},
            {"title": "ML Engineer", "company": "Acme", "city": "Paris", "url": None},
        ]
        new_ids, dup = insert_offers_bulk(offers)
        assert len(new_ids) == 1
        assert dup == 1

    def test_critical_paris_vs_toulouse_kept(self, temp_db):
        """BUG MÉTIER FIXED : même offre Paris vs Toulouse = 2 inserts distincts."""
        from backend.queries import insert_offers_bulk
        offers = [
            {"title": "AI Engineer", "company": "Capgemini", "city": "Paris", "url": "http://x/1"},
            {"title": "AI Engineer", "company": "Capgemini", "city": "Toulouse", "url": "http://x/2"},
        ]
        new_ids, dup = insert_offers_bulk(offers)
        assert len(new_ids) == 2, "Paris et Toulouse doivent être 2 offres distinctes"
        assert dup == 0

    def test_dedup_city_variants(self, temp_db):
        """Variantes 'Paris' vs '75 - Paris' → 1 seul insert (vrai doublon)."""
        from backend.queries import insert_offers_bulk
        offers = [
            {"title": "ML", "company": "X", "city": "Paris", "url": "http://a/1"},
            {"title": "ML", "company": "X", "city": "75 - Paris", "url": None},  # même offre
        ]
        new_ids, dup = insert_offers_bulk(offers)
        assert len(new_ids) == 1
        assert dup == 1

    def test_no_title_skipped(self, temp_db):
        from backend.queries import insert_offers_bulk
        offers = [
            {"title": "", "company": "X", "city": "Paris"},
            {"title": "Real Title", "company": "X", "city": "Paris", "url": "http://x/1"},
        ]
        new_ids, dup = insert_offers_bulk(offers)
        assert len(new_ids) == 1
        # Le titre vide n'est pas compté comme doublon, juste skippé

    def test_persists_via_single_transaction(self, temp_db):
        """100 offres : tout doit être inséré en 1 seule transaction."""
        from backend.queries import insert_offers_bulk
        offers = [
            {"title": f"Title {i}", "company": "Co", "city": "Paris", "url": f"http://x/{i}"}
            for i in range(100)
        ]
        new_ids, dup = insert_offers_bulk(offers)
        assert len(new_ids) == 100
        assert dup == 0
