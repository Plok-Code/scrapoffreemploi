---
description: SQLite schema, queries, migrations, cycle de vie des offres
paths:
  - backend/schema.sql
  - backend/db.py
  - backend/queries.py
  - backend/migrate_xlsx.py
  - backend/seed_*.py
  - backend/dedup_*.py
---

# Database (SQLite via stdlib `sqlite3`)

## Source de vérité

- **Fichier DB** : `data/app.db` (gitignored)
- **DDL** : `backend/schema.sql` (idempotent grâce à `CREATE TABLE IF NOT EXISTS`)
- **Toujours initialiser via** : `init_schema()` dans `backend/db.py` (auto au démarrage uvicorn)
- **Migrations conditionnelles** : ajoutées dans `init_schema()` via `PRAGMA table_info` + `ALTER TABLE`

## Tables

### `offers` (table principale)

Colonnes par groupe :
- **Offre (immutable post-scraping)** : `title, company, city, department, source, url, description, date_published, remote, contract_type, salary`
- **Scoring LLM** : `match_score (0-100), score_pipeline, score_exploration, score_modelisation, score_deploiement, score_cadrage (chacun /20), match_label, match_reasoning, scored_at`
- **Tracking user (manuel)** : `status, application_method, date_applied, date_followup, date_interview, notes, priority`
- **Cycle de vie** : `is_active (0/1), last_checked_at`
- **Méta** : `created_at, updated_at, scraped_at, dedup_key`

Statuts valides (`backend/models.py:VALID_STATUSES`) :
- vide = à postuler
- `Postulé`, `Relancé`, `Entretien`, `Test technique`, `Refusé`, `Accepté`, `Sans réponse`, `Abandonné`
- `Pas intéressé` (offre vue mais ne correspond pas — masquée de "À postuler")

### `target_companies` (entreprises cibles candidature spontanée)

Une ligne par couple **(entreprise, ville)** — index `UNIQUE(LOWER(name), LOWER(city))`.

Colonnes :
- `name, sector, city, relevance, priority, contact_channel, contact_name`
- `notes, feedback, email, reliability, source_url, source`
- `status, date_contacted, date_followup` (tracking applicatif)
- `created_at, updated_at`

Source :
- 65 importées du xlsx historique (`data/companies_spontaneous_extracted.json`)
- +128 importées depuis offres scrapées par ville
- +16 Hautes priorité hors-5-villes
- +52 lignes pour multi-implantation (Airbus Toulouse/Nantes/Paris, Capgemini ×5, etc.)
- = ~260 rows totales

Statuts (`backend/models.py:VALID_COMPANY_STATUSES`) : `Contacté`, `Relancé`, `Entretien`, `Refusé`, `Sans réponse`, `Abandonné`

### `scrape_runs`

Historique des runs de scraping pour audit.

## Connexion

```python
from backend.db import db

with db() as conn:
    rows = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchall()
```

- `db()` est un context manager → commit auto en sortie OK, rollback sur exception
- `row_factory = sqlite3.Row` (accès par clé : `row["title"]`)
- WAL mode activé, FK on

## Règles

