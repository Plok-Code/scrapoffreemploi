# Code style (always loaded)

## Python

- **Version cible** : 3.10+ (PEP 604 union syntax `str | None` autorisée)
- **Indentation** : 4 espaces, pas de tabs
- **Quotes** : double quotes `"..."` par défaut (cohérent avec la codebase existante)
- **Max line** : 100 chars indicatif (pas strict)
- **Imports** ordre :
  1. stdlib (`from __future__ import annotations` en premier si annotations)
  2. third-party (`fastapi`, `pydantic`, `httpx`, `tenacity`, `loguru`, etc.)
  3. local `from backend.x import y` (`_logging` en premier des locaux)

```python
"""Docstring module (1 ligne max)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from openpyxl import load_workbook
from tenacity import retry, stop_after_attempt, wait_exponential

from backend._logging import logger
from backend import queries
from backend.db import db
```

## Type hints

- Toujours typer les paramètres et retours des fonctions exportées
- Utiliser la syntaxe moderne : `list[dict]` (pas `List[Dict]`), `str | None` (pas `Optional[str]`)
- Pour les Pydantic models : `Optional[X] = None` reste OK (cohérent avec models.py)

## Naming

- **Modules** : `snake_case.py`
- **Fonctions/variables** : `snake_case`
- **Classes / Pydantic models** : `PascalCase`
- **Constantes** : `UPPER_SNAKE_CASE`
- **Routes HTTP (URL)** : `kebab-case` (ex: `/api/stats`, `/offers/{id}`)
- **Templates Jinja** : `snake_case.html`

## Gestion d'erreurs

- Lever `HTTPException(404, "message")` pour les erreurs HTTP attendues
- Laisser remonter les exceptions inattendues (FastAPI les gère)
- **JAMAIS `try/except: pass` silencieux** — toujours `logger.warning("...", err=str(e))` au minimum
- Si on veut le traceback complet : `logger.opt(exception=True).debug("...")` (loguru capture la stack)
- Pour les opérations DB : laisser remonter sauf cas connu (ex: contrainte UNIQUE)

## Logging (loguru)

```python
from backend._logging import logger

# Niveaux
logger.debug("Détail verbeux pour debug (chaque requête HTTP)")
logger.info("Événement normal : Scrape FT terminé, {n} nouvelles", n=42)
logger.warning("Anomalie non bloquante : URL morte {url}", url=u)
logger.error("Échec d'une opération : {err}", err=str(e))
logger.critical("Panne grave : DB inaccessible")

# Avec stacktrace (catch silencieux mais on garde la trace)
try:
    risky()
except Exception as e:
    logger.warning("Op KO : {err}", err=str(e))
    logger.opt(exception=True).debug("Traceback complet")
```

Sortie : `data/logs/app.log` (INFO+) + `data/logs/errors.log` (ERROR+). Rotation auto.

## HTTP / Resilience (tenacity)

```python
from backend.scrapers._http import get_with_retry, http_client, DEFAULT_RATE_LIMITER

# Retries auto (exponential backoff 2/4/8/16s sur 429/500/timeout)
with http_client() as client:
    DEFAULT_RATE_LIMITER.acquire()  # pause aléatoire 1.0-2.5s
    resp = get_with_retry(client, url)
```

Pour un scraper avec sa propre cadence : `RateLimiter(min_delay=0.5, max_delay=1.5)`.

## Validation (Pydantic)

Pour les inputs externes (API, scrape) : utiliser `BaseModel`, pas `@dataclass`.

```python
from pydantic import BaseModel, Field, field_validator

class RawOffer(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    title: str = Field(min_length=1)
    company: Optional[str] = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title is empty")
        return v.strip()
```

Si un scraper renvoie un titre vide / un type incohérent, Pydantic catch immédiatement → pas de pollution DB.

## SQL (dans queries.py)

- Multilignes triple-quoted avec indentation 4 espaces dans la chaîne
- Paramètres nommés `:name` (preferred) ou `?` positional
- Toujours utiliser le context manager `with db() as conn:`
- Retourner des `dict` (jamais des `sqlite3.Row` exposés à l'extérieur)

```python
def list_x(*, filter_a: str = "") -> list[dict]:
    sql = "SELECT * FROM offers WHERE col = :a"
    with db() as conn:
        rows = conn.execute(sql, {"a": filter_a}).fetchall()
    return [dict(r) for r in rows]
```

## Templates Jinja

- Indentation 4 espaces dans le HTML
- Macros au début du fichier `{% macro ... %}`
- Classes Tailwind sur une ligne ; si trop long, splitter par groupes logiques
- Pas d'inline JavaScript : utiliser HTMX `hx-*` attributes

## FastAPI

- Routes web (HTML) : sous `/` ou `/offers/...` — retourne `templates.TemplateResponse(...)`
- Routes API (JSON) : préfixe `/api/...` — retourne dict ou Pydantic model
- Utiliser `Form(...)` pour les POST HTML, `payload: dict` ou Pydantic pour JSON

## Commits / changelog

- Format conventional commits si tu commits (mais n'AGIS PAS sans demande explicite) : `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`
- Mettre à jour `CHANGELOG.md` section `[Unreleased]` pour toute modif user-facing

## Anti-patterns à éviter

- ❌ `from x import *` (sauf cas justifié)
- ❌ Strings concaténées pour le SQL (utiliser params nommés `:name`)
- ❌ Globals mutables (préférer constantes ou config) — `_SCRAPE_STATE` est l'exception assumée
- ❌ Fonctions de >50 lignes (extraire des helpers)
- ❌ Réimplémenter ce qui existe dans `queries.py` / `db.py` / `models.py` / `_logging.py` / `_http.py`
- ❌ `print()` dans les modules non-CLI (utiliser `logger.X`)
- ❌ `time.sleep(2)` en boucle pour retry (utiliser `tenacity`)
- ❌ `@dataclass` pour les inputs externes (utiliser `BaseModel` Pydantic pour validation)
- ❌ `except Exception: pass` (catch ET logger, sinon laisser remonter)
- ❌ Pour le scraping : pas de `requests` synchrones séquentielles sans `RateLimiter` (anti-ban IP)
- ❌ `make_dedup_key` sans city — la ville fait partie de la clé (bug audit)
