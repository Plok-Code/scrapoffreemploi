# Scrap'Offre Emploi — Tracker alternance AI Engineer

App web locale (Python + SQLite, sans Node.js) pour scraper, scorer et suivre des offres d'alternance "AI Engineer" en France, alignées avec le programme OpenClassrooms AI Engineer.

## Stack

- **Backend** : Python 3.13 + FastAPI + Uvicorn
- **DB** : SQLite (un seul fichier `data/app.db`)
- **Templating** : Jinja2 (HTML server-rendered)
- **Frontend** : HTMX 2.0 + Tailwind v3 via CDN (zéro build step, zéro Node.js)
- **Scraping** (à venir) : `httpx` + `beautifulsoup4` + `lxml`
- **Xlsx I/O** : `openpyxl` (migration et export uniquement)
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
```

## Architecture

```
scrapoffreemploi/
├── backend/
│   ├── __main__.py             # python -m backend → uvicorn
│   ├── main.py                 # FastAPI app + toutes les routes web/API
│   ├── db.py                   # connexion SQLite + helpers
│   ├── schema.sql              # DDL (1 table offers + scrape_runs)
│   ├── models.py               # Pydantic + constantes (statuts, labels, mapping score)
│   ├── queries.py              # CRUD + filtres + stats (couche d'accès données)
│   ├── migrate_xlsx.py         # one-shot xlsx -> SQLite (préserve le xlsx)
│   ├── scrapers/               # À VENIR : 1 fichier par source
│   ├── templates/              # Jinja : base, offers, offer_detail
│   └── static/                 # CSS minimal (Tailwind via CDN)
├── data/                       # gitignored
│   ├── app.db                  # SQLite, source de vérité
│   ├── batches/                # JSON offres à scorer (échange avec moi)
│   ├── scrapes/                # raw outputs scraping par run
│   ├── exports/                # xlsx générés à la demande
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
- **Le schéma DB** → `backend/schema.sql`
- **Une requête SQL** → `backend/queries.py` (toujours passer par là, jamais d'inline SQL ailleurs)
- **Une route HTTP** → `backend/main.py` (toutes les routes y sont, séparées si la liste grossit)
- **Le scoring LLM** → `backend/models.py` (constantes), workflow décrit ci-dessous
- **La migration xlsx** → `backend/migrate_xlsx.py` (NE PAS toucher au xlsx original)
- **Une vue HTML** → `backend/templates/offers.html` ou `offer_detail.html`

## Données du projet

- **194 offres** dans `data/app.db` (table `offers`), migrées depuis le xlsx du 12 mai 2026
- **71 entreprises cibles** en "candidature spontanée" sauvées dans `data/companies_spontaneous_extracted.json` pour la phase 2
- Le xlsx **source de vérité historique** : `data/source/candidatures_alternance_AI_Engineer.xlsx` (gitignored, dans le projet)

## Règles non-négociables

1. **JAMAIS toucher au xlsx** `data/source/candidatures_alternance_AI_Engineer.xlsx` — lecture seule uniquement. Si tu dois modifier des données, fais-le dans SQLite. (Le xlsx est conservé pour audit et migration ; la SQLite est la source de vérité vivante.)
2. **JAMAIS d'API Anthropic** — pas de clé. Le scoring LLM passe par ce chat Claude Code Max (workflow batch ci-dessous).
3. **Toujours passer par `queries.py`** pour les accès DB — pas de SQL inline dans `main.py` ou les templates.
4. **Mojibake** : les fichiers source du xlsx avaient des problèmes d'encodage (cp1252). La fonction `fix_mojibake()` dans `migrate_xlsx.py` gère ça — réutiliser si nouveau import.
5. **Encoding PowerShell** : pour les print Unicode, toujours `$env:PYTHONIOENCODING="utf-8"` avant les commandes Python sinon les `é` deviennent `?`.
6. **Pas de Node.js, pas de build step** — si tu envisages d'ajouter du React/Vite/Webpack, STOP et propose une alternative en HTMX/Jinja.

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
- **vide** = pas encore postulé
- `Postulé`, `Relancé`, `Entretien`, `Test technique`, `Refusé`, `Accepté`, `Sans réponse`, `Abandonné`

Le champ séparé `application_method` (libre) sert pour les notes "Portail officiel recommandé / Email RH / etc." — ne PAS le mélanger avec `status`.

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
