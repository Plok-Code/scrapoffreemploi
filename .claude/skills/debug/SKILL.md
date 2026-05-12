---
name: debug
description: |
  Systematic bug debugging with hypotheses, investigation, and verification.
  Use when an error is reported, a route returns 500, a scraper fails, or
  a behavior is unexpected.
arguments:
  - name: error
    description: Description of the bug or error message
    required: true
---

# Debug Workflow

Bug : **{{error}}**

## Étape 1 : Reproduire

1. Lire le message d'erreur attentivement (stack trace complet si dispo)
2. Identifier fichier/fonction impliqué (depuis stack trace ou description)
3. Si logs manquants :
   - Ajouter `print(f"[DEBUG] var={var!r}")` aux points clés
   - Demander au user de relancer et partager l'output
4. Obtenir les étapes exactes de reproduction

## Étape 2 : Formuler 3 hypothèses

Classées par probabilité décroissante :
1. **Plus probable** : ...
2. **Possible** : ...
3. **Moins probable** : ...

## Étape 3 : Investiguer

Pour chaque hypothèse :
- Lire le code concerné (`Read`)
- Si `.git` existe : `git log --oneline -- <fichier>` pour les changements récents
- Si scraper en cause : vérifier le JSON brut dans `data/scrapes/`
- Si DB en cause : query directe en CLI :
  ```powershell
  python -c "import sqlite3; c=sqlite3.connect('data/app.db'); print(list(c.execute('SELECT ...')))"
  ```

## Étape 4 : Fixer

Une fois la root cause identifiée :
- Proposer le fix au user (si pas en mode auto)
- Appliquer après confirmation
- Vérifier : smoke test + curl sur la route en cause + `python -m backend.migrate_xlsx` si DB touchée

## Étape 5 : Prévenir

Si applicable : mettre à jour `.claude/rules/` pour empêcher la récidive.

Exemple :
> "Le bug venait du fait que le scraper renvoyait des URLs avec `?` mal échappés. J'ajoute une règle dans `.claude/rules/scrapers.md` : 'Toujours quoter les URLs avant insertion en DB.'"

## Anti-patterns à éviter

- ❌ Fix symptômes sans comprendre la cause
- ❌ Toucher du code non lié au bug
- ❌ Ajouter `try/except: pass` pour "que ça marche"
- ❌ Déclarer "fixé" sans vérification
- ❌ Modifier le xlsx C:\Users\novar\Downloads\... (lecture seule)

## Bugs typiques de ce projet (référence)

- **Mojibake** : si tu vois des `?` ou `é` à la place d'accents → encoding cp1252/utf-8. Utiliser `fix_mojibake()` de `migrate_xlsx.py` ou préfixer la commande avec `$env:PYTHONIOENCODING="utf-8"`.
- **404 sur /offers/{id}** : les IDs après une migration repartent à 1, mais si tu as fait 2 migrations sans reset AUTOINCREMENT, l'ID 1 peut ne pas exister. Solution : reset via `DELETE FROM sqlite_sequence` (déjà dans `migrate_xlsx.py`).
- **403/429 du scraper** : User-Agent manquant ou rate limit. Vérifier `_http.py` (à venir).
- **Form HTML qui n'updatent pas** : vérifier que les `Form("")` sont là (pas `Form(None)`) et que `queries.update_offer` convertit `""` → `None`.
