"""App FastAPI : routes web + Jinja templates."""
from __future__ import annotations

from contextlib import asynccontextmanager
from math import ceil
from pathlib import Path
from threading import Lock
from typing import Annotated, Any

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BeforeValidator
from starlette.middleware.base import BaseHTTPMiddleware

from backend import queries
from backend._logging import init_logging, logger
from backend.db import init_schema
from backend.models import (
    VALID_COMPANY_STATUSES,
    VALID_PRIORITIES,
    VALID_REMOTE,
    VALID_STATUSES,
)


def _empty_str_to_none(v: Any) -> Any:
    """Convertit "" (chaîne vide HTML form) en None avant validation Pydantic.

    Sans ça, un GET `/?min_score=` (input number vide submit) fait crasher
    FastAPI en 422 `int_parsing` car il essaie `int("")`. Avec ce validator,
    `""` devient `None` puis Pydantic accepte (Optional[int]).
    """
    return None if v == "" else v


# Type réutilisable pour les query params int optionnels qui doivent accepter
# la chaîne vide depuis un form HTML.
OptionalIntFromForm = Annotated[int | None, BeforeValidator(_empty_str_to_none)]

# Init du logging dès le module import (avant tout autre log)
init_logging(level="INFO")

BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan handler (remplace @app.on_event 'startup' déprécié).

    Au démarrage :
    1. init_schema() : crée les tables + migre les colonnes (idempotent)
    2. Reset _SCRAPE_STATE.running : si le serveur précédent a été tué pendant
       un scrape, l'état RAM en arrière-plan est mort avec lui — on évite le
       'running=True' fantôme qui bloque tout nouveau scrape.
    Shutdown : rien à nettoyer (uvicorn ferme les sockets, sqlite ferme via
    context manager `db()` de chaque request).
    """
    init_schema()
    if _SCRAPE_STATE.get("running"):
        logger.warning(
            "Reset _SCRAPE_STATE au boot : un scrape était marqué 'running' "
            "(probablement tué avec le serveur précédent)"
        )
    _SCRAPE_STATE["running"] = False
    _SCRAPE_STATE["step"] = "idle"
    yield
    # rien à faire au shutdown


app = FastAPI(title="Scrap'Offre Emploi", docs_url="/api/docs", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _safe_href(url: str | None) -> str:
    """Filtre Jinja : retourne `url` si http(s)://, sinon `#`.

    Défense en profondeur : même si une URL avec schéma dangereux (javascript:,
    data:, file:) arrive en DB depuis un vieux scrape, elle ne sera pas rendue
    en clickable. Utiliser dans les templates : `{{ offer.url | safe_href }}`.
    """
    if not url:
        return "#"
    url = str(url).strip()
    lo = url.lower()
    if lo.startswith("http://") or lo.startswith("https://"):
        return url
    return "#"


templates.env.filters["safe_href"] = _safe_href


# --- CSRF light : check Origin/Referer sur les routes mutantes ---

# Origins acceptés pour les requêtes mutantes (POST/PATCH/PUT/DELETE).
# L'app bind sur 127.0.0.1:8000, donc seules ces origins doivent valider.
_ALLOWED_ORIGINS = {
    "http://127.0.0.1:8000",
    "http://localhost:8000",
}


class CSRFOriginMiddleware(BaseHTTPMiddleware):
    """Bloque les POST/PATCH/PUT/DELETE qui viennent d'une origin externe.

    Protection légère contre les "CSRF via page web malveillante visitée
    localement qui tente un POST localhost:8000".

    Règle :
    - GET/HEAD/OPTIONS : passent toujours
    - Mutants sans `Origin` ni `Referer` : passent (HTMX / curl en CLI / Swagger UI)
    - Mutants avec `Origin` : doit être dans `_ALLOWED_ORIGINS`
    - Mutants avec `Referer` : doit pointer vers une origin allowed
    """

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        if method in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)
        origin = request.headers.get("origin", "").rstrip("/")
        if origin:
            if origin not in _ALLOWED_ORIGINS:
                logger.warning(
                    "CSRF block : {m} {p} origin={o}",
                    m=method, p=request.url.path, o=origin,
                )
                return JSONResponse(
                    {"detail": f"Origin '{origin}' non autorisée pour les mutations."},
                    status_code=403,
                )
            return await call_next(request)
        # Pas d'Origin : on regarde Referer
        referer = request.headers.get("referer", "")
        if referer:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            ref_origin = f"{parsed.scheme}://{parsed.netloc}"
            if ref_origin not in _ALLOWED_ORIGINS:
                logger.warning(
                    "CSRF block : {m} {p} referer={r}",
                    m=method, p=request.url.path, r=referer,
                )
                return JSONResponse(
                    {"detail": f"Referer '{ref_origin}' non autorisée pour les mutations."},
                    status_code=403,
                )
        # Ni Origin ni Referer : on accepte (curl, Swagger UI, scripts CLI)
        return await call_next(request)


app.add_middleware(CSRFOriginMiddleware)


# ---------- Pages ----------

@app.get("/", response_class=HTMLResponse)
def page_offers(
    request: Request,
    search: str = "",
    status: str = "",
    source: str = "",
    min_score: OptionalIntFromForm = None,
    only_to_apply: bool = False,
    include_archived: bool = False,
    sort: str = "score_desc",
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=25, le=500),
):
    total_offers = queries.count_offers(
        search=search,
        status=status,
        source=source,
        min_score=min_score,
        only_to_apply=only_to_apply,
        include_archived=include_archived,
    )
    total_pages = max(1, ceil(total_offers / per_page))
    page = min(page, total_pages)
    offers = queries.list_offers(
        search=search,
        status=status,
        source=source,
        min_score=min_score,
        only_to_apply=only_to_apply,
        include_archived=include_archived,
        sort=sort,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    stats = queries.get_stats()
    sources = queries.list_sources()
    return templates.TemplateResponse(
        request,
        "offers.html",
        {
            "request": request,
            "offers": offers,
            "stats": stats,
            "sources": sources,
            "statuses": VALID_STATUSES,
            "filters": {
                "search": search,
                "status": status,
                "source": source,
                "min_score": min_score,
                "only_to_apply": only_to_apply,
                "include_archived": include_archived,
                "sort": sort,
            },
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_offers,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages,
            },
            "page": "offers",
        },
    )


@app.get("/offers/{offer_id}", response_class=HTMLResponse)
def page_offer_detail(request: Request, offer_id: int):
    offer = queries.get_offer(offer_id)
    if not offer:
        raise HTTPException(404, "Offre introuvable")
    return templates.TemplateResponse(
        request,
        "offer_detail.html",
        {
            "offer": offer,
            "statuses": VALID_STATUSES,
            "priorities": VALID_PRIORITIES,
            "remotes": VALID_REMOTE,
            "page": "offer_detail",
        },
    )


@app.post("/offers/{offer_id}")
def update_offer_route(
    offer_id: int,
    status: str = Form(""),
    application_method: str = Form(""),
    date_applied: str = Form(""),
    date_followup: str = Form(""),
    date_interview: str = Form(""),
    notes: str = Form(""),
    priority: str = Form(""),
    remote: str = Form(""),
):
    try:
        ok = queries.update_offer(
            offer_id,
            {
                "status": status,
                "application_method": application_method,
                "date_applied": date_applied,
                "date_followup": date_followup,
                "date_interview": date_interview,
                "notes": notes,
                "priority": priority,
                "remote": remote,
            },
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not ok:
        raise HTTPException(404, "Offre introuvable ou aucun champ à mettre à jour")
    return RedirectResponse(f"/offers/{offer_id}", status_code=303)


# ---------- Pages Entreprises ----------

@app.get("/companies", response_class=HTMLResponse)
def page_companies(
    request: Request,
    search: str = "",
    priority: str = "",
    status: str = "",
    city: str = "",
    other_haute: bool = False,
    sort: str = "priority",
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=25, le=500),
):
    total_companies = queries.count_target_companies(
        search=search, priority=priority, status=status,
        city=city, other_haute=other_haute,
    )
    total_pages = max(1, ceil(total_companies / per_page))
    page = min(page, total_pages)
    companies = queries.list_target_companies(
        search=search, priority=priority, status=status,
        city=city, other_haute=other_haute, sort=sort,
        limit=per_page, offset=(page - 1) * per_page,
    )
    stats = queries.get_company_stats()
    priorities = queries.list_company_priorities()
    cities = queries.list_company_cities()
    target_cities = queries.count_companies_per_target_city()
    other_haute_count = queries.count_other_haute()
    return templates.TemplateResponse(
        request,
        "companies.html",
        {
            "request": request,
            "companies": companies,
            "stats": stats,
            "priorities": priorities,
            "cities": cities,
            "target_cities": target_cities,
            "other_haute_count": other_haute_count,
            "statuses": VALID_COMPANY_STATUSES,
            "filters": {
                "search": search,
                "priority": priority,
                "status": status,
                "city": city,
                "other_haute": other_haute,
                "sort": sort,
            },
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_companies,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages,
            },
            "page": "companies",
        },
    )


@app.get("/companies/{company_id}", response_class=HTMLResponse)
def page_company_detail(request: Request, company_id: int):
    company = queries.get_target_company(company_id)
    if not company:
        raise HTTPException(404, "Entreprise introuvable")
    return templates.TemplateResponse(
        request,
        "company_detail.html",
        {
            "company": company,
            "statuses": VALID_COMPANY_STATUSES,
            "priorities": VALID_PRIORITIES,
            "page": "company_detail",
        },
    )


@app.post("/companies/{company_id}")
def update_company_route(
    company_id: int,
    status: str = Form(""),
    date_contacted: str = Form(""),
    date_followup: str = Form(""),
    notes: str = Form(""),
    feedback: str = Form(""),
    priority: str = Form(""),
):
    try:
        ok = queries.update_target_company(
            company_id,
            {
                "status": status,
                "date_contacted": date_contacted,
                "date_followup": date_followup,
                "notes": notes,
                "feedback": feedback,
                "priority": priority,
            },
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not ok:
        raise HTTPException(404, "Entreprise introuvable ou aucun champ à mettre à jour")
    return RedirectResponse(f"/companies/{company_id}", status_code=303)


# ---------- API JSON ----------

@app.get("/api/stats")
def api_stats():
    return queries.get_stats()


@app.patch("/api/offers/{offer_id}")
def api_update_offer(offer_id: int, payload: dict):
    try:
        ok = queries.update_offer(offer_id, payload)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not ok:
        raise HTTPException(404, "Offre introuvable")
    return {"ok": True}


@app.post("/api/offers/{offer_id}/status")
def api_set_offer_status(offer_id: int, status: str = Form("")):
    """Toggle rapide du statut depuis la liste (form-encoded, compatible HTMX).

    `status=""` (vide) remet l'offre en `status=NULL` (= À postuler).
    """
    try:
        ok = queries.update_offer(offer_id, {"status": status})
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not ok:
        raise HTTPException(404, "Offre introuvable")
    return {"ok": True, "offer_id": offer_id, "status": status or None}


# ---------- API Scraping ----------

# État du scraping en cours (in-memory, lifecycle = uvicorn worker)
_SCRAPE_STATE: dict = {
    "running": False,
    "source": None,
    "started_at": None,
    "finished_at": None,
    "total_fetched": 0,
    "total_new": 0,
    "total_duplicates": 0,
    "error": None,
}
_SCRAPE_STATE_LOCK = Lock()


def _queue_scrape_or_409(source_label: str) -> None:
    """Marque un scrape comme réservé avant que BackgroundTasks ne démarre.

    Sans cette réservation synchrone, deux POST très proches peuvent tous les deux
    voir `running=False` avant que la tâche background ne pose `running=True`.
    """
    from datetime import datetime

    with _SCRAPE_STATE_LOCK:
        if _SCRAPE_STATE["running"]:
            raise HTTPException(409, f"Un scrape '{_SCRAPE_STATE.get('source')}' est déjà en cours.")
        _SCRAPE_STATE.update({
            "running": True,
            "source": source_label,
            "step": "queued",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
            "total_fetched": 0,
            "total_new": 0,
            "total_duplicates": 0,
            "deleted_dead": 0,
            "archived_dead": 0,
            "scoring_applied": 0,
            "error": None,
        })


def _run_scrape_bg(source: str, max_pages: int) -> None:
    """Tâche d'arrière-plan : scrape d'une seule source."""
    from datetime import datetime

    from backend.scrapers.runner import run_scrape

    _SCRAPE_STATE.update({
        "running": True,
        "source": source,
        "step": "scraping",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "total_fetched": 0,
        "total_new": 0,
        "total_duplicates": 0,
        "deleted_dead": 0,
        "scoring_applied": 0,
        "error": None,
    })
    try:
        result = run_scrape(source, max_pages=max_pages)
        _SCRAPE_STATE.update({
            "total_fetched": result.total_fetched,
            "total_new": result.total_new,
            "total_duplicates": result.total_duplicates,
        })
    except Exception as e:  # noqa: BLE001
        # Le traceback complet va dans data/logs/errors.log (loguru backtrace=True).
        # _SCRAPE_STATE garde juste le message court pour l'affichage UI.
        logger.opt(exception=True).warning(
            "Scrape background failed : source={s} err={err}",
            s=source, err=str(e),
        )
        _SCRAPE_STATE["error"] = str(e)
    finally:
        _SCRAPE_STATE["running"] = False
        _SCRAPE_STATE["step"] = "done"
        _SCRAPE_STATE["finished_at"] = datetime.now().isoformat(timespec="seconds")


def _run_full_scrape_bg(
    max_pages: int,
    use_playwright: bool = False,
    generate_batch: bool = False,
) -> None:
    """Tâche d'arrière-plan : scrape complet + cleanup + filtre + scoring auto.

    Étapes :
    1. Cleanup URLs existantes (404/soft-404 → archive)
    2. Job boards : FT + WTTJ + HelloWork (séquentiel, dédup auto)
    3. Portails entreprises : Workable/Lever/Workday/Greenhouse + best-effort
       (+ Playwright si use_playwright=True, sur les SPAs sans API)
    4. Filtre non-alternance (CDI/Senior/stage seul → archive)
    5. Heuristic scoring auto sur les nouvelles offres
    6. Si `generate_batch=True` : écrit `data/batches/{date}_to_score.json`
       avec les nouvelles offres pour scoring LLM manuel via chat.
    """
    from datetime import datetime

    from backend.scrapers.runner import run_full_scrape

    _SCRAPE_STATE.update({
        "running": True,
        "source": "ALL (FT+WTTJ+HW+portails)" + (" + Playwright" if use_playwright else ""),
        "step": "starting",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "total_fetched": 0,
        "total_new": 0,
        "total_duplicates": 0,
        "deleted_dead": 0,
        "archived_dead": 0,
        "scoring_applied": 0,
        "per_source": {},
        "playwright_enabled": use_playwright,
        "batch_file": None,
        "error": None,
    })
    try:
        _SCRAPE_STATE["step"] = "cleanup (ping URLs existantes)"
        result = run_full_scrape(
            max_pages=max_pages,
            do_cleanup=True,
            do_auto_score=True,
            do_portals=True,
            use_playwright_fallback=use_playwright,
            generate_batch=generate_batch,
        )
        cleanup = result.cleanup
        per_source_summary = {
            src: {
                "fetched": r.total_fetched,
                "new": r.total_new,
                "dup": r.total_duplicates,
            }
            for src, r in result.per_source.items()
        }
        _SCRAPE_STATE.update({
            "step": "done",
            "total_fetched": sum(r.total_fetched for r in result.per_source.values()),
            "total_new": result.total_new,
            "total_duplicates": sum(r.total_duplicates for r in result.per_source.values()),
            "deleted_dead": cleanup.deleted if cleanup else 0,
            "archived_dead": cleanup.archived if cleanup else 0,
            "portals_attempted": result.portals_attempted,
            "portals_offers_inserted": result.portals_offers_inserted,
            "non_alternance_removed": result.non_alternance_removed,
            "scoring_applied": result.scoring_applied,
            "per_source": per_source_summary,
            "batch_file": result.batch_file,
        })
    except Exception as e:  # noqa: BLE001
        # Le traceback complet va dans data/logs/errors.log (loguru backtrace=True).
        # _SCRAPE_STATE garde juste le message court pour l'affichage UI.
        logger.opt(exception=True).warning(
            "Full scrape background failed : err={err}", err=str(e),
        )
        _SCRAPE_STATE["error"] = str(e)
    finally:
        _SCRAPE_STATE["running"] = False
        _SCRAPE_STATE["finished_at"] = datetime.now().isoformat(timespec="seconds")


@app.post("/api/scrape")
def api_scrape(
    bg: BackgroundTasks,
    source: str = Form(...),
    max_pages: int = Form(3, ge=1, le=30),
    use_playwright: bool = Form(False),
    generate_batch: bool = Form(False),
):
    """Lance un scrape en arrière-plan.

    `source=all` ou `source=ALL` lance un scrape multi-source complet.
    `max_pages` : 1-30 (FastAPI valide via `ge`/`le`, retourne 422 si hors borne).
    `use_playwright=True` active le fallback Playwright pour les SPAs React
    (Capgemini, Airbus, Atos, etc.) — lent (~30s par portail SPA).
    `generate_batch=True` (mode 'all' uniquement) écrit en plus
    `data/batches/{date}_to_score.json` avec les nouvelles offres pour scoring
    LLM manuel via chat. Par défaut False — le scoring heuristique auto suffit.
    Statut via GET /api/scrape/status (champ `batch_file` si batch généré).
    """
    from backend.scrapers.registry import list_scrapers

    if source.lower() == "all":
        label = "ALL (FT+WTTJ+HW+portails)" + (" + Playwright" if use_playwright else "")
        _queue_scrape_or_409(label)
        bg.add_task(_run_full_scrape_bg, max_pages, use_playwright, generate_batch)
        return {
            "ok": True, "source": "ALL", "max_pages": max_pages,
            "playwright": use_playwright, "generate_batch": generate_batch,
        }

    available = set(list_scrapers())
    if source not in available:
        raise HTTPException(400, f"Source inconnue : {source}. Dispo : {sorted(available)}")
    _queue_scrape_or_409(source)
    bg.add_task(_run_scrape_bg, source, max_pages)
    return {"ok": True, "source": source, "max_pages": max_pages}


@app.get("/api/scrape/status")
def api_scrape_status():
    """Renvoie l'état du scrape en cours (ou du dernier)."""
    return _SCRAPE_STATE


@app.post("/api/scrape/reset")
def api_scrape_reset():
    """Reset manuel de l'état scrape (escape-hatch si bloqué sur 'running').

    À utiliser si un scrape a planté silencieusement et que `_SCRAPE_STATE['running']`
    est resté à True. Le boot reset auto déjà au démarrage, mais cette route
    permet de forcer sans redémarrer le serveur.
    """
    with _SCRAPE_STATE_LOCK:
        was_running = _SCRAPE_STATE.get("running", False)
        _SCRAPE_STATE["running"] = False
        _SCRAPE_STATE["step"] = "reset (manual)"
        _SCRAPE_STATE["error"] = "Reset manuel par utilisateur"
    logger.warning("Reset manuel de _SCRAPE_STATE (was_running={r})", r=was_running)
    return {"ok": True, "was_running": was_running}


# ---------- API Toulouse / Companies extraction ----------

@app.post("/api/companies/import-from-offers")
def api_import_companies_from_offers(city: str = Form(...)):
    """Importe en `target_companies` les entreprises distinctes des offres pour
    une ville donnée (ex Toulouse). Permet d'enrichir la liste de cibles
    candidature spontanée."""
    result = queries.import_companies_from_offers_to_targets(city_substr=city, min_score=0)
    return result
