"""Tests du retry token France Travail sur 401.

Le `_TOKEN_CACHE` du scraper FT peut périmer côté serveur (rotation, abuse
detection, révocation) avant son `expires_at` local. Le helper
`_request_with_token_retry` doit :
1. Renvoyer directement les réponses non-401.
2. Sur 401, invalider le cache + refresh + rejouer LA MÊME requête (pas la
   suivante — bug pré-existant fixé).
3. Limiter à 1 retry (au-delà = creds KO, fail fast).
4. Mettre à jour `auth_headers` in-place pour les requêtes ultérieures.

Mocks via `httpx.MockTransport` (idiomatique httpx, pas de network).
"""
from __future__ import annotations

import httpx
import pytest


def _make_transport(statuses: list[int]) -> tuple[httpx.MockTransport, list[str]]:
    """Crée un MockTransport qui répond les statuses dans l'ordre.

    Retourne aussi la liste des Authorization headers reçus (pour assert).
    """
    seen_auth: list[str] = []
    idx = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("Authorization", ""))
        s = statuses[idx["i"]] if idx["i"] < len(statuses) else 200
        idx["i"] += 1
        return httpx.Response(s, json={"ok": True})

    return httpx.MockTransport(handler), seen_auth


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """Reset le cache du token entre chaque test (state global du module)."""
    from backend.scrapers import francetravail
    francetravail._TOKEN_CACHE["token"] = None
    francetravail._TOKEN_CACHE["expires_at"] = 0.0
    yield
    francetravail._TOKEN_CACHE["token"] = None
    francetravail._TOKEN_CACHE["expires_at"] = 0.0


class TestRequestWithTokenRetry:
    def test_200_no_retry(self, monkeypatch):
        from backend.scrapers.francetravail import _request_with_token_retry

        transport, seen = _make_transport([200])
        client = httpx.Client(transport=transport)
        headers = {"Authorization": "Bearer old"}

        resp = _request_with_token_retry(
            client, "GET", "https://api.fr/x", auth_headers=headers
        )

        assert resp.status_code == 200
        assert len(seen) == 1
        assert seen[0] == "Bearer old"
        # Header inchangé puisque pas de refresh
        assert headers["Authorization"] == "Bearer old"

    def test_401_then_200_refreshes_and_retries_same_request(self, monkeypatch):
        """La régression originale : sur 401, `continue` skippait la page.
        Le helper doit rejouer la MÊME requête après refresh."""
        from backend.scrapers.francetravail import _request_with_token_retry

        # Mock `_get_token` pour ne pas hit le serveur OAuth réel
        new_token_calls = {"n": 0}

        def fake_get_token(client):
            new_token_calls["n"] += 1
            return f"new-{new_token_calls['n']}"

        monkeypatch.setattr(
            "backend.scrapers.francetravail._get_token", fake_get_token
        )

        transport, seen = _make_transport([401, 200])
        client = httpx.Client(transport=transport)
        headers = {"Authorization": "Bearer old"}

        resp = _request_with_token_retry(
            client, "GET", "https://api.fr/x", auth_headers=headers
        )

        assert resp.status_code == 200
        # 2 requêtes : la 1re avec old token (→ 401), la 2e avec nouveau
        assert len(seen) == 2
        assert seen[0] == "Bearer old"
        assert seen[1] == "Bearer new-1"
        # Header in-place mis à jour
        assert headers["Authorization"] == "Bearer new-1"

    def test_persistent_401_returns_last_401(self, monkeypatch):
        """Deux 401 consécutifs (creds KO) → 1 retry, puis retourne le dernier 401."""
        from backend.scrapers.francetravail import _request_with_token_retry

        monkeypatch.setattr(
            "backend.scrapers.francetravail._get_token",
            lambda client: "new_token",
        )

        transport, seen = _make_transport([401, 401])
        client = httpx.Client(transport=transport)
        headers = {"Authorization": "Bearer old"}

        resp = _request_with_token_retry(
            client, "GET", "https://api.fr/x", auth_headers=headers
        )

        assert resp.status_code == 401
        # 2 requêtes : la 1re et le retry, pas de 3e
        assert len(seen) == 2

    def test_invalidates_token_cache_on_401(self, monkeypatch):
        """`_TOKEN_CACHE["expires_at"]` doit passer à 0.0 sur 401."""
        from backend.scrapers import francetravail
        from backend.scrapers.francetravail import _request_with_token_retry

        # Pré-rempli un cache "valide encore 1h"
        francetravail._TOKEN_CACHE["token"] = "stale"
        francetravail._TOKEN_CACHE["expires_at"] = 9_999_999_999.0

        monkeypatch.setattr(
            "backend.scrapers.francetravail._get_token",
            lambda client: "refreshed",
        )

        transport, _ = _make_transport([401, 200])
        client = httpx.Client(transport=transport)
        _request_with_token_retry(
            client, "GET", "https://api.fr/x",
            auth_headers={"Authorization": "Bearer stale"},
        )

        # _get_token a été appelé, mais on s'assure surtout que expires_at a été
        # remis à 0 AVANT son appel (= forçage du refresh même si cache "valide")
        # Comme le mock _get_token renvoie direct sans toucher au cache,
        # on vérifie que la valeur est restée à 0.0 (ou très basse).
        assert francetravail._TOKEN_CACHE["expires_at"] == 0.0

    def test_no_retry_on_other_status_codes(self, monkeypatch):
        """500, 503, 429, 200, 204 : pas de retry token (autres handlers s'en chargent)."""
        from backend.scrapers.francetravail import _request_with_token_retry

        for status in (500, 503, 429, 204):
            transport, seen = _make_transport([status])
            client = httpx.Client(transport=transport)
            resp = _request_with_token_retry(
                client, "GET", "https://api.fr/x",
                auth_headers={"Authorization": "Bearer x"},
            )
            assert resp.status_code == status
            assert len(seen) == 1, f"unexpected retry on status={status}"

    def test_passes_params_through(self, monkeypatch):
        """Les query params doivent être passés à la requête réelle."""
        from backend.scrapers.francetravail import _request_with_token_retry

        seen_params: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_params.append(dict(request.url.params))
            return httpx.Response(200, json={})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        _request_with_token_retry(
            client, "GET", "https://api.fr/x",
            auth_headers={"Authorization": "Bearer x"},
            params={"motsCles": "ML", "range": "0-49"},
        )

        assert seen_params[0]["motsCles"] == "ML"
        assert seen_params[0]["range"] == "0-49"
