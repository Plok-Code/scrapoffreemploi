# Workflow rules (always loaded)

## CRITICAL : avant toute modif de code

1. **Lire au moins 3 fichiers similaires** dans la codebase pour matcher les patterns existants
2. **Vérifier les imports existants** avant d'ajouter une dépendance
3. **Utiliser Glob et Grep** pour vérifier qu'une fonction/route/template n'existe pas déjà
4. **Lire les types/Pydantic models** (`backend/models.py`) avant de toucher au schéma de données

## Avant toute modif DB

1. **Lire `backend/schema.sql`** pour comprendre le modèle
2. **Lire `backend/queries.py`** pour voir si une query similaire existe déjà
3. Si modif de schéma : modifier `schema.sql` ET migrer la DB existante (script ou ALTER)

## Après toute modif de code

1. **Smoke-test rapide** : importer le module modifié pour vérifier qu'il parse
   ```powershell
   python -c "from backend.main import app; print('OK', len(app.routes))"
   ```
2. **Lancer pytest** si modif touchant `db.py`, `queries.py`, `filter_alternance.py`, `scrapers/runner.py`, `scrapers/base.py`, ou `_keywords.py` :
   ```powershell
   $env:PYTHONIOENCODING="utf-8"; python -m pytest tests/ -q
   ```
   83 tests, ~2 sec. Si un test casse, fixer **avant** de déclarer "done".
3. Si modif de `queries.py` : tester aussi avec une requête réelle (`curl http://localhost:8000/`)
4. **Si l'app tourne déjà** (uvicorn en background) : la redémarrer pour charger le nouveau code
   ```powershell
   # Kill l'ancien process puis relance
   Get-Process python | Where-Object {$_.Id -eq <PID>} | Stop-Process -Force
   Start-Process python -ArgumentList "-m","backend" -WorkingDirectory "<path>"
   ```
   Sans reload, le user voit l'ancien code et peut signaler un faux bug (`{"detail":"Not Found"}`).
5. **Mettre à jour `CHANGELOG.md`** si changement user-facing (nouvelle route, nouvelle colonne DB, nouveau template)
6. Reporter brièvement les fichiers touchés au user

## Si tu ajoutes une nouvelle fonction critique (scoring, dédup, scrape...)

**TOUJOURS écrire un test pytest** dans `tests/` :
- Un fichier `tests/test_<feature>.py`
- Une classe par fonction
- Des fixtures HTML mockées dans `conftest.py` si besoin (jamais de network call dans les tests)
- Coverage minimale : cas keep + cas reject + cas edge (None, vide, doublons)

Exemple : voir `tests/test_dedup_key.py:test_critical_bug_paris_vs_toulouse_kept` qui formalise une règle métier.

## Quand tu doutes

- Si tu ne trouves pas de pattern dans la codebase : DEMANDE au user
- Si la tâche touche >5 fichiers : suggère `/apex`
- Si lib inconnue : utilise l'agent `explore-doc` (avec context7 si dispo)
- Si info récente nécessaire (changement API web, doc d'un site) : utilise `web-search` (avec exa si dispo)

## Encoding PowerShell (Windows)

Toujours préfixer les commandes Python qui affichent du français :
```powershell
$env:PYTHONIOENCODING="utf-8"; python -m backend.migrate_xlsx
```
Sinon les accents deviennent `?` ou `�`.

## Ne fais JAMAIS

- ❌ Modifier `data/source/candidatures_alternance_AI_Engineer.xlsx` (lecture seule, conservé pour audit)
- ❌ Mettre du SQL inline dans `main.py` ou les templates (passer par `queries.py`)
- ❌ Introduire Node.js, pnpm, React, Vite ou un build step JS
- ❌ Ajouter Anthropic API ou autre clé API (workflow batch via chat seulement)
- ❌ Créer des commentaires sans qu'on te le demande
- ❌ Utiliser `Remove-Item -Recurse -Force` sur du contenu user
- ❌ Skip les hooks de pré-commit (--no-verify)

## Fais TOUJOURS

- ✅ Matcher le style existant (snake_case Python, kebab-case pour les routes URL)
- ✅ Utiliser les helpers existants (`backend/db.py`, `backend/queries.py`, `backend/models.py`)
- ✅ Type hints Python (`str | None`, `list[dict]`, etc.) — Python 3.10+ syntax
- ✅ Validation Pydantic pour les payloads externes (API entrée) ET pour les objets scrapés (`RawOffer`)
- ✅ `logger.info/warning/error` au lieu de `print()` dans les modules (loguru auto-init)
- ✅ `tenacity` @retry pour les calls HTTP externes, pas de retry maison
- ✅ `RateLimiter` pour les boucles d'appels HTTP (anti-ban IP)
- ✅ `insert_offers_bulk` pour les batchs d'insertion (pas `insert_offer` × N)
- ✅ Tester l'import du module modifié avant de déclarer "done"
- ✅ Lancer `pytest` après modif fonctionnelle (filter, dedup, scoring, scrape...)

## Ne fais JAMAIS (additionnel)

- ❌ `except Exception: pass` silencieux — toujours `logger.warning("...", err=str(e))` au minimum
- ❌ `print()` dans les modules non-CLI — `logger.X` à la place
- ❌ Retry HTTP maison avec `time.sleep(2**i)` — utiliser `tenacity` via `get_with_retry`
- ❌ Modifier `make_dedup_key` sans inclure la ville (bug critique : Paris vs Toulouse)
- ❌ Lancer Playwright sans passer par `persistent_browser` (pas de lock guard)
