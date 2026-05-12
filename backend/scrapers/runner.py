"""Orchestrateur de scraping : lance un scraper, insère en DB, génère le batch."""
from __future__ import annotations

from dataclasses import dataclass

from backend import matching, queries
from backend.db import db
from backend.scrapers._http import polite_sleep
from backend.scrapers.base import RawOffer, Scraper
from backend.scrapers.registry import get_scraper

# Mots-clés de recherche par défaut envoyés au scraper (alternance + IA/data)
DEFAULT_SEARCH_KEYWORDS = [
    "alternance intelligence artificielle",
    "alternance machine learning",
    "alternance data scientist",
    "alternance MLOps",
    "alternance AI engineer",
    "alternance deep learning",
]


@dataclass
class ScrapeResult:
    source: str
    total_fetched: int
    total_new: int
    total_duplicates: int
    batch_file: str | None
    new_ids: list[int]


def run_scrape(
    source: str,
    *,
    keywords: list[str] | None = None,
    max_pages: int = 3,
    generate_batch: bool = True,
) -> ScrapeResult:
    """Lance le scraper d'une source, insère en DB, optionnellement génère le batch JSON.

    Args:
        source: nom du scraper (cf registry.SCRAPERS, ex "hellowork")
        keywords: mots-clés de recherche envoyés au scraper. None → DEFAULT_SEARCH_KEYWORDS.
        max_pages: pagination max par mot-clé.
        generate_batch: si True, génère data/batches/{date}_to_score.json après.
    """
    scraper = get_scraper(source)
    raw_offers: list[RawOffer] = scraper.fetch_list(
        keywords=keywords or DEFAULT_SEARCH_KEYWORDS,
        max_pages=max_pages,
    )

    new_ids: list[int] = []
    duplicates = 0
    for raw in raw_offers:
        offer_id, was_new = queries.insert_offer({
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
        if was_new and offer_id is not None:
            new_ids.append(offer_id)
        else:
            duplicates += 1

    batch_path = None
    if generate_batch and new_ids:
        # Génère un batch ne contenant QUE les nouvelles offres
        # (l'export par défaut prend toutes les non-scorées, ce qui peut être large)
        from backend.matching import export_batch_to_score
        path = export_batch_to_score(only_unscored=True, limit=None)
        batch_path = str(path)

    queries.record_scrape_run(
        sources=source,
        total_fetched=len(raw_offers),
        total_new=len(new_ids),
        total_duplicates=duplicates,
        batch_file=batch_path,
    )

    return ScrapeResult(
        source=source,
        total_fetched=len(raw_offers),
        total_new=len(new_ids),
        total_duplicates=duplicates,
        batch_file=batch_path,
        new_ids=new_ids,
    )


# --- Enrichissement des descriptions sur offres existantes ---

# Map des valeurs `source` rencontrées en DB vers la clé du registry.
# On match `prefix in source.lower()`. Préfixes plus longs prioritaires.
_SOURCE_TO_REGISTRY = {
    "hellowork":             "hellowork",
    "france travail":        "francetravail",
    "francetravail":         "francetravail",
    "linkedin":              "linkedin",
    "welcometothejungle":    "wttj",
    "welcome to the jungle": "wttj",
    "wttj":                  "wttj",
    "career site":           "generic",  # fallback générique pour tous les "Career site - X"
}


def _scraper_for_source(source_value: str | None) -> Scraper | None:
    s = (source_value or "").lower().strip()
    if not s:
        return None
    # Match du préfixe le plus long en premier
    for prefix in sorted(_SOURCE_TO_REGISTRY, key=len, reverse=True):
        if prefix in s:
            key = _SOURCE_TO_REGISTRY[prefix]
            try:
                return get_scraper(key)
            except KeyError:
                return None
    # Fallback : on tente le scraper générique pour les sources non mappées
    # (Indeed, JobTeaser, Glassdoor, Studyrama, etc. — peut échouer si anti-bot)
    try:
        return get_scraper("generic")
    except KeyError:
        return None


@dataclass
class EnrichResult:
    total_candidates: int
    updated: int
    failed: int
    skipped_no_scraper: int


def enrich_descriptions(
    *,
    source: str | None = None,
    limit: int | None = None,
    sleep_between: float = 1.0,
) -> EnrichResult:
    """Re-fetche les descriptions manquantes pour les offres déjà en DB.

    Sélectionne `description IS NULL AND url IS NOT NULL`, filtre par `source`
    si fourni. Dispatch sur le scraper correspondant à chaque source.

    Args:
        source: filtre sur la colonne offers.source (ex "Hellowork"). None = toutes.
        limit: max d'offres à enrichir (None = toutes les candidates).
        sleep_between: pause entre 2 requêtes (politesse).
    """
    where = ["(description IS NULL OR description = '')", "url IS NOT NULL", "url != ''"]
    params: list = []
    if source:
        where.append("LOWER(source) LIKE LOWER(?)")
        params.append(f"{source}%")
    sql = f"SELECT id, url, source FROM offers WHERE {' AND '.join(where)} ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"

    with db() as conn:
        candidates = [dict(r) for r in conn.execute(sql, params).fetchall()]

    scraper_cache: dict[str, Scraper] = {}
    updated = 0
    failed = 0
    skipped = 0
    for i, off in enumerate(candidates, 1):
        src = (off["source"] or "").lower().strip()
        if src not in scraper_cache:
            scraper = _scraper_for_source(src)
            if scraper is None:
                skipped += 1
                continue
            scraper_cache[src] = scraper
        scraper = scraper_cache[src]
        try:
            desc = scraper.fetch_detail(off["url"])
        except Exception:  # noqa: BLE001
            failed += 1
            continue
        if desc:
            queries.update_description(off["id"], desc)
            updated += 1
        else:
            failed += 1
        if i < len(candidates):
            polite_sleep(sleep_between)

    return EnrichResult(
        total_candidates=len(candidates),
        updated=updated,
        failed=failed,
        skipped_no_scraper=skipped,
    )