- ❌ **JAMAIS de SQL inline** dans `main.py` ou les templates — passer par `queries.py`
- ❌ **JAMAIS de string concat** pour le SQL (`f"... {value}"` est interdit, sauf `ORDER BY` whitelisté)
- ✅ Toujours params nommés `:name` ou positional `?`
- ✅ Toujours retourner `dict` (`dict(row)`), jamais `sqlite3.Row`
- ✅ Pour les writes multi-step : utiliser une seule transaction (le context manager s'en charge)

## Dédoublonnage

### Offres
Stratégie en 2 niveaux à `queries.insert_offer()` / `insert_offers_bulk()` :
1. **Par URL** : `UNIQUE INDEX idx_offers_url ON offers(url) WHERE url IS NOT NULL AND url != ''`
2. **Par clé titre+entreprise+ville normalisée** : champ `dedup_key`, via `make_dedup_key(title, company, city)`

⚠️ **Bug critique fixé** : `make_dedup_key` inclut maintenant la **ville**.
Sans elle, une offre Capgemini "AI Engineer" publiée à Paris ET à Toulouse
serait considérée comme doublon → la 2e jetée silencieusement. Pour un outil
de recherche d'emploi où la localisation est clé, c'est inacceptable.

`normalize_city_for_dedup()` normalise les variantes : "Paris" / "75 - Paris" /
"Paris, France" / "Paris (Saint-Cloud)" → toutes "paris" (vraie dédup).
Migration : `python -m backend.seed_recompute_dedup_keys` recalcule tous les
dedup_key existants.

### Entreprises cibles
Dédup à `queries.insert_target_company()` sur `(LOWER(name), LOWER(city))`. Une même entreprise sur 2 villes = 2 rows distincts (2 candidatures séparées).

## Bulk inserts (performance)

Pour insérer N offres scrapées, **utiliser `queries.insert_offers_bulk(payload)`** :
- 1 seule connexion SQLite + 1 seule transaction
- Dédup en mémoire (charge `existing_urls` et `existing_dedup_keys` une fois)
- Gain x10-x50 sur 1000+ offres vs `insert_offer` × N (qui ouvrait/fermait la connexion à chaque appel)

Signature : `insert_offers_bulk(offers: list[dict]) -> (new_ids: list[int], duplicates: int)`

## Helpers `queries.py` importants

### Offres
- `list_offers(search, status, source, min_score, only_to_apply, include_archived, sort)` : filtré + tri
- `get_offer(id)`, `insert_offer(data)`, `update_offer(id, fields)`, `update_description(id, text)`
- `set_alive_state(id, is_active)` : marque archived/active + stamp `last_checked_at`
- `delete_offer(id)` : DELETE direct (réservé au cleanup URLs mortes + status NULL)
- `apply_llm_scores(scores)` : applique batch JSON de scoring
- `get_stats()` : KPIs (total, to_apply, applied, top_fit, bon_fit, archived, not_interested, etc.)

### Entreprises
- `list_target_companies(search, priority, status, city, other_haute, sort)` : filtré
- `get_target_company(id)`, `insert_target_company(data)`, `update_target_company(id, fields)`
- `count_companies_per_target_city()` : pour les tabs villes
- `count_other_haute()` : compteur "Autres villes Haute"
- `extract_companies_from_offers_by_city(city)` : extraction depuis offres
- `import_companies_from_offers_to_targets(city)` : import depuis offres scrapées
- `get_company_stats()` : KPIs entreprises

## Migration / changement de schéma

1. Modifier `backend/schema.sql`
2. Décider : reset DB ou `ALTER TABLE` ?
3. Pour `ALTER` : ajouter dans `init_schema()` une instruction conditionnelle (vérifier `PRAGMA table_info` d'abord)
4. **Documenter dans CHANGELOG.md**
5. Si renaming/restructuring complexe : créer un script `backend/seed_*.py` ou `backend/dedup_*.py` one-shot idempotent

Migrations passées :
- v1 → v2 : ajout `offers.is_active`, `offers.last_checked_at`
- v2 → v3 : ajout `target_companies.city`, `target_companies.source`
- v3 → v4 : drop `UNIQUE INDEX idx_target_companies_name`, create `UNIQUE INDEX (name, city)`
- v4 → v5 : signature `make_dedup_key(title, company, city)` (bug audit) + script `seed_recompute_dedup_keys`

## Scripts seed/migration one-shot

- `seed_company_cities.py` : remplit `city` pour les 65 entreprises xlsx + duplique multi-villes (Airbus ×3, Capgemini ×5...)
- `seed_high_priority_other_cities.py` : importe entreprises Haute hors-5-villes
- `seed_toulouse_contact_methods.py` : remplit `contact_channel` optimisé pour les 40 Toulouse
- `seed_recompute_dedup_keys.py` : **recompute des `offers.dedup_key`** avec city (fix bug audit)
- `dedup_company_names.py` : fusion des alias (`Capgemini Engineering (ex-Altran)` → `Capgemini Engineering`)

Tous sont idempotents (peuvent être relancés sans risque).

## Reset complet

```powershell
$env:PYTHONIOENCODING="utf-8"; python -m backend.migrate_xlsx
```
→ Vide `offers`, reset AUTOINCREMENT, re-importe depuis le xlsx.

⚠️ Pour `target_companies`, il faut aussi rejouer les seeds dans l'ordre :
1. `python -m backend.migrate_xlsx`
2. `python -m backend.seed_company_cities`
3. `python -m backend.seed_high_priority_other_cities`
4. `python -m backend.seed_toulouse_contact_methods`
5. `python -m backend.dedup_company_names`

## Mojibake

Le xlsx source a des problèmes d'encodage. La fonction `fix_mojibake()` dans `migrate_xlsx.py` corrige les patterns connus (`é` → `é`, `�` → `""`). Réutiliser si nouveau parsing de fichier sale.
