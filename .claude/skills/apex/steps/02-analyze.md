# Step 2 : Analyze

Construire le contexte AVANT d'écrire du code.

## Lancer des sub-agents en parallèle

Utiliser l'outil `Task` (ou `Agent`) pour lancer en parallèle :

1. **explore-codebase** :
   > "Explore la codebase scrapoffreemploi pour trouver les patterns liés à : {{task}}. Identifie : fichiers similaires (queries, routes, templates), helpers réutilisables, conventions à matcher. Retourne synthèse <500 mots."

2. **explore-doc** (seulement si lib externe peu connue) :
   > "Recherche la doc de [lib X] concernant [feature Y]."

3. **web-search** (seulement si infos récentes nécessaires — ex: comment scraper un site spécifique) :
   > "Cherche [question]."

Attendre tous les retours.

## Synthétiser

Combiner les findings :
- Patterns existants à suivre (paths:lines)
- Fichiers à modifier (paths)
- Libs/outils à utiliser (ou à éviter)
- Risques identifiés

Si flag `-s` : sauver la synthèse dans `.claude/.tmp/<feature>-context.md`

## Vérifications spécifiques au projet

- Le xlsx `data/source/candidatures_alternance_AI_Engineer.xlsx` est-il impacté ? → Si oui, **lecture seule obligatoire** (memory user).
- La feature implique-t-elle une clé API externe ? → Si oui, STOP : pas d'API key dans ce projet, workflow batch via chat.
- Touche-t-on au schéma DB ? → Lire `backend/schema.sql` ET prévoir la migration.

**Lis ensuite** `.claude/skills/apex/steps/03-plan.md`
