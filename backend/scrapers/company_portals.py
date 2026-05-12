"""Scrape des portails d'entreprises (target_companies.source_url).

Pour chaque entreprise cible avec un portail, tente d'extraire les offres IA/data
en alternance via :
1. Workable API publique (apply.workable.com/{slug})
2. Lever API publique (jobs.lever.co/{slug})
3. Best-effort générique : parse les liens d'offres depuis la page de listing.

Les offres trouvées sont insérées via queries.insert_offer() (dédup par URL + dedup_key
automatique). Pas de fetch_detail() ici (la description sera enrichie plus tard via
`cli.py enrich-descriptions`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from backend import queries
from backend.db import db
from backend.scrapers._http import DEFAULT_HEADERS, polite_sleep
from backend.scrapers._keywords import matches_keywords
from backend.scrapers.base import RawOffer


@dataclass
class PortalScrapeResult:
    total_companies: int
    portals_attempted: int
    portals_succeeded: int
    offers_found: int
    new_offers_inserted: int
    duplicates: int


def _extract_workable_slug(url: str) -> str | None:
    """`https://apply.workable.com/huggingface/` → `huggingface`."""
    m = re.match(r"https?://apply\.workable\.com/([^/?#]+)", url)
    return m.group(1) if m else None


def _extract_lever_slug(url: str) -> str | None:
    """`https://jobs.lever.co/mistral/...` → `mistral`."""
    m = re.match(r"https?://jobs\.lever\.co/([^/?#]+)", url)
    return m.group(1) if m else None


def _is_workday(url: str) -> bool:
    return bool(re.match(r"https?://[^.]+\.[a-z0-9]+\.myworkdayjobs\.com", url))


def _fetch_workable_jobs(slug: str, company_name: str, client: httpx.Client) -> list[RawOffer]:
    """API Workable publique : retourne toutes les offres d'un compte."""
    url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
    try:
        r = client.get(url, headers={"Accept": "application/json"}, params={"limit": 100})
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:  # noqa: BLE001
        return []

    offers: list[RawOffer] = []
    for j in data.get("results", []):
        title = j.get("title", "").strip()
        if not title:
            continue
        if not matches_keywords(title, j.get("description") or ""):
            continue
        shortcode = j.get("shortcode") or ""
        offer_url = f"https://apply.workable.com/{slug}/j/{shortcode}/"
        location = j.get("location") or {}
        city = location.get("city") or location.get("country")
        country = (location.get("country") or "").upper()
        if country and country not in ("FR", "FRANCE"):
            continue  # skip offres hors France
        offers.append(RawOffer(
            title=title,
            company=company_name,
            city=city,
            url=offer_url,
            source=f"Portail entreprise - {company_name} (Workable)",
            description=j.get("description"),
            contract_type="Alternance" if "alterna" in title.lower() else None,
        ))
    return offers


def _fetch_lever_jobs(slug: str, company_name: str, client: httpx.Client) -> list[RawOffer]:
    """API Lever publique : retourne toutes les offres d'un compte."""
    url = f"https://api.lever.co/v0/postings/{slug}"
    try:
        r = client.get(url, params={"mode": "json"}, headers={"Accept": "application/json"})
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:  # noqa: BLE001
        return []

    offers: list[RawOffer] = []
    items = data if isinstance(data, list) else data.get("postings", [])
    for j in items:
        title = (j.get("text") or j.get("title") or "").strip()
        if not title:
            continue
        categories = j.get("categories") or {}
        location = categories.get("location") or j.get("location")
        country = (location or "").upper() if isinstance(location, str) else ""
        # Lever location est un string libre ; on essaie de filtrer la France
        if location and isinstance(location, str):
            if not re.search(r"\b(France|Paris|Toulouse|Bordeaux|Lyon|Nantes|Pau|Nancy|FR|EMEA|Remote)\b", location, re.IGNORECASE):
                continue
        desc_plain = j.get("descriptionPlain") or j.get("description") or ""
        if not matches_keywords(title, desc_plain):
            continue
        offer_url = j.get("hostedUrl") or j.get("applyUrl") or ""
        if not offer_url:
            continue
        offers.append(RawOffer(
            title=title,
            company=company_name,
            city=location if isinstance(location, str) else None,
            url=offer_url,
            source=f"Portail entreprise - {company_name} (Lever)",
            description=desc_plain,
            contract_type="Alternance" if "alterna" in title.lower() else None,
        ))
    return offers


