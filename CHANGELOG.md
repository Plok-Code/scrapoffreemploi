# Changelog

Toutes les modifs notables de ce projet seront documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [Unreleased]

### Added
- Setup Claude Code complet : `CLAUDE.md`, `.claude/settings.json`, 6 rules modulaires (`workflow`, `code-style`, `database`, `routes`, `templates`, `scrapers`), 3 sub-agents (`explore-codebase`, `explore-doc`, `web-search`), 4 skills (`apex` multi-step, `one-shot`, `debug`, `review-code`).
- Mode `bypassPermissions` avec deny list adaptée Windows (Bash + PowerShell).
- `docs/SOURCES.md` : liste structurée et triée par priorité des sources à scraper (jobboards prioritaires, tech/IA spécialisés, plateformes alternance, pages carrières par secteur, recherche publique, hubs). Inclut tiers de difficulté de scraping, mots-clés de filtrage, notes anti-bot, plan MVP. **Update via MCP exa** : WTTJ reclassé T2 → T1 avec credentials Algolia publiques documentées (§11).
- `docs/CRITERIA.md` : grille de scoring complète (5 axes /20 chacun → total /100), heuristiques par axe, workflow batch JSON, schémas I/O, prompt de référence pour le LLM (moi dans le chat).
- **MCPs installés** (user scope, dans `C:\Users\novar\.claude.json`) :
  - `context7` (https://mcp.context7.com/mcp) — doc à jour des libs Python
  - `exa` (https://mcp.exa.ai/mcp) — recherche web sémantique
  - Les deux utilisent transport `http` avec endpoint `/mcp` (pas `/sse`).
- **`backend/matching.py`** : `export_batch_to_score()` (génère `data/batches/{date}_to_score.json`), `parse_scores_file()`, `apply_scores_from_file()`, `list_batches()`, `latest_batch()`.
- **`cli.py`** à la racine avec commandes : `stats`, `export-batch`, `apply-scores PATH`, `scrape SOURCE`, `list-batches`.
- **Infrastructure scrapers** :
  - `backend/scrapers/base.py` : ABC `Scraper` + dataclass `RawOffer`.
  - `backend/scrapers/_http.py` : session httpx mutualisée (User-Agent Chrome, retry exponentiel, sans brotli).
  - `backend/scrapers/_keywords.py` : regex compilée de tous les mots-clés IA/data.
  - `backend/scrapers/registry.py` : `SCRAPERS = {"hellowork": ...}` + `get_scraper(name)`.
  - `backend/scrapers/runner.py` : orchestrateur `run_scrape(source)` qui scrape, dédoublonne via `queries.insert_offer()`, génère le batch, log dans `scrape_runs`.
- **`backend/scrapers/hellowork.py`** : scraper HelloWork **opérationnel** (httpx + BeautifulSoup). Parse `[data-cy=serpCard]` (30 cartes/page), extrait titre/entreprise via le DOM et city/dept/contract/salaire via l'`aria-label`. Filtre alternance + mots-clés IA. Pagination par `&p={n}`.
- **`queries.insert_offer()` + `queries.record_scrape_run()`** : dédup en 2 niveaux (URL puis `dedup_key`), audit dans `scrape_runs`.

### Test E2E réussi
- `python cli.py scrape hellowork --max-pages 2` → 123 offres fetched, **96 nouvelles** insérées en DB, 27 doublons skippés. Total DB : 194 → **290 offres**. Batch `data/batches/2026-05-12_to_score.json` généré.

### Bugs résolus pendant le dev
- httpx ne décode pas brotli par défaut → retiré `br` de `Accept-Encoding` (sinon HTML reçu compressé en binaire).
- Regex aria-label initiale était trop greedy → rewrite via split sur `", "` séparateurs (plus robuste).
- **Descriptions manquantes** : `fetch_detail()` initial parsait juste le HTML brut. Découverte (via inspection page détail HelloWork) que chaque page contient un **JSON-LD `JobPosting`** avec description complète (3-10k chars). `fetch_detail()` refactor pour parser ce JSON-LD en priorité (fallback HTML brut). Effet : descriptions passent de vides à 3000-9000 chars. Détection bonus : offres expirées révélées (description = juste menu HelloWork → scores tombent en Faible).

### Scoring loop bout en bout — démontré
- 290 offres exportées en batch (`cli.py export-batch`)
- Scorées via chat Claude (5 axes /20) → `data/batches/2026-05-12_scores.json`
- `cli.py apply-scores` → 290 offres màj en DB
- Re-score progressif après enrichissement descriptions (HelloWork + MCP Chrome + Playwright) → **5 Top** émergent :
  - 84 Direct Assurance (AXA) — Databricks/MLflow/Kedro/Pydantic/PySpark
  - 82 Malakoff Humanis — 120 experts IA, data/model drift, MLflow CI/CD
  - 81 Malakoff Humanis (Indeed) — idem via MCP Chrome
  - 81 MACIF — MLOps Document AI, Evidently AI
  - 80 Schneider Electric — GenAI + CV + agentic + garde-fous

### MCP Claude-in-Chrome — workflow scrape semi-auto validé
- Découverte : `js_exec` retourne output tronqué ~1024 chars. Solution : `console.log` + `read_console_messages` permet de récupérer 10k+ chars complets.
- 8 offres enrichies via MCP (Indeed redirige sur les sites carrière : Malakoff, LVMH, Natixis, SFR, STMicro, Michelin, Schneider, Malakoff RAG).
- Re-score ces 8 → 4 nouvelles Top (149 Malakoff MLOps, 142 Schneider GenAI+CV à 80+).

### Playwright (installé) — setup pour scrape LinkedIn loggué
- Ajout `playwright==1.56.0` + `backend/scrapers/_playwright.py` (helper `persistent_browser` avec user_data_dir = `data/.playwright_profile/`).
- `backend/scrapers/linkedin_login.py` : script standalone pour login manuel (lance Chromium visible, attend que l'utilisateur se connecte, sauve les cookies).
- `backend/scrapers/linkedin.py` : `fetch_detail()` tente Playwright d'abord (si profil existe), fallback httpx.
- **Limitation découverte** : les 16 offres LinkedIn de la DB (datant 2024-2025) sont **toutes expirées** côté LinkedIn — Premium ou non, LinkedIn supprime l'annonce de son index public et redirige vers une page de recherche (`?trk=expired_jd_redirect`). Marquées en DB avec description "(LinkedIn — URL expirée, annonce retirée de l'index public)" pour ne plus re-tenter.

### Distribution actuelle (290 offres)
```
🟢 Top (≥80)   :   5
🟡 Bon (60-79) : 117
🟠 Moyen       : 158
⚪ Faible      :  10
```

### Changed
- **xlsx déplacé** dans le projet : `C:\Users\novar\Downloads\` → `data/source/candidatures_alternance_AI_Engineer.xlsx`. Toutes les références mises à jour (`backend/migrate_xlsx.py`, `CLAUDE.md`, `.claude/settings.json`, `.claude/rules/workflow.md`, `.claude/skills/apex/steps/02-analyze.md`).
- `.gitignore` étendu pour ignorer `.claude/.tmp/`, `.claude/sessions/`, `.claude/settings.local.json`.

### Removed
- `deep-research-report.md` à la racine du projet (contenu refactor + complété dans `docs/SOURCES.md`).

## [0.1.0] — 2026-05-12

### Added
- Structure projet propre : `backend/`, `data/`, `docs/`, `legacy/`, `reference/`.
- Backend FastAPI (`backend/main.py`) : routes `/`, `/offers/{id}`, `POST /offers/{id}`, `/api/stats`, `PATCH /api/offers/{id}`.
- Couche d'accès données `backend/queries.py` : `list_offers` (filtres search/status/source/min_score/sort), `get_offer`, `update_offer`, `apply_llm_scores`, `get_stats`, `list_sources`, `list_distinct_statuses`.
- Schéma SQLite `backend/schema.sql` : table `offers` (24 colonnes) + `scrape_runs`, index, triggers.
- Helpers DB `backend/db.py` : context manager `db()`, `init_schema()`, `make_dedup_key()`, `normalize_for_dedup()`.
- Pydantic models et constantes `backend/models.py` : statuts/priorités/remote valides, `label_for_score()`, `LLMScoreBreakdown`.
- Migration `backend/migrate_xlsx.py` : import 194 offres + extraction de 71 entreprises "cibles candidature spontanée" en JSON.
- Templates Jinja : `base.html`, `offers.html` (tableau + filtres + stats), `offer_detail.html` (breakdown 5 axes + form tracking).
- Configuration : `requirements.txt`, `run.ps1` (lancement Windows), `README.md`, `.gitignore`.

### Changed
- **Rebuild complet** depuis l'ancien scrapoffreemploi (20+ scripts Python éparpillés) vers une vraie app web locale.
- Stack figée : FastAPI + SQLite + Jinja + HTMX + Tailwind v3 CDN (zéro Node.js, zéro build step).
- Statuts d'une offre clarifiés : vide = pas postulé, sinon `Postulé/Relancé/Entretien/Test technique/Refusé/Accepté/Sans réponse/Abandonné`. Le champ séparé `application_method` accueille les notes "Portail officiel recommandé / Email RH" qui polluaient la colonne Statut du xlsx historique.
- Grille de scoring redéfinie : 5 axes /20 (Pipeline, Exploration, Modélisation, Déploiement, Cadrage) = total /100. Labels Top (≥80) / Bon (60-79) / Moyen (40-59) / Faible (<40).

### Migrated
- 194 offres scrapées (Table_1 du xlsx) → SQLite, encoding corrigé (mojibake cp1252→utf-8).
- 71 entreprises cibles spontanées (Tables 2-6 du xlsx) → `data/companies_spontaneous_extracted.json` pour la phase 2 (page "Entreprises").

### Archived (dans `legacy/`)
- 18 scripts Python one-shot (`apply_match_scores.py`, `build_xlsx*.py`, `compute_match.py`, `merge_*.py`, `fix_*.py`, etc.).
- 10 fichiers JSON intermédiaires (`all_match_scores.json`, `all_sources_merged.json`, `oc_ai_engineer_jobs.json`, etc.).
- 2 snapshots de scraping : `sources_2026_05_04/` et `sources_2026_05_11/` (15 sources chacun).
- Anciens batches : `url_batches/`, `score_batches/`.
- Backup xlsx `1candidatures_alternance_AI_Engineer-1.xlsx`.

### Constraints
- Le xlsx source est désormais **dans le projet** à `data/source/candidatures_alternance_AI_Engineer.xlsx` (déplacé depuis `C:\Users\novar\Downloads\`) et reste en **lecture seule**. La SQLite est la nouvelle source de vérité pour les données vivantes.
- Pas de clé API Anthropic dans le projet. Le scoring LLM passe par le chat Claude Code Max (workflow batch JSON : app génère `data/batches/*.json` → Claude lit/score dans le chat → user lance `python cli.py apply-scores`).
