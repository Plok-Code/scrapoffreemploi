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
2. **Consulter les logs** : `Get-Content data\logs\app.log -Tail 100` et `data\logs\errors.log`
   - loguru capture les exceptions avec `backtrace + diagnose` dans `errors.log`
3. Identifier fichier/fonction impliqué (depuis stack trace ou description)
4. Si logs manquants :
   - Ajouter `logger.debug("var={v!r}", v=var)` aux points clés (PAS `print`)
   - Demander au user de relancer et partager l'output
5. Obtenir les étapes exactes de reproduction

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
- ❌ Ajouter `try/except: pass` pour "que ça marche" — toujours `logger.warning("...", err=str(e))`
- ❌ Déclarer "fixé" sans vérification (pytest + smoke + curl)
- ❌ Modifier `data/source/candidatures_alternance_AI_Engineer.xlsx` (lecture seule)
- ❌ Modifier le `.env` sans demander confirmation user (creds FT dedans)
- ❌ Supprimer `data/.playwright_profile/` entier (on perd les logins LinkedIn)

## Bugs typiques de ce projet (référence)

- **Mojibake** : `?` ou `é` à la place d'accents → encoding cp1252/utf-8. Utiliser `fix_mojibake()` de `migrate_xlsx.py` ou préfixer la commande avec `$env:PYTHONIOENCODING="utf-8"`.
- **404 sur /offers/{id}** : les IDs après une migration repartent à 1, mais si tu as fait 2 migrations sans reset AUTOINCREMENT, l'ID 1 peut ne pas exister. Solution : reset via `DELETE FROM sqlite_sequence` (déjà dans `migrate_xlsx.py`).
- **{"detail":"Not Found"} sur /companies ou route récente** : `uvicorn` tourne avec l'ancien code chargé en mémoire. Solution : kill le process Python + relancer `python -m backend`.
- **403/429 du scraper** : User-Agent manquant ou rate limit. Vérifier `_http.py` (`DEFAULT_HEADERS`, `RateLimiter`). Si Cloudflare → mode lent Playwright peut aider.
- **Form HTML qui n'updatent pas** : vérifier que les `Form("")` sont là (pas `Form(None)`) et que `queries.update_offer` convertit `""` → `None`.
- **`_SCRAPE_STATE.running=True` bloqué** : un scrape a planté silencieusement. Solutions :
  1. `POST /api/scrape/reset` (escape-hatch endpoint)
  2. Redémarrer uvicorn (reset auto au startup)
- **PlaywrightProfileLocked** : `data/.playwright_profile/SingletonLock` présent. Vérifier qu'aucun Chromium tourne. Si oui, supprimer manuellement le `SingletonLock` (PAS le dossier entier — on perd les cookies).
- **Doublons offres Paris vs Toulouse** : si tu vois 1 seule offre alors qu'il y en a 2 (1 par ville), vérifier `make_dedup_key` — la ville DOIT être dans la clé. Relancer `python -m backend.seed_recompute_dedup_keys` si besoin.
- **OAuth FT 400 invalid_client** : l'API n'est pas souscrite côté console FT (`francetravail.io/data/api/offres-emploi` → "Mes API"). Vérifier que "Offres d'emploi v2" et "La Bonne Boite v2" sont dans la liste.
- **Logs incompréhensibles** : `data/logs/errors.log` capture la stacktrace complète avec `backtrace=True, diagnose=True` (loguru). Plus complet que stdout.
