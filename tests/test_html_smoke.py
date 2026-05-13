"""Smoke tests des pages HTML rendues côté serveur.

Catch les régressions du type "TemplateResponse change de signature" (bug
introduit en upgradant Starlette 1.0 sans adapter le code).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient avec DB temp pour ne pas dépendre de data/app.db."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.db.DB_PATH", db_file)
    from backend.db import init_schema
    init_schema()
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)


class TestPageOffers:
    def test_get_root(self, client):
        """GET / doit retourner 200 + HTML (la liste des offres, même vide)."""
        r = client.get("/")
        assert r.status_code == 200, f"Body: {r.text[:500]}"
        assert "text/html" in r.headers.get("content-type", "")
        # Vérifie qu'on a bien rendu un template Jinja (présence du wrapper nav)
        assert "Scrap'Offre Emploi" in r.text

    def test_get_root_with_filters(self, client):
        """Les filtres query params ne doivent pas casser le rendu."""
        r = client.get("/?search=ML&min_score=60&sort=score_desc")
        assert r.status_code == 200

    def test_get_root_include_archived(self, client):
        r = client.get("/?include_archived=true")
        assert r.status_code == 200

    def test_get_root_pagination_shows_total(self, client):
        from backend.db import db as _db

        with _db() as conn:
            conn.executemany(
                "INSERT INTO offers (title, company, city, dedup_key) VALUES (?, ?, ?, ?)",
                [
                    (f"Job {i}", "Acme", "Paris", f"job{i}|acme|paris")
                    for i in range(1, 27)
                ],
            )

        r = client.get("/?per_page=25")

        assert r.status_code == 200
        assert "26 offres au total" in r.text
        assert "page 1/2" in r.text


class TestPageCompanies:
    def test_get_companies(self, client):
        r = client.get("/companies")
        assert r.status_code == 200, f"Body: {r.text[:500]}"
        assert "text/html" in r.headers.get("content-type", "")
        # Vérifie présence du tab "Toutes"
        assert "Toutes" in r.text

    def test_get_companies_filtered_city(self, client):
        r = client.get("/companies?city=Toulouse")
        assert r.status_code == 200

    def test_get_companies_other_haute(self, client):
        r = client.get("/companies?other_haute=true")
        assert r.status_code == 200


class TestOfferDetail404:
    def test_offer_detail_not_found(self, client):
        """Détail d'une offre inexistante → 404 propre (pas 500)."""
        r = client.get("/offers/99999")
        assert r.status_code == 404


class TestCompanyDetail404:
    def test_company_detail_not_found(self, client):
        r = client.get("/companies/99999")
        assert r.status_code == 404
