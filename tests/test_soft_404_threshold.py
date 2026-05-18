"""Tests du seuil soft-404 sur l'heuristique de redirect court.

Audit user (19 mai 2026, 4e passe) : seuil 50% trop agressif → faux positifs
sur canonical redirects qui passent typiquement à 70-80% de la longueur
originale. Fix : seuil 30% + exigence que l'URL finale ne contienne PAS
de marqueur d'offre individuelle.

Les patterns body/title/URL-marker du soft-404 sont déjà couverts par
`test_soft_404.py`. Ici on isole l'heuristique de redirect drastique.
"""
from __future__ import annotations

import pytest


# HTML quelconque sans pattern soft-404 explicite (pour isoler l'heuristique URL)
_HTML_NEUTRAL = (
    "<!DOCTYPE html><html><head><title>Doctolib careers</title></head>"
    "<body><main><h1>Welcome</h1><p>...</p></main></body></html>"
)


class TestRedirectThresholdHeuristic:
    def test_canonical_redirect_70pct_keeps_alive(self):
        """Redirect canonical typique : `/jobs/12345-data-engineer-alternance-h-f`
        → `/jobs/12345`. URL finale = ~30% de l'origine MAIS contient `/jobs/`
        → on DOIT considérer alive (pas soft-404)."""
        from backend.scrapers.runner import _is_soft_404
        original = "https://acme.com/careers/jobs/12345-alternance-data-engineer-h-f-paris-2026"
        # final = ~30% length, MAIS contient /jobs/ → garde-fou doit déclencher
        final = "https://acme.com/jobs/12345"
        assert _is_soft_404(_HTML_NEUTRAL, original_url=original, final_url=final) is False

    def test_login_redirect_to_short_url_is_soft_404(self):
        """Redirect vers login/home (URL très courte, pas de marqueur d'offre)
        → soft-404."""
        from backend.scrapers.runner import _is_soft_404
        original = "https://acme.com/careers/jobs/12345-alternance-data-engineer-h-f-paris-2026"
        final = "https://acme.com/login"  # < 30%, pas de /jobs/
        assert _is_soft_404(_HTML_NEUTRAL, original_url=original, final_url=final) is True

    def test_redirect_to_home_is_soft_404(self):
        from backend.scrapers.runner import _is_soft_404
        original = "https://acme.com/careers/jobs/12345-alternance-data-engineer-h-f-paris-2026"
        final = "https://acme.com/"
        assert _is_soft_404(_HTML_NEUTRAL, original_url=original, final_url=final) is True

    def test_redirect_above_30pct_threshold_keeps_alive(self):
        """L'ancien seuil 50% archivait à tort les redirects 35-50%. Avec 30%,
        un redirect qui reste à 40% de l'original (sans pattern soft-404 dans
        body/title) est considéré alive."""
        from backend.scrapers.runner import _is_soft_404
        # 100 chars → 40 chars = 40% (au-dessus du seuil 30%) — pas soft-404
        original = "https://acme.com/careers/jobs/12345-some-very-long-job-slug-here-paris-2026-data"
        final = "https://acme.com/12345"  # 23 chars ≈ 29% ← juste sous 30%
        # Cette URL passe sous 30% MAIS ne contient PAS /jobs/ → soft-404
        assert _is_soft_404(_HTML_NEUTRAL, original_url=original, final_url=final) is True

    def test_same_url_no_redirect_keeps_alive(self):
        """Pas de redirect (final == original) → pas soft-404 (cette heuristique
        ne se déclenche pas)."""
        from backend.scrapers.runner import _is_soft_404
        url = "https://acme.com/careers/jobs/12345-alternance"
        assert _is_soft_404(_HTML_NEUTRAL, original_url=url, final_url=url) is False

    @pytest.mark.parametrize("offer_marker", [
        "/jobs/",
        "/offers/",
        "/offer/",
        "/job/",
        "/position/",
        "/emploi/",
        "/career/",
    ])
    def test_offer_marker_in_final_url_keeps_alive(self, offer_marker):
        """Tous les marqueurs d'offre individuelle empêchent le soft-404."""
        from backend.scrapers.runner import _is_soft_404
        original = "https://acme.com/very/long/original/url/with/details/2026/job"
        final = f"https://acme.com{offer_marker}777"  # court mais contient le marqueur
        assert _is_soft_404(_HTML_NEUTRAL, original_url=original, final_url=final) is False
