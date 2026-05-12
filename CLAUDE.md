# Scrap'Offre Emploi — Tracker alternance AI Engineer

App web locale (Python + SQLite, sans Node.js) pour scraper, scorer et suivre des offres d'alternance "AI Engineer" en France, alignées avec le programme OpenClassrooms AI Engineer.

## Stack

- **Backend** : Python 3.13 + FastAPI + Uvicorn
- **DB** : SQLite (un seul fichier `data/app.db`)
- **Templating** : Jinja2 (HTML server-rendered)
- **Frontend** : HTMX 2.0 + Tailwind v3 via CDN (zéro build step, zéro Node.js)
- **Scraping** : `httpx` + `beautifulsoup4` + `lxml` + `playwright` (fallback SPA)
- **Xlsx I/O** : `openpyxl` (migration et export uniquement)
- **APIs externes** : France Travail Offres d'emploi v2 (OAuth), WTTJ Algolia (clés publiques)
- **OS** : Windows 11, shell PowerShell (Bash dispo via Git Bash)
- **Pas de** : Node.js, pnpm, React, Tailwind build, TypeScript, ORM, Prisma, Docker

## Commandes

```powershell
# Setup (une fois)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Migration xlsx -> SQLite (déjà fait, à re-lancer pour reset DB)
$env:PYTHONIOENCODING="utf-8"; python -m backend.migrate_xlsx

# Lancer l'app
.\run.ps1
# OU directement :
python -m backend
# → http://localhost:8000

# Tests pytest (83 tests, ~2 sec, sans network)
$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/ -v

# Logs (rotation auto 10MB, 7 fichiers gz)
Get-Content data\logs\app.log -Tail 30 -Wait
Get-Content data\logs\errors.log -Tail 50

# CLI utiles
python cli.py stats                                    # KPIs DB
python cli.py scrape <source> [--max-pages N]          # scrape un job board
python cli.py check-alive [--min-score N]              # ping URLs + delete/archive mortes
python cli.py enrich-descriptions [--source X]         # re-fetch desc manquantes
python cli.py export-batch [--only-unscored]           # batch JSON pour scoring manuel
python cli.py apply-scores <path>                      # applique scores JSON
python -m backend.heuristic_scorer [--rescore]         # scoring auto sur unscored
python -m backend.filter_alternance [--dry-run]        # filtre CDI/Senior/stage
python -m backend.seed_recompute_dedup_keys            # migration dedup_key + city
```

## Architecture

