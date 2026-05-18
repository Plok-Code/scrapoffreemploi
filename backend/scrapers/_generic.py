"""Scraper générique pour les career sites individuels.

Stratégie multi-fallback :
1. JSON-LD `JobPosting` (standard Schema.org, présent sur 50%+ des sites carrières
   modernes : Workable, Lever, Workday, Greenhouse, etc.)
2. `[itemprop=description]` (microdata Schema.org)
3. `[data-testid*="description"]` / `[data-cy*="description"]` (patterns modernes)
4. `<meta name="description">` (fallback minimaliste — toujours < 200 chars donc skip)
5. Texte du `<main>` ou `<article>` (last resort, peut inclure du bruit)

Utilisé pour les sources "Career site - X" non couvertes par un scraper dédié.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from backend.scrapers._http import get_with_retry, http_client
from backend.scrapers._jsonld import (
    extract_jobposting_description,
    normalize_whitespace,
)
from backend.scrapers.base import RawOffer, Scraper


def _extract_microdata(soup: BeautifulSoup) -> str | None:
    """Schema.org microdata : `itemprop="description"`."""
    el = soup.select_one('[itemprop="description"]')
    if el:
        text = normalize_whitespace(el.get_text(separator="\n", strip=True))
        if len(text) > 200:
            return text
    return None


def _extract_by_attribute(soup: BeautifulSoup) -> str | None:
    """data-testid / data-cy / class contenant 'description' ou 'job-body'."""
    for sel in (
        '[data-testid*="description"]',
        '[data-cy*="description"]',
        '[data-cy*="jobBody"]',
        '[data-automation-id*="jobPostingDescription"]',  # Workday
        ".job-description",
        ".description-text",
        ".job-body",
    ):
        el = soup.select_one(sel)
        if el:
            text = normalize_whitespace(el.get_text(separator="\n", strip=True))
            if len(text) > 200:
                return text
    return None


def _extract_main(soup: BeautifulSoup) -> str | None:
    """Last resort : main / article (peut contenir du bruit)."""
    for sel in ("main", "article"):
        el = soup.select_one(sel)
        if el:
            text = normalize_whitespace(el.get_text(separator="\n", strip=True))
            if len(text) > 500:  # exigence plus forte pour limiter le bruit
                return text
    return None


class GenericScraper(Scraper):
    """Scraper bouche-trou pour les career sites variés (Workable, Lever, Workday, etc.)."""

    source_name = "Generic"

    def fetch_list(self, *, keywords: list[str], max_pages: int = 5) -> list[RawOffer]:  # noqa: ARG002
        return []

    def fetch_detail(self, url: str) -> str | None:
        with http_client() as client:
            try:
                resp = get_with_retry(client, url)
            except Exception:  # noqa: BLE001
                return None
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "lxml")

        for extractor in (
            extract_jobposting_description,
            _extract_microdata,
            _extract_by_attribute,
            _extract_main,
        ):
            result = extractor(soup)
            if result:
                return result
        return None
