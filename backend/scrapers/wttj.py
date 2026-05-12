"""Scraper Welcome to the Jungle (https://www.welcometothejungle.com).

Pour l'instant : uniquement `fetch_detail()`. Chaque page détail contient un
JSON-LD `JobPosting` avec description complète (HTML). Fetch direct ok.

Pour `fetch_list()` à terme : utiliser l'API Algolia publique (clés exposées
dans le frontend JS — cf docs/SOURCES.md §11).
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from backend.scrapers._http import get_with_retry, http_client
from backend.scrapers.base import RawOffer, Scraper


class WTTJScraper(Scraper):
    source_name = "WelcomeToTheJungle"

    def fetch_list(self, *, keywords: list[str], max_pages: int = 5) -> list[RawOffer]:  # noqa: ARG002
        # À venir : Algolia search API (cf docs/SOURCES.md §11)
        return []

    def fetch_detail(self, url: str) -> str | None:
        with http_client() as client:
            resp = get_with_retry(client, url)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "lxml")

            # 1) JSON-LD JobPosting (le plus propre)
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                candidates = data if isinstance(data, list) else [data]
                for item in candidates:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        desc_html = item.get("description", "")
                        if desc_html:
                            inner = BeautifulSoup(desc_html, "lxml")
                            text = inner.get_text(separator="\n", strip=True)
                            text = re.sub(r"\n{3,}", "\n\n", text)
                            if len(text) > 200:
                                return text

            # 2) Fallback HTML brut
            for sel in ('[data-testid="job-description"]', "main", "article"):
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(separator="\n", strip=True)
                    text = re.sub(r"\n{3,}", "\n\n", text)
                    if len(text) > 200:
                        return text
            return None
