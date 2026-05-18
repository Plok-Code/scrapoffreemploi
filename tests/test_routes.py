"""Tests d'intégration des routes HTTP via FastAPI `TestClient`.

Complémentaires aux smoke tests (`test_html_smoke.py`) et sécurité
(`test_security.py`). Ici on assert :
- **Contenu rendu** : filtres GET retournent les bonnes lignes (pas juste 200)
- **Pagination** : page=2 marche, page > total_pages est normalisée
- **/api/scrape** : 400 sur source inconnue, 409 sur double-POST, structure status
- **API JSON** : PATCH success/404, structure /api/stats, toggle status HTMX
- **POST /offers/{id}** : redirect 303 chemin OK, 404 sur id inexistant

L'objectif : un changement de signature `queries.list_offers()` ou un breaking
change dans `_offer_filters` doit faire échouer un test ici avant la prod.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient avec DB temp + lifespan exécuté (init_schema)."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.db.DB_PATH", db_file)
    from backend.db import init_schema
    init_schema()
    from fastapi.testclient import TestClient
    from backend.main import app
    # NB: TestClient déclenche le lifespan via `with` mais on init explicitement
    # pour rester compatible avec les autres fixtures (test_html_smoke pattern).
    return TestClient(app)


def _seed_offer(*, title: str = "Alternance ML Engineer",
                company: str = "Acme",
                city: str = "Paris",
                source: str = "HelloWork",
                match_score: int | None = None,
                status: str | None = None,
                is_active: int = 1) -> int:
    """Insère une offre minimale et renvoie son id."""
    from backend.db import db, make_dedup_key
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO offers (
                title, company, city, source, url, dedup_key,
                match_score, status, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title, company, city, source,
                f"http://x/{title}/{company}/{city}/{match_score}/{status}",
                make_dedup_key(title, company, city),
                match_score, status, is_active,
            ),
        )
        return cur.lastrowid


# ============================================================
# Section 1 — Filtres GET / (asserter contenu, pas juste 200)
# ============================================================


class TestOffersListFiltering:
    """Les filtres query params doivent réellement filtrer la liste rendue."""

    def test_search_filters_by_title(self, client):
        _seed_offer(title="Alternance ML Engineer", company="Acme")
        _seed_offer(title="Alternance DevOps Cloud", company="Beta")

        r = client.get("/?search=ML")
        assert r.status_code == 200
        assert "Alternance ML Engineer" in r.text
        assert "Alternance DevOps Cloud" not in r.text

    def test_search_filters_by_company_case_insensitive(self, client):
        _seed_offer(title="Job A", company="DataCorp")
        _seed_offer(title="Job B", company="OtherCorp")

        r = client.get("/?search=datacorp")
        assert r.status_code == 200
        assert "Job A" in r.text
        assert "Job B" not in r.text

    def test_min_score_filters_threshold(self, client):
        _seed_offer(title="High score", match_score=85)
        _seed_offer(title="Low score", match_score=30)

        r = client.get("/?min_score=60")
        assert "High score" in r.text
        assert "Low score" not in r.text

    def test_status_filter_explicit_value(self, client):
        _seed_offer(title="Postulée", status="Postulé")
        _seed_offer(title="Pas encore", status=None)

        r = client.get("/?status=Postul%C3%A9")
        assert "Postulée" in r.text
        assert "Pas encore" not in r.text

    def test_status_filter_none_sentinel(self, client):
        """`status=_NONE_` cible les offres sans statut (À postuler)."""
        _seed_offer(title="A postuler", status=None)
        _seed_offer(title="Deja postule", status="Postulé")

        r = client.get("/?status=_NONE_")
        assert "A postuler" in r.text
        assert "Deja postule" not in r.text

    def test_archived_hidden_by_default(self, client):
        _seed_offer(title="Live offer", is_active=1)
        _seed_offer(title="Dead offer", is_active=0)

        r = client.get("/")
        assert "Live offer" in r.text
        assert "Dead offer" not in r.text

    def test_archived_visible_with_flag(self, client):
        _seed_offer(title="Live offer", is_active=1)
        _seed_offer(title="Dead offer", is_active=0)

        r = client.get("/?include_archived=true")
        assert "Live offer" in r.text
        assert "Dead offer" in r.text


# ============================================================
# Section 2 — Pagination
# ============================================================


class TestPagination:
    def test_page_2_returns_next_slice(self, client):
        """Page 2 doit montrer les offres 26-... pas les premières."""
        for i in range(1, 51):
            _seed_offer(title=f"Job {i:03d}", company="Acme")

        r1 = client.get("/?per_page=25&page=1&sort=title")
        r2 = client.get("/?per_page=25&page=2&sort=title")
        assert r1.status_code == 200 and r2.status_code == 200
        assert "Job 001" in r1.text and "Job 001" not in r2.text
        assert "Job 026" in r2.text and "Job 026" not in r1.text

    def test_page_beyond_total_normalized(self, client):
        """`page=999` doit se faire ramener sur la dernière page existante."""
        _seed_offer(title="Only one")

        r = client.get("/?per_page=25&page=999")
        assert r.status_code == 200
        assert "Only one" in r.text

    def test_per_page_validation_min(self, client):
        """`per_page < 25` doit renvoyer 422 (Query(ge=25))."""
        r = client.get("/?per_page=1")
        assert r.status_code == 422

    def test_per_page_validation_max(self, client):
        """`per_page > 500` doit renvoyer 422 (Query(le=500))."""
        r = client.get("/?per_page=9999")
        assert r.status_code == 422

    def test_page_validation_min(self, client):
        """`page < 1` doit renvoyer 422."""
        r = client.get("/?page=0")
        assert r.status_code == 422


# ============================================================
# Section 3 — POST /offers/{id} (form submit)
# ============================================================


class TestPostOfferTracking:
    def test_update_status_redirects_303(self, client):
        oid = _seed_offer(title="X")

        r = client.post(
            f"/offers/{oid}",
            data={"status": "Postulé"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == f"/offers/{oid}"

    def test_update_status_persists(self, client):
        oid = _seed_offer(title="X")

        client.post(
            f"/offers/{oid}",
            data={"status": "Postulé", "notes": "envoyé via portail"},
            follow_redirects=False,
        )

        from backend.queries import get_offer
        updated = get_offer(oid)
        assert updated["status"] == "Postulé"
        assert updated["notes"] == "envoyé via portail"

    def test_update_nonexistent_returns_404(self, client):
        r = client.post(
            "/offers/99999",
            data={"status": "Postulé"},
            follow_redirects=False,
        )
        assert r.status_code == 404


# ============================================================
# Section 4 — /api/scrape concurrence + structure
# ============================================================


class TestApiScrape:
    def test_unknown_source_returns_400(self, client):
        r = client.post("/api/scrape", data={"source": "monster"})
        assert r.status_code == 400
        assert "monster" in r.text or "inconnu" in r.text.lower()

    def test_double_post_returns_409(self, client, monkeypatch):
        """Le 2e POST pendant qu'un scrape `running=True` renvoie 409.

        On simule `running=True` via le module global (sans réellement scrape).
        """
        from backend import main as backend_main
        # Force running=True comme si un scrape précédent était en cours
        monkeypatch.setitem(backend_main._SCRAPE_STATE, "running", True)
        monkeypatch.setitem(backend_main._SCRAPE_STATE, "source", "francetravail")

        r = client.post("/api/scrape", data={"source": "francetravail"})
        assert r.status_code == 409
        assert "cours" in r.text.lower() or "déjà" in r.text.lower()

    def test_max_pages_bounds_validation(self, client):
        """`max_pages=0` ou `> 30` → 422 (Form(ge=1, le=30))."""
        r = client.post("/api/scrape", data={"source": "francetravail", "max_pages": "0"})
        assert r.status_code == 422
        r = client.post("/api/scrape", data={"source": "francetravail", "max_pages": "999"})
        assert r.status_code == 422

    def test_scrape_status_structure(self, client):
        r = client.get("/api/scrape/status")
        assert r.status_code == 200
        data = r.json()
        # Champs minimums attendus côté UI HTMX (cf base.html:renderScrapeStatus)
        for key in ("running", "source", "started_at", "finished_at",
                    "total_fetched", "total_new", "total_duplicates", "error"):
            assert key in data, f"clef manquante : {key!r}"

    def test_scrape_reset_clears_running(self, client, monkeypatch):
        from backend import main as backend_main
        monkeypatch.setitem(backend_main._SCRAPE_STATE, "running", True)

        r = client.post("/api/scrape/reset")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert backend_main._SCRAPE_STATE["running"] is False


# ============================================================
# Section 5 — API JSON : stats, PATCH, toggle status
# ============================================================


class TestApiJsonRoutes:
    def test_api_stats_structure(self, client):
        _seed_offer(title="x", status="Postulé", match_score=85)

        r = client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        # Toutes les clefs consommées par les stats cards (offers.html)
        for key in ("total", "to_apply", "applied", "interviews", "refused",
                    "top_fit", "bon_fit", "unscored", "not_interested", "archived"):
            assert key in data, f"clef manquante dans /api/stats : {key!r}"
        assert data["total"] >= 1
        assert data["applied"] >= 1
        assert data["top_fit"] >= 1

    def test_patch_offer_success(self, client):
        oid = _seed_offer(title="X")

        r = client.patch(f"/api/offers/{oid}", json={"status": "Postulé"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        from backend.queries import get_offer
        assert get_offer(oid)["status"] == "Postulé"

    def test_patch_offer_404(self, client):
        r = client.patch("/api/offers/99999", json={"status": "Postulé"})
        assert r.status_code == 404

    def test_post_offer_status_toggle_to_pas_interesse(self, client):
        """Endpoint dédié HTMX 👎. status='Pas intéressé' OK."""
        oid = _seed_offer(title="X")

        r = client.post(
            f"/api/offers/{oid}/status",
            data={"status": "Pas intéressé"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "Pas intéressé"

        from backend.queries import get_offer
        assert get_offer(oid)["status"] == "Pas intéressé"

    def test_post_offer_status_empty_resets_to_null(self, client):
        """status='' depuis HTMX bouton ↩ doit remettre status=NULL."""
        oid = _seed_offer(title="X", status="Pas intéressé")

        r = client.post(f"/api/offers/{oid}/status", data={"status": ""})
        assert r.status_code == 200
        assert r.json()["status"] is None

        from backend.queries import get_offer
        assert get_offer(oid)["status"] is None


# ============================================================
# Section 6 — POST /api/companies/import-from-offers
# ============================================================


class TestImportCompaniesFromOffers:
    def test_import_returns_structured_dict(self, client):
        _seed_offer(title="Alternance Data Eng", company="ToulouseTech", city="Toulouse")

        r = client.post(
            "/api/companies/import-from-offers",
            data={"city": "Toulouse"},
        )
        assert r.status_code == 200
        body = r.json()
        for key in ("city", "candidates", "inserted", "skipped_dup"):
            assert key in body, f"clef manquante : {key!r}"
        assert body["city"] == "Toulouse"
        assert body["inserted"] >= 1

    def test_import_empty_city_no_match(self, client):
        r = client.post(
            "/api/companies/import-from-offers",
            data={"city": "NowhereLand"},
        )
        assert r.status_code == 200
        assert r.json()["inserted"] == 0
