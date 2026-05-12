---
name: one-shot
description: |
  Quick fix workflow for small, simple changes (1-3 files max).
  Use for typos, small UI tweaks, simple bug fixes, copy changes.
  If the task grows beyond 3 files or becomes a new feature, STOP and
  suggest /apex instead.
arguments:
  - name: task
    description: The small task to do
    required: true
---

# One-shot Workflow

Tâche : **{{task}}**

## Process

1. **Identification rapide** des fichiers à toucher (max 2-3)
2. **Appliquer le changement** directement
3. **Smoke test** : `python -c "from backend.main import app; print('OK', len(app.routes))"`
4. **Reporter brièvement** au user (fichiers + nature du changement)

## Stop conditions

Si pendant l'exécution tu réalises que :
- Plus de 3 fichiers à toucher
- Une vraie feature à créer (pas juste un fix)
- Migration DB nécessaire
- Plusieurs sub-agents nécessaires

→ **STOP**, surface au user, suggère `/apex`.

## Skip (vs /apex)

- ❌ Exploration profonde de la codebase
- ❌ Plan formel
- ❌ Multi-step verification
- ❌ Sub-agents

## Toujours

- ✅ Smoke test rapide après modif
- ✅ Bref rapport au user
- ✅ Mettre à jour `CHANGELOG.md` si user-facing (ne pas demander à Claude pour ça — c'est inclus)
- ✅ Encoding PowerShell si commande Python avec accents : `$env:PYTHONIOENCODING="utf-8";`
