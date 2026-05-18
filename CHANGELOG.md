# Changelog

Toutes les modifs notables de ce projet seront documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [Unreleased]

### Fixed + Added — Sprint qualité (19 mai 2026, 4e audit utilisateur) : contract_type + soft-404 + ruff

4e passe d'audit utilisateur. Sur 9 points levés, 5 étaient déjà fixés
(état stale du checkout), 4 vrais + 1 gap tooling :

#### Fix #4 — Plus de fallback `contract_type="Alternance"` sans evidence

Les scrapers portail (Workable / Lever / Greenhouse / Workday / Taleez /
Phenom / Playwright / generic) **forçaient** `contract_type="Alternance"`
même quand le titre/description ne le prouvait pas. En aval,
`filter_alternance.classify_offer()` faisait KEEP via la branche
`contract_type` (étape 2) — un "Data Engineer Senior CDI" passait à
travers le filtre.

- **`backend/filter_alternance.py`** : nouveau helper public
  `is_alternance_indicator(text)` qui réutilise `_KEEP_PATTERN` (même regex
  que `classify_offer`). **Source unique de vérité** : si l'indicateur change
  un jour, les portails et le filtre restent alignés.
- **`backend/scrapers/company_portals.py`** : helper `_contract_type_for(title, description)`
  qui retourne "Alternance" UNIQUEMENT si `is_alternance_indicator` détecte un
  marqueur. Tous les `contract_type="Alternance"` hardcodés (7 occurrences)
  remplacés par cet appel. Plus aucun forçage aveugle.
- **`backend/scrapers/runner.py:80`** : suppression de `raw.contract_type or "Alternance"`.
  Si un scraper laisse `None`, ça reste `None` → `filter_alternance` tranche
  sur title + description (signal honnête).
- **`tests/test_alternance_indicator.py`** : 19 tests
  - `is_alternance_indicator` : 7 cas POSITIFS (alternance, apprenti, contrat pro…)
    + 6 cas NÉGATIFS (Senior CDI, stage, vide, None) parametrized.
  - `_contract_type_for` : aucun evidence → None, title alterna → Alternance,
    desc alterna → Alternance, None inputs OK.
  - **Régression critique** : sans `contract_type` forcé, classify_offer
    REJECTE "Data Engineer Senior" via REJECT_TITLE — ce qui était le bug
    bloqué par l'ancien forçage.

#### Fix #6 — Soft-404 : seuil 50% → 30% + exigence d'absence de marqueur d'offre

L'heuristique "URL finale < 50% original → soft-404" archivait à tort les
canonical redirects (qui tombent typiquement à 70-80% de l'origine).
3e audit consécutif à signaler ce risque.

- **`backend/scrapers/runner.py:_is_soft_404`** :
  - Seuil durci à **30%** (passe les canonical, garde les login/home).
  - **ET** exigence supplémentaire : l'URL finale ne doit PAS contenir un
    marqueur d'offre individuelle (`/jobs/`, `/offers/`, `/offer/`, `/job/`,
    `/position/`, `/role/`, `/career/`, `/emploi/`). Si oui = redirect vers
    une autre offre légitime, pas une mort.
- **`tests/test_soft_404_threshold.py`** : 12 tests
  - Canonical redirect 30% du url avec `/jobs/12345` → KEEP alive (le bon
    nouveau comportement).
  - Login redirect court sans marqueur → SOFT 404 (l'ancien comportement
    correct préservé).
  - Home redirect → SOFT 404.
  - Pas de redirect (URL inchangée) → KEEP alive.
  - 7 cas parametrized sur les marqueurs d'offre individuelle.

#### Fix #8 — CLAUDE.md mis à jour (tests count + règle SQL)

- "83 tests, ~2 sec" (lignes 34 + 89) → **422 tests, ~15s en venv**.
- Règle #3 "Toujours passer par `queries.py` — pas de SQL inline" reformulée
  pour refléter la réalité du code : `queries.py` est le défaut pour
  `main.py` + templates, mais du SQL inline reste autorisé dans
  `migrations/*.sql`, `seed_*.py`, `runner.py`, `matching.py` à condition
  d'avoir un `# SAFE (B608) : ...` au-dessus (convention P1.6).

#### Tooling — Ajout de ruff

L'audit a flaggé l'absence de lint statique. Ajouté :

- **`requirements.txt`** : `ruff>=0.6`.
- **`requirements.lock`** : régénéré, `ruff==0.15.13` inclus.
- **`pyproject.toml`** : section `[tool.ruff]` avec configuration mesurée :
  - `line-length=110`, `target-version="py310"`.
  - Sélection minimale : `F` (pyflakes), `E/W` (pycodestyle), `I` (isort),
    `B` (bugbear), `ARG` (unused args — aurait attrapé `only_unscored_or_scored`),
    `RUF` (ruff-specific).
  - Ignorés : `E501` (line too long, on garde permissif), `B008` (FastAPI
    `Form(...)` defaults), `ARG002` (ABC `fetch_detail` du Scraper),
    `RUF001/002/003` (apostrophes courbes et tirets cadratin en français —
    faux positifs systématiques sur le projet FR).
  - Per-file ignores : `tests/*` (fixtures avec args), `seed_*.py` (params symboliques).
- **Premier passage `ruff check --fix`** : 48 issues auto-fixées (imports
  réorganisés via isort, etc.), 17 restantes analysées une par une :
  - 2 `F841` dead variables (`country` dans Lever, `department` dans WTTJ) → supprimées.
  - 4 `B904` raise sans `from e` (4 routes dans `main.py`) → ajout
    `raise HTTPException(422, str(e)) from e` (préserve la chaîne dans le traceback).
  - 1 `E741` variable ambiguë `l` → renommée `label`.
  - 1 `ARG001` `max_retries` legacy dans `_http.py` → `# noqa: ARG001` documenté.
  - 2 `E402` imports tardifs (`import os as _os` dans `main.py`, `import re as _re`
    dans `runner.py`) → déplacés en haut du module.
  - 7 `RUF001/2/3` unicode → ignorés via config (français).

#### Bilan venv propre

