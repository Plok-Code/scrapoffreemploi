# Changelog

Toutes les modifs notables de ce projet seront documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [Unreleased]

### Added — Sprint qualité (14 mai 2026) : audit GPT — Vague 4 (CHECK constraints DB)

Le point « contraintes DB faibles » de l'audit GPT est traité : les enums
(`status`, `priority`, `remote`, `match_label`) et les bornes numériques
(`match_score ∈ [0,100]`, `score_* ∈ [0,20]`, `is_active ∈ {0,1}`) sont
maintenant **enforced côté SQLite** via `CHECK` constraints. Un script
seed/migration ou un futur scraper buggué ne peut plus polluer la DB avec
des valeurs hors-grille — l'INSERT est rejeté avec `CHECK constraint failed`
avant que la donnée touche la table.

Validation côté Python (Pydantic models + `_validate_enum`) restait en
place — c'est de la défense en profondeur : 2 lignes contre les valeurs
invalides.

#### Migration 002 (recréation de table)

- **`backend/migrations/002_check_constraints.sql`** : SQLite ne supporte
  pas `ALTER TABLE ADD CONSTRAINT`, donc la migration recrée `offers` et
  `target_companies` avec les CHECK, copie les données via
  `INSERT INTO ... SELECT` (colonnes nommées explicitement), drop l'ancienne,
  rename la nouvelle, recrée les 7 indexes sur `offers` + 4 sur
  `target_companies` + les 2 triggers `updated_at`.
- **Pré-validation des données** : audit avant migration a confirmé que
  toutes les valeurs existantes (1189 offers, ~250 target_companies)
  respectent les contraintes envisagées — la migration s'applique sans
  rollback.
- **Synchro avec `models.py`** : les listes énumérées dans les CHECK
  reflètent exactement `VALID_STATUSES`, `VALID_PRIORITIES`, `VALID_REMOTE`,
  `MATCH_LABELS`, `VALID_COMPANY_STATUSES`. Commentaire en tête du fichier
  documente la règle "modif d'un VALID_* → nouvelle migration 00X".

#### CHECK constraints appliquées

Sur `offers` :
- `remote` ∈ {NULL, 'Oui', 'Non', 'Hybride'}
- `match_label` ∈ {NULL, 'Top', 'Bon', 'Moyen', 'Faible'}
- `status` ∈ {NULL, Postulé, Relancé, Entretien, Test technique, Refusé,
  Accepté, Sans réponse, Abandonné, Pas intéressé}
- `priority` ∈ {NULL, 'Haute', 'Moyenne', 'Basse'}
- `match_score` ∈ [0, 100] (ou NULL)
- `score_pipeline / exploration / modelisation / deploiement / cadrage`
  ∈ [0, 20] (ou NULL)
- `is_active` ∈ {0, 1}

Sur `target_companies` :
- `priority` ∈ {NULL, 'Haute', 'Moyenne', 'Basse'}
- `status` ∈ {NULL, Contacté, Relancé, Entretien, Refusé, Sans réponse,
  Abandonné} (≠ VALID_STATUSES des offers — `Postulé` n'est pas valable
  pour une entreprise cible).

#### Tests

- **`tests/test_check_constraints.py`** : 112 cas parametrisés, ~12s.
  Couvre pour chaque colonne contrainte : valeurs valides acceptées (dont
  NULL), valeurs invalides rejetées avec `sqlite3.IntegrityError`
  ("CHECK constraint failed: ..."). Inclut le bypass via `sqlite3` direct
  pour valider que la défense agit au niveau **DB** (pas seulement Python).
  Tests de non-régression sur `queries.insert_offer` / `update_offer` pour
  s'assurer que le filet ne casse pas les flux légitimes.

#### Validation E2E

- Migration v2 appliquée sur la DB du user (1189 offers + ~250 companies)
  en ~0.5s, aucune donnée perdue, tous les indexes et triggers recréés.
- `pytest tests/ -q` : **256 passed in ~19s** (144 → 256, +112 tests
  CHECK constraints).
- `bandit -r backend cli.py` : **0 issues** (stdout, exit 0).
- Smoke test : 18 routes OK, `schema_version=2`, stats total=1189.

