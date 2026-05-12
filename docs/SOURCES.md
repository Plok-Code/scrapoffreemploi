# Sources d'offres à scraper

> Liste des sites à scraper pour trouver des offres d'**alternance AI Engineer en France**.
> Filtres communs à appliquer côté scraper : `contrat = Alternance`, `pays = France`, `mots-clés IA/data` (voir `.claude/rules/scrapers.md`).

## Méthode de scraping par difficulté

| Tier | Approche technique | Caractéristique |
|---|---|---|
| **T1 — Facile** | `httpx` + `BeautifulSoup` (HTML statique) ou API publique | Sites accueillants, peu/pas d'anti-bot |
| **T2 — Moyen** | `httpx` + parsing JSON-LD ou API non publique | Anti-bot léger, User-Agent suffit |
| **T3 — Difficile** | `Playwright` avec cookies persistés | Anti-bot fort (Cloudflare, captcha), JS-rendered |
| **T4 — Manuel** | Pas de scraping, suivi à la main ou via carrières directes | Trop hostile / pas assez de volume |

---

## 1. Jobboards prioritaires (à scraper en premier)

Volume élevé + accès relativement simple + filtres alternance présents :

| Source | URL accueil | URL recherche typée | Tier | Notes |
|---|---|---|---|---|
| **France Travail** | https://www.francetravail.fr | [recherche alternance IA](https://candidat.francetravail.fr/offres/recherche?motsCles=intelligence+artificielle&typeContrat=E2,FS&lieux=99) | **T1** | API officielle dispo (`api.francetravail.io`). Le plus simple. |
| **HelloWork** | https://www.hellowork.com | [alternance + "AI Engineer"](https://www.hellowork.com/fr-fr/emploi/recherche.html?k=AI+Engineer&c=Alternance) | **T1** | JSON-LD dans le HTML. Bon volume alternance. |
| **APEC** | https://www.apec.fr | [recherche cadres](https://www.apec.fr/candidat/recherche-emploi.html/emploi?typesContrat=109883) | **T2** | Public APEC = cadres, peu d'alternance mais qualité. |
| **Indeed France** | https://fr.indeed.com | [Indeed alternance IA](https://fr.indeed.com/jobs?q=alternance+intelligence+artificielle&l=France) | **T2** | Volume énorme, anti-bot moyen. User-Agent indispensable. |
| **Welcome to the Jungle** | https://www.welcometothejungle.com | [WTTJ alternance ML](https://www.welcometothejungle.com/fr/jobs?refinementList%5Bcontract_type%5D%5B%5D=apprenticeship&query=machine%20learning) | **T1** ⭐ | Algolia public — clés embedded dans le frontend JS (voir §11). Pas de Playwright nécessaire. |
| **JobTeaser** | https://www.jobteaser.com | https://www.jobteaser.com/fr/job-offers | **T2** | Très bon pour étudiants/alternance, mais nécessite parfois login école. |
| **LinkedIn Jobs** | https://www.linkedin.com/jobs | [LinkedIn alternance IA France](https://www.linkedin.com/jobs/search/?keywords=alternance%20AI%20engineer&location=France) | **T3** | Cloudflare + détection bot dure. Playwright avec cookies utilisateur. |

---

## 2. Jobboards tech/IA spécialisés (utiles, volume moindre)

| Source | URL | Tier | Notes |
|---|---|---|---|
| **LesJeudis** | https://www.lesjeudis.com | T2 | Spécialisé tech, recherche simple. |
| **Free-Work** | https://www.free-work.com/fr/tech-it/jobs | T2 | Tech FR + freelance. Filtrer "Alternance". |
| **Wellfound** (ex AngelList) | https://wellfound.com | T2 | Startup-only, volume FR limité. |
| **eFinancialCareers** | https://www.efinancialcareers.fr | T2 | Finance + data/MLOps/GenAI. |
| **AI Jobs** | https://ai-jobs.net | T1 | Listing IA international (filtrer Paris/France). |
| **Open Data Science Jobs** | https://jobs.opendatascience.com | T1 | Petit volume mais ciblé. |
| **WeAreDevelopers** | https://www.wearedevelopers.com/en/jobs | T1 | Tech FR + DE. |
| **Cadremploi** | https://www.cadremploi.fr | T2 | Cadres, peu d'alternance. |
| **Meteojob** | https://www.meteojob.com | T2 | Généraliste. |

