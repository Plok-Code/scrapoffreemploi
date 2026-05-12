"""Tests du détecteur soft-404 (`backend.scrapers.runner._is_soft_404`)."""
from __future__ import annotations

from backend.scrapers.runner import _is_soft_404


class TestSoft404Detector:
    """4 niveaux : body patterns, redirect URL, title, etc."""

    def test_workday_dead_title(self, html_workday_dead):
        """Workday : title contient 'page que vous recherchez'."""
        assert _is_soft_404(
            html_workday_dead,
            original_url="https://example.com/job/JOBREQ_12345",
            final_url="https://example.com/job/JOBREQ_12345",
        ) is True

    def test_axa_redirect_to_listing(self, html_axa_redirect):
        """AXA : title 'Nos offres d'emploi' + body '663 offres correspondent'."""
        result = _is_soft_404(
            html_axa_redirect,
            original_url="https://recrutement.axa.fr/nos-offres-emploi/250002F1-foo",
            final_url="https://recrutement.axa.fr/nos-offres-emploi",
        )
        assert result is True

    def test_workable_not_found_url(self):
        """Workable : URL finale contient `?not_found=true`."""
        html = "<html><head><title>Hugging Face - Current Openings</title></head><body></body></html>"
        result = _is_soft_404(
            html,
            original_url="https://apply.workable.com/huggingface/j/76B3E7710A/",
            final_url="https://apply.workable.com/huggingface/?not_found=true",
        )
        assert result is True

    def test_linkedin_expired_redirect(self):
        """LinkedIn : `trk=expired_jd_redirect` dans URL finale."""
        html = "<html><title>LinkedIn</title></html>"
        result = _is_soft_404(
            html,
            original_url="https://fr.linkedin.com/jobs/view/12345",
            final_url="https://www.linkedin.com/jobs/search?trk=expired_jd_redirect",
        )
        assert result is True

    def test_short_redirect_url(self):
        """URL finale tronquée à < 50% original → soft 404 (redirect home)."""
        html = "<html><title>Sanofi</title></html>"
        result = _is_soft_404(
            html,
            original_url="https://example.com/very/long/specific/job/path/with/lots/of/segments/12345",
            final_url="https://example.com/",
        )
        assert result is True

    def test_alive_offer_not_soft_404(self, html_alive_offer):
        """Page vivante avec vraie description → pas un soft 404."""
        result = _is_soft_404(
            html_alive_offer,
            original_url="https://careers.doctolib.com/jobs/123",
            final_url="https://careers.doctolib.com/jobs/123",
        )
        assert result is False

    def test_empty_html(self):
        """HTML vide → pas un soft-404 (on n'a pas d'info)."""
        result = _is_soft_404("", original_url="http://x", final_url="http://x")
        assert result is False

    def test_cea_title_inexistante(self):
        """CEA : title contient 'inexistante'."""
        html = "<html><head><title>Erreur - Offre demandée inexistante</title></head></html>"
        result = _is_soft_404(
            html,
            original_url="https://www.emploi.cea.fr/job/123",
            final_url="https://www.emploi.cea.fr/job/123",
        )
        assert result is True
