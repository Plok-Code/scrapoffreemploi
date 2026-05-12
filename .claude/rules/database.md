---
description: SQLite schema, queries, migrations
paths:
  - backend/schema.sql
  - backend/db.py
  - backend/queries.py
  - backend/migrate_xlsx.py
---

# Database (SQLite via stdlib `sqlite3`)

## Source de vérité

- **Fichier DB** : `data/app.db` (gitignored)
- **DDL** : `backend/schema.sql` (idempotent grâce à `CREATE TABLE IF NOT EXISTS`)
- **Toujours initialiser via** : `init_schema()` dans `backend/db.py`

## Tables

### `offers` (table principale)

Colonnes par groupe :
- **Offre (immutable post-scraping)** : `title, company, city, department, source, url, description, date_published, remote, contract_type, salary`
- **Scoring LLM** : `match_score (0-100), score_pipeline, score_exploration, score_modelisation, score_deploiement, score_cadrage (chacun /20), match_label, match_reasoning, scored_at`
- **Tracking user (manuel)** : `status, application_method, date_applied, date_followup, date_interview, notes, priority`
- **Méta** : `created_at, updated_at, scraped_at, dedup_key`

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
- ❌ **JAMAIS de string concat** pour le SQL (`f"... {value}"` est interdit, sauf le `ORDER BY` whitelisté)
- ✅ Toujours params nommés `:name` ou positional `?`
- ✅ Toujours retourner `dict` (`{k: v for k, v in row}`), jamais `sqlite3.Row`
- ✅ Pour les writes multi-step : utiliser une seule transaction (le context manager s'en charge)

## Dédoublonnage

Stratégie en 2 niveaux :
1. **Par URL** : `UNIQUE INDEX idx_offers_url ON offers(url) WHERE url IS NOT NULL AND url != ''`
2. **Par clé titre+entreprise normalisée** : champ `dedup_key`, créé via `make_dedup_key(title, company)` dans `db.py`

Lors d'un INSERT, vérifier les 2 :
```python
from backend.db import make_dedup_key

key = make_dedup_key(title, company)
# tester URL d'abord, sinon dedup_key
```

## Migration / changement de schéma

1. Modifier `backend/schema.sql`
2. Décider : reset DB (re-lancer `migrate_xlsx`) ou `ALTER TABLE` ?
3. Pour `ALTER` : ajouter dans `init_schema()` une instruction conditionnelle (sqlite3 ne supporte pas tout l'ALTER)
4. **Documenter dans CHANGELOG.md**

## Reset complet

```powershell
$env:PYTHONIOENCODING="utf-8"; python -m backend.migrate_xlsx
```
→ Vide `offers`, reset AUTOINCREMENT, re-importe depuis le xlsx.

## Mojibake

Le xlsx source a des problèmes d'encodage. La fonction `fix_mojibake()` dans `migrate_xlsx.py` corrige les patterns connus (`é` → `é`, `�` → `""`). Réutiliser si nouveau parsing de fichier sale.