### Added — Sprint qualité (14 mai 2026) : audit GPT — Vague 3 (migrations versionnées)

Le point « migrations trop artisanales » de l'audit GPT est traité : on
remplace les `ALTER TABLE ... if column not in cols` éparpillés dans
`init_schema()` par un vrai runner de migrations versionnées avec table
de tracking. Compatibilité : la DB du user (1189 offres, backups) est
préservée — la migration v1 est marquée appliquée sans rien re-créer
(CREATE IF NOT EXISTS).

#### Système de migrations

- **`backend/migrations/`** : dossier de fichiers SQL numérotés (convention
  `{NNN}_<descripteur>.sql`).
- **`backend/migrations/001_initial.sql`** : baseline = schéma courant complet
  (offers + target_companies + scrape_runs + indexes + triggers). Idempotent
  via `CREATE TABLE IF NOT EXISTS` pour gérer les DB existantes.
- **`backend/_migrations.py`** : runner avec `apply_migrations()` (itère sur
  les fichiers triés par version, applique en transaction ceux absents de
  `schema_migrations`, log chaque application) + `current_schema_version()`
  (max version appliquée, 0 si aucune).
- **Table `schema_migrations(version INTEGER PK, name TEXT, applied_at TEXT)`** :
  créée automatiquement au premier `apply_migrations()`.
- **Tri par version numérique** : `010_xxx.sql` vient après `002_xxx.sql`
  (pas de surprise lexicographique).
- **Validation au chargement** : doublons de version → `RuntimeError` clair ;
  fichiers mal nommés → ignorés avec `logger.warning`.
- **Rollback transactionnel** : si une migration SQL invalide casse, la
  transaction est rollback et l'exception remonte — les migrations suivantes
  ne sont pas tentées (état DB cohérent).

#### Intégration

- **`backend/db.py:init_schema()`** : simplifié — appelle juste
  `apply_migrations()`. Les anciens `ALTER TABLE ADD COLUMN IF...` (4 colonnes,
  un DROP INDEX) sont supprimés (formalisés dans la migration 001).
- **`backend/schema.sql`** : conservé comme **référence documentaire** du
  schéma final (vue synthétique). Plus appliqué directement par l'app.
  Header banderole explicite. Pour évoluer, créer une nouvelle migration.

#### Tests

- **`tests/test_migrations.py`** : 14 nouveaux tests, ~0.8s. Couvre :
  application sur DB vide, sur schéma pré-existant, idempotence, tri
  numérique des versions, ignorance des fichiers mal nommés, doublons de
  version → RuntimeError, rollback transactionnel sur SQL invalide,
  table `schema_migrations` (colonnes, applied_at), `current_schema_version()`
  retours 0 / max version, alias `init_schema()`.

#### Validation E2E

- DB du user (1189 offres) : `apply_migrations()` appliquée → v1 marquée
  appliquée sans re-créer les tables (no-op SQL), aucune donnée perdue.
- `pytest tests/ -q` : **144 passed in ~4.6s** (130 → 144, +14 migration tests).
- `bandit -r backend cli.py` : **0 issues** (stdout, exit 0).
- Smoke test `from backend.main import app` : 18 routes OK, stats total=1189,
  schema_version=1.

### Added / Changed — Sprint qualité (13 mai 2026) : audit GPT — Vague 1 + 2

Suite à un audit externe (cf branche `claude/intelligent-easley-f22566`),
nettoyage qualité des 7 points soulevés. Pas de changement fonctionnel
user-facing — l'app continue de marcher pareil, mais la base est plus saine.

#### Vague 1 — Quick wins observabilité / sécurité / reproductibilité