def _fetch_workday_jobs(url: str, company_name: str, client: httpx.Client) -> list[RawOffer]:
    """Workday : tente de hit l'API JSON `/wday/cxs/{tenant}/{site}/jobs`.

    Le `source_url` doit déjà pointer vers une page de jobs Workday. On extrait
    `{tenant}` et `{site}` depuis l'URL puis on POST sur l'API de search.
    """
    m = re.match(r"https?://([^.]+)\.([^.]+)\.myworkdayjobs\.com/([^/]+)/([^/?#]+)", url)
    if not m:
        return []
    tenant, _server, _lang, site = m.groups()
    api_url = f"https://{tenant}.wd3.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    try:
        # POST avec un body de recherche (alternance + France)
        r = client.post(
            api_url,
            json={
                "appliedFacets": {},
                "limit": 20,
                "offset": 0,
                "searchText": "alternance data",
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:  # noqa: BLE001
        return []

    offers: list[RawOffer] = []
    for j in data.get("jobPostings", []):
        title = (j.get("title") or "").strip()
        if not title or not matches_keywords(title):
            continue
        ext = j.get("externalPath") or ""
        offer_url = f"https://{tenant}.wd3.myworkdayjobs.com/{_lang}/{site}{ext}" if ext else ""
        city = j.get("locationsText") or None
        if city and "France" not in city and "Toulouse" not in city and "Paris" not in city:
            # Skip si hors France évident
            if not re.search(r"France|Toulouse|Bordeaux|Paris|Pau|Nancy|Lyon|Nantes", city):
                continue
        offers.append(RawOffer(
            title=title,
            company=company_name,
            city=city,
            url=offer_url,
            source=f"Portail entreprise - {company_name} (Workday)",
            contract_type="Alternance" if "alterna" in title.lower() else None,
        ))
    return offers


# Heuristique : URLs internes qui ressemblent à une offre individuelle
_JOB_LINK_HINTS = re.compile(
    r"/(jobs?|offres?|offer|career|carriere|emploi[s]?|apprenti|alternance|"
    r"recruitment|recrutement|postuler|opening)/",
    re.IGNORECASE,
)


def _fetch_generic_career_page(url: str, company_name: str, client: httpx.Client) -> list[RawOffer]:
    """Best-effort : parse la page de listing, extrait les `<a>` ressemblant à
    des offres dont le texte matche les mots-clés IA/data + alternance."""
    try:
        r = client.get(url)
        if r.status_code != 200 or len(r.text) < 1000:
            return []
    except Exception:  # noqa: BLE001
        return []

    soup = BeautifulSoup(r.text, "lxml")
    base = url
    seen_urls: set[str] = set()
    offers: list[RawOffer] = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        # Doit ressembler à une offre individuelle
        if not _JOB_LINK_HINTS.search(href):
            continue
        # Texte du lien = candidat titre
        text = a.get_text(" ", strip=True)
        if not text or len(text) < 8 or len(text) > 200:
            continue
        if not matches_keywords(text):
            continue
        # Bonus : on cherche "alternance" / "apprenti" dans le contexte (texte ou href)
        ctx = (text + " " + href).lower()
        if not re.search(r"alternan|apprenti|stage|contrat\s*pro", ctx):
            continue
        full_url = urljoin(base, href)
        # Garde uniquement domaine principal de la page (pas de liens externes)
        if urlparse(full_url).netloc != urlparse(base).netloc:
            continue
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        offers.append(RawOffer(
            title=text,
            company=company_name,
            url=full_url,
            source=f"Portail entreprise - {company_name}",
            contract_type="Alternance",
        ))
        if len(offers) >= 20:  # cap par portail pour éviter spam
            break
    return offers


def scrape_target_company_portals(
    *,
    city_filter: str | None = None,
    limit: int | None = None,
    sleep_between: float = 1.0,
) -> PortalScrapeResult:
    """Itère sur target_companies avec source_url et scrape leurs offres.

    Args:
        city_filter: si fourni, ne scrape que les entreprises matchant cette ville.
        limit: max d'entreprises à scraper.
        sleep_between: pause entre 2 portails.
    """
    where = ["source_url IS NOT NULL", "source_url != ''"]
    params: list = []
    if city_filter:
        where.append("LOWER(city) LIKE ?")
        params.append(f"%{city_filter.lower()}%")
    sql = (
        f"SELECT id, name, source_url FROM target_companies "
        f"WHERE {' AND '.join(where)} ORDER BY id"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"

    with db() as conn:
        targets = [dict(r) for r in conn.execute(sql, params).fetchall()]

    portals_attempted = 0
    portals_succeeded = 0
    offers_found = 0
    inserted = 0
    dup = 0

    with httpx.Client(
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(20.0, connect=8.0),
        follow_redirects=True,
    ) as client:
        for i, t in enumerate(targets, 1):
            company_name = t["name"]
            url = t["source_url"]
            portals_attempted += 1

            # Dispatch par type de plateforme
            raw_offers: list[RawOffer] = []
            try:
                slug = _extract_workable_slug(url)
                if slug:
                    raw_offers = _fetch_workable_jobs(slug, company_name, client)
                elif _extract_lever_slug(url):
                    raw_offers = _fetch_lever_jobs(_extract_lever_slug(url), company_name, client)
                elif _is_workday(url):
                    raw_offers = _fetch_workday_jobs(url, company_name, client)
                else:
                    raw_offers = _fetch_generic_career_page(url, company_name, client)
            except Exception:  # noqa: BLE001
                pass

            if raw_offers:
                portals_succeeded += 1
            offers_found += len(raw_offers)

            for raw in raw_offers:
                try:
                    _id, was_new = queries.insert_offer({
                        "title": raw.title,
                        "company": raw.company,
                        "city": raw.city,
                        "department": raw.department,
                        "source": raw.source,
                        "url": raw.url,
                        "description": raw.description,
                        "date_published": raw.date_published,
                        "remote": raw.remote,
                        "contract_type": raw.contract_type or "Alternance",
                        "salary": raw.salary,
                    })
                    if was_new:
                        inserted += 1
                    else:
                        dup += 1
                except Exception:  # noqa: BLE001
                    pass

            if i < len(targets):
                polite_sleep(sleep_between)

    return PortalScrapeResult(
        total_companies=len(targets),
        portals_attempted=portals_attempted,
        portals_succeeded=portals_succeeded,
        offers_found=offers_found,
        new_offers_inserted=inserted,
        duplicates=dup,
    )


if __name__ == "__main__":
    import sys
    city = sys.argv[1] if len(sys.argv) > 1 else None
    result = scrape_target_company_portals(city_filter=city, sleep_between=0.5)
    print(f"Portails entreprises scrapés (city={city or 'all'}):")
    print(f"  Tentatives    : {result.portals_attempted}")
    print(f"  Réussites     : {result.portals_succeeded}")
    print(f"  Offres trouvées : {result.offers_found}")
    print(f"  Nouvelles ins. : {result.new_offers_inserted}")
    print(f"  Doublons      : {result.duplicates}")