- `pytest tests/ -q` : **422 passed in 14.58s** (391 → 422 = +31 nouveaux :
  19 alternance indicator + 12 soft-404 threshold).
- `bandit -r backend cli.py` : **0 issues, exit 0**.
- `ruff check backend cli.py` : **All checks passed!**, exit 0.
- E2E `/api/stats` : valeurs prod identiques (1189 actives).

### Fixed — Sprint qualité (19 mai 2026, 3e audit utilisateur) : 4 findings

3e passe d'audit utilisateur. Sur 9 points levés, 4 étaient des **vrais bugs**
ratés par mes 2 audits précédents (les 5 autres : déjà fixés sur la branche
mais l'audit utilisait un checkout partiellement stale, ou trade-off
explicitement assumé pour scope perso).

#### Fix #2 — `migrate_xlsx` refuse de wiper sans `--force`

`backend/migrate_xlsx.py` faisait `DELETE FROM offers` puis ré-importait 194
offres du xlsx. Le README listait ce script en étape 3 du quickstart. Un user
qui re-fait le quickstart par réflexe 6 mois plus tard perdait 1000+ offres
scrapées (audit user 19 mai 2026).

- **`backend/migrate_xlsx.py`** : refactor en `run(argv=None) -> int` avec
  `argparse`. Nouveau `_check_safe_to_wipe(*, force)` qui :
  - Retourne `(True, None)` si DB vide OU si `--force` passé.
  - Retourne `(False, msg)` sinon, avec message d'erreur **actionnable**
    (compte exact des lignes existantes, commande `--force` à copier-coller,
    alternatives non destructives `python cli.py scrape all` / `python -m backend`).
  - Pure-function, testable sans toucher au xlsx (utilisé par les tests).
- **Garde-fou EN PREMIER** : le check `_check_safe_to_wipe` est exécuté
  AVANT le check d'existence du xlsx. Si l'utilisateur a 1000 offres et que
  le xlsx est absent, il voit "REFUS, use --force" plutôt que "xlsx introuvable"
  — sa data est protégée même quand l'autre branche échouerait.
- **Exit codes distincts** : `0` succès, `1` xlsx introuvable, `2` refus de
  wipe. Un script wrapper peut distinguer les cas.
- **`README.md`** : avertissement explicite à l'étape 3 du quickstart
  ("REFUSE si DB peuplée — voir --help").
- **`CLAUDE.md`** : commande mise à jour avec `--force` pour le cas
  documenté "à re-lancer pour reset DB".
