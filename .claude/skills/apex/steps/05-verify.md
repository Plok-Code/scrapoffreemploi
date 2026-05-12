# Step 5 : Verify

Validation finale.

## 1. Smoke test du module modifié

```powershell
python -c "from backend.main import app; print('Routes:', len(app.routes))"
```

Si erreur d'import → revenir corriger.

## 2. Test fonctionnel rapide

Lancer le serveur en background et tester les routes touchées :
```powershell
python -m backend
# dans un autre terminal (ou via curl) :
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/offers/1
curl http://127.0.0.1:8000/api/stats
```

Vérifier :
- HTTP 200 pour les routes existantes
- HTML rendu correctement (pas de KeyError Jinja)
- Données cohérentes (les KPI changent comme attendu)

## 3. Si modif DB

- Re-lancer la migration : `$env:PYTHONIOENCODING="utf-8"; python -m backend.migrate_xlsx`
- Vérifier le count : `python -c "import sqlite3; print(sqlite3.connect('data/app.db').execute('SELECT COUNT(*) FROM offers').fetchone()[0])"`

## 4. Tests pytest (par défaut si modif fonctionnelle)

```powershell
$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/ -q
```

Si la modif touche `db.py`, `queries.py`, `filter_alternance.py`, `scrapers/*`, ou `_keywords.py` → **écrire un test pytest dans `tests/test_<feature>.py`** :
- Une classe par fonction testée
- Fixtures HTML mockées dans `conftest.py` si besoin
- Coverage : keep + reject + edge (None, vide, doublons)
- Pas de network call (utiliser des fixtures statiques)

Exemple : `tests/test_dedup_key.py::test_critical_bug_paris_vs_toulouse_kept` formalise une règle métier critique.

Si `-t` est explicitement demandé : écrire le test même si la zone modifiée n'a pas de test existant.

## 5. Mettre à jour `CHANGELOG.md`

Ajouter dans la section `[Unreleased]` :
```markdown
### Added / Fixed / Changed
- Brève description (1 ligne)
```

## 6. Rapport final au user

```
✅ Tâche terminée : [résumé]

Fichiers créés :
- backend/x.py (purpose)

Fichiers modifiés :
- backend/main.py (3 nouvelles routes)
- backend/queries.py (2 fonctions)

Smoke test : passé (X routes chargées)
Curl test : 200 OK sur les routes touchées

[Si applicable] CHANGELOG.md mis à jour.

[Si applicable] Prochaines étapes suggérées : ...
```

DONE. Ne continue pas — attends le user.
