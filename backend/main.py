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
    sort: str = "priority",
):
    companies = queries.list_target_companies(
        search=search, priority=priority, status=status, sort=sort
    )
    stats = queries.get_company_stats()
    priorities = queries.list_company_priorities()
    return templates.TemplateResponse(
        "companies.html",
        {
            "request": request,
            "companies": companies,
            "stats": stats,
            "priorities": priorities,
            "statuses": VALID_COMPANY_STATUSES,
            "filters": {
                "search": search,
                "priority": priority,
                "status": status,
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
    """Tâche d'arrière-plan exécutée par BackgroundTasks."""
    from datetime import datetime

    from backend.scrapers.runner import run_scrape

    _SCRAPE_STATE.update({
        "running": True,
        "source": source,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "total_fetched": 0,
        "total_new": 0,
        "total_duplicates": 0,
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
        _SCRAPE_STATE["finished_at"] = datetime.now().isoformat(timespec="seconds")


@app.post("/api/scrape")
def api_scrape(bg: BackgroundTasks, source: str = Form(...), max_pages: int = Form(3)):
    """Lance un scrape en arrière-plan. Statut via GET /api/scrape/status."""
    from backend.scrapers.registry import list_scrapers

    available = set(list_scrapers())
    if source not in available:
        raise HTTPException(400, f"Source inconnue : {source}. Dispo : {sorted(available)}")
    if _SCRAPE_STATE["running"]:
        raise HTTPException(409, f"Un scrape '{_SCRAPE_STATE['source']}' est déjà en cours.")
    bg.add_task(_run_scrape_bg, source, max_pages)
    return {"ok": True, "source": source, "max_pages": max_pages}


@app.get("/api/scrape/status")
def api_scrape_status():
    """Renvoie l'état du scrape en cours (ou du dernier)."""
    return _SCRAPE_STATE
