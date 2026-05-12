---
name: review-code
description: |
  Comprehensive code review with parallel reviewers (security, performance,
  style). Use before merging code or after completing major features in
  scrapoffreemploi.
arguments:
  - name: scope
    description: |
      What to review:
      - "pending changes" → diff vs last commit (or all uncommitted if no .git)
      - path → review files in that path (e.g. "backend/scrapers/hellowork.py")
    required: true
---

# Code Review Workflow

Scope : **{{scope}}**

## Étape 1 : Récupérer ce qui doit être reviewé

- Si `"pending changes"` :
  - Si `.git` existe : `git diff HEAD` (ou `git status` si pas encore commit)
  - Sinon : lister les fichiers modifiés récemment dans `backend/`, `cli.py`, templates
- Si path : Glob les fichiers correspondants

## Étape 2 : Review multi-aspect (sub-agents en parallèle)

Lancer 3 sub-agents en parallèle via `Task` :

1. **Security reviewer** (prompt) :
   > "Review ces fichiers pour : SQL injection (string concat dans queries), secrets en dur (`.env` jamais commité), validation des inputs (Pydantic / Form), exposition d'erreurs internes (stack trace), XSS dans les templates Jinja (autoescape OK ?), accès direct au xlsx user."

2. **Performance reviewer** :
   > "Review ces fichiers pour : N+1 queries SQL, requêtes sans LIMIT, fichiers chargés en mémoire complète, scrapers sans RateLimiter, **insert_offer × N au lieu d'insert_offers_bulk** (1 transaction), locks SQLite (WAL mode OK)."

3. **Style/qualité reviewer** :
   > "Review ces fichiers pour : respect des conventions du projet (snake_case Python, type hints modernes `list[dict]`, SQL via queries.py uniquement, pas de SQL inline), import order, gestion d'erreurs (`logger.warning` JAMAIS `except: pass`), `print()` interdit en module (utiliser `logger.X`), naming kebab-case pour les routes URL, **dedup_key inclut city** (bug critique)."

## Étape 3 : Synthétiser

Compiler les findings par sévérité :

```
# Code Review — [scope]

## 🔴 CRITICAL (must fix)
- [path:line] description du problème + fix proposé

## 🟠 IMPORTANT (should fix)
- [path:line] ...

## 🟡 MINOR (nice to have)
- [path:line] ...

## 💚 GOOD (points positifs)
- [path:line] ...

## Résumé
[Total : X critical, Y important, Z minor. Recommandation : APPROVE / REQUEST CHANGES]
```

## Étape 4 : Output

Sauver dans `.claude/.tmp/review-<YYYY-MM-DD>.md` ET afficher dans le chat.

## Checklist spécifique scrapoffreemploi

- [ ] SQL toujours dans `queries.py` (pas inline ailleurs)
- [ ] `insert_offers_bulk` utilisé pour les batchs (pas `insert_offer` × N)
- [ ] `make_dedup_key(title, company, **city**)` — la ville fait partie de la clé
- [ ] Pas d'écriture sur le xlsx user / le `.env`
- [ ] Pas d'API key Anthropic introduite
- [ ] Pas de Node.js / build step JS ajouté
- [ ] Type hints sur les fonctions exportées
- [ ] Pydantic models pour les payloads externes (`RawOffer` BaseModel + validators)
- [ ] Templates Jinja : pas de logique métier complexe
- [ ] Scrapers : User-Agent défini, `RateLimiter` présent, `get_with_retry` (tenacity)
- [ ] Playwright : passer par `persistent_browser` (lock guard)
- [ ] `logger.X` jamais `print()` dans les modules non-CLI
- [ ] `except Exception as e: logger.warning(...)` jamais `except: pass`
- [ ] Tests pytest pour les fonctions critiques (filter, dedup, scoring)
- [ ] CHANGELOG.md mis à jour pour les changements user-facing
