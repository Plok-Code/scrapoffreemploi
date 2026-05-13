# Scrap'OffreEmploi — Tracker alternance AI Engineer

App web locale pour scraper, scorer et suivre les offres d'alternance "AI Engineer" en France, alignées avec le programme OpenClassrooms AI Engineer.

## Quickstart

```powershell
# 1. Une seule fois : créer le venv et installer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Migrer l'ancien xlsx vers SQLite (une seule fois)
python -m backend.migrate_xlsx

# 3. Lancer l'app
.\run.ps1
# → http://localhost:8000
```

## Structure

```
backend/    Code FastAPI + Jinja + SQLite
cli.py      Commandes : scrape, apply-scores, export-batch
data/       SQLite + batches JSON + scrapes (gitignored)
docs/       ARCHITECTURE.md, CRITERIA.md
reference/  PDF du programme OC + pages PNG
legacy/     Ancien code archivé
```

## Workflow scoring (via chat Claude)

1. Tu cliques "Scraper" dans l'app (ou `python cli.py scrape`).
2. L'app génère `data/batches/{date}_to_score.json` avec les offres nouvelles.
3. Dans le chat Claude : "score le dernier batch".
4. Claude écrit `data/batches/{date}_scores.json`.
5. Tu lances `python cli.py apply-scores` (ou bouton dans l'UI).

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) et [docs/CRITERIA.md](docs/CRITERIA.md).
