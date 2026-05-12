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

| Méthode | Path | Description |
|---|---|---|
| GET | `/` | Liste filtrée des offres |
| GET | `/offers/{id}` | Détail offre + form de tracking |
| POST | `/offers/{id}` | Update tracking (status, dates, notes...) |
| GET | `/api/stats` | KPIs JSON (total, postulé, etc.) |
| PATCH | `/api/offers/{id}` | Update via JSON |
| GET | `/api/docs` | Swagger UI |
