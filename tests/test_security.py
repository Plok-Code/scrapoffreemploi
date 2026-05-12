"""Tests des fixes de sécurité issus de l'audit user (12 mai 2026)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.scrapers.base import RawOffer


class TestUrlValidator:
    """RawOffer.url DOIT rejeter les schémas dangereux."""

    def test_https_accepted(self):
        o = RawOffer(title="X", url="https://example.com/job/1")
        assert o.url == "https://example.com/job/1"

    def test_http_accepted(self):
        o = RawOffer(title="X", url="http://example.com")
        assert o.url == "http://example.com"

    def test_url_empty_normalized_to_none(self):
        assert RawOffer(title="X", url="").url is None
        assert RawOffer(title="X", url=None).url is None

    def test_url_strip_whitespace(self):
        o = RawOffer(title="X", url="  https://x.com  ")
        assert o.url == "https://x.com"

    @pytest.mark.parametrize("dangerous", [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",          # casse insensible
        "data:text/html,<script>x</script>",
        "file:///etc/passwd",
        "vbscript:msgbox(1)",
        "//evil.com/path",                # protocol-relative
        "ftp://example.com",              # autres schémas
        "mailto:hr@example.com",          # mailto rejeté pour les URL d'offre
    ])
    def test_dangerous_schemes_rejected(self, dangerous):
        """Tout schéma autre que http(s):// doit être rejeté par Pydantic."""
        with pytest.raises(ValidationError):
            RawOffer(title="X", url=dangerous)


class TestSafeHrefFilter:
    """Filtre Jinja `safe_href` : http(s) passe, autre → #."""

    def test_http_passes(self):
        from backend.main import _safe_href
        assert _safe_href("http://x.com") == "http://x.com"
        assert _safe_href("https://x.com/path") == "https://x.com/path"

    def test_none_or_empty(self):
        from backend.main import _safe_href
        assert _safe_href(None) == "#"
        assert _safe_href("") == "#"
        assert _safe_href("   ") == "#"

    def test_dangerous_replaced(self):
        from backend.main import _safe_href
        assert _safe_href("javascript:alert(1)") == "#"
        assert _safe_href("data:text/html,foo") == "#"
        assert _safe_href("file:///etc/passwd") == "#"


class TestCSRFOriginMiddleware:
    """Vérifie que les routes mutantes bloquent les origins externes."""

    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        # Utilise une DB temporaire pour ne pas polluer
        db_file = tmp_path / "test.db"
        monkeypatch.setattr("backend.db.DB_PATH", db_file)
        from backend.db import init_schema
        init_schema()
        from fastapi.testclient import TestClient
        from backend.main import app
        return TestClient(app)

    def test_get_passes_without_origin(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200

    def test_post_localhost_origin_passes(self, client):
        r = client.post(
            "/api/scrape/reset",
            headers={"Origin": "http://127.0.0.1:8000"},
        )
        assert r.status_code == 200

    def test_post_external_origin_blocked(self, client):
        r = client.post(
            "/api/scrape/reset",
            headers={"Origin": "https://evil.com"},
        )
        assert r.status_code == 403

    def test_post_external_referer_blocked(self, client):
        r = client.post(
            "/api/scrape/reset",
            headers={"Referer": "https://evil.com/page"},
        )
        assert r.status_code == 403

    def test_post_no_origin_no_referer_passes(self, client):
        """curl / Swagger UI / scripts CLI n'envoient pas Origin/Referer → on accepte."""
        r = client.post("/api/scrape/reset")
        assert r.status_code == 200