```
scrapoffreemploi/
├── backend/
│   ├── __main__.py             # python -m backend → uvicorn
│   ├── main.py                 # FastAPI app + routes web/API (18 routes)
│   ├── db.py                   # connexion SQLite + migrations + make_dedup_key(t,c,city)
│   ├── schema.sql              # DDL : offers + target_companies + scrape_runs
│   ├── models.py               # Pydantic + constantes (statuts, labels, etc.)
│   ├── queries.py              # CRUD + filtres + stats + insert_offers_bulk
│   ├── migrate_xlsx.py         # one-shot xlsx -> SQLite (préserve le xlsx)
│   ├── matching.py             # export batch JSON pour scoring + apply scores
│   ├── _logging.py             # loguru centralisé (3 sinks : console + app.log + errors.log)
│   ├── heuristic_scorer.py     # scoring auto v2 (mots-clés par axe + pénalités)
│   ├── filter_alternance.py    # filtre auto non-alternance (delete + archive)
│   ├── seed_company_cities.py  # one-shot : remplit city + multi-villes
│   ├── seed_high_priority_other_cities.py  # one-shot : Hautes hors-5-villes
│   ├── seed_toulouse_contact_methods.py    # one-shot : canaux contact Toulouse
│   ├── seed_recompute_dedup_keys.py        # one-shot : recompute dedup_key avec city
│   ├── dedup_company_names.py  # one-shot : fusion alias (Capgemini Eng (ex-Altran))
│   ├── scrapers/               # 1 module par source/SaaS
│   │   ├── _http.py            # session httpx (UA Chrome) + tenacity + RateLimiter
│   │   ├── _keywords.py        # regex IA/ML/DL/LLM/data
│   │   ├── _playwright.py      # persistent_browser + lock guard (PlaywrightProfileLocked)
│   │   ├── base.py             # ABC Scraper + Pydantic RawOffer (validation stricte)
│   │   ├── registry.py         # SCRAPERS dict
│   │   ├── runner.py           # run_scrape + check_alive + cleanup + full_scrape
│   │   ├── _generic.py         # GenericScraper (multi-fallback HTML)
│   │   ├── hellowork.py        # HelloWork (httpx + JSON-LD JobPosting)
│   │   ├── francetravail.py    # API OAuth2 v2 (E1/E2 alternance)
│   │   ├── wttj.py             # Algolia public keys
│   │   ├── linkedin.py         # Playwright loggué (archives = expired)
│   │   ├── company_portals.py  # Workable / Lever / Workday / Greenhouse / Taleez / Phenom / Playwright
│   │   └── labonneboite.py     # LBB v2 (bloqué 403, habilitation FT requise)
│   ├── templates/              # Jinja : base, offers, offer_detail, companies, company_detail
├── tests/                      # pytest avec mocks HTML (83 tests, ~2 sec)
│   ├── conftest.py             # fixtures HTML (Workday dead, AXA redirect, Doctolib alive)
│   ├── test_keywords.py        # 15 tests : matches_keywords
│   ├── test_filter_alternance.py  # 14 tests : classify_offer
│   ├── test_soft_404.py        # 8 tests : _is_soft_404 (4 niveaux)
│   ├── test_dedup_key.py       # 9 tests : make_dedup_key (incl. Paris vs Toulouse)
│   ├── test_raw_offer.py       # 10 tests : Pydantic RawOffer validation
│   ├── test_bulk_insert.py     # 8 tests : insert_offers_bulk (DB temp)
│   └── test_playwright_lock.py # 6 tests : _is_profile_locked
│   └── static/                 # CSS minimal (Tailwind via CDN)
├── data/                       # gitignored
│   ├── app.db                  # SQLite, source de vérité
│   ├── batches/                # JSON offres à scorer (échange avec moi)
│   ├── logs/                   # loguru rotation (app.log + errors.log + .gz archives)
│   ├── scrapes/                # raw outputs scraping par run
│   ├── exports/                # xlsx générés à la demande
│   ├── .playwright_profile/    # profil Chromium persistant (cookies LinkedIn, etc.)
│   └── companies_spontaneous_extracted.json  # 71 entreprises cibles (phase 2)
├── docs/                       # ARCHITECTURE / CRITERIA / SOURCES (à venir)
├── reference/
│   ├── Parcours_AI_Engineer_OC.pdf
│   └── pdf_pages/              # 37 PNG du PDF (extraits)
├── legacy/                     # tout l'ancien code archivé (20+ scripts)
└── requirements.txt
```

## Fichiers centraux (lire en priorité)

