"""App FastAPI : routes web + Jinja templates."""
from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend import queries
from backend.db import init_schema
from backend.models import (
    VALID_COMPANY_STATUSES,
    VALID_PRIORITIES,
    VALID_REMOTE,
    VALID_STATUSES,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Scrap'Offre Emploi", docs_url="/api/docs")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def _startup() -> None:
    """S'assure que le schéma existe."""
    init_schema()


# ---------- Pages ----------

@app.get("/", response_class=HTMLResponse)
def page_offers(
    request: Request,
    search: str = "",
    status: str = "",
    source: str = "",
    min_score: int | None = None,
    only_to_apply: bool = False,
    include_archived: bool = False,
    sort: str = "score_desc",
):
    offers = queries.list_offers(
        search=search,
        status=status,
        source=source,
        min_score=min_score,
        only_to_apply=only_to_apply,
        include_archived=include_archived,
        sort=sort,
    )
    stats = queries.get_stats()
    sources = queries.list_sources()
    return templates.TemplateResponse(
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
            "page": "offers",
        },
    )


@app.get("/offers/{offer_id}", response_class=HTMLResponse)
def page_offer_detail(request: Request, offer_id: int):
    offer = queries.get_offer(offer_id)
    if not offer:
        raise HTTPException(404, "Offre introuvable")
    return templates.TemplateResponse(
        "offer_detail.html",
        {
            "request": request,
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
    sort: str = "priority",
):
    companies = queries.list_target_companies(
        search=search, priority=priority, status=status, city=city, sort=sort
    )
    stats = queries.get_company_stats()
    priorities = queries.list_company_priorities()
    cities = queries.list_company_cities()
    target_cities = queries.count_companies_per_target_city()
    return templates.TemplateResponse(
        "companies.html",
        {
            "request": request,
            "companies": companies,
            "stats": stats,
            "priorities": priorities,
            "cities": cities,
            "target_cities": target_cities,
            "statuses": VALID_COMPANY_STATUSES,
            "filters": {
                "search": search,
                "priority": priority,
                "status": status,
                "city": city,
                "sort": sort,
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
        "company_detail.html",
        {
            "request": request,
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
    if not ok:
        raise HTTPException(404, "Entreprise introuvable ou aucun champ à mettre à jour")
    return RedirectResponse(f"/companies/{company_id}", status_code=303)


# ---------- API JSON ----------

@app.get("/api/stats")
def api_stats():
    return queries.get_stats()


@app.patch("/api/offers/{offer_id}")
def api_update_offer(offer_id: int, payload: dict):
    ok = queries.update_offer(offer_id, payload)
    if not ok:
        raise HTTPException(404, "Offre introuvable")
    return {"ok": True}


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
        _SCRAPE_STATE["error"] = str(e)
    finally:
        _SCRAPE_STATE["running"] = False
        _SCRAPE_STATE["step"] = "done"
        _SCRAPE_STATE["finished_at"] = datetime.now().isoformat(timespec="seconds")


def _run_full_scrape_bg(max_pages: int) -> None:
    """Tâche d'arrière-plan : scrape TOUTES les sources + cleanup + scoring auto.

    Étapes :
    1. Cleanup : ping URLs existantes, supprime celles 404+sans statut user, archive les autres.
    2. Scrape : FT + WTTJ + HelloWork (séquentiel, dédup auto).
    3. Scoring auto : heuristique v2 sur les nouvelles offres.
    """
    from datetime import datetime

    from backend.scrapers.runner import run_full_scrape

    _SCRAPE_STATE.update({
        "running": True,
        "source": "ALL (FT+WTTJ+HW)",
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
        "error": None,
    })
    try:
        _SCRAPE_STATE["step"] = "cleanup (ping URLs existantes)"
        result = run_full_scrape(
            max_pages=max_pages,
            do_cleanup=True,
            do_auto_score=True,
            do_portals=True,
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
            "scoring_applied": result.scoring_applied,
            "per_source": per_source_summary,
        })
    except Exception as e:  # noqa: BLE001
        _SCRAPE_STATE["error"] = str(e)
    finally:
        _SCRAPE_STATE["running"] = False
        _SCRAPE_STATE["finished_at"] = datetime.now().isoformat(timespec="seconds")


@app.post("/api/scrape")
def api_scrape(bg: BackgroundTasks, source: str = Form(...), max_pages: int = Form(3)):
    """Lance un scrape en arrière-plan.

    `source=all` ou `source=ALL` lance un scrape multi-source : cleanup + FT + WTTJ + HW + scoring.
    Sinon, scrape de la source unique nommée.
    Statut via GET /api/scrape/status.
    """
    from backend.scrapers.registry import list_scrapers

    if _SCRAPE_STATE["running"]:
        raise HTTPException(409, f"Un scrape '{_SCRAPE_STATE.get('source')}' est déjà en cours.")

    if source.lower() == "all":
        bg.add_task(_run_full_scrape_bg, max_pages)
        return {"ok": True, "source": "ALL", "max_pages": max_pages}

    available = set(list_scrapers())
    if source not in available:
        raise HTTPException(400, f"Source inconnue : {source}. Dispo : {sorted(available)}")
    bg.add_task(_run_scrape_bg, source, max_pages)
    return {"ok": True, "source": source, "max_pages": max_pages}


@app.get("/api/scrape/status")
def api_scrape_status():
    """Renvoie l'état du scrape en cours (ou du dernier)."""
    return _SCRAPE_STATE


# ---------- API Toulouse / Companies extraction ----------

@app.post("/api/companies/import-from-offers")
def api_import_companies_from_offers(city: str = Form(...)):
    """Importe en `target_companies` les entreprises distinctes des offres pour
    une ville donnée (ex Toulouse). Permet d'enrichir la liste de cibles
    candidature spontanée."""
    result = queries.import_companies_from_offers_to_targets(city_substr=city, min_score=0)
    return result
