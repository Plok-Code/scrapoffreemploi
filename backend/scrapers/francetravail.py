"""Scraper France Travail (https://candidat.francetravail.fr).

Pour l'instant : uniquement `fetch_detail()` pour enrichir les descriptions des
offres déjà en DB. La page détail expose la description sous `[itemprop=description]`
(microdata Schema.org). Pas d'anti-bot, fetch direct possible.

Pour `fetch_list()` à terme : préférer l'API officielle https://api.francetravail.io
(nécessite OAuth client_credentials, gratuit après inscription).
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from backend.scrapers._http import get_with_retry, http_client
from backend.scrapers.base import RawOffer, Scraper


class FranceTravailScraper(Scraper):
    source_name = "France Travail"

    def fetch_list(self, *, keywords: list[str], max_pages: int = 5) -> list[RawOffer]:  # noqa: ARG002
        # Non implémenté : à venir via API officielle francetravail.io (OAuth requis)
        return []

    def fetch_detail(self, url: str) -> str | None:
        with http_client() as client:
            resp = get_with_retry(client, url)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "lxml")
            el = soup.select_one("[itemprop=description]")
            if not el:
                return None
            text = el.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text if len(text) > 200 else None
