# Step 1 : Init

1. Parse les flags depuis la requête utilisateur d'origine :
   - `-a` / `--auto` : skip confirmations
   - `-b` / `--branch` : créer une branche git (seulement si `.git` existe — ce projet n'est PAS un repo git pour l'instant)
   - `-t` / `--test` : écrire des tests (informel — pas de suite de tests formelle)
   - `-s` / `--save` : sauver les artefacts intermédiaires dans `.claude/.tmp/`
   - `--no-plan` : skip le plan mode

2. Si `-b` flag ET `.git` existe (vérifier avec `git rev-parse --git-dir 2>$null`) :
   ```powershell
   git checkout -b feature/<short-name>
   ```
   Sinon : ignorer le flag et continuer.

3. Affiche une ligne récap au user :
   > "Je vais implémenter : [tâche]. Mode : [flags actifs]."

4. **Lis ensuite** `.claude/skills/apex/steps/02-analyze.md`
