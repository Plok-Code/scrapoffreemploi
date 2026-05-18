"""Scraper Welcome to the Jungle (https://www.welcometothejungle.com).

- `fetch_list()` : interroge l'API Algolia publique de WTTJ (clés embedded dans
  leur frontend JS, cf `docs/SOURCES.md` §11). Filtre alternance + France.
- `fetch_detail()` : parse le JSON-LD `JobPosting` de la page détail.
"""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from backend.scrapers._http import (
    DEFAULT_HEADERS, get_with_retry, http_client, polite_sleep,
)
from backend.scrapers._jsonld import (
    extract_jobposting_description,
    normalize_whitespace,
)
from backend.scrapers._keywords import matches_keywords
from backend.scrapers.base import RawOffer, Scraper

# Clés Algolia publiques WTTJ (cf docs/SOURCES.md §11, source GitHub juan-azabal)
ALGOLIA_APP_ID = "CSEKHVMS53"
ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
ALGOLIA_INDEX_FR = "wttj_jobs_production_fr"
ALGOLIA_URL = (
    f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/"
    f"{ALGOLIA_INDEX_FR}/query"
)

ALGOLIA_HEADERS = {
    **DEFAULT_HEADERS,
    "x-algolia-application-id": ALGOLIA_APP_ID,
    "x-algolia-api-key": ALGOLIA_API_KEY,
    "Content-Type": "application/json",
    "Referer": "https://www.welcometothejungle.com/",
    "Origin": "https://www.welcometothejungle.com",
}

# Filtre Algolia : alternance + apprentissage, en France
# Note : champ s'appelle `offices` (pluriel) côté Algolia
ALGOLIA_FILTERS = (
    "(contract_type:apprenticeship OR contract_type:professional_training)"
    " AND offices.country_code:FR"
)


def _hit_to_raw(hit: dict) -> RawOffer | None:
    """Convertit un hit Algolia en RawOffer."""
    title = hit.get("name") or hit.get("title")
    if not title:
        return None
    org = hit.get("organization") or {}
    company = org.get("name")
    offices = hit.get("offices") or []
    office = offices[0] if offices else {}
    city = office.get("city") or office.get("locality")
    department = None
    org_slug = org.get("slug")
    job_slug = hit.get("slug") or hit.get("reference")
    url = (
        f"https://www.welcometothejungle.com/fr/companies/{org_slug}/jobs/{job_slug}"
        if org_slug and job_slug else None
    )

    # Description depuis summary + profile + key_missions (champs Algolia WTTJ)
    def _to_str(v):
        if not v:
            return ""
        if isinstance(v, list):
            return "\n".join(str(x) for x in v)
        return str(v)

    desc_parts = [_to_str(hit.get(k)) for k in ("summary", "profile", "key_missions")]
    description = "\n\n".join(p for p in desc_parts if p).strip() or None

    # Nettoyage HTML si présent (certains champs contiennent du HTML)
    if description and ("<" in description and ">" in description):
        description = BeautifulSoup(description, "lxml").get_text(separator="\n", strip=True)
        description = normalize_whitespace(description)

    return RawOffer(
        title=title,
        company=company,
        city=city,
        source="WelcomeToTheJungle",
        url=url,
        description=description if description and len(description) > 100 else None,
        contract_type="Alternance",
        date_published=hit.get("published_at"),
        raw={"objectID": hit.get("objectID")},
    )


class WTTJScraper(Scraper):
    source_name = "WelcomeToTheJungle"

    def fetch_list(
        self,
        *,
        keywords: list[str],
        max_pages: int = 5,
    ) -> list[RawOffer]:
        """Recherche via l'API Algolia publique de WTTJ.

        Une requête Algolia par mot-clé. Dedup par URL.
        Filtres serveur : contract_type alternance/apprentissage + pays FR.
        Filtre client : mots-clés IA/data (au cas où Algolia laisse passer du bruit).
        """
        seen_urls: set[str] = set()
        results: list[RawOffer] = []

        with httpx.Client(headers=ALGOLIA_HEADERS, timeout=20.0, http2=True) as client:
            for kw in keywords:
                for page in range(max_pages):
                    body = {
                        "query": kw,
                        "filters": ALGOLIA_FILTERS,
                        "hitsPerPage": 50,
                        "page": page,
                    }
                    try:
                        resp = client.post(ALGOLIA_URL, json=body)
                        resp.raise_for_status()
                    except httpx.HTTPError:
                        break
                    data = resp.json()
                    hits = data.get("hits", [])
                    if not hits:
                        break

                    new_in_page = 0
                    for hit in hits:
                        off = _hit_to_raw(hit)
                        if not off:
                            continue
                        if off.url and off.url in seen_urls:
                            continue
                        # Filtre IA/data
                        if not matches_keywords(off.title, off.description):
                            continue
                        if off.url:
                            seen_urls.add(off.url)
                        results.append(off)
                        new_in_page += 1

                    # Si on a moins de pages que prévu, arrêter
                    if data.get("nbPages", 0) <= page + 1:
                        break
                    if new_in_page == 0:
                        # Page entière déjà vue / tout filtré
                        break

                    polite_sleep(0.8)

        return results

    def fetch_detail(self, url: str) -> str | None:
        with http_client() as client:
            resp = get_with_retry(client, url)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "lxml")

            # 1) JSON-LD JobPosting (gère dict / list / @graph)
            text = extract_jobposting_description(soup)
            if text:
                return text

            # 2) Fallback HTML brut sur les containers WTTJ
            for sel in ('[data-testid="job-description"]', "main", "article"):
                el = soup.select_one(sel)
                if el:
                    text = normalize_whitespace(
                        el.get_text(separator="\n", strip=True)
                    )
                    if len(text) > 200:
                        return text
            return None
