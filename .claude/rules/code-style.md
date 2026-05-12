# Code style (always loaded)

## Python

- **Version cible** : 3.10+ (PEP 604 union syntax `str | None` autorisée)
- **Indentation** : 4 espaces, pas de tabs
- **Quotes** : double quotes `"..."` par défaut (cohérent avec la codebase existante)
- **Max line** : 100 chars indicatif (pas strict)
- **Imports** ordre :
  1. stdlib (`from __future__ import annotations` en premier si annotations)
  2. third-party (`fastapi`, `pydantic`, `openpyxl`, etc.)
  3. local `from backend.x import y`

```python
"""Docstring module (1 ligne max)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from openpyxl import load_workbook

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
- Pas de `try/except: pass` silencieux
- Pour les opérations DB : laisser remonter sauf cas connu (ex: contrainte UNIQUE)

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
- ❌ Strings concaténées pour le SQL (utiliser params)
- ❌ Globals mutables (préférer constantes ou config)
- ❌ Fonctions de >50 lignes (extraire des helpers)
- ❌ Réimplémenter ce qui existe dans `queries.py` / `db.py` / `models.py`