---

## 3. Plateformes alternance dédiées (à valider — souvent < AI Engineer)

| Source | URL | Tier | Notes |
|---|---|---|---|
| **L'Étudiant — Alternance** | https://www.letudiant.fr/jobsetudes/alternance.html | T2 | Plus généraliste, mais possible. |
| **Studyrama Emploi** | https://www.studyrama-emploi.com | T2 | Alternance majoritaire. |
| **CIDJ** | https://www.cidj.com | T4 | Plus orientation que jobboard. |

→ À investiguer en premier au scraping pour valider le volume IA.

---

## 4. Pages carrières directes — par secteur

### 4.1 Tech FR & startups IA (forte pertinence)

| Entreprise | Carrières | Pertinence |
|---|---|---|
| Mistral AI | https://mistral.ai/careers | ★★★★★ |
| Dataiku | https://www.dataiku.com/careers/ | ★★★★★ |
| Hugging Face | https://huggingface.co/jobs | ★★★★★ |
| Owkin | https://owkin.com/careers | ★★★★ |
| Shift Technology | https://www.shift-technology.com/careers | ★★★★ |
| LightOn | https://lighton.ai/careers | ★★★★ |
| Giskard | https://www.giskard.ai/careers | ★★★★ |
| Nabla | https://www.nabla.com/careers | ★★★★ |
| Dust | https://dust.tt/careers | ★★★★ |
| AQEMIA | https://www.aqemia.com/careers | ★★★★ |
| Alice & Bob | https://www.alice-bob.com/careers | ★★★ (quantum) |
| Quandela | https://www.quandela.com/careers | ★★★ (quantum) |
| Bioptimus | https://www.bioptimus.com/careers | ★★★★ |
| Kayrros | https://www.kayrros.com/careers | ★★★★ |
| Pasqal | https://www.pasqal.com/careers/ | ★★★ |
| Criteo | https://careers.criteo.com | ★★★★ |
| Doctolib | https://careers.doctolib.com | ★★★ |
| Alan | https://alan.com/jobs | ★★★ |
| BlaBlaCar | https://www.blablacar.com/jobs | ★★★ |
| Qonto | https://qonto.com/en/jobs | ★★★ |
| PayFit | https://payfit.com/careers/ | ★★★ |
| Pigment | https://www.pigment.com/careers | ★★★ |
| Mirakl | https://www.mirakl.com/careers | ★★★ |
| Contentsquare | https://contentsquare.com/jobs/ | ★★★ |
| Aircall | https://aircall.io/careers | ★★★ |
| Spendesk | https://www.spendesk.com/careers/ | ★★★ |
| Swile | https://www.swile.co/fr/careers | ★★ |
| Pennylane | https://www.pennylane.com/fr/carrieres/ | ★★ |
| Exotec | https://www.exotec.com/careers/ | ★★★ |
| Ledger | https://www.ledger.com/careers | ★★★ |
| Voodoo | https://www.voodoo.io/careers | ★★★ (gaming AI) |
| Sorare | https://sorare.com/careers | ★★ |
| Back Market | https://www.backmarket.fr/en-us/careers | ★★ |
| Vestiaire Collective | https://www.vestiairecollective.com/careers | ★★ |
| Younited | https://www.younited-credit.com/recrutement | ★★ |
| OVHcloud | https://careers.ovhcloud.com | ★★★ |
| Scaleway | https://www.scaleway.com/en/careers/ | ★★★ |

### 4.2 ESN / Conseil tech

