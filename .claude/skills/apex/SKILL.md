---
name: apex
description: |
  Complete feature development workflow for scrapoffreemploi (exploration,
  planning, execution, verification). Use for medium-to-large features
  (>3 files) or anything touching DB schema, scrapers, or major UI flows.
arguments:
  - name: task
    description: The feature or task to implement
    required: true
  - name: flags
    description: |
      Optional flags:
      -a / --auto       Skip user confirmations (fully autonomous)
      -b / --branch     Create a git branch (only if .git exists)
      -t / --test       Write tests (informal — there are no formal tests yet)
      -s / --save       Save intermediate artifacts to .claude/.tmp/
      --no-plan         Skip plan mode (for clearer / simpler features)
    required: false
---

# Apex Workflow

Tâche : **{{task}}**

Workflow **prompt discovery multi-step**. Tu DOIS lire les steps dans l'ordre, un par un.

## Étapes

1. **READ** `.claude/skills/apex/steps/01-init.md` puis suis-le
2. Ensuite, **READ** `.claude/skills/apex/steps/02-analyze.md`
3. Continue avec `03-plan.md`, `04-execute.md`, `05-verify.md` dans l'ordre

⚠️ Ne pas sauter d'étapes. Ne pas tout faire en une fois.

Commence MAINTENANT en lisant `01-init.md`.
