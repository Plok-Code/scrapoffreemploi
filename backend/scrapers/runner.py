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


# --- Suppression auto des offres mortes sans statut user ---

@dataclass
class CleanupResult:
    total_checked: int
    deleted: int            # URL morte + status NULL → supprimé
    archived: int           # URL morte mais status renseigné → archived seulement
    inconclusive: int       # 403/timeout → on touche pas
    still_alive: int


def cleanup_dead_unstatused(
    *,
    min_score: int | None = None,
    sleep_between: float = 0.5,
    limit: int | None = None,
) -> CleanupResult:
    """Ping chaque URL et SUPPRIME les offres mortes sans statut user.

    Règle métier :
    - URL morte (404/410/soft-404) + `status IS NULL` → DELETE de la DB
    - URL morte + `status IS NOT NULL` → garder mais marquer `is_active=0`
      (l'user a postulé ou a une trace utile)
    - URL vivante → marquer `is_active=1`
    - URL 403/timeout → on ne touche pas

    Returns:
        Stats du nettoyage.
    """
    where = ["url IS NOT NULL", "url != ''"]
    params: list = []
    if min_score is not None:
        where.append("match_score >= ?")
        params.append(min_score)
    sql = f"SELECT id, url, status FROM offers WHERE {' AND '.join(where)} ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"

    with db() as conn:
        candidates = [dict(r) for r in conn.execute(sql, params).fetchall()]

    deleted = 0
    archived = 0
    alive = 0
    inconclusive = 0
    with httpx.Client(
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(15.0, connect=8.0),
        follow_redirects=True,
    ) as client:
        for i, off in enumerate(candidates, 1):
            url = off["url"]
            has_status = bool(off["status"])
            is_dead = False

            # Workday-specific check d'abord
            wd_verdict = _probe_workday_api(url, client)
            if wd_verdict is False:
                is_dead = True
            elif wd_verdict is True:
                pass  # alive
            else:
                # HTTP check
                try:
                    resp = client.get(url)
                except Exception:  # noqa: BLE001
                    inconclusive += 1
                    if i < len(candidates):
                        polite_sleep(sleep_between)
                    continue

                if resp.status_code in _ARCHIVED_STATUS:
                    is_dead = True
                elif resp.status_code in _INCONCLUSIVE_STATUS:
                    inconclusive += 1
                    if i < len(candidates):
                        polite_sleep(sleep_between)
                    continue
                elif 200 <= resp.status_code < 400:
                    if _is_soft_404(resp.text, original_url=url, final_url=str(resp.url)):
                        is_dead = True
                else:
                    inconclusive += 1
                    if i < len(candidates):
                        polite_sleep(sleep_between)
                    continue

            if is_dead:
                if has_status:
                    queries.set_alive_state(off["id"], is_active=False)
                    archived += 1
                else:
                    queries.delete_offer(off["id"])
                    deleted += 1
            else:
                queries.set_alive_state(off["id"], is_active=True)
                alive += 1

            if i < len(candidates):
                polite_sleep(sleep_between)

    return CleanupResult(
        total_checked=len(candidates),
        deleted=deleted,
        archived=archived,
        inconclusive=inconclusive,
        still_alive=alive,
    )


# --- Scrape global : toutes les sources + cleanup + scoring auto ---

@dataclass
class FullScrapeResult:
    cleanup: CleanupResult | None
    per_source: dict[str, ScrapeResult]
    portals_attempted: int
    portals_offers_inserted: int
    non_alternance_removed: int   # delete + archive après filtre
    total_new: int
    scoring_applied: int


def run_full_scrape(
    *,
    sources: list[str] | None = None,
    max_pages: int = 5,
    do_cleanup: bool = True,
    do_auto_score: bool = True,
    do_portals: bool = True,
    use_playwright_fallback: bool = False,
) -> FullScrapeResult:
    """Lance un scrape multi-source complet : cleanup → job boards → portails entreprises → scoring auto.

    Args:
        sources: liste des scrapers de job boards. None = tous (FT+WTTJ+HW).
        max_pages: pages max par mot-clé pour chaque source.
        do_cleanup: si True, ping URLs existantes ; supprime celles mortes+sans statut, archive les autres.
        do_auto_score: si True, lance le heuristic scorer sur les nouvelles offres.
        do_portals: si True, scrape aussi les portails de chaque target_company avec source_url.
        use_playwright_fallback: si True, lance Playwright sur les portails SPA sans API (lent).
    """
    from backend.scrapers.registry import list_scrapers

    if sources is None:
        sources = [s for s in list_scrapers() if s != "generic"]

    cleanup_result: CleanupResult | None = None
    if do_cleanup:
        cleanup_result = cleanup_dead_unstatused(sleep_between=0.3)

    per_source: dict[str, ScrapeResult] = {}
    total_new = 0
    for src in sources:
        try:
            r = run_scrape(src, max_pages=max_pages, generate_batch=False)
            per_source[src] = r
            total_new += r.total_new
        except Exception as e:  # noqa: BLE001
            per_source[src] = ScrapeResult(
                source=src, total_fetched=0, total_new=0,
                total_duplicates=0, batch_file=None, new_ids=[],
            )
            queries.record_scrape_run(
                sources=src, total_fetched=0, total_new=0,
                total_duplicates=0, error=str(e),
            )

    # Scrape des portails entreprises (Workable / Lever / Workday / best-effort)
    portals_attempted = 0
    portals_inserted = 0
    if do_portals:
        from backend.scrapers.company_portals import scrape_target_company_portals
        try:
            pr = scrape_target_company_portals(
                sleep_between=0.8,
                use_playwright_fallback=use_playwright_fallback,
            )
            portals_attempted = pr.portals_attempted
            portals_inserted = pr.new_offers_inserted
            total_new += pr.new_offers_inserted
        except Exception as e:  # noqa: BLE001
            queries.record_scrape_run(
                sources="portails-entreprises", total_fetched=0, total_new=0,
                total_duplicates=0, error=str(e),
            )

    # Filtre non-alternance : delete/archive les offres CDI/CDD/stage seul/senior/etc.
    # Appliqué après les scrapes pour rattraper les faux positifs (FT renvoie parfois
    # des CDI Senior malgré natureContrat=E1,E2).
    from backend.filter_alternance import filter_non_alternance_offers
    filter_result = filter_non_alternance_offers()
    non_alternance_removed = filter_result["reject_deleted"] + filter_result["reject_archived"]

    scoring_applied = 0
    if do_auto_score and total_new > 0:
        from backend.heuristic_scorer import apply_heuristic_to_unscored
        result = apply_heuristic_to_unscored()
        scoring_applied = result["updated"]

    return FullScrapeResult(
        cleanup=cleanup_result,
        per_source=per_source,
        portals_attempted=portals_attempted,
        portals_offers_inserted=portals_inserted,
        non_alternance_removed=non_alternance_removed,
        total_new=total_new,
        scoring_applied=scoring_applied,
    )
