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
2. Si modif de queries.py : tester avec une requête réelle (`curl http://localhost:8000/`)
3. **Si l'app tourne déjà** (uvicorn en background) : la redémarrer pour charger le nouveau code
   ```powershell
   # Kill l'ancien process puis relance
   Get-Process python | Where-Object {$_.Id -eq <PID>} | Stop-Process -Force
   Start-Process python -ArgumentList "-m","backend" -WorkingDirectory "<path>"
   ```
   Sans reload, le user voit l'ancien code et peut signaler un faux bug (`{"detail":"Not Found"}`).
4. **Mettre à jour `CHANGELOG.md`** si changement user-facing (nouvelle route, nouvelle colonne DB, nouveau template)
5. Reporter brièvement les fichiers touchés au user

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
- ✅ Validation Pydantic pour les payloads externes (API entrée)
- ✅ Tester l'import du module modifié avant de déclarer "done"
