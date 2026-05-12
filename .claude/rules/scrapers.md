---
description: Scrapers (à venir) — patterns et conventions
paths:
  - backend/scrapers/**
  - backend/jobs/**
---

# Scrapers

## État actuel

Dossier `backend/scrapers/` créé mais **vide** au moment où cette règle est écrite. À implémenter quand l'utilisateur le demande.

## Sources cibles (héritées de l'ancien projet, voir `legacy/sources_2026_05_11/`)

Job boards principaux :
- **HelloWork** (le plus simple, JSON public)
- **France Travail** (API officielle dispo)
- **APEC**
- **Welcome to the Jungle** (WTTJ)
- **Indeed**
- **LinkedIn** (le plus difficile : Playwright + cookies persistés probablement nécessaire)

Plus 9 listes sectorielles manuelles (banques/assurances, conseil/ESN, défense/aéro, énergie, etc.) — voir `legacy/sources_2026_05_11/*.json` pour les exemples de données.

## Architecture à respecter

```
backend/scrapers/
├── __init__.py
├── base.py          # ABC Scraper avec fetch_list() / fetch_detail()
├── registry.py      # SCRAPERS = {"hellowork": HelloWorkScraper, ...}
├── _http.py         # session httpx réutilisable, fallback Playwright si bloqué
├── hellowork.py
├── francetravail.py
├── apec.py
├── wttj.py
├── indeed.py
└── linkedin.py
```

## Interface `Scraper` (à créer dans base.py)

```python
from abc import ABC, abstractmethod

class Scraper(ABC):
    source_name: str  # "Hellowork", "France Travail", etc.

    @abstractmethod
    def fetch_list(self, *, keywords: list[str], region: str = "France") -> list[dict]:
        """Liste les offres alternance correspondant aux mots-clés."""

    @abstractmethod
    def fetch_detail(self, url: str) -> dict | None:
        """Récupère la description complète d'une offre. Retourne None si 404/dead."""
```

## Filtrage AU scraping (règle métier)

L'app filtre côté scraper :
1. Toujours : `contract = alternance` (via filtres URL du site)
2. Toujours : `country = France` (via filtres URL du site)
3. Toujours : titre OU description contient au moins un mot-clé parmi :
   - IA, AI, artificial intelligence, intelligence artificielle
   - data, donnée(s)
   - ML, machine learning, deep learning
   - MLOps, LLM, NLP, computer vision, RAG
   - AI engineer, data scientist, data engineer

→ Centraliser la liste de mots-clés dans `backend/scrapers/_keywords.py`.

## Dédoublonnage post-scrape

Après `fetch_list()`, le `runner` :
1. Calcule `dedup_key = make_dedup_key(title, company)` (de `backend/db.py`)
2. Vérifie en DB : URL existante OU dedup_key existante → skip
3. Si offre nouvelle ET URL valide → `fetch_detail()` pour la description
4. Insère en DB avec `status=NULL`, `match_score=NULL`, `scraped_at=now`

## Output batch JSON pour scoring

Après un run de scrape, écrire :
```
data/batches/{YYYY-MM-DD}_to_score.json
```

Format attendu par moi (Claude) :
```json
[
  {
    "id": 195,
    "title": "...",
    "company": "...",
    "description": "..."
  },
  ...
]
```

## Convention `httpx`

- Session unique partagée : `client = httpx.Client(timeout=30, follow_redirects=True)`
- User-Agent réaliste obligatoire : `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."`
- Backoff exponentiel sur 429/503 (utiliser `tenacity` si nécessaire — l'ajouter à requirements.txt)
- Pas d'auth/login dans les scrapers stables — si site bloque, escalader vers Playwright en background

## Convention parsing

- BeautifulSoup + lxml pour HTML
- `selectolax` si performance critique (à ajouter si besoin)
- Toujours valider les champs critiques (titre, URL) — skip si manquant

## Quand ajouter un scraper

1. Lire 2 scrapers existants (HelloWork + France Travail recommandés, plus simples)
2. Créer `backend/scrapers/<source>.py` qui implémente `Scraper`
3. L'enregistrer dans `registry.py`
4. Tester en isolation : `python -m backend.scrapers.<source>` (ajouter un `if __name__ == "__main__":` de test)
5. Mettre à jour `docs/SOURCES.md` avec la méthode utilisée (httpx vs Playwright, robustesse)

## Anti-patterns

- ❌ Scrapers monolithiques de 500+ lignes — découper en helpers
- ❌ Hard-coder les URLs de recherche — paramétrer
- ❌ Ignorer les 429/503 — implémenter du backoff
- ❌ Polluer le main avec la logique de scrape — passer par `runner`
- ❌ Scraper sans User-Agent (banni immédiatement)
