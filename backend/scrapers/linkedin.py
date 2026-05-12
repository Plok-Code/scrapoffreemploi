"""Scraper LinkedIn Jobs (https://fr.linkedin.com).

Stratégie `fetch_detail()` :
1. **Playwright avec profil persistant** (`data/.playwright_profile/`) — si dispo,
   utilise les cookies de login (incl. Premium) → accès aux offres archivées et
   contenu enrichi. Lancer `python -m backend.scrapers.linkedin_login` une fois
   pour le premier login.
2. **Fallback httpx** sur `section.description` (page guest) — marche pour les
   offres encore actives sans login.

Pour `fetch_list()` à terme : utiliser le contexte Playwright loggué pour scraper
la recherche LinkedIn (jobs/search/...).
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from backend.scrapers._http import get_with_retry, http_client
from backend.scrapers.base import RawOffer, Scraper

# Sélecteurs LinkedIn essayés dans l'ordre. Diffèrent selon page guest vs loggué.
_DESCRIPTION_SELECTORS = (
    # Loggué (jobs/view classic)
    "div.jobs-description__content",
    "div.jobs-description-content__text",
    "article.jobs-description__container",
    "div.jobs-box__html-content",
    # Guest / non-loggué
    "section.description div.show-more-less-html__markup",
    "section.description",
    "div.show-more-less-html__markup",
    "div.description__text",
)


def _extract_from_html(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for sel in _DESCRIPTION_SELECTORS:
        el = soup.select_one(sel)
        if not el:
            continue
        text = el.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        if len(text) > 200:
            return text
    return None


class LinkedInScraper(Scraper):
    source_name = "LinkedIn"

    def fetch_list(self, *, keywords: list[str], max_pages: int = 5) -> list[RawOffer]:  # noqa: ARG002
        # À venir : Playwright sur la page de recherche LinkedIn avec cookies persistés
        return []

    def fetch_detail(self, url: str) -> str | None:
        # 1) Tentative Playwright (profil persistant, login Premium si dispo)
        try:
            from backend.scrapers._playwright import PROFILE_DIR, persistent_browser
            if PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir()):
                desc = self._fetch_detail_playwright(url, persistent_browser)
                if desc:
                    return desc
        except Exception:  # noqa: BLE001
            # Si Playwright n'est pas installé ou plante, on passe au fallback
            pass

        # 2) Fallback httpx (guest, marche pour les offres actives)
        with http_client() as client:
            resp = get_with_retry(client, url)
            if resp.status_code != 200:
                return None
            return _extract_from_html(resp.text)

    def _fetch_detail_playwright(self, url: str, persistent_browser) -> str | None:
        """Récupère la description via Playwright avec profil persistant."""
        with persistent_browser(headless=True) as ctx:
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Attend que l'un des sélecteurs de description apparaisse (max 12s)
                try:
                    page.wait_for_selector(
                        ", ".join(_DESCRIPTION_SELECTORS),
                        timeout=12000,
                        state="attached",
                    )
                except Exception:  # noqa: BLE001
                    pass  # on tente quand même l'extract sur le HTML actuel
                html = page.content()
                return _extract_from_html(html)
            finally:
                page.close()