- **Observabilité scraping** : les `except Exception as e: ... _SCRAPE_STATE["error"] = str(e)` (2 dans `main.py`, 2 dans `runner.run_full_scrape`) capturent maintenant le traceback complet via `logger.opt(exception=True).warning(...)` dans `data/logs/errors.log`. Le `str(e)` reste affiché en UI pour le user, mais le diagnostic d'un scraper qui casse devient instantané.
- **Bandit clean** : 17 alertes B608 (faux positifs SQL f-string) résolues. Refactor de `queries.get_stats()` en littéraux SQL constants (9 lignes → 0 f-string). 11 autres lignes annotées `# nosec B608` au format strict (sans `:` ni texte après — bandit parsait les mots comme test IDs). Config bandit centralisée dans `pyproject.toml`. **Default invocation `bandit -r backend cli.py` = 0 issues, exit 0**.
- **`pyproject.toml`** créé avec `[tool.bandit]` (config) + `[tool.pytest.ini_options]` (testpaths + `-ra --strict-markers`).
- **Flag `generate_batch=True`** ajouté à `run_full_scrape()` + propagé au bg task `_run_full_scrape_bg` + exposé via `POST /api/scrape` (Form param). Quand activé, agrège les `new_ids` de tous les scrapers et appelle `matching.export_batch_to_score(only_ids=new_ids)` → écrit `data/batches/{date}_to_score.json` pour scoring LLM précis via chat. Param `only_ids: list[int] | None = None` ajouté à `export_batch_to_score`. Nouveau champ `batch_file: str | None` sur `FullScrapeResult` et `_SCRAPE_STATE`.
- **`requirements.lock`** généré via `pip-compile` (pip-tools) : 35 lignes (deps directs + transitives) avec versions exactes, commentaires `# via X` pour traçabilité. Header documentaire pour régénération. Plateforme Windows + Python 3.13.
- **README.md** : Quickstart mis à jour (2 modes d'install : `.lock` pour reproductible, `.txt` pour dev), section "Limitations connues" (RAM state, bind 127.0.0.1, no auth, Tailwind), section "Qualité du code" avec commandes pytest/bandit/smoke.

#### Vague 2 — Tailwind vendoré localement

- **`backend/static/tailwind-3.4.17.min.js`** : bundle Tailwind v3.4.17 final stable téléchargé localement (407 KB). Plus aucune dépendance réseau au runtime. Hash SRI sha384 calculé : `sha384-igm5BeiBt36UU4gqwWS7imYmelpTsZlQ45FZf+XBn9MuJbn4nQr7yx1yFydocC/K`.
- **`backend/templates/base.html`** : `<script src="https://cdn.tailwindcss.com">` remplacé par `<script src="/static/tailwind-3.4.17.min.js" integrity="sha384-..." crossorigin="anonymous">`. HTMX 2.0.4 garde son SRI existant.
- **README** : section Limitations Tailwind mise à jour + commande de mise à jour documentée.

#### Bilan vague 1+2

- **126 tests pytest** OK (~3s, sans network)
- **0 issues bandit** (default invocation, stdout, exit 0)
- **13 fichiers** touchés (10 modifs + 3 créés : `pyproject.toml`, `requirements.lock`, `tailwind-3.4.17.min.js`)
- **Aucune régression fonctionnelle** — comportement utilisateur strictement identique

### Added — Sprint 2 (12 mai 2026 soir) : "Tout scraper" en un clic + cleanup auto + Toulouse

#### Bouton "Tout scraper" (mode recommandé)
- **API** : `POST /api/scrape` accepte maintenant `source=all` → lance le workflow complet en arrière-plan via `run_full_scrape()` :
  1. **Cleanup** : ping toutes les URLs existantes (Workday API JSON inclus, soft-404 detection 4 niveaux).
  2. **Scrape multi-sources** : FT (API officielle) → WTTJ (Algolia) → HelloWork (HTML+JSON-LD), dédup automatique (URL + dedup_key titre+entreprise).
  3. **Scoring auto** : `apply_heuristic_to_unscored()` post-scrape → toutes les nouvelles offres ont un score immédiatement.
- **`_SCRAPE_STATE`** enrichi avec : `step`, `deleted_dead`, `archived_dead`, `scoring_applied`, `per_source` (détail par scraper).
- **UI** : panneau "Scraper" repensé avec 2 modes — "Tout scraper (recommandé)" en bouton emerald principal + section repliée pour scraper une seule source. Status display détaillé (delete/archive/scoring counters + breakdown par source).

#### Cleanup auto des URLs mortes (avec règle métier)
- **`backend/scrapers/runner.cleanup_dead_unstatused()`** : ping HTTP de chaque URL, applique la règle :
  - URL morte (404/410/soft-404/Workday API 404) **+ status NULL** → `DELETE` de la DB (offre supprimée définitivement)
  - URL morte **+ status NOT NULL** (postulé/refusé/entretien/etc.) → `is_active = 0` (archivée pour l'historique applicatif)
  - URL vivante → `is_active = 1` (rafraîchit le statut)
  - 403/timeout → ne touche pas (ambigus)
- **`queries.delete_offer(offer_id)`** : helper pour DELETE direct (réservé au cleanup).
- Intégré automatiquement au début de `run_full_scrape(do_cleanup=True)`.

#### Page Entreprises — Toulouse + filtre ville + import depuis offres
- **Migration DB** : ajout colonnes `target_companies.city TEXT` et `target_companies.source TEXT` via ALTER conditionnel dans `init_schema()`.
- **`queries.extract_companies_from_offers_by_city(city_substr)`** : agrège les entreprises distinctes ayant des offres pour une ville donnée (matching LIKE %ville%).
- **`queries.import_companies_from_offers_to_targets(city_substr)`** : insère ces entreprises dans `target_companies` avec source `"offres-agrégées-{ville}"`, dédup sur LOWER(name).
- **Route** : `POST /api/companies/import-from-offers` (Form `city`) → import en un clic depuis l'UI.
- **UI** : 
  - Filtre **Ville** ajouté à la barre de filtres (`/companies?city=Toulouse`).
  - Nouvelle colonne **Ville** dans le tableau.
  - Bouton **"Importer depuis offres"** en haut de la page (formulaire avec input ville, défaut "Toulouse").
- **Résultat E2E sur Toulouse** : 14 entreprises importées (Thales, Sopra Steria, ONERA, CLS Ramonville, etc.) en plus des 65 du xlsx historique. Total target_companies = **79**.

#### La Bonne Boite v2 — tentative bloquée (HTTP 403)
- `backend/scrapers/labonneboite.py` codé (OAuth scope `api_labonneboitev2`, endpoint `partenaire/labonneboite/v2/company/`, params `latitude/longitude/distance/rome_codes`).
- **Test échoue avec 403** malgré scope valide et endpoint correct (vérifié via context7). Cause probable : l'API LBB v2 nécessite une **habilitation supplémentaire** côté FT au-delà de la simple souscription dans le catalogue.
- Décision : **skip LBB pour l'instant**, l'extraction depuis les offres scrapées (Toulouse a déjà 33+ offres avec city "31 - Toulouse") fait largement le job.

### Added — Sprint final 12 mai 2026 : UI complète + Page Entreprises + Scoring de masse

#### Page Entreprises (phase 2)
- **DB** : nouvelle table `target_companies` (15 colonnes : name, sector, relevance, priority, contact_channel, status, dates, notes, feedback, etc.) + index sur LOWER(name)/priority/status + trigger updated_at.
- **Migration** : import depuis `data/companies_spontaneous_extracted.json` → **65 entreprises** insérées (6 dédupliquées par nom).
- **`queries.py`** : `list_target_companies`, `get_target_company`, `update_target_company`, `get_company_stats`, `list_company_priorities`.
- **Routes** : `GET /companies` (liste + filtres priority/status/search/sort), `GET /companies/{id}` (détail), `POST /companies/{id}` (update tracking).
- **Templates** : `companies.html` (tableau + stats + filtres, palette rose/amber pour priorité Haute/Moyenne), `company_detail.html` (col gauche infos xlsx historique + col droite form tracking).
- **`models.py`** : nouvelle constante `VALID_COMPANY_STATUSES` (Contacté/Relancé/Entretien/Refusé/Sans réponse/Abandonné).
- **`base.html`** : nav avec liens "Offres" / "Entreprises" actifs selon page.

#### Bouton "Scraper" UI (avec progress live)
- **API** : `POST /api/scrape` (BackgroundTasks, accepte source+max_pages), `GET /api/scrape/status` (état in-memory).
- **`_SCRAPE_STATE`** : dict global (running, source, started_at, finished_at, total_fetched, total_new, total_duplicates, error).
- **UI** : `<details>` dans la nav → formulaire HTMX. Le statut se met à jour via `hx-trigger="load, every 3s"`. JS minimal pour formater le JSON renvoyé en HTML (running/error/done avec stats).

#### Filtre "Inclure archivées"
- `queries.list_offers(include_archived=...)` documenté + ajouté.
- `offers.html` : checkbox dans la barre de filtres. Quand cochée, affiche aussi les offres `is_active=0`.

#### Scoring heuristique automatique (v1 → v2)
- **`backend/heuristic_scorer.py`** : nouveau module. Compte les mots-clés techniques par axe (Pipeline/Exploration/Modélisation/Déploiement/Cadrage), poids variable (ex : `MLOps`=12, `LLM`=10, `RAG`=10, `Databricks`=9, `PyTorch`=7, etc.). Cap à 20 par axe.
- **Pénalités v2** (post-feedback "beaucoup de CDI dans le top heuristique") :
  - Stage (pas alternance) : −15
  - Senior / Confirmé / Tech Lead / Lead Data/ML/AI / Manager / Architecte / Expert / Directeur / Responsable : −12 à −20 chacun
  - BTS bac+2 : −8, formation à distance : −5
  - **Absence du mot "alternance/apprentissage" dans le texte : −25** (catch les CDI faussement taggés E1/E2 par FT)
- **Bonus v2** : Bac+5 / Master / Mastère : +4, "alternant"/"apprenti" explicite : +6, alternance+AI/ML engineer combo : +5.
- **CLI** : `python -m backend.heuristic_scorer [--rescore]` → `--rescore` ré-écrase aussi les scores déjà heuristiques.
- **Reasoning auto-marqué** : `auto:heuristic-v1 (total=X, axes=A+B+C+D+E)` → identifiable et écrasable par scoring manuel.

#### Re-scrape massif 12 mai 2026
Suite à amélioration des keywords (suppression du préfixe "alternance" qui réduisait inutilement les hits car `natureContrat=E1,E2` filtre déjà côté serveur FT) :
- **France Travail** : `cli.py scrape francetravail --max-pages 15` → 1070 fetched, **799 nouvelles** (271 doublons).
- **WTTJ** : `cli.py scrape wttj --max-pages 10` → 425 fetched, **162 nouvelles** (263 doublons).
- **HelloWork** : `cli.py scrape hellowork --max-pages 5` → 115 fetched, **40 nouvelles** (75 doublons).
- **Total : +1001 nouvelles offres** en une matinée.
- Scoring : heuristique v2 sur les 1001 → distribution `2 Top, 32 Bon, 125 Moyen, 842 Faible` (v1) puis après pénalités v2 → `0 Top, 9 Bon, 32 Moyen, 960 Faible` (filtre les CDI cachés).

#### Manual rescore du top 17 heuristique
Re-scoring manuel précis (5 axes /20) pour les 17 offres ≥50 heuristique :
- **10 vraies alternances** confirmées (Framatome IA CORP nucléaire 66 — meilleur du batch, NEXQT GeoData Scientist 55, EDF Concepteur Dév & IA 51, Brinks Data Engineer 51, Mousquetaires Data Factory ×2 56, etc.)
- **7 CDI/Senior cachés** descores à Faible 18-30 (Decathlon Data Scientist confirmé, GIO ML confirmé, TRIMANE Chef projet, RSM Data analyst, AKKODIS, ML engineer générique, Archives Luxembourg).

### Distribution finale au 12 mai 2026
```
Total actives  : 1543 (+1001 sur la journée)
🟢 Top (≥80)   :    5  (inchangé — Direct Assurance 84, Malakoff 82+81, MACIF 81, Schneider 80)
🟡 Bon (60-79) :  167  (+5 net après FT)
🟠 Moyen       :  306
⚪ Faible      : 1065
```

Sources avec offres Bon+ :
| Source | Total | Bon+ |
|---|---:|---:|
| WelcomeToTheJungle | 408 | 85 |
| Hellowork (toutes) | 217 | 46 |
| France Travail | 859 | 8 |
| Indeed | 23 | 14 |
| Career sites (Schneider/MAIF/MACIF/AXA/BPCE/etc.) | 30 | 14 |

### Added — Scraper France Travail via API officielle v2 (12 mai 2026)
- **Credentials gitignored** : `FRANCETRAVAIL_CLIENT_ID` / `FRANCETRAVAIL_CLIENT_SECRET` dans `.env` (déjà dans `.gitignore`). Lus via fonction maison (pas de dépendance python-dotenv).
- **`backend/scrapers/francetravail.py`** : OAuth2 client_credentials avec cache token in-memory (refresh auto avant les 25 min d'expiration). Scope `api_offresdemploiv2 o2dsoffre`. Endpoints :
  - Token : `https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire`
  - Search : `https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search` paginé par `range=0-49`
  - Détail : `https://api.francetravail.io/partenaire/offresdemploi/v2/offres/{id}`
- **Filtre serveur** : `natureContrat=E1,E2` (apprentissage + professionnalisation), `pays=FR`. Mots-clés via `motsCles`.
- **Filtre client** : `matches_keywords()` sur titre+description (élimine les faux positifs où FT renvoie un poste pas vraiment IA).
- **Rate limit** : 8 req/s respectées (plafond user activé = 10 req/s).
- **Pédagogique** : la création de compte FT côté user nécessite (a) créer l'app, **(b) explicitement souscrire à l'API "Offres d'emploi v2" via le catalogue**. Sans (b), token endpoint renvoie 400 `invalid_client` même si les credentials sont corrects.

### Résultat scrape FT — 12 mai 2026
- `python cli.py scrape francetravail --max-pages 5` → 57 fetched, **52 nouvelles** insérées (5 doublons).
- Toutes les 52 ont une description complète **directement dans la réponse search** (entre 449 et 3651 chars) — pas besoin d'appeler `fetch_detail()` séparément.
- Distribution scoring après applique (52 offres) :
  ```
  🟡 Bon (60-79) :  7
  🟠 Moyen       : 22
  ⚪ Faible      : 31
  ```
- **Top FT** : Boulogne-Billancourt Ad Tech (72, Databricks/Snowflake/Azure pour reco/CV/TimeSeries), ALE Guipavas (64, A.I. Operations GenAI+agents), Dassault Systèmes Versailles (61), Annecy Dev IA (60), Compagnie des Alpes Chambéry (60).
- Le top global du projet reste inchangé (5 Top ≥80 : Direct Assurance 84, Malakoff Humanis 82+81, MACIF 81, Schneider 80). Aucune offre FT ne perce le top 5 car la majorité des offres "alternance + IA" sur FT sont des postes mixtes (chef de projet, BTS SIO, dev logiciel avec petit volet IA) plutôt que du vrai IA Engineering.

### Distribution globale finale après FT
```
Total visibles : 545  (+52 FT, +13 nouveaux scorés)
🟢 Top (≥80)   :   5
🟡 Bon (60-79) : 169  (+5 net : 7 FT − 2 déjà existants par dedup)
🟠 Moyen       : ~275
⚪ Faible      : ~95
```

### Added — Scraper WTTJ via API Algolia (12 mai 2026)
- **`backend/scrapers/wttj.py`** : scraper Welcome To The Jungle via API publique **Algolia**. Clés publiques (App ID `CSEKHVMS53`, search key `4bd8f6215d0cc52b26430765769e65a0`) découvertes via MCP exa (repo `juan-azabal/jobagent`). Index `wttj_jobs_production_fr`. Filtre `(contract_type:apprenticeship OR contract_type:professional_training) AND offices.country_code:FR`.
- **Résultat E2E** : `python cli.py scrape wttj --max-pages 5` → 257 offres fetched, **242 nouvelles** insérées (15 doublons). Toutes ont description directement via Algolia (pas de fetch_detail séparé).
- **Scoring batch** : `data/batches/2026-05-12_wttj_242_scores.json` appliqué via `cli.py apply-scores` → 242 offres scorées en un coup. Distribution après scoring :
  ```
  🟢 Top (≥80)   :   5  (inchangé, aucune WTTJ ne perce le top 5)
  🟡 Bon (60-79) : 199  (+82)
  🟠 Moyen       : 258  (+100)
  ⚪ Faible      :  70  (+60 — marketing/admin/eng-non-IA filtrés trop largement)
  ```
- **Bug fixé pendant le dev WTTJ** : champ Algolia est `offices` (pluriel) pas `office`. Initial test retournait 0 hits avec `office.country_code:FR`. Fix : filtre + `_hit_to_raw` lisent `offices[0]`.

### Added — Cycle de vie des offres : `is_active` + `check-alive` (12 mai 2026)
- **Migration DB** : ajout colonnes `is_active INTEGER DEFAULT 1` et `last_checked_at TEXT` sur `offers`. Index `idx_offers_is_active`. Migration conditionnelle dans `init_schema()` via `PRAGMA table_info` + `ALTER TABLE`.
- **`queries.set_alive_state(offer_id, is_active=...)`** : marque l'offre active/archivée et stamp `last_checked_at`.
- **`queries.list_offers(include_archived=False)`** : par défaut filtre `is_active = 1` (offres archivées masquées de l'UI sauf flag explicite).
- **`queries.get_stats()`** : KPIs calculés sur offres actives uniquement + champ `archived` séparé.
- **`backend/scrapers/runner.check_alive(min_score, limit, sleep_between)`** : ping HTTP de chaque URL.
- **`cli.py check-alive [--min-score N] [--limit N] [--sleep s]`** : commande CLI.

### Added — Détection soft-404 (12 mai 2026, après feedback user)
**Problème identifié** : le check initial ne testait que le code HTTP. Or beaucoup
de career sites renvoient **HTTP 200 même quand l'offre est supprimée** : redirect
silencieux vers la home des offres, SPA qui affiche "n'existe plus" via JS, query
param `?not_found=true`, title `Erreur - Offre inexistante`, etc.

**Détection à 4 niveaux** dans `_is_soft_404()` :
1. Body : 18 patterns regex (`n'est plus disponible`, `no longer available`,
   `perdu cette page`, `résultats de la recherche`, etc.)
2. Title : 8 patterns (`erreur.*inexistante`, `current openings`, `404`, etc.)
3. URL finale après redirects : `?not_found=true`, `/404`, `trk=expired_jd_redirect`,
   ou URL finale < 50% de la longueur originale (= redirigé vers home liste).
4. Workday-specific : probe direct l'API JSON `wd/cxs/{tenant}/{site}/job/{id}` car
   les pages Workday sont des SPAs purs (HTML inutile).

**Validation sur 6 URLs confirmées mortes par user** : AXA ✅, Workable HF ✅,
CEA ✅, Studyrama ✅, Renault Workday ✅ (via API), Nokia ❌ (SPA Phenom People,
title générique). Soit **5/6 = 83%** d'auto-détection.

**Exécution E2E finale** : `cli.py check-alive` → 472 offres pingées, **39 marquées
archived** au total :
- 14 archivées manuellement après confirmation user (HF Workable, JobTeaser AXA,
  AXA recrutement x3, Argus, BPCE x2, HSBC, Safran, Studyrama, Renault, CEA, Nokia)
- 13 détectées via HTTP 404/410 (Lever Mistral, BCG X, SG, Bordeaux-Emplois,
  Engagement-Jeunes Airbus x2, Agefiph, Schneider careers.se.com, Sanofi, LinkedIn obsolète)
- 11 détectées via soft-404 (LinkedIn redirects, Renault Workday API 404,
  IDEMIA / Naval Group / CEVA / EPSI / Chanel / Crédit Mutuel Arkéa LinkedIn,
  Thales x2 expirées, Airbus expirée, Danone, OpenClassrooms x3, etc.)

Distribution finale après cleanup :
```
Total visibles : 493  (-39 archived)
🟢 Top (≥80)   :   5
🟡 Bon (60-79) : 164
🟠 Moyen       : 254
⚪ Faible      :  70
```
Top 5 inchangé : Direct Assurance (84), Malakoff Humanis (82, 81), MACIF (81), Schneider Electric (80).

### Fixed — Score Criteo Internship réajusté (12 mai 2026)
Après récupération de la description complète (via user qui a copié-collé la page),
**Criteo Machine Learning Engineer Intern** réévalué : titre brut "ML Engineer
Intern" sans contexte → 74. Avec description : c'est un **stage** (pas alternance),
focus modélisation pure (multi-task two-tower DL avec PyTorch), peu de MLOps explicite,
Spark/Ray en "nice to have". Score recalculé : 8+12+17+8+9 = **54 (Moyen)**. La règle
"alternance uniquement" est respectée — note ajoutée dans `match_reasoning`.

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