Quand tu travailles sur :
- **Le schéma DB** → `backend/schema.sql` (offers + target_companies + scrape_runs)
- **Une requête SQL** → `backend/queries.py` (toujours passer par là, jamais d'inline SQL ailleurs) — utiliser `insert_offers_bulk` pour les batchs
- **Une route HTTP** → `backend/main.py` (18 routes ; splitter si > 200 lignes via APIRouter)
- **Le scoring LLM manuel** → `backend/matching.py` + `backend/models.py` (workflow batch JSON)
- **Le scoring auto heuristique** → `backend/heuristic_scorer.py` (mots-clés par axe + pénalités CDI/Senior)
- **Le filtre alternance** → `backend/filter_alternance.py` (delete/archive non-alternance, appliqué auto à chaque scrape)
- **Le cleanup URLs mortes** → `backend/scrapers/runner.cleanup_dead_unstatused` (4 niveaux de détection)
- **Un nouveau scraper SaaS RH** → `backend/scrapers/company_portals.py` (dispatcher Workable/Lever/Workday/Greenhouse/Taleez/Phenom/Playwright)
- **La migration xlsx** → `backend/migrate_xlsx.py` (NE PAS toucher au xlsx original)
- **Une vue HTML** → `backend/templates/{offers, offer_detail, companies, company_detail}.html`
- **Logging** → `backend/_logging.py` (loguru, init dans `main.py`, sortie dans `data/logs/`)
- **Tests** → `tests/` (pytest + fixtures HTML mockées, jamais de network call)
- **dedup_key** → `backend/db.py:make_dedup_key(title, company, city)` — la **ville fait partie de la clé** (bug critique fix : Paris vs Toulouse ≠ doublons)

## Données du projet

État au 12 mai 2026 (après scraping mode lent complet + filtres) :
- **1120 offres actives** dans `data/app.db` (5 Top, 170 Bon, ~280 Moyen, ~665 Faible)
- **~260 entreprises cibles** dans `target_companies` :
  - 65 initiales du xlsx historique (priorité Haute/Moyenne/Basse, 36 Haute)
  - +128 importées depuis offres scrapées via les 5 villes cibles
  - +16 entreprises Haute hors-5-villes
  - +52 lignes multi-implantation (Airbus Toulouse/Nantes/Paris, Capgemini ×5, etc.)
  - 1 row par couple (entreprise, ville) — index UNIQUE (LOWER(name), LOWER(city))
- **5 villes cibles fixes** : Toulouse, Bordeaux, Pau, Paris, Nancy. Pour les autres villes France → seulement priorité Haute.
- Le xlsx **source de vérité historique** : `data/source/candidatures_alternance_AI_Engineer.xlsx` (gitignored, dans le projet)
- **Credentials FT** dans `.env` (gitignored) : `FRANCETRAVAIL_CLIENT_ID` / `FRANCETRAVAIL_CLIENT_SECRET`

## Règles non-négociables

1. **JAMAIS toucher au xlsx** `data/source/candidatures_alternance_AI_Engineer.xlsx` — lecture seule uniquement. Si tu dois modifier des données, fais-le dans SQLite.
2. **JAMAIS d'API Anthropic** — pas de clé. Le scoring LLM manuel passe par ce chat Claude Code Max (workflow batch). Le scoring auto utilise des heuristiques sans LLM.
3. **Toujours passer par `queries.py`** pour les accès DB — pas de SQL inline dans `main.py` ou les templates. Pour les batchs, utiliser `insert_offers_bulk` (1 transaction).
4. **dedup_key inclut la ville** : `make_dedup_key(title, company, city)`. Une même offre à Paris vs Toulouse = 2 inserts distincts.
5. **JAMAIS `except Exception: pass`** silencieux — toujours `logger.warning/error` avec le contexte (offer_id, url, etc.).
6. **`print()` interdit dans les modules non-CLI** — utiliser `logger.info/warning/error/debug` (loguru auto-init dans main.py).
7. **Pydantic pour les inputs externes** — `RawOffer` (BaseModel) valide chaque offre scrapée avant insertion.
8. **`tenacity` pour les retries** — pas de retry maison, utiliser `get_with_retry` de `_http.py`.
9. **`RateLimiter` aléatoire entre requêtes** — `DEFAULT_RATE_LIMITER` ou instance dédiée par scraper.
10. **Playwright lock guard** — toujours passer par `persistent_browser` qui check le `SingletonLock` avant d'ouvrir.
11. **Mojibake** : `fix_mojibake()` dans `migrate_xlsx.py` (cp1252 → utf-8).
12. **Encoding PowerShell** : `$env:PYTHONIOENCODING="utf-8"` avant les commandes Python qui affichent du français.
13. **Pas de Node.js, pas de build step** — si tu envisages d'ajouter du React/Vite/Webpack, STOP et propose HTMX/Jinja.
14. **Tester l'import après modif** : `python -c "from backend.main import app; print('OK', len(app.routes))"` + `python -m pytest tests/ -q`.
15. **Redémarrer uvicorn après modif** (si l'app tourne en background) sinon l'utilisateur voit l'ancien code.

## Workflow scoring LLM (spécifique à ce projet)

Pas de clé API → on passe par CE chat :

```
1. App scrape → écrit data/batches/{date}_to_score.json
2. User : "score le dernier batch"
3. MOI (Claude dans ce chat) : lis le JSON, score chaque offre selon la grille (5 axes /20)
4. MOI : écris data/batches/{date}_scores.json
5. User : `python cli.py apply-scores` → backend importe les scores en DB
```

## Grille de scoring (référence : `docs/CRITERIA.md` à créer)

Score sur 100, somme de **5 axes /20** :

1. **Pipeline / ingestion** (Airbyte, Kestra, PySpark, ETL/ELT)
2. **Exploration / analyse** (Pandas, viz, stats, exploration)
3. **Modélisation IA** (ML supervisé, DL, NLP, CV, RAG, LLM, fine-tuning, agents, RL)
4. **Déploiement / MLOps** (Docker, FastAPI, CI/CD, MLflow, BentoML, monitoring, drift)
5. **Cadrage / qualité / indus** (cadrage projet IA, KPIs, Pytest, great-expectations, gouvernance)

Labels (calculés via `label_for_score()` dans `models.py`) :
- ≥80 : Top (vert) — à postuler en priorité
- 60-79 : Bon (jaune)
- 40-59 : Moyen (orange)
- <40 : Faible (gris)

## Filtrage des offres au scraping

L'app ne scrape QUE les offres contenant un mot-clé IA/data :
`IA, AI, artificial intelligence, intelligence artificielle, data, donnée(s), ML, machine learning, deep learning, MLOps, LLM, NLP, computer vision, RAG, AI engineer, data scientist, data engineer`

Et filtre sources : `alternance` + `France` uniquement.

## Statuts d'une offre

Champ `status` (table `offers`) :
- **vide** = pas encore postulé (= "À postuler")
- `Postulé`, `Relancé`, `Entretien`, `Test technique`, `Refusé`, `Accepté`, `Sans réponse`, `Abandonné`
- `Pas intéressé` : offre vue mais ne correspond pas — disparaît de l'onglet "À postuler"

Le champ séparé `application_method` (libre) sert pour les notes "Portail officiel recommandé / Email RH / etc." — ne PAS le mélanger avec `status`.

## Cycle de vie d'une offre (règle métier)

À chaque scrape "Tout" (`POST /api/scrape` source=all) :

1. **Cleanup URLs mortes** (`cleanup_dead_unstatused`) — détection à 4 niveaux :
   - HTTP 404/410 explicite
   - Body : 18 regex (`offre n'est plus disponible`, `no longer available`, `résultats de la recherche`, etc.)
   - Title : `erreur.*inexistante`, `current openings`, `404`
   - URL finale après redirects : `?not_found=true`, `trk=expired_jd_redirect`, ou URL < 50% de l'original
   - Workday : probe API JSON dédiée `/wday/cxs/{tenant}/{site}/job/{id}`
   - **Action** : si `status=NULL` → `DELETE` ; si `status≠NULL` → `is_active=0` (préserve l'historique applicatif)

2. **Scrape job boards** (FT API + WTTJ Algolia + HelloWork HTML)
3. **Scrape portails entreprises** (Workable/Lever/Workday/Greenhouse/Taleez/Phenom/Playwright)
4. **Filtre non-alternance** (`filter_non_alternance_offers`) :
   - Garde : `alternance|apprenti|professionnalisation` mentionné
   - Rejet : `CDI|CDD|Senior|Lead Data/ML|Tech Lead|Manager|Director|stage seul` dans titre
   - Doute → garde (principe : on garde sauf si on est sûr de rejeter)
5. **Heuristic scoring auto** sur les nouvelles offres
6. **Toutes les nouvelles offres** ont un score immédiatement

## MCPs installés (scope user)

Configurés dans `C:\Users\novar\.claude.json` (hors repo, gitignored par nature) :

- **context7** ✓ — doc à jour des libs Python (FastAPI, Pydantic, openpyxl, httpx, beautifulsoup4). Endpoint : `https://mcp.context7.com/mcp` (transport HTTP).
- **exa** ✓ — recherche web sémantique AI-optimized. Utile pour comprendre les sites à scraper (HelloWork, APEC, etc.). Endpoint : `https://mcp.exa.ai/mcp` (transport HTTP).

**Utilisation automatique** par les sub-agents (`explore-doc` → context7, `web-search` → exa). Tu peux aussi les invoquer manuellement : *"Use context7 to look up FastAPI dependency injection"*.

Si une recherche MCP échoue ou retourne vide, l'agent fallback sur WebFetch/WebSearch natif.

## Comment me parler

- Pour une feature moyenne/grosse : `/apex implement X` (workflow EPCT)
- Pour un petit fix (1-3 fichiers) : `/one-shot fix X`
- Pour un bug : `/debug [message d'erreur]`
- Pour review avant commit : `/review-code pending changes`
- Référence toujours un fichier existant comme exemple ("comme dans `backend/queries.py`")
- Si tu ne sais pas trancher, demande-moi 2-3 questions avant de coder

Si je fais une erreur récurrente, dis-moi : *"ajoute une règle dans `.claude/rules/` pour t'empêcher de refaire ça"*.