| Entreprise | Carrières | Pertinence |
|---|---|---|
| Capgemini | https://www.capgemini.com/careers/ | ★★★★ (gros volume) |
| Sopra Steria | https://www.soprasteria.fr/nous-rejoindre | ★★★★ |
| Accenture France | https://www.accenture.com/fr-fr/careers | ★★★★ |
| Atos | https://atos.net/fr/carrieres | ★★★★ |
| Eviden | https://eviden.com/careers/ | ★★★ |
| Devoteam | https://www.devoteam.com/careers | ★★★ |
| Alten | https://www.alten.com/talent | ★★★ |
| CGI France | https://www.cgi.com/france/fr-fr/carrieres | ★★★ |
| Inetum | https://www.inetum.com/fr/carrieres | ★★★ |
| Wavestone | https://careers.wavestone.com/jobs | ★★★ |
| Talan | https://careers.talan.com/ | ★★ |
| SII Groupe | https://www.groupe-sii.com/fr/carrieres/nos-offres | ★★ |
| onepoint | https://careers.onepointgroup.com/jobs | ★★ |
| Publicis Sapient | https://www.publicissapient.com/careers | ★★ |
| Deloitte France | https://www2.deloitte.com/fr/fr/pages/careers/articles/nos-offres.html | ★★★ |
| PwC France | https://www.pwc.fr/fr/carriere/offres-emploi.html | ★★★ |
| EY Careers France | https://careers.ey.com/ | ★★★ |
| KPMG France | https://home.kpmg/fr/fr/home/carrieres/nos-offres.html | ★★ |
| BearingPoint | https://www.bearingpoint.com/fr-fr/carrieres/offres/ | ★★ |
| Ekimetrics | https://join.ekimetrics.com | ★★★★ (data pure) |

### 4.3 Industriel / Défense / Aéronautique

| Entreprise | Carrières | Pertinence |
|---|---|---|
| Airbus | https://www.airbus.com/en/careers | ★★★★ |
| Thales | https://careers.thalesgroup.com/global/en | ★★★★★ (AMIAD) |
| Safran | https://www.safran-group.com/careers | ★★★★ |
| Dassault Aviation | https://www.dassault-aviation.com/fr/groupe/carrieres/ | ★★★ |
| Dassault Systèmes | https://www.3ds.com/careers | ★★★★ |
| Naval Group | https://www.naval-group.com/fr/carrieres | ★★★ |
| ArianeGroup | https://www.ariane.group/en/careers/ | ★★ |
| Stellantis | https://www.stellantis.com/fr/carrieres | ★★★ |
| Renault Group | https://www.renaultgroup.com/en/talents/ | ★★★★ |
| Valeo | https://www.valeo.com/en/careers/ | ★★★ |
| Michelin | https://careers.michelin.com | ★★★ |
| Alstom | https://www.alstom.com/careers | ★★ |
| Bouygues | https://carrieres.bouygues.com/ | ★★ |
| VINCI | https://jobs.vinci.com/ | ★★ |
| ONERA | https://www.onera.fr/fr/recrutement | ★★★ |

### 4.4 Banques / Assurances

| Entreprise | Carrières | Pertinence |
|---|---|---|
| BNP Paribas | https://group.bnpparibas/en/careers/jobs | ★★★★ |
| Société Générale | https://careers.societegenerale.com | ★★★★ |
| Crédit Agricole | https://www.credit-agricole.com/en/careers | ★★★★ |
| AXA France | https://www.axa.com/fr/recrutement | ★★★★ |
| BPCE / Natixis | https://groupebpce.com/carriere | ★★★ |
| LCL | https://www.recrute.lcl.fr | ★★★ |
| CNP Assurances | https://www.cnp.fr/cnp/Le-Groupe/Carrieres | ★★ |
| HSBC France | https://www.hsbc.com/careers | ★★ |
| Allianz France | https://careers.allianz.com | ★★★ |
| Generali France | https://www.generali.fr/recrutement | ★★ |
| Crédit Mutuel | https://www.creditmutuel.fr/fr/recrutement.html | ★★ |
| Younited Credit | https://www.younited.com/jobs | ★★★ |
| Pasqal | https://www.pasqal.com/careers/ | ★★★ |

### 4.5 Tech internationale (FR offices)

| Entreprise | Carrières France | Pertinence |
|---|---|---|
| Google | https://careers.google.com (filter France) | ★★★★ |
| Meta | https://www.metacareers.com (filter France) | ★★★ |
| Microsoft | https://careers.microsoft.com (filter France) | ★★★ |
| Amazon | https://www.amazon.jobs/en/locations/france | ★★★ |
| IBM | https://www.ibm.com/employment/ | ★★★ |
| Oracle | https://careers.oracle.com | ★★ |
| Salesforce | https://careers.salesforce.com | ★★ |
| Apple | https://jobs.apple.com/fr-fr/search | ★★ |
| Adobe | https://careers.adobe.com | ★★ |
| Nvidia | https://nvidia.wd5.myworkdayjobs.com | ★★★★ |

