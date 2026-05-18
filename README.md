# Scrap'OffreEmploi — Tracker alternance AI Engineer

App web locale pour scraper, scorer et suivre les offres d'alternance "AI Engineer"
en France, alignées avec le programme OpenClassrooms AI Engineer.

**Stack** : Python 3.10+ · FastAPI · SQLite · Jinja2 · HTMX (vendoré) · Tailwind v3 (vendoré).
Aucun Node.js, aucun build step, aucune clé API LLM, **aucune dépendance CDN runtime**.

## Quickstart

```powershell
# 1. Setup une seule fois — venv obligatoire (cf "Limitations" plus bas)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Installer les deps. Deux options :
#    a. Versions exactes (reproductible — recommandé) :
pip install -r requirements.lock
#    b. Contraintes lâches (dev, peut récupérer des minor bumps) :
pip install -r requirements.txt

# 3. Migrer l'ancien xlsx vers SQLite — UNE SEULE FOIS au premier setup.
# ⚠️ Ce script fait `DELETE FROM offers` avant l'import. Sur une DB déjà
# peuplée (ex tu re-fais le quickstart par réflexe 6 mois plus tard),
# il REFUSE de tourner et te demande `--force` explicite — pas de
# perte de données scrapées par accident. Voir `python -m backend.migrate_xlsx --help`.
$env:PYTHONIOENCODING="utf-8"; python -m backend.migrate_xlsx

# 4. Lancer l'app
.\run.ps1
# → http://localhost:8000
```

## Structure

```
backend/     Code FastAPI + Jinja + SQLite
cli.py       Commandes : scrape, apply-scores, export-batch, check-alive
tests/       pytest (367 tests, ~15-26s, sans network)
data/        SQLite + batches JSON + scrapes (gitignored)
docs/        ARCHITECTURE.md, CRITERIA.md (grille scoring), SOURCES.md (sites scrapés)
reference/   PDF du programme OC + pages PNG
legacy/      Ancien code archivé
```

## Workflow scoring LLM (via chat Claude)

Pas de clé API Anthropic dans le projet — le scoring se fait dans **ce chat** :

1. App scrape → écrit `data/batches/{date}_to_score.json` (cocher "Générer batch
   pour scoring LLM" lors du scrape, ou `python cli.py export-batch`).
2. Dans le chat Claude : "score le dernier batch".
3. Claude lit le JSON, applique la grille 5 axes /20 (cf `docs/CRITERIA.md`),
   écrit `data/batches/{date}_scores.json`.
4. `python cli.py apply-scores data/batches/{date}_scores.json` → DB à jour.

Le scoring **heuristique automatique** (mots-clés + pénalités CDI/Senior) s'applique
de toute façon à chaque scrape — le batch LLM est juste un raffinement optionnel.

## Qualité du code

`bandit` et `pytest` sont déclarés dans `requirements.txt`/`.lock` — installés
par le `pip install -r requirements.lock` ci-dessus.

```powershell
# Tests
$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/ -q
# → 367 passed in ~15-26s (selon machine)

# Sécurité (statique) — bandit pinné dans requirements
python -m bandit -r backend cli.py
# → 0 issues (les `# nosec B608` sont commentés `# SAFE (B608) : ...` au-dessus)

# Smoke test (import OK + nb routes)
python -c "from backend.main import app; print('OK', len(app.routes), 'routes')"
```

## Limitations connues (usage local mono-utilisateur)

Cette app est conçue pour **un usage perso en local**, pas pour la prod multi-user.
Certains choix volontaires :

- **`_SCRAPE_STATE` en RAM** : l'état du scrape en cours vit dans une variable
  module-level. Si le serveur est tué pendant un scrape, l'état est perdu.
  Mitigation : reset auto au startup (lifespan) + endpoint `POST /api/scrape/reset`
  comme escape-hatch. Pour un vrai multi-process, il faudrait Redis/SQLite.

- **Bind 127.0.0.1 seulement** : l'app n'écoute pas sur `0.0.0.0` — pas exposée
  au réseau. Si tu veux la partager, mets-la derrière un reverse proxy (nginx/caddy)
  + auth basique.

- **Pas d'authentification** : les routes `POST /api/scrape/reset`,
  `PATCH /api/offers/{id}`, `POST /api/companies/import-from-offers`, etc. sont
  accessibles sans login. C'est OK en local (seul toi as accès à `127.0.0.1:8000`),
  pas OK en remote. Le middleware CSRF (`CSRFOriginMiddleware`) bloque déjà les
  requêtes mutantes depuis une origin externe.

- **Tailwind + HTMX vendorés localement** : les 2 bundles sont servis via
  `backend/static/` avec SRI sha384. Plus aucune dépendance CDN au runtime —
  l'app marche en mode avion / firewall corporate / unpkg down.
  - `backend/static/tailwind-3.4.17.min.js` (~407 KB)
  - `backend/static/htmx-2.0.4.min.js` (~50 KB)

  Pour mettre à jour une lib :

  ```powershell
  curl -o backend/static/<lib>-<version>.min.js https://unpkg.com/<lib>@<version>
  python -c "import hashlib, base64; d=open('backend/static/<lib>-<version>.min.js','rb').read(); print('sha384-'+base64.b64encode(hashlib.sha384(d).digest()).decode())"
  # → mettre à jour le src + integrity dans backend/templates/base.html
  ```

- **CSRF middleware lié au port** : `CSRFOriginMiddleware` (`backend/main.py`)
  filtre les Origin/Referer des requêtes mutantes. Origins acceptées par
  défaut : `http://127.0.0.1:8000` et `http://localhost:8000`. Si tu lances
  l'app sur un autre port (`uvicorn --port 8001`) ou derrière un reverse proxy,
  les POST navigateur seront bloqués → override via la variable d'environnement
  `ALLOWED_ORIGINS` (CSV) :

  ```powershell
  $env:ALLOWED_ORIGINS="http://127.0.0.1:8001,https://mon-proxy.local"
  python -m backend
  ```

- **Credentials France Travail dans `.env`** (gitignored). Si tu publies sur
  GitHub : vérifier que `.env` n'est PAS commité (`git ls-files | grep .env`).

## MCPs (optionnels)

Le projet bénéficie de 2 MCP servers configurés au user scope :

- **context7** — doc à jour des libs Python (FastAPI, Pydantic, httpx, etc.)
- **exa** — recherche web sémantique (utile pour comprendre les sites à scraper)

Voir `CLAUDE.md` section "MCPs installés".

## Plus de doc

- `CLAUDE.md` — guide complet pour Claude Code (architecture, règles, commandes)
- `docs/CRITERIA.md` — grille de scoring 5 axes /20
- `docs/SOURCES.md` — sites à scraper (job boards + portails entreprise + secteurs)
- `CHANGELOG.md` — journal des changements user-facing
- `.claude/rules/*.md` — règles modulaires (database, routes, scrapers, templates, code-style, workflow)
