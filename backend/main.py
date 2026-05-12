"""App FastAPI : routes web + Jinja templates."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend import queries
from backend.db import init_schema
from backend.models import VALID_STATUSES, VALID_PRIORITIES, VALID_REMOTE

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
    sort: str = "score_desc",
):
    offers = queries.list_offers(
        search=search,
        status=status,
        source=source,
        min_score=min_score,
        only_to_apply=only_to_apply,
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
