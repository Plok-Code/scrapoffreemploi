---
description: Scrapers — patterns, SaaS RH supportés, pipeline complet
paths:
  - backend/scrapers/**
  - backend/filter_alternance.py
  - backend/heuristic_scorer.py
---

# Scrapers

## État actuel (mai 2026)

Plateforme complète avec dispatcher multi-SaaS dans `backend/scrapers/`.

## Architecture

```
backend/scrapers/
├── _http.py          # Session httpx réutilisable (UA Chrome, retry exponentiel, NO brotli)
├── _keywords.py      # Regex IA/ML/DL/LLM/data (compilée 1 fois)
├── _playwright.py    # persistent_browser headless pour scrape SPA / loggué
├── base.py           # ABC Scraper + dataclass RawOffer
├── registry.py       # SCRAPERS dict {name: instance}
├── runner.py         # Orchestrateur : run_scrape + check_alive + cleanup + run_full_scrape
├── _generic.py       # GenericScraper (JSON-LD JobPosting → microdata → main/article)
├── hellowork.py      # HelloWork (httpx + parsing [data-cy=serpCard] + JSON-LD detail)
├── francetravail.py  # API OAuth2 v2 (E1/E2 alternance) — credentials dans .env
├── wttj.py           # WTTJ via Algolia public keys
├── linkedin.py       # Playwright loggué (archives expired)
├── company_portals.py # Dispatcher SaaS RH (Workable/Lever/Workday/Greenhouse/Taleez/Phenom/Playwright)
└── labonneboite.py   # LBB v2 (bloqué 403, habilitation FT supplémentaire requise)
```

## Sources implémentées (job boards)

| Source | Méthode | Fichier | Volume typique |
|---|---|---|---|
| **France Travail** | API OAuth2 v2 (E1+E2) | `francetravail.py` | ~800-1000 offres/scrape (max 1150/mot-clé) |
| **Welcome to the Jungle** | Algolia public keys | `wttj.py` | ~250 offres/scrape |
| **HelloWork** | httpx + JSON-LD | `hellowork.py` | ~50-120 offres/scrape |
| **LinkedIn** | Playwright loggué | `linkedin.py` | ❌ archives = expired_jd_redirect |

## SaaS RH supportés (portails entreprises)

`company_portals.py` dispatch automatiquement par URL :

| SaaS RH | Méthode | Status |
|---|---|---|
| **Workable** | API JSON `apply.workable.com/api/v3/accounts/{slug}/jobs` | ✅ Fonctionne |
| **Lever** | API JSON `api.lever.co/v0/postings/{slug}?mode=json` | ✅ Testé 104 offres Mistral |
| **Workday** | API JSON `/wday/cxs/{tenant}/{site}/jobs` (POST search) | ✅ Pour ceux exposant l'API publique |
| **Greenhouse** | API JSON `boards-api.greenhouse.io/v1/boards/{slug}/jobs` | ✅ Testé 99 offres Doctolib |
| **Taleez** | HTML SSR parsing `{tenant}.taleez.com/` | ⚠️ Peu de hits sur landing pages |
| **Phenom People** | Endpoints `/api/widget/jobsSearch` | ⚠️ Tenant_id requis |
| **Generic HTML** | Parse `<a href>` avec `/jobs/`, `/offres/` | Best-effort |
| **Playwright** (fallback opt-in) | Chromium headless + DOM rendu | ✅ Couvre SPAs React (Capgemini, Airbus, Atos, Sopra Steria...) |

## Interface `Scraper` (`base.py`)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class RawOffer:
    title: str
    company: str | None = None
    city: str | None = None
    department: str | None = None
    url: str | None = None
    source: str = ""
    description: str | None = None
    date_published: str | None = None
    contract_type: str | None = None
    salary: str | None = None
    remote: str | None = None
    raw: dict | None = None

class Scraper(ABC):
    source_name: str

    @abstractmethod
    def fetch_list(self, *, keywords: list[str], max_pages: int = 5) -> list[RawOffer]: ...

    def fetch_detail(self, url: str) -> str | None:
        """Récupère la description complète. Optionnel."""
```

## Filtrage AU scraping (règle métier)

Côté serveur si supporté (FT `natureContrat=E1,E2`, WTTJ Algolia filter `contract_type:apprenticeship`).

Côté client TOUJOURS : `matches_keywords(title, description)` dans `_keywords.py`.

## Dédoublonnage post-scrape

À l'insertion via `queries.insert_offer()` :
1. **Par URL** : `UNIQUE INDEX idx_offers_url ON offers(url)`
2. **Par clé titre+entreprise normalisée** : champ `dedup_key`

## Pipeline complet `run_full_scrape()`

Appelé par `POST /api/scrape` (source=all) :

```python
1. cleanup_dead_unstatused()      # ping URLs, delete sans-statut, archive avec
2. for src in [FT, WTTJ, HW]:
       run_scrape(src)            # Insert via insert_offer (dédup auto)
3. scrape_target_company_portals( # Itère target_companies.source_url
       use_playwright_fallback=opt-in
   )
4. filter_non_alternance_offers() # Delete/archive CDI/Senior/stage seul
5. apply_heuristic_to_unscored()  # Score auto sur les nouvelles offres
```

État exposé dans `_SCRAPE_STATE` (`backend/main.py`), consulté via HTMX polling.

## Conventions techniques

### httpx (`_http.py`)
- Session unique : `httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True, http2=True)`
- UA réaliste : `Chrome/130.0.0.0`
- **Accept-Encoding: gzip, deflate** (PAS `br` — httpx sans la lib `brotli` reçoit du binaire)
- `get_with_retry()` : décorée `@retry` de **tenacity** (4 tentatives, exponential backoff 2/4/8/16s)
  - Retry sur : `TimeoutException`, `NetworkError`, `RemoteProtocolError`, status `429/500/502/503/504`
  - Log `error` sur `RetryError` (retries épuisés)
- `RateLimiter(min_delay, max_delay)` : pauses **uniformes aléatoires** entre requêtes (anti-fingerprint)
  - `DEFAULT_RATE_LIMITER` : 1.0-2.5s par défaut
  - `rl.acquire()` avant chaque requête HTTP
- `polite_sleep(seconds)` : sleep simple avec jitter ±20% (compat ancienne API)

### Playwright (`_playwright.py`)
- `persistent_browser(headless=True, slow_mo=0)` : context dir `data/.playwright_profile/`
- Args : `--disable-blink-features=AutomationControlled`
- **Lock guard** : `_is_profile_locked()` check `SingletonLock` / `lockfile` / `SingletonSocket`
  - Raise `PlaywrightProfileLocked` si profil déjà ouvert (double-clic Scraper)
  - Param `wait_for_lock_release=10.0` pour attendre la libération
- Utilisé pour : LinkedIn loggué, fallback SPA dans `company_portals` (mode lent)

### Mots-clés (`_keywords.py`)
Toutes les regex compilées en une seule fois via OR. `matches_keywords(*texts)` vérifie ≥ 1 match.

## Filtre alternance auto (`filter_alternance.py`)

Appliqué automatiquement après chaque scrape dans `run_full_scrape`.

Règle :
- **Keep** : `\b(alternan[ct]e?s?|apprenti|apprentissage|contrat\s*pro|professionnali[sz]ation)\b`
- **Reject titre** : `CDI|CDD|Senior|Confirmé|Lead Data/ML/AI|Tech Lead|Manager|Director|Stage seul|freelance|intérim`
- **Reject description** : `\d{2,3}k€|salaire annuel|\d+ ans d'expérience`
- **Reject contract_type** : 'cdi' / 'cdd' (litéral)
- **Doute** → garde (principe : on garde sauf si on est sûr)

Action :
- `status=NULL` + reject → DELETE
- `status≠NULL` + reject → `is_active=0` (préserve l'historique)

## Cleanup URLs mortes (`runner.cleanup_dead_unstatused`)

Détection à 4 niveaux :
1. **HTTP** : 404, 410
2. **Body** : 18 regex (`offre n'est plus disponible`, `résultats de la recherche`...)
3. **Title** : `erreur.*inexistante`, `current openings`, `404`
4. **URL finale** : `?not_found=true`, `/404`, `trk=expired_jd_redirect`, longueur < 50% original
5. **Workday spécifique** : probe API JSON `/wday/cxs/.../job/{jobreq_id}`

Action identique au filtre alternance : DELETE si status NULL, archive sinon.

## Output batch JSON pour scoring manuel

Pour les offres complexes où on veut un scoring LLM précis (pas heuristique) :

```python
from backend import matching
path = matching.export_batch_to_score(only_unscored=True)
# → data/batches/{YYYY-MM-DD}_to_score.json
```

Apply via `python cli.py apply-scores <path>` ou `matching.apply_scores_from_file(path)`.

## Quand ajouter un scraper

### Pour un nouveau **job board** (Indeed, APEC, JobTeaser…)
1. Lire `hellowork.py` (httpx) et `francetravail.py` (OAuth API) comme exemples
2. Créer `backend/scrapers/<source>.py` qui implémente `Scraper`
3. L'enregistrer dans `registry.SCRAPERS`
4. Tester en isolation : `python -m backend.scrapers.<source>` (ajouter `if __name__ == "__main__":`)
5. Mettre à jour `docs/SOURCES.md`

### Pour un nouveau **SaaS RH** (SmartRecruiters, SuccessFactors, iCIMS…)
1. Lire `company_portals.py` (dispatcher)
2. Ajouter `_extract_<saas>_slug(url)` ou `_is_<saas>_url(url)`
3. Ajouter `_fetch_<saas>_jobs(slug, company_name, client)` qui retourne `list[RawOffer]`
4. Insérer dans le dispatcher (ordre : avant le générique et Playwright)

### Pour un nouveau **portail custom** (Capgemini, Airbus…)
1. Vérifier d'abord que **Playwright fallback** suffit (généralement oui)
2. Sinon, ajouter une heuristique spécifique dans `_fetch_generic_career_page`

## Anti-patterns

- ❌ Scrapers monolithiques de 500+ lignes — découper en helpers
- ❌ Hard-coder les URLs de recherche — paramétrer
- ❌ Ignorer les 429/503 — utiliser `get_with_retry()`
- ❌ Polluer `main.py` avec la logique de scrape — passer par `runner`
- ❌ Scraper sans User-Agent (banni immédiatement)
- ❌ Ajouter `br` à Accept-Encoding sans installer la lib `brotli`
- ❌ Faire `requests` synchrones séquentielles sans pause — `polite_sleep(1.5)` entre chaque
