---
description: FastAPI routes (HTML web + JSON API)
paths:
  - backend/main.py
  - backend/__main__.py
---

# Routes FastAPI

## Conventions de routes

Deux familles, distinguées par préfixe :

### Routes web (HTML)
- Sans préfixe (`/`, `/offers/{id}`)
- Retournent `templates.TemplateResponse("file.html", {...})`
- Acceptent les forms via `Form(...)` puis redirect 303

```python
@app.get("/", response_class=HTMLResponse)
def page_offers(request: Request, search: str = "", ...):
    offers = queries.list_offers(search=search, ...)
    return templates.TemplateResponse("offers.html", {
        "request": request,
        "offers": offers,
        ...
    })
```

### Routes API (JSON)
- Préfixe `/api/...`
- Retournent dict ou Pydantic model
- PATCH avec `payload: dict` (ou `OfferUpdate` Pydantic depuis `models.py`)

```python
@app.patch("/api/offers/{offer_id}")
def api_update_offer(offer_id: int, payload: dict):
    ok = queries.update_offer(offer_id, payload)
    if not ok:
        raise HTTPException(404, "Offre introuvable")
    return {"ok": True}
```

## Pattern : forms HTML

Toutes les valeurs du `Form(...)` doivent avoir `= Form("")` (default empty string), pas `= None`, pour matcher le comportement des `<input>` qui envoient toujours une string.

```python
@app.post("/offers/{offer_id}")
def update_offer_route(
    offer_id: int,
    status: str = Form(""),
    date_applied: str = Form(""),
    ...
):
    ok = queries.update_offer(offer_id, {"status": status, ...})
    if not ok:
        raise HTTPException(404, "...")
    return RedirectResponse(f"/offers/{offer_id}", status_code=303)
```

`queries.update_offer()` convertit `""` → `None` automatiquement (cf. `ALLOWED_UPDATE_FIELDS`).

## Toujours

- ✅ Passer par `queries.py` pour toute query DB (pas de SQL inline)
- ✅ Lever `HTTPException(404, ...)` si ressource introuvable
- ✅ Valider les enums (`status`, `priority`, `remote`) via les constantes de `models.py`
- ✅ Si nouvelle route web : ajouter le lien dans `templates/base.html` si pertinent

## Jamais

- ❌ `NextResponse` ou patterns Node.js (on est en Python)
- ❌ Logique métier dans les routes — extraire dans `queries.py` ou un module dédié
- ❌ Rendre du HTML manuellement (toujours via Jinja templates)
- ❌ Renvoyer du `text/html` depuis une route `/api/...`

## Lancement

L'app se lance via `backend/__main__.py` :
```python
import uvicorn
uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
```

→ `python -m backend` ou `.\run.ps1`. **Ne pas activer `reload=True`** par défaut (peut casser le mode bypass des permissions Claude).

## Quand ajouter une route

- 1-2 nouvelles routes : ajouter dans `main.py`
- Si `main.py` > 200 lignes : splitter via `APIRouter` (créer `backend/api/offers.py`, etc.)

## Routes existantes (référence)

### Pages web
| Méthode | Path | Description |
|---|---|---|
| GET | `/` | Liste filtrée des offres + bouton 👎 "Pas intéressé" inline |
| GET | `/offers/{id}` | Détail offre + form de tracking |
| POST | `/offers/{id}` | Update tracking (status, dates, notes...) |
| GET | `/companies` | Liste entreprises cibles, tabs villes, filtre `?city=Toulouse&other_haute=true` |
| GET | `/companies/{id}` | Détail entreprise + form de tracking |
| POST | `/companies/{id}` | Update tracking entreprise |

### API JSON
| Méthode | Path | Description |
|---|---|---|
| GET | `/api/stats` | KPIs JSON (total, postulé, top_fit, archived, not_interested…) |
| PATCH | `/api/offers/{id}` | Update offre via JSON payload |
| POST | `/api/offers/{id}/status` | Toggle rapide statut (form-encoded, pour HTMX bouton 👎) |
| POST | `/api/scrape` | Lance scrape async (`source=all` pour multi-source, `use_playwright=true` pour SPAs) |
| GET | `/api/scrape/status` | État du scrape en cours (running, step, total_new, deleted_dead, scoring_applied, per_source...) |
| POST | `/api/companies/import-from-offers` | Import auto entreprises depuis offres scrapées (filtre par ville) |
| GET | `/api/docs` | Swagger UI |

## Pattern : background tasks (scrape async)

Le scrape "Tout" tourne en arrière-plan via `BackgroundTasks` et expose son état via une variable globale in-memory `_SCRAPE_STATE` :

```python
_SCRAPE_STATE: dict = {
    "running": False, "source": None, "step": "...",
    "total_fetched": 0, "total_new": 0, "deleted_dead": 0,
    "non_alternance_removed": 0, "scoring_applied": 0,
    "per_source": {...}, "error": None,
}

@app.post("/api/scrape")
def api_scrape(bg: BackgroundTasks, source: str = Form(...),
               max_pages: int = Form(3), use_playwright: bool = Form(False)):
    if _SCRAPE_STATE["running"]:
        raise HTTPException(409, "Un scrape est déjà en cours.")
    if source.lower() == "all":
        bg.add_task(_run_full_scrape_bg, max_pages, use_playwright)
    else:
        bg.add_task(_run_scrape_bg, source, max_pages)
    return {"ok": True, "source": source}

@app.get("/api/scrape/status")
def api_scrape_status():
    return _SCRAPE_STATE
```

UI HTMX :
- `<form hx-post="/api/scrape">` lance le scrape
- `<div hx-get="/api/scrape/status" hx-trigger="load, every 3s">` poll l'état toutes les 3 sec
- JS minimal pour formater le JSON en HTML (déjà dans `base.html`)

## Pattern : statut "Pas intéressé" inline avec HTMX

Pour les actions one-click qui n'ouvrent pas le détail :

```html
<button hx-post="/api/offers/{{ o.id }}/status"
        hx-vals='{"status": "Pas intéressé"}'
        hx-swap="none"
        hx-on::after-request="if(event.detail.successful) document.getElementById('offer-row-{{ o.id }}').remove();">
    👎
</button>
```

Endpoint dédié `POST /api/offers/{id}/status` (form-encoded, pas JSON) compatible HTMX sans extension `json-enc`.
