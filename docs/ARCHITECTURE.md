# Architecture

Scrap'OffreEmploi est une application locale FastAPI + Jinja + SQLite pour suivre des offres d'alternance AI Engineer et des entreprises cibles.

## Principes

- **Local-first** : l'app écoute sur `127.0.0.1:8000`, stocke tout dans `data/app.db`, et ne vise pas le multi-utilisateur.
- **Préservation des données** : les scrapes et cleanups archivent par défaut via `is_active=0` plutôt que supprimer définitivement.
- **Scraping best-effort** : chaque source est indépendante ; un échec de source ne bloque pas les autres.
- **Scoring séparé** : le score heuristique sert au tri rapide, le scoring manuel via batch JSON reste disponible.

## Flux Principal

1. `run.ps1` lance `python -m backend`, qui démarre FastAPI.
2. Au boot, `backend.db.init_schema()` crée ou migre le schéma SQLite.
3. L'UI appelle `/api/scrape` pour planifier un scrape en tâche background.
4. `backend.scrapers.runner.run_full_scrape()` enchaîne cleanup, job boards, portails, filtre alternance et scoring heuristique.
5. Les offres sont listées avec pagination côté serveur, filtres SQL paramétrés, et templates Jinja échappés.

## Modules

- `backend/main.py` : routes web/API, middleware CSRF local, état de scrape.
- `backend/queries.py` : accès SQLite, filtres, pagination, updates whitelistés.
- `backend/scrapers/` : scrapers par source, helpers HTTP/Playwright et orchestration.
- `backend/matching.py` : export/import des batches de scoring.
- `backend/filter_alternance.py` : classement alternance vs hors-scope.
- `backend/heuristic_scorer.py` : scoring automatique par mots-clés pondérés.

## Données

- `offers` : offres scrapées, scoring, suivi utilisateur, archivage.
- `target_companies` : entreprises pour candidature spontanée.
- `scrape_runs` : historique synthétique des runs.
- `data/` : DB, logs, batches, backups et profil Playwright, volontairement gitignored.

## Garde-Fous

- URLs d'offres validées en `http(s)` dans `RawOffer`.
- Liens rendus avec le filtre Jinja `safe_href`.
- Mutations bloquées si `Origin` ou `Referer` externe.
- Scrape global protégé contre le double lancement par verrou mémoire.
- Tests couvrant sécurité, rendu HTML, déduplication, soft-404, filtre alternance et batches.
