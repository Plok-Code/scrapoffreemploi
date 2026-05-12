# Step 3 : Plan

1. Si `--no-plan` flag : skip directement vers step 4
2. Si `-a` flag NON passé : entrer en plan mode (Shift+Tab équivalent — ou simplement annoncer "Je propose ce plan, valide avant que j'exécute")

3. Output un plan clair :
   - **Fichiers à CRÉER** (chemins absolus depuis racine projet)
   - **Fichiers à MODIFIER** (avec résumé des changements)
   - **Ordre d'opérations** (typiquement : schema → queries → models → routes → templates)
   - **Risques / inconnues**
   - **Impact DB** (migration nécessaire ? reset ? ALTER ?)
   - **Impact CHANGELOG.md** (entrée à ajouter)

4. Si `-s` flag : sauver le plan dans `.claude/.tmp/<feature>-plan.md`
5. Si `-a` flag : continuer sans demander
6. Sinon : attendre confirmation du user

**Lis ensuite** `.claude/skills/apex/steps/04-execute.md`