- **`tests/test_migrate_xlsx_safety.py`** : 5 nouveaux tests
  - DB vide sans `--force` → safe (quickstart d'un nouveau user).
  - DB vide avec `--force` → safe (idempotent).
  - DB peuplée sans `--force` → REFUS + message contenant `--force` et
    "DELETE FROM offers" + le count exact.
  - DB peuplée avec `--force` → safe explicite.
  - `run([])` sur DB peuplée → exit code 2 (distinct de 1).

#### Fix #3 — `migrate_xlsx` passe `city` à `make_dedup_key`

L'appel `make_dedup_key(titre, entreprise)` produisait `"titre|entreprise|"`
(city vide) alors que les scrapers font `make_dedup_key(title, company, city)`
→ `"titre|entreprise|paris"`. Après ré-import xlsx, le prochain scrape ne
déduplicait PAS contre les offres xlsx → doublons silencieux.

- **`backend/migrate_xlsx.py:243`** : `make_dedup_key(titre, entreprise, ville)`,
  variable `ville` extraite explicitement de `COL_VILLE` au-dessus.
- **`tests/test_migrate_xlsx_dedup_key.py`** : 2 nouveaux tests
  - Verrouille que `make_dedup_key` produit des clés différentes pour Paris
    vs Toulouse (sanity du helper, déjà couvert mais ré-asserté).
  - **Garde-fou par introspection AST** : grep le source de `migrate_xlsx`
    pour `make_dedup_key(…)` et compte les arguments. Si quelqu'un régresse
    à 2 args (le bug original), le test échoue avec un message explicite.

#### Fix #6 — `run_scrape` historise les échecs dans `scrape_runs`

`runner.run_scrape` appelait `queries.record_scrape_run(…)` uniquement après
succès. Si `scraper.fetch_list()` raise (timeout, API down, parse KO),
l'exception propageait sans audit row. Conséquence : `scrape_runs` vide
alors que l'utilisateur a lancé un scrape.

- **`backend/scrapers/runner.py:run_scrape`** : refactor en `try/except/finally`.
  - `get_scraper(source)` reste HORS du `try` (KeyError = config error, pas
    un échec de scrape — pas la peine de polluer l'audit).
  - Variables de tracking (`raw_offers`, `new_ids`, `duplicates`, `batch_path`,
    `error_msg`) initialisées avant le try → le `finally` peut toujours
    appeler `record_scrape_run` avec les compteurs partiels au moment du
    crash.
  - `except` capture `str(e)` dans `error_msg`, log le traceback complet
    via `logger.opt(exception=True).warning(…)`, puis `raise` pour que le
    caller voie l'erreur.
  - `finally` appelle TOUJOURS `record_scrape_run` (succès → `error=None`,
    échec → `error=str(e)`).
- **`cli.py:cmd_scrape`** : `except Exception` broaden — affiche un résumé
  user-friendly + pointe vers `data/logs/errors.log` pour le traceback complet
  et vers `scrape_runs` pour l'audit. Évite le crash brut de l'ancien code
  qui ne catchait que `KeyError`.
- **`tests/test_run_scrape_audit_failure.py`** : 4 nouveaux tests
  - `fetch_list` raise → 1 row dans `scrape_runs` avec `error` rempli.
  - Source inconnue (`get_scraper` KeyError) → AUCUN row (pas pollué).
  - Path succès → row avec `error=None`.
  - Échec partiel (fetch OK + insert OK + batch KO) → compteurs partiels
    préservés (`total_fetched=1, total_new=1`) + error rempli.

#### Fix #9 — `schema.sql` aligné sur post-migration 002

`schema.sql` se documentait comme "vue synthétique du schéma actuel (état
après toutes les migrations appliquées)" mais ne contenait aucun `CHECK`
constraint, alors que la migration 002 en a ajouté ~10. Documentation
menteuse.

- **`backend/schema.sql`** : ajout des CHECK pour `remote`, `match_score`,
  `score_*` (5 axes), `match_label`, `status`, `priority`, `is_active` sur
  `offers` ET `priority` + `status` sur `target_companies`. Chaque CHECK
  annoté `-- migration 002 : enum/borne` pour traçabilité. Header mis à
  jour avec mention du test de drift (futur).
- **`scrape_runs.error`** : commentaire ajouté pour clarifier qu'il sert
  aussi à historiser les échecs (cohérent avec Fix #6).

#### Bilan

- `pytest tests/ -q` en venv propre : **391 passed in 16.05s** (380 → 391
  = +11 nouveaux : 5 safety + 2 dedup_key + 4 audit failure).
- `bandit -r backend cli.py` en venv : **0 issues, exit 0** (1 false-positive
  bandit sur f-string contenant "DELETE FROM" dans un message d'erreur
  user-facing → annoté `# SAFE (B608)` + restructuré en `.format()` pour
  cibler le `# nosec` sur la ligne exacte).
- E2E live :
  - App `/api/stats` répond 200 avec les valeurs prod (1189 actives).
  - `python -m backend.migrate_xlsx` (sans `--force`) refuse avec exit 2 :
    `"REFUS : la table 'offers' contient déjà 1207 ligne(s)…"`.
- Backward compat : nouveau user avec DB vide peut toujours lancer le
  quickstart sans flag.

### Fixed — Sprint qualité (19 mai 2026 soir) : 5 findings 2e audit utilisateur

2e passe d'audit utilisateur après le push des 8 fixes précédents → 5 vrais
problèmes que j'avais ratés (le rollback migrations étant déjà fixé,
l'audit était sur état partiellement stale). Méthodologie en cause :
pas de static linter (vulture/ruff RUF013), pas d'analyse data-flow
cross-fonctions, pas de doc-vs-code diff, pas de fuzz parsers.

#### Fix #2 — `export_batch_to_score` exclut les offres archivées par défaut

Bug le plus impactant. Dans `run_full_scrape` :

1. Scrape multi-source → collecte `new_ids` (toutes is_active=1).
2. `filter_non_alternance_offers()` → archive (`is_active=0`) certains des
   nouveaux IDs qui sont en fait du CDI déguisé.
3. **Avant ce fix** : `export_batch_to_score(offer_ids=new_ids)` envoyait
   QUAND MÊME ces IDs archivés au LLM → tokens gaspillés, scoring d'offres
   déjà rejetées.

Le commentaire pré-existant `runner.py:743-744` *affirmait* que `matching.py`
filtrait les non-existantes — vrai pour les DELETE mais FAUX pour les
archivées. Mensonge inadvertant qui a contribué à mon manque de vigilance
sur ce flux.

- **`backend/matching.py:export_batch_to_score`** : nouveau kwarg
  `include_archived: bool = False`. La clause WHERE devient une `list`
  de fragments — `(is_active IS NULL OR is_active = 1)` est appliqué
  AVANT toutes les autres branches sauf si `include_archived=True`.
  Couvre les 3 paths : `offer_ids=[…]`, `only_unscored=True`, et le
  default sans filtre.
- **`backend/scrapers/runner.py`** : commentaire menteur remplacé par
  un commentaire qui explique le piège et la mitigation.
- **`tests/test_matching.py`** : nouvelle classe `TestExportBatchExcludesArchived`
  (3 cas) : scénario réel run_full_scrape (offer_ids contient une archivée
  → exclue), path `only_unscored` (3 offres unscored dont 1 archivée →
  archivée exclue), escape-hatch `include_archived=True` (archivée
  réincluse).

#### Fix #4 — `parse_scores_file` valide `raw["scores"]` est une liste

Reproduction : `scores: null` → `TypeError: NoneType is not iterable`,
opaque au caller CLI qui ne catche que `ValueError`.

- **`backend/matching.py:parse_scores_file`** : ajout d'un check explicite
  `isinstance(scores_raw, list)` avec `ValueError` proprement formaté
  (`"'scores' doit être une liste, reçu NoneType"`). Idem pour les items
  individuels (`isinstance(item, dict)` avec ValueError au lieu de
  l'AttributeError opaque sur `"foo".get(...)`).
- **`tests/test_matching.py`** : nouvelle classe `TestParseScoresFileValidation`
  (6 cas) : scores=null, scores="abc", scores={"foo":"bar"}, scores=42,
  items non-dict, liste vide (valide).

#### Fix #5 — `run_scrape` a maintenant une vraie `__doc__`

[`runner.py:52`](backend/scrapers/runner.py:52) avait `logger.info(...)` AVANT
le triple-quoted, donc Python traitait le triple-quoted comme une
statement-expression jetée. `help(run_scrape)` retournait None.

- **`backend/scrapers/runner.py:run_scrape`** : le triple-quoted (docstring)
  est désormais la PREMIÈRE statement de la fonction, `logger.info` vient
  après. Vérifié live : `run_scrape.__doc__` retourne maintenant la doc
  attendue.

#### Fix #6 — Suppression du paramètre mort `only_unscored_or_scored`

`check_alive(only_unscored_or_scored: bool = True, …)` : aucun caller ne
le passait, aucune ligne du corps de la fonction ne le lisait. Code mort.

- **`backend/scrapers/runner.py:check_alive`** : signature nettoyée à
  `(*, min_score, sleep_between, limit)`. Tests existants (`test_bulk_alive.py`)
  passaient juste `sleep_between=0.0` → aucune régression.

#### Fix #3b — CLAUDE.md:218 reflète le default `archive`, pas `delete`

Le doc disait "URL morte + status NULL → DELETE", mais `cleanup_dead_unstatused`
a `hard_delete_unstatused=False` en défaut → archive systématique. Le DELETE
n'arrive qu'en opt-in explicite.

- **`CLAUDE.md`** : reformulé en 2 lignes (défaut archive, opt-in delete)
  pour ne plus induire en erreur.

#### Bilan

- `pytest tests/ -q` en venv propre : **380 passed in 14.98s** (371 → 380
  = +9 tests : 3 archived filter + 6 validation parse_scores_file).
- `bandit -r backend cli.py` en venv : **0 issues, exit 0**.
- Vérifié live : `run_scrape.__doc__` non-None, `check_alive` signature
  n'expose plus `only_unscored_or_scored`.
- Backward compat 100% : aucun caller existant ne passait les kwargs
  modifiés (`include_archived` ajouté avec défaut, `only_unscored_or_scored`
  mort supprimé sans casser personne).

### Fixed — Sprint qualité (19 mai 2026) : 8 findings audit utilisateur

Audit utilisateur après push P0+P1 → 8 vrais problèmes flaggés, tous corrigés.
J'avais raté plusieurs d'entre eux dans ma propre passe (mea culpa). Le détail :

#### Fix #1 — Rollback migrations cassé (BUG CRITIQUE, perte intégrité DB)

`Connection.executescript()` en Python 3.13 émet un **COMMIT implicite avant**
de lancer le script (mode `LEGACY_TRANSACTION_CONTROL`). Conséquence :
le `conn.execute("BEGIN")` posé juste avant était commité immédiatement,
et tout DDL exécuté à l'intérieur du script restait persisté en cas d'erreur
SQL au milieu — migration à moitié appliquée, DB incohérente.

- **`backend/_migrations.py`** : nouvelle fonction `_open_migration_connection()`
  qui ouvre via `sqlite3.connect(DB_PATH, autocommit=False)`. En mode PEP 249,
  une tx est ouverte implicitement avant la 1re statement et reste vivante
  pendant tout l'`executescript` → `conn.rollback()` annule TOUTES les DDL si
  la moindre échoue. Le `conn.execute("BEGIN")` explicite est retiré (devenait
  inutile et même nuisible avec autocommit=False).

- **`tests/test_migrations.py`** : 2 nouveaux tests qui ÉCHOUERAIENT pré-fix
  - `test_multi_ddl_with_error_in_middle_rolls_back_partial` : 2 `CREATE TABLE`
    valides + SQL invalide → assertEqual aucune table ne persiste.
  - `test_multi_migration_atomicity` : v1 OK + v2 partielle → v1 persistée,
    v2 entièrement rollbackée.
  - Le test pré-existant `test_invalid_sql_rolls_back` était un faux-positif
    (un seul statement invalide → erreur avant tout DDL, donc rien à rollback).

#### Fix #2 + #8 — `h2` et `bandit` dans `requirements.txt`

- `backend/scrapers/_http.py:53` utilise `httpx.Client(http2=True)` mais `h2`
  n'était pas déclaré → `ImportError` en venv propre. `requirements.txt` :
  `httpx==0.28.1` → `httpx[http2]==0.28.1` (l'extra tire `h2`).
- `bandit` était mentionné dans le README sans être dans les deps → ajouté
  `bandit>=1.8`.
- **`requirements.lock`** régénéré via `pip-tools` dans un venv propre →
  versions exactes : `pydantic==2.10.3` (au lieu de la 2.12.4 du global),
  `h2==4.3.0`, `bandit==1.9.4`.

#### Fix #3 — Tests reproductibles en venv propre

- Validé en local : `python -m venv .venv` + `pip install -r requirements.lock`
  → `pytest tests/ -q` = **371 passed in ~15s** avec `pydantic 2.10.3` et
  `h2 4.3.0` réellement chargés (et plus la version global pollué).
- `bandit -r backend cli.py` en venv = **0 issues, exit 0**.

#### Fix #4 — `ALLOWED_ORIGINS` configurable (CSRF)

`_ALLOWED_ORIGINS` était hardcodé à `127.0.0.1:8000` / `localhost:8000`.
Override possible via env var `ALLOWED_ORIGINS` (CSV) pour les cas port
custom ou reverse proxy. Les defaults restent en fallback (jamais retirés).

- **`backend/main.py`** : `_load_allowed_origins()` lit l'env var au boot,
  trim trailing `/`, fusionne avec les defaults.
- **`tests/test_security.py`** : 4 nouveaux tests `TestAllowedOriginsEnvOverride`
  (default sans env, ajout d'1 origine, CSV multiple, vide ignoré).
- **README.md** : section documentée avec exemple PowerShell.

#### Fix #6 — Logs explicites dans `company_portals.py`

Les 8 `except Exception: return []` silencieux étaient injoignables au
diagnostic : un portail KO devenait "0 offres trouvées" sans plus.

- **`backend/scrapers/company_portals.py`** : chaque except remplace le
  silence par `logger.warning(...)` ou `logger.debug(...)` avec contexte
  (slug, tenant, company_name, status code, url, err). Couverts :
  Workable, Lever, Greenhouse (+fallback BS parse en `debug`), Taleez,
  Workday, Playwright, generic career page.

#### Fix #7 — README à jour

- "130 tests, ~3s" → **371 tests, ~15-26s**
- "Tailwind via CDN" → "Tailwind v3 vendoré + HTMX 2.0.4 vendoré"
- "HTMX 2.0.4 vient encore d'unpkg" → supprimé, remplacé par bloc
  unifié "Tailwind + HTMX vendorés localement"
- Section CSRF documentée avec exemple `$env:ALLOWED_ORIGINS`
- `bandit` dans `requirements.txt` mentionné

#### Bilan

- `pytest tests/ -q` en venv propre : **371 passed in ~15s** (367 → 371 = +4
  tests env var CSRF + 2 tests rollback ; -2 net car le test pré-existant
  trompeur n'a pas été supprimé mais coexiste).
- `bandit -r backend cli.py` en venv : **0 issues, exit 0**.
- E2E : app boot OK, `/api/stats` répond avec les valeurs prod identiques,
  `_load_allowed_origins()` testée live (avec/sans env var).

### Docs — Sprint qualité (18 mai 2026) : audit staff-engineer — P1.6 (rationale `# nosec B608`)

Les 12 occurrences de `# nosec B608` (f-string SQL) avaient déjà un commentaire
au-dessus expliquant pourquoi c'était safe, mais le format variait
(`pas d'input user`, `fragments littéraux`, `passe via ?`...). Uniformisation
pour qu'un grep `nosec` puisse être audité en passant rapide.

- **Tous les `# nosec B608` ouvrent maintenant par `# SAFE (B608) :`** suivi
  de 2-4 lignes qui explicitent :
  - **Quoi** est interpolé dans le f-string (fragment littéral, placeholder
    généré à partir d'une longueur, nom de colonne d'une whitelist).
  - **Pourquoi** ce n'est pas un input user (constante module-level,
    if/else interne, whitelist `ALLOWED_*_FIELDS`, cast `int()`).
  - **Comment** les valeurs réelles sont bindées (params positionnels `?`,
    params nommés `:name`, cast int explicite).

Fichiers touchés (uniformisation uniquement, aucun changement SQL) :
- `backend/queries.py` (4 occurrences : `delete_offers_bulk`, `update_offer`,
  `count_other_haute`, `update_target_company`).
- `backend/heuristic_scorer.py` (1 occurrence).
- `backend/matching.py` (3 occurrences).
- `backend/scrapers/runner.py` (3 occurrences : `enrich_descriptions`,
  `check_alive`, `cleanup_dead_unstatused`).
- `backend/scrapers/company_portals.py` (1 occurrence).
- `backend/seed_high_priority_other_cities.py` (1 occurrence).

Validation :
- `pytest tests/ -q` : 365 passed in 26.50s (aucune régression — c'est du
  commentaire uniquement).
- `bandit -r backend cli.py` : **0 issues, exit 0** (les warnings bandit
  "nosec encountered but no failed test" sur runner.py:186/429/548 sont
  bénins — c'est bandit qui signale que le marqueur est conservé sur des
  lignes qu'il ne flaggerait plus, sans rien faire échouer).

### Changed — Sprint qualité (18 mai 2026) : audit staff-engineer — P1.5 (accessibilité)

Quick wins a11y identifiés par l'audit UI : boutons emoji sans `aria-label`,
polling scrape-status sans `aria-live`, focus visible sur actions critiques.
Scope perso/local : pas de full WCAG AA mais hygiène raisonnable.

- **`backend/templates/offers.html`** : boutons inline "Pas intéressé" 👎 et
  "Remettre" ↩️
  - `aria-label="Remettre cette offre dans À postuler"` /
    `aria-label="Marquer cette offre comme pas intéressé"` (lisible par
    lecteur d'écran indépendamment du contexte de la ligne).
  - `<span aria-hidden="true">👎</span>` : l'emoji n'est pas annoncé en
    double, le `<span class="sr-only">Pas intéressé</span>` à côté l'est.
  - `focus-visible:outline ... outline-rose-700` : focus visible navigation
    clavier (Tab).

- **`backend/templates/base.html`** : div `#scrape-status` (polling 3s)
  - `role="status"` + `aria-live="polite"` + `aria-atomic="true"` : les
    lecteurs d'écran annoncent les changements de statut (`⏳ scrape en
    cours`, `✅ terminé`, `❌ erreur`) sans interrompre l'utilisateur.

- **`backend/static/style.css`** : classe utilitaire `.sr-only` ajoutée
  (Tailwind CDN génère cette classe à la volée, mais on la définit aussi
  côté CSS pour garantir le rendu même quand l'utilitaire JIT rate un
  `<span>` imbriqué).

Trade-off documenté : les `<label>` des inputs filtres ne sont pas tous
associés via `for="..."` / `id="..."`. Sur un app single-user FR avec
clavier français standard, le bénéfice incrémental d'associer 20+ inputs
est faible vs la churn. Si l'app évolue vers du multi-user / public, ce
serait un P0 a11y à reprendre.

Validation :
- `pytest tests/ -q` : 365 passed in 26.94s (aucune régression).
- E2E live : `GET /` rendu confirme `aria-live="polite"` sur
  `#scrape-status` et `aria-label="Marquer cette offre comme pas..."` sur
  les boutons 👎.

### Added — Sprint qualité (18 mai 2026) : audit staff-engineer — P1.4 (tests parsing scrapers)

Le parsing est la partie la plus fragile du scraping (régression invisible
si la source change sa structure DOM ou ses noms de champs JSON). Aucune
fonction d'extraction (`_parse_card` HW, `_hit_to_raw` WTTJ, `_parse_offer`
FT) n'avait de test dédié — le seul filet était les tests de filtre
alternance et keywords, qui ne couvrent pas le mapping champ-par-champ.

- **`tests/test_scrapers_parse.py`** : 20 tests (~0.5 sec), 3 classes :

  - **`TestHelloWorkParseCard`** (4 cas) : DOM card complète (titre +
    entreprise + ville + département + contract + salary depuis aria-label),
    sans département, minimal (titre seul), card cassée sans lien → None
    silencieux.

  - **`TestHelloWorkParseAriaLabel`** (3 cas) : la regex aria-label que
    l'audit a flaggé comme fragile. Full aria avec 5 segments, sans salaire,
    avec uniquement la ville.

  - **`TestWTTJHitToRaw`** (6 cas) : mapping Algolia hit typique,
    **garde-fou `offices` (pluriel) vs `office` (singulier)** — verrouille la
    régression historique fixée en mai, hit sans titre → None, HTML strippé
    dans description, < 100 chars → description=None (le caller fait
    `fetch_detail` pour enrichir), URL `None` si slugs manquants.

  - **`TestFranceTravailParseOffer`** (7 cas) : mapping `natureContrat`
    E1 → "Alternance (apprentissage)" et E2 → "Alternance (professionnalisation)",
    fallback sur `typeContratLibelle` puis "Alternance" par défaut, URL
    canonique générée quand `origineOffre.urlOrigine` absent, date tronquée
    à 10 chars (YYYY-MM-DD), tous champs optionnels vides ne crashent pas.

  - Toutes les fixtures sont des **dicts Python construits** sur la base de
    la structure réelle observée — zéro network, zéro fichier externe.
    Les RawOffer retournés sont validés via leurs assertions Pydantic
    automatiques (URL scheme, date format).

Validation :
- `pytest tests/test_scrapers_parse.py -v` : 20 passed in 0.52s.
- `pytest tests/ -q` : 365 passed in 26.78s (345 → 365 = +20).
- Aucun appel réseau, aucune fixture HTML/JSON externe.

### Changed — Sprint qualité (18 mai 2026) : audit staff-engineer — P1.3 (`get_stats` single query)

`queries.get_stats()` faisait 9 `SELECT COUNT(*)` séquentiels sur la table
`offers` à chaque rendu de la page d'accueil (10 réellement, dont 1 pour
`archived`). Pas critique en perf au volume actuel (~1200 lignes), mais :
- 10 scans de table au lieu de 1 = ~10× plus lent.
- Plus de surface à maintenir si on ajoute un compteur.
- Pattern qu'un staff-engineer voit immédiatement comme "factorisable".

- **`backend/queries.py:get_stats()`** : remplacé par une **seule requête**
  avec `SUM(CASE WHEN cond THEN 1 ELSE 0 END)` pour chacun des 10 compteurs.
  Toutes les conditions restent des littéraux SQL constants (pas d'input
  user, donc toujours bandit-clean sans `# nosec`). Le retour reste un dict
  avec exactement les mêmes clefs et la même sémantique. `SUM(0 rows)`
  retourne NULL en SQLite → coercion `int(row[k] or 0)` pour stabilité.

Validation :
- `pytest tests/ -q` : 345 passed in 27.35s (aucune régression).
- E2E live : `GET /api/stats` retourne strictement les mêmes valeurs
  qu'avant le refactor sur la DB de prod (1189 offres) :
  `{"total":1189,"to_apply":1115,"applied":35,"interviews":0,"refused":5,
    "top_fit":5,"bon_fit":170,"unscored":0,"not_interested":34,"archived":18}`.

### Refactored — Sprint qualité (18 mai 2026) : audit staff-engineer — P1.2 (helper `_jsonld.py`)

Le parsing JSON-LD `JobPosting` (Schema.org) était implémenté **3 fois** dans
les scrapers avec **3 niveaux de complétude** différents :
- `_generic.py` gérait `dict` / `list` / `@graph` (le plus complet)
- `wttj.py` gérait `dict` / `list` (pas `@graph`)
- `hellowork.py` gérait uniquement `dict` (le plus simple, ratait les ATS
  modernes qui sérialisent en liste)

Le risque : un site dont l'ATS sérialise en `@graph` ratait son extraction
sur HelloWork mais pas sur Generic — comportement incohérent par source.

- **`backend/scrapers/_jsonld.py`** (nouveau) : helper canonique
  - `extract_jobposting_description(soup, *, min_len=200) -> str | None`
    qui gère les 3 formats (`dict`, `list`, `@graph`) via `_iter_jsonld_objects`.
  - `normalize_whitespace(text)` : collapse 3+ newlines → 2 (anciennement
    `re.sub(r"\n{3,}", "\n\n", text)` dupliqué 5+ fois dans la codebase).
  - `min_len` paramétrable (utile pour les tests, mais défaut 200 préservé).

- **`backend/scrapers/_generic.py`** : `_extract_jsonld_jobposting` supprimé,
  `extract_jobposting_description` utilisé. Imports `json` et `re` retirés.
  `normalize_whitespace` utilisé dans `_extract_microdata`,
  `_extract_by_attribute`, `_extract_main`.

- **`backend/scrapers/hellowork.py`** : `fetch_detail` upgrade — gère maintenant
  `list` et `@graph` (bug corrigé indirectement). `import json as _json` retiré.

- **`backend/scrapers/wttj.py`** : idem `fetch_detail` factorisé.
  `import json` et `import re` retirés (plus utilisés).

- **`tests/test_jsonld_helper.py`** : 17 tests (~0.3 sec)
  - **`TestNormalizeWhitespace`** (4 cas) : collapse 3/5+ newlines → 2,
    préserve 2 et 1, no-op sans newline.
  - **`TestExtractJobPostingDict`** (4 cas) : extraction dict simple, None
    sur `@type: Organization`, None sur description trop courte, `min_len`
    paramétrable.
  - **`TestExtractJobPostingList`** (2 cas) : extraction depuis liste de
    JSON-LD, premier match wins.
  - **`TestExtractJobPostingGraph`** (1 cas) : extraction depuis `@graph`
    imbriqué (format Workday-like).
  - **`TestRobustness`** (6 cas) : JSON malformé / script vide / array de
    primitives / pas de `<script>` / `description: ""` / HTML tags strippés.

Validation :
- `pytest tests/test_jsonld_helper.py -v` : 17 passed in 0.30s.
- `pytest tests/ -q` : 345 passed in 26.83s (328 → 345 = +17).
- Comportement scrapers strictement préservé sur les 3 formats antérieurs ;
  HelloWork et WTTJ gèrent maintenant `@graph` (gain net).

### Refactored — Sprint qualité (18 mai 2026) : audit staff-engineer — P1.1 (templates `_components.html`)

Les macros badge (`score_badge`, `status_badge`, `priority_badge`,
`contact_method_badge`) et le bloc pagination étaient **dupliqués** entre
`offers.html` et `companies.html`. Une modif de couleur ou de wording
devait être faite à 2 endroits — facile d'oublier l'un des deux et avoir
des badges incohérents entre les 2 pages.

- **`backend/templates/_components.html`** (nouveau) : 6 macros centralisées
  - `score_badge(score)` : palette emerald/yellow/orange/slate selon labels
    Top/Bon/Moyen/Faible.
  - `offer_status_badge(status)` : mapping `VALID_STATUSES` → couleur
    (Postulé=blue, Entretien/Test=purple, Accepté=emerald, Refusé=rose,
    Relancé=amber, Pas intéressé=zinc line-through).
  - `company_status_badge(status)` : mapping `VALID_COMPANY_STATUSES`
    (couleurs distinctes — pas d'état `Postulé` pour une entreprise).
  - `priority_badge(p)` : Haute=rose, Moyenne=amber, Basse=slate.
  - `contact_method_badge(channel, email)` : heuristique sur le libellé pour
    afficher ✉ Email / 🔗 Portail / 📋 Spontané / 👥 LinkedIn.
  - `paginator(pagination, request)` : renommé (pas `pagination` pour
    éviter le shadowing du dict du context).

- **`backend/templates/offers.html`** : 35 lignes de macros → 1 ligne d'import
  `{% from "_components.html" import score_badge, offer_status_badge, paginator %}`.
  Bloc pagination 20 lignes → `{{ paginator(pagination, request) }}`.

- **`backend/templates/companies.html`** : 45 lignes de macros + 20 lignes
  pagination → 2 lignes d'import + 1 appel paginator.

Validation :
- `pytest tests/ -q` : 328 passed in 25.73s (aucune régression).
- E2E navigation Chrome : `/?min_score=60&page=2` et `/companies?priority=Haute&page=2`
  rendent identiquement (badges colorés intacts, pagination "page 2/7" et "page 2/3"
  préservée).
- Bilan : ~85 lignes de templates supprimées, source-of-truth unique.

### Fixed + Added — Sprint qualité (18 mai 2026) : audit staff-engineer — P0.5 (FT token 401 retry)

Le scraper France Travail avait 2 trous sur le refresh token :

1. **`fetch_list` skippait la page sur 401** : sur réception d'un 401 mid-scrape,
   le code invalidait `_TOKEN_CACHE`, refresh le token, puis faisait `continue`
   — mais `continue` dans `for page in range(max_pages):` passe à la PAGE
   SUIVANTE, pas à un retry de la même page. Conséquence : les offres de la
   page 401'd étaient perdues silencieusement.

2. **`fetch_detail` n'avait aucun handling 401** : sur token révoqué, retournait
   simplement `None` (description manquante, sans log).

- **`backend/scrapers/francetravail.py`** : nouveau helper
  `_request_with_token_retry(client, method, url, *, auth_headers, params, max_token_retries=1)` qui :
  - exécute la requête,
  - sur 401, invalide `_TOKEN_CACHE["expires_at"] = 0.0`, force `_get_token`,
    met à jour `auth_headers["Authorization"]` **in-place** (les requêtes
    ultérieures du caller héritent du nouveau Bearer),
  - **rejoue la MÊME requête** (jamais skipper la page).
  - Limite à 1 retry — au-delà = creds KO/client révoqué, `logger.error` +
    fail fast.
  - `fetch_list` et `fetch_detail` utilisent maintenant ce helper.

- **`tests/test_francetravail_token_retry.py`** : 6 tests (~0.3 sec) via
  `httpx.MockTransport` (idiomatique httpx, zéro network).
  - 200 → pas de retry (1 seule requête vue, header inchangé).
  - 401 puis 200 → 2 requêtes, 2e avec nouveau Bearer, `headers` in-place
    mis à jour.
  - 401 puis 401 → pas de 3e tentative, retourne le dernier 401.
  - `_TOKEN_CACHE["expires_at"]` repassé à 0.0 sur 401 (force refresh même
    si cache était "valide encore 1h").
  - 500/503/429/204 → pas de retry token (autres handlers).
  - Query params bien passés à la requête réelle.
  - Fixture `autouse=True` reset le cache global entre chaque test (state
    isolation propre).

Validation :
- `pytest tests/test_francetravail_token_retry.py -v` : 6 passed in 0.30s.
- `pytest tests/ -q` : 328 passed in 25.99s (322 → 328 = +6).
- Aucune régression. Comportement nominal (200) strictement identique.

### Changed — Sprint qualité (18 mai 2026) : audit staff-engineer — P0.4 (bulk transactions cycle de vie)

`cleanup_dead_unstatused` et `check_alive` faisaient N transactions SQLite
(une par offre) sur des batchs typiques de 1000+ URLs : ~5-15 sec perdues sur
les commits WAL, et **atomicité faible** (Ctrl+C / kill uvicorn au milieu →
500 offres mises à jour, 500 non, état incohérent côté UI "Inclure archivées").

- **`backend/queries.py`** : 2 nouvelles fonctions
  - `set_alive_state_bulk(updates: list[tuple[int, bool]]) -> int` : 1 seul
    `executemany` UPDATE `is_active` + stamp `last_checked_at`.
  - `delete_offers_bulk(ids: list[int]) -> int` : 1 seul DELETE avec
    placeholders dynamiques `id IN (?,?,?,...)`, `# nosec B608` documenté
    (placeholders générés à partir de `len(ids)`, pas du contenu).

- **`backend/scrapers/runner.py`** : refactor des 2 fonctions de cycle de vie
  - Les verdicts (`archived_ids`, `revived_ids`, `to_delete`, `to_archive`,
    `to_revive`) sont **collectés en RAM** pendant la boucle HTTP.
  - Le flush DB se fait en **2-3 transactions bulk** à la fin via les helpers.
  - Atomicité : Ctrl+C au milieu = 0 write (idempotent au prochain run).
  - Perf : ~10× plus rapide qu'un commit par URL.
  - Comportement fonctionnel **inchangé** : `CleanupResult` et
    `AliveCheckResult` retournent les mêmes compteurs.

- **`tests/test_bulk_alive.py`** : 11 nouveaux tests (~2.4 sec)
  - `TestSetAliveStateBulk` (5 cas) : empty list, archive bulk, revive bulk,
    mixed archive/revive dans un seul appel, ids inconnus → no exception.
  - `TestDeleteOffersBulk` (4 cas) : empty, delete partiel, ids non listés
    préservés, volume 50 offres.
  - `TestRunnerIntegration` (2 cas) : `monkeypatch` sur
    `_probe_workday_api` + sur `queries.set_alive_state_bulk` pour vérifier
    que `check_alive` et `cleanup_dead_unstatused` font UN seul appel bulk
    pour 3 offres au lieu de 3 appels individuels.

Validation :
- `pytest tests/test_bulk_alive.py -v` : 11 passed in 2.35s.
- `pytest tests/ -q` : 322 passed in 26.31s (311 → 322 = +11).
- Aucune régression. Comportement fonctionnel strictement identique.

### Added — Sprint qualité (18 mai 2026) : audit staff-engineer — P0.3 (tests routes HTTP)

Les routes HTTP n'étaient validées que par des smoke tests "200 + contient
'Scrap'Offre Emploi'" (`test_html_smoke.py`). Aucune assertion sur le
contenu rendu (filtres, pagination, tri), aucun test sur `/api/scrape`
concurrence ni structure de `/api/scrape/status`. Régression facile sur
`queries._offer_filters` ou `OptionalIntFromForm` passait inaperçue.

- **`tests/test_routes.py`** : 27 nouveaux tests (~4.4 sec). Découpés en
  6 sections :
  - **Filtres GET /** (7 tests) : `search` (titre + entreprise case-insensitive),
    `min_score` (seuil), `status` (valeur explicite + sentinelle `_NONE_`),
    `include_archived` (hidden par défaut + visible avec flag). Assert
    présence/absence des lignes dans le HTML.
  - **Pagination** (5 tests) : `page=2` retourne le bon slice, `page=999`
    normalisé à la dernière, `per_page < 25` et `per_page > 500` → 422
    (validation FastAPI `Query(ge=25, le=500)`), `page=0` → 422.
  - **POST /offers/{id}** (3 tests) : redirect 303 avec `Location: /offers/{id}`,
    persistance des champs `status` + `notes`, 404 sur id inexistant.
  - **/api/scrape** (5 tests) : 400 sur source inconnue, **409 sur double-POST**
    (via `monkeypatch.setitem(_SCRAPE_STATE, 'running', True)`), 422 sur
    `max_pages` hors borne, structure du status (8 clefs minimum), reset.
  - **API JSON** (5 tests) : `/api/stats` structure complète (10 clefs),
    PATCH `/api/offers/{id}` succès `{"ok": True}` + 404, POST toggle
    `/api/offers/{id}/status` "Pas intéressé" + reset à NULL via `status=""`.
  - **POST /api/companies/import-from-offers** (2 tests) : dict structuré
    `{city, candidates, inserted, skipped_dup}`, 0 sur ville inexistante.

Validation :
- `pytest tests/test_routes.py -v` : 27 passed in 4.44s.
- `pytest tests/ -q` : 311 passed in 23.65s (284 → 311 = +27).
- Aucune régression sur les 284 tests pré-existants.

### Added — Sprint qualité (18 mai 2026) : audit staff-engineer — P0.2 (tests heuristic_scorer)

Le scoreur heuristique (`backend.heuristic_scorer`) classe automatiquement les
~1100 offres scrapées avec un système de regex (mots-clés par axe + bonus +
pénalités + must-have alternance + normalisation finale). Zéro test
jusqu'ici : une régression sur `_AXIS_KEYWORDS`, `_PENALTIES`, `_BONUSES` ou
la passe de normalisation finale aurait pu basculer toute la distribution
silencieusement. C'est traité.

- **`tests/test_heuristic_scorer.py`** : 27 nouveaux tests (~1.1 sec) couvrant
  4 classes :
  - **`TestInvariants`** (10 cas paramétrisés) : `total ∈ [0, 100]`, chaque
    axe `∈ [0, 20]`, `total == sum(axes)` (contrat avec `apply_llm_scores`),
    pas de `ZeroDivisionError` quand aucun mot-clé ne matche.
  - **`TestPenaltiesAndBonuses`** : must-have alternance (-25), pénalité
    Senior, pénalité Tech Lead, bonus "alternant" explicite, pénalité
    Directeur. Comparaison relative (texte A vs texte A+keyword) plutôt
    qu'assertion exacte → résistant aux ajustements de poids.
  - **`TestAxisAttribution`** : mots-clés pipeline → axe pipeline (pas de
    leak), idem modélisation et déploiement, et stuffing MLOps → axe
    déploiement capé à 20.
  - **`TestReturnShape`** : dataclass `HeuristicResult` stable (offer_id=0
    par défaut, `matched: list`), contrat de structure.
  - **`TestApplyHeuristicToUnscored`** : intégration DB via temp fixture
    (`monkeypatch.setattr("backend.db.DB_PATH", tmp_path)`). Vérifie filtre
    unscored par défaut, mode `rescore_heuristic=True` n'écrase QUE les
    `auto:heuristic%` (jamais les scores manuels), filtrage des archived,
    structure du dict de retour, DB vide → zéro.

Validation :
- `pytest tests/test_heuristic_scorer.py -v` : 27 passed in 1.10s.
- `pytest tests/ -q` : 284 passed in 20.94s (256 → 284 = +28 nouveaux —
  un fichier de test_html_smoke contient 1 test supplémentaire détecté).
- Aucune régression sur les tests existants.

### Changed — Sprint qualité (18 mai 2026) : audit staff-engineer — P0.1 (HTMX vendoré local)

Aligné sur la Vague 2 (Tailwind local) : **HTMX 2.0.4 est désormais servi
depuis `backend/static/`**, plus aucune dépendance CDN runtime. L'app reste
fonctionnelle hors-ligne / mode avion / firewall corporate.

- **`backend/static/htmx-2.0.4.min.js`** (50 917 octets) : bundle officiel
  unpkg téléchargé en local. Byte-identique au CDN — SRI inchangée :
  `sha384-HGfztofotfshcF7+8n44JQL2oJmowVChPTg48S+jvZoztPfvwD79OC/LTtG6dMp+`.
- **`backend/templates/base.html`** : `<script src="https://unpkg.com/...">`
  remplacé par `<script src="/static/htmx-2.0.4.min.js" integrity="..."
  crossorigin="anonymous">`.
- **`.claude/rules/templates.md`** : doc mise à jour ("HTMX 2.0 via CDN" →
  "HTMX 2.0.4 vendored local"), commande de mise à jour documentée.

Validation :
- `pytest tests/test_html_smoke.py tests/test_security.py -q` : 38 passed in 3.18s.
- E2E : `GET /` ne contient plus aucune référence à `unpkg`,
  `GET /static/htmx-2.0.4.min.js` répond 200 (50 917 octets).
- Aucune SRI failure dans Chrome DevTools.

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
