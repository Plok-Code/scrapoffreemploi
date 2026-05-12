"""Orchestrateur de scraping : lance un scraper, insère en DB, génère le batch."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from backend import matching, queries
from backend.db import db
from backend.scrapers._http import DEFAULT_HEADERS, polite_sleep
from backend.scrapers.base import RawOffer, Scraper
from backend.scrapers.registry import get_scraper

# Mots-clés de recherche par défaut.
# Note : pour France Travail le filtre contrat est déjà côté serveur (natureContrat=E1,E2)
# donc on n'a pas besoin de mettre "alternance" devant — au contraire ça réduit les hits.
# Pour HelloWork / WTTJ on garde "alternance" car la recherche y est full-text.
DEFAULT_SEARCH_KEYWORDS = [
    "intelligence artificielle",
    "machine learning",
    "data scientist",
    "MLOps",
    "AI engineer",
    "deep learning",
    "data engineer",
    "LLM",
    "NLP",
    "computer vision",
    "MLOps engineer",
    "ML engineer",
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


# --- Vérification "URL toujours vivante" ---

@dataclass
class AliveCheckResult:
    total_checked: int
    still_alive: int
    archived_http: int       # 404/410 explicites
    archived_soft: int       # HTTP 200 mais contenu "offre supprimée"
    inconclusive: int

    @property
    def archived(self) -> int:
        return self.archived_http + self.archived_soft


# Statuts considérés comme "offre supprimée définitivement"
_ARCHIVED_STATUS = {404, 410}
# Statuts ambigus (403 anti-bot, 5xx temporaires) → on ne marque PAS archived
_INCONCLUSIVE_STATUS = {401, 403, 429, 500, 502, 503, 504}

# Patterns regex (sur body en minuscules) qui indiquent un "soft 404" :
# le serveur renvoie 200 mais l'offre est en réalité supprimée.
# Ordre = du plus spécifique au plus générique.
import re as _re
_SOFT_404_PATTERNS = [
    _re.compile(p, _re.IGNORECASE) for p in [
        r"cette offre n[''e]?\s*est plus disponible",
        r"cette offre n[''e]?\s*existe plus",
        r"offre n[''e]?\s*est plus disponible",
        r"offre n[''e]?\s*est plus dispo",
        r"this job is no longer available",
        r"this position is no longer available",
        r"this job posting is no longer",
        r"la page que vous recherchez n[''e]?\s*existe pas",
        r"page introuvable",
        r"page non trouv[ée]e",
        r"nous avons perdu cette page",
        r"oops[!,]\s*page not found",
        r"offre introuvable",
        r"offre expir[ée]e",
        r"poste pourvu",
        r"this position has been filled",
        # Workable : quand un job_shortcode n'existe plus, redirect vers la liste de jobs
        r"job openings.*hot tip.*unclick your automatically detected location",
        # Renault Workday : message exact
        r"careers\s*\|\s*renault group\s*la page que vous recherchez",
    ]
]

# Indicateurs de "redirigé vers une page liste / recherche" (présents souvent quand
# une URL d'offre individuelle n'existe plus et le site renvoie sa home des offres).
_REDIRECT_TO_LIST_PATTERNS = [
    _re.compile(p, _re.IGNORECASE | _re.DOTALL) for p in [
        r"\b(\d{2,4})\s*offres?\s*correspondent",            # Studyrama "17 offres correspondent"
        r"votre recherche.*?\d{2,4}\s*offres?",              # AXA "Votre recherche... 663 offres"
        r"affinez votre recherche",                           # AXA / autres listings
        r"r[ée]sultats?\s*de\s*la\s*recherche",              # Studyrama "Résultats de la recherche"
        r"resultats?_recherche",                              # Studyrama class CSS
    ]
]

# Patterns dans le <title> qui indiquent une offre supprimée.
_TITLE_DEAD_PATTERNS = [
    _re.compile(p, _re.IGNORECASE) for p in [
        r"erreur.*inexistante",          # CEA "Erreur - Offre demandée inexistante"
        r"offre\s+inexistante",
        r"offre\s+introuvable",
        r"offre\s+expir[ée]e",
        r"current openings",             # Workable redirect vers liste génération
        r"\bnos\s+offres?\s+d['e]?emploi$",  # AXA "Recrutement AXA en France. Nos offres d'emploi"
        r"page not found",
        r"404\b",
    ]
]

# Patterns dans l'URL finale (après redirects) qui indiquent un soft 404.
_FINAL_URL_DEAD_PATTERNS = [
    _re.compile(p, _re.IGNORECASE) for p in [
        r"[?&]not_found=true\b",          # Workable
        r"[?&]error=",
        r"/404\b",
        r"/error\b",
        r"/expired\b",
        r"trk=expired_jd_redirect",       # LinkedIn
    ]
]


def _probe_workday_api(detail_url: str, client: httpx.Client) -> bool | None:
    """Pour les URLs Workday (SPAs purs), hit l'API JSON pour le vrai statut.

    Returns: True=alive, False=dead (404), None=URL non-Workday ou indéterminé.
    """
    m = _re.match(
        r"https://([^.]+)\.([^.]+)\.myworkdayjobs\.com/([^/]+)/([^/]+)/job/[^/]+/([^/]+)",
        detail_url,
    )
    if not m:
        return None
    tenant, _server, _lang, site, slug_id = m.groups()
    mj = _re.search(r"_(JOBREQ_\d+)", slug_id, _re.IGNORECASE)
    if not mj:
        return None
    job_id = mj.group(1)
    api_url = f"https://{tenant}.wd3.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{job_id}"
    try:
        r = client.get(api_url, headers={"Accept": "application/json"})
        if r.status_code == 404:
            return False
        if 200 <= r.status_code < 300:
            return True
    except Exception:  # noqa: BLE001
        return None
    return None


def _title_text(html: str) -> str | None:
    """Extrait le contenu de <title>...</title> sans bs4 (rapide)."""
    m = _re.search(r"<title[^>]*>([^<]+)</title>", html, _re.IGNORECASE)
    if not m:
        return None
    # Décode les entités HTML basiques
    return m.group(1).replace("&#x27;", "'").replace("&amp;", "&").strip()


def _is_soft_404(html: str, *, original_url: str, final_url: str) -> bool:
    """Retourne True si la page (HTTP 200) est en fait une offre supprimée.

    Détecte via 4 signaux :
    1. Body contient explicitement "offre n'est plus disponible" etc.
    2. Body contient un "redirect to listing" (ex : "17 offres correspondent").
    3. Le <title> indique une erreur (ex : "Erreur - Offre inexistante", "404").
    4. L'URL finale contient `?not_found=true`, `/404`, etc.
    """
    if not html:
        return False
    sample = html[:50000]

    # 4. URL finale changée → marqueur explicite
    if original_url != final_url:
        for pat in _FINAL_URL_DEAD_PATTERNS:
            if pat.search(final_url):
                return True
        # Heuristique : redirect d'une URL longue (offre individuelle) vers une URL
        # significativement plus courte (probable redirect vers la liste/home)
        # → on ne déclenche que si la URL finale est < 50% de l'originale.
        if len(final_url) < len(original_url) * 0.5:
            return True

    # 3. Title
    title = _title_text(html)
    if title:
        for pat in _TITLE_DEAD_PATTERNS:
            if pat.search(title):
                return True

    # 1 & 2. Body
    for pat in _SOFT_404_PATTERNS:
        if pat.search(sample):
            return True
    for pat in _REDIRECT_TO_LIST_PATTERNS:
        if pat.search(sample):
            return True
    return False


def check_alive(
    *,
    only_unscored_or_scored: bool = True,
    min_score: int | None = None,
    sleep_between: float = 0.8,
    limit: int | None = None,
) -> AliveCheckResult:
    """Ping chaque URL des offres et marque is_active=0 sur les 404/410 et soft 404.

    Détecte 2 types d'offres mortes :
    - **Hard 404/410** : code HTTP explicite.
    - **Soft 404** : code 200 mais body contient "offre supprimée", "no longer
      available", ou redirection vers une page de liste générique (Workable,
      AXA recrutement, Studyrama, Workday Renault, etc.).

    Args:
        min_score: ne checker que les offres avec score >= min_score.
        sleep_between: pause entre 2 requêtes.
        limit: max d'offres à pinguer.
    """
    where = ["url IS NOT NULL", "url != ''", "(is_active IS NULL OR is_active = 1)"]
    params: list = []
    if min_score is not None:
        where.append("match_score >= ?")
        params.append(min_score)
    sql = f"SELECT id, url FROM offers WHERE {' AND '.join(where)} ORDER BY match_score DESC NULLS LAST, id"
    if limit:
        sql += f" LIMIT {int(limit)}"

    with db() as conn:
        candidates = [dict(r) for r in conn.execute(sql, params).fetchall()]

    archived_http = 0
    archived_soft = 0
    alive = 0
    inconclusive = 0
    with httpx.Client(
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(15.0, connect=8.0),
        follow_redirects=True,
    ) as client:
        for i, off in enumerate(candidates, 1):
            url = off["url"]

            # Cas spécial : Workday est un SPA pur, le HTML ne dit rien.
            # On va directement sur l'API JSON pour confirmer.
            workday_verdict = _probe_workday_api(url, client)
            if workday_verdict is False:
                queries.set_alive_state(off["id"], is_active=False)
                archived_soft += 1
                if i < len(candidates):
                    polite_sleep(sleep_between)
                continue
            if workday_verdict is True:
                queries.set_alive_state(off["id"], is_active=True)
                alive += 1
                if i < len(candidates):
                    polite_sleep(sleep_between)
                continue

            try:
                resp = client.get(url)
                status = resp.status_code
            except Exception:  # noqa: BLE001
                inconclusive += 1
                continue
            if status in _ARCHIVED_STATUS:
                queries.set_alive_state(off["id"], is_active=False)
                archived_http += 1
            elif status in _INCONCLUSIVE_STATUS:
                inconclusive += 1
            elif 200 <= status < 400:
                # 200 mais peut-être un soft 404 — on regarde body + title + URL finale
                if _is_soft_404(resp.text, original_url=url, final_url=str(resp.url)):
                    queries.set_alive_state(off["id"], is_active=False)
                    archived_soft += 1
                else:
                    queries.set_alive_state(off["id"], is_active=True)
                    alive += 1
            else:
                inconclusive += 1
            if i < len(candidates):
                polite_sleep(sleep_between)

    return AliveCheckResult(
        total_checked=len(candidates),
        still_alive=alive,
        archived_http=archived_http,
        archived_soft=archived_soft,
        inconclusive=inconclusive,
    )