### 4.6 Énergie / Industrie / Pharma / Luxe / Retail

| Entreprise | Carrières | Pertinence |
|---|---|---|
| EDF | https://www.edf.fr/edf-recrute | ★★★ |
| ENGIE | https://www.engie.com/en/careers/jobs | ★★★ |
| TotalEnergies | https://jobs.totalenergies.com | ★★★ |
| Air Liquide | https://www.airliquide.com/careers | ★★★ |
| Schneider Electric | https://www.se.com/ww/en/about-us/careers/ | ★★★ |
| Sanofi | https://www.sanofi.com/en/your-career | ★★★ |
| L'Oréal | https://careers.loreal.com | ★★★ |
| Kering | https://www.kering.com/en/talents | ★★ |
| LVMH | https://www.lvmh.com/talents/ | ★★ |
| Carrefour | https://recrute.carrefour.fr | ★★ |
| Decathlon | https://jobs.decathlon.com | ★★ |
| Orange | https://orange.jobs/jobs/v3/search | ★★★ |
| Orange Business | https://orange-business.com/en/careers | ★★★ |

---

## 5. Recherche publique / académique

| Source | URL | Pertinence |
|---|---|---|
| Inria | https://recrutement.inria.fr | ★★★★ |
| CNRS | https://emploi.cnrs.fr | ★★★ |
| CEA | https://www.cea.fr/Pages/cea/emploi.aspx | ★★★ |
| Inserm | https://emploi.inserm.fr | ★★ |
| Institut Pasteur | https://www.pasteur.fr/fr/emploi | ★★ |
| INRAE | https://jobs.inrae.fr/ | ★★ |
| École polytechnique | https://www.polytechnique.edu/recrutement | ★★ |
| Télécom Paris | https://www.telecom-paris.fr/recrutement | ★★ |
| CentraleSupélec | https://www.centralesupelec.fr/recrutement | ★★ |
| Université Paris-Saclay | https://www.universite-paris-saclay.fr/emplois | ★★ |
| ENS Paris-Saclay | https://ens-paris-saclay.fr/recrutement | ★★ |
| Mines Paris - PSL | https://www.minesparis.psl.eu/Recrutement | ★★ |
| Hi! PARIS | https://www.hi-paris.fr/recruitment/ | ★★★ |
| ABG (asso bac+8) | https://www.abg.asso.fr | ★★★ (alternance + thèses CIFRE) |
| EURAXESS France | https://www.euraxess.fr | ★★ |

---

## 6. Hubs / agrégateurs (à valider en T1)

| Source | URL | Notes |
|---|---|---|
| **STATION F job board** | https://stationf.co/jobs | Marketplace startups, alternance fréquente |
| **France Digitale** | https://francedigitale.org/jobs/ | Startups françaises |
| **Eurazeo portfolio jobs** | https://www.eurazeo.com/en/careers | Portfolio VC |
| **Partech portfolio** | https://partechpartners.com/companies | Portfolio VC (carrières via sites portfolio) |
| **Choisir le service public** | https://choisirleservicepublic.gouv.fr | Postes État |
| **Emploi Public** | https://www.emploipublic.fr | Public secteur |

---

## 7. Sources écartées (volontairement non scrapées)

Raisons : pas d'alternance / hors-scope / doublons / freelance.

