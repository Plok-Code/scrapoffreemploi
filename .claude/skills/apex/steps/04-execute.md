# Step 4 : Execute

Implémenter le plan.

## Ordre recommandé (dépendances)

1. **Schéma DB** (`backend/schema.sql`) si touché
2. **Constantes / models Pydantic** (`backend/models.py`)
3. **Queries DB** (`backend/queries.py`) — pas de SQL inline ailleurs !
4. **Routes FastAPI** (`backend/main.py`)
5. **Templates Jinja** (`backend/templates/`)
6. **Scrapers** (`backend/scrapers/`) si concerné
7. **CLI / scripts** (`cli.py` à venir, `backend/migrate_xlsx.py`)

## Checklist à chaque modification

- [ ] Type hints modernes (`list[dict]`, `str | None`)
- [ ] Imports ordonnés (stdlib, third-party, local)
- [ ] Pattern existant suivi (avoir lu 3+ fichiers similaires en step 2)
- [ ] Erreurs gérées explicitement (`HTTPException(404, ...)`)
- [ ] Pas de SQL inline en dehors de `queries.py`
- [ ] Pas de commentaires inutiles (only WHY non-évident)
- [ ] Pas de `print` dans le code prod (sauf migrate scripts)

## Si tu rencontres un inconnu non prévu

→ **STOP**. Surface au user. Attends input.

## Encoding PowerShell

Pour les print Python avec accents :
```powershell
$env:PYTHONIOENCODING="utf-8"; python -c "..."
```

**Lis ensuite** `.claude/skills/apex/steps/05-verify.md`