- **Plateformes freelance** : Malt, Upwork, Comet, LeHibou, FreelanceRepublik, Codeur.com, Crème de la Crème, Collective.work
- **Cabinets cadres senior** : Michael Page, Robert Walters, Hays, Randstad, LHH, Expectra, Harnham (peu d'alternance, mid+)
- **Agrégateurs doublons** : Adzuna, Talent.com, Jooble, Jobijoba, Optioncarriere, Careerjet, Jobrapido (ré-indexent les autres)
- **Généralistes peu IA** : Glassdoor (souvent vide alternance IA), Le Figaro Emploi, Monster (qualité faible)
- **Communautés / Meetups** : MLOps Paris, PyData Paris, Paris ML Group, MLOps Community, DataTalks Slack, Hugging Face Discord, AFIA, Hub France IA (utile pour networking, pas pour scrape automatisé)

---

## 8. Plan de priorité pour le MVP scraping

Ordre proposé d'implémentation des scrapers :

1. **`francetravail.py`** — API officielle, le plus propre (T1)
2. **`hellowork.py`** — JSON-LD, volume + alternance natif (T1)
3. **`wttj.py`** — Algolia public, qualité startup + alternance (T1, cf §11)
4. **`indeed.py`** — gros volume, anti-bot moyen (T2)
5. **`apec.py`** — qualité, peu de volume (T2)
6. **`linkedin.py`** — gros volume mais T3, à mettre en dernier (Playwright)

Sources sectorielles (Tier 3-4) en parallèle :
- Tier 1 sectoriel (3-5 entreprises max) : Mistral AI, Thales, Dataiku, Capgemini, BNP — scrapers dédiés simples
- Tier 2 sectoriel : à ajouter au fil de l'eau si demande utilisateur

---

## 9. Mots-clés de filtrage (cf `.claude/rules/scrapers.md`)

Filtre titre OU description (insensible à la casse), au moins UN match parmi :

```
IA | AI | artificial intelligence | intelligence artificielle
data | donnée | données
ML | machine learning | apprentissage automatique
deep learning | apprentissage profond
MLOps | LLM | NLP | computer vision | RAG
AI engineer | ML engineer | data scientist | data engineer
genAI | generative AI | agent IA | agentic
```

Filtres systématiques source-side (paramètres URL) :
- `type_contrat = alternance` (ou équivalent : "apprentissage", "professionnalisation")
- `pays = France`

---

## 10. Notes anti-bot

- **User-Agent obligatoire** : un Chrome récent Windows
- **Rate limit** : 1 requête / 2-3s pour httpx, exponentiel sur 429/503 (`tenacity`)
- **LinkedIn et WTTJ** : Cloudflare. Playwright avec session persistée.
- **APEC** : tokens CSRF, peut nécessiter session
- **France Travail** : utiliser l'**API officielle** (https://api.francetravail.io) avec OAuth client credentials — gratuit, pas d'anti-bot

---

## 11. Credentials publiques connues (frontend-exposed)

### Welcome to the Jungle — Algolia search

Les clés Algolia sont **embedded dans le frontend JS** de WTTJ (donc légitimement publiques, non-secret). Source : https://github.com/juan-azabal/jobagent/blob/master/wttj_scraper.py (vérifié 2026-05-12).

```python
ALGOLIA_APP_ID  = "CSEKHVMS53"
ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
ALGOLIA_INDEX   = "wttj_jobs_production_en"  # ou "wttj_jobs_production_fr"
SEARCH_URL      = "https://csekhvms53-dsn.algolia.net/1/indexes/wttj_jobs_production_en/query"
```

**Headers obligatoires** :
```python
{
    "x-algolia-application-id": ALGOLIA_APP_ID,
    "x-algolia-api-key": ALGOLIA_API_KEY,
    "Content-Type": "application/json",
    "Referer": "https://www.welcometothejungle.com/",   # restriction par domaine
    "Origin":  "https://www.welcometothejungle.com",
}
```

**Filtres utiles** :
- `contract_type:apprenticeship` (alternance)
- `office.country_code:FR`
- Recherche full-text sur `title` + `description` via le param `query`

⚠️ Ces clés peuvent **tourner** (rotation Algolia). Si on a un 401/403, re-fetcher la page WTTJ et extraire les clés du JS bundlé.

### France Travail — API officielle (recommandée)

L'API officielle nécessite un **OAuth client_credentials** (gratuit après inscription sur https://api.francetravail.io). À demander une clé puis stocker dans `.env` (gitignored). Pas de credentials publics ici — c'est de l'auth perso.

---

## Références

- Ancien export du projet (mai 2026) avec scraps par source : `legacy/sources_2026_05_11/*.json` (15 sources)
- Doc bibliothèques scraping : voir `.claude/agents/explore-doc.md` pour la liste des libs Python du projet
- Source pour le scraper WTTJ : https://github.com/juan-azabal/jobagent/blob/master/wttj_scraper.py
