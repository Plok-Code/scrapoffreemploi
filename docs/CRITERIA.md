# Grille de scoring — alignement offre vs Parcours AI Engineer OC

Référence : `reference/Parcours_AI_Engineer_OC.pdf` (37 pages, 14 projets, 804h supervisées).

## Vue d'ensemble

Chaque offre reçoit **5 sous-scores sur 20** (total /100) qui mesurent à quel point le quotidien dans cette boîte va recouper ce qu'on apprend dans le programme OC.

Le filtrage "alternance / France / mots-clés IA" est déjà fait **côté scraper** — donc la grille n'a PAS à pénaliser ces dimensions (toutes les offres en base passent ces critères). Le score se concentre sur **la pertinence des missions** vs le programme.

## Les 5 axes

### Axe 1 — Pipeline / ingestion de données (/20)

**Que le programme couvre :** Airbyte, Kestra, PySpark, ETL/ELT, ingestion data, streaming (Redpandas), PostgreSQL, NoSQL/MongoDB.

**Signaux à chercher dans l'offre :**
- Verbes : ingestion, extraction, transformation, orchestration, pipeline, ETL/ELT
- Outils : Airflow, Kestra, Airbyte, Dagster, Prefect, Talend, Fivetran, Spark/PySpark, Kafka, Redpanda
- Stockage : PostgreSQL, MySQL, MongoDB, Snowflake, BigQuery, Redshift, S3 data lake, Iceberg, Delta Lake
- Concepts : data engineering, data warehouse, data lake, batch processing, stream processing, CDC

**Échelle indicative :**
- **18-20** : Poste data engineer/pipeline central avec stack mainstream (Airflow, Spark, Postgres/Mongo)
- **12-17** : Pipeline mentionné comme une partie significative du poste
- **6-11** : Quelques mentions ponctuelles (consommer/produire une queue, écrire un script ETL one-shot)
- **0-5** : Aucune trace de data engineering dans la fiche

---

### Axe 2 — Exploration / analyse de données (/20)

**Que le programme couvre :** Pandas, NumPy, Matplotlib, Seaborn, statistiques descriptives, visualisation, Jupyter Notebook, exploration de données.

**Signaux à chercher :**
- Verbes : explorer, analyser, viz, dashboard, reporter, exploiter, étudier
- Outils : Pandas, NumPy, Matplotlib, Seaborn, Plotly, Jupyter, Streamlit, Power BI/Tableau (à pondérer plus bas), SQL d'analyse
- Concepts : EDA, feature engineering descriptif, statistiques inférentielles, A/B testing, segmentation

**Échelle indicative :**
- **18-20** : Cœur du poste = analyser des données, produire des insights, viz, dashboards techniques
- **12-17** : Exploration est explicitement une mission régulière (en plus du modeling)
- **6-11** : Analyse occasionnelle ou implicite (forcément un peu d'EDA avant de modéliser)
- **0-5** : Poste purement industrialisation/ops, pas d'analyse

---

### Axe 3 — Modélisation IA (/20)

**Que le programme couvre :** ML supervisé (sk-learn), Deep Learning (PyTorch, TensorFlow), Computer Vision (CNN, GANs), NLP (LSTM, RNN, transformers), RAG (LangChain, Mistral, Faiss), agents IA, fine-tuning LLM, Reinforcement Learning.

**Signaux à chercher :**
- Verbes : entraîner, fine-tuner, optimiser, évaluer, benchmark, modéliser
- Outils : sk-learn, PyTorch, TensorFlow, JAX, Keras, HuggingFace, LangChain, LlamaIndex, Faiss, Pinecone, Weaviate, vLLM
- Concepts : ML supervisé, classification, régression, clustering, DL, CV, NLP, LLM, GenAI, RAG, agents, fine-tuning, RLHF, RL
- LLMs spécifiques : Mistral, Llama, GPT, Claude, Gemini

**Échelle indicative :**
- **18-20** : Le cœur du poste = construire/entraîner/évaluer des modèles IA modernes (DL/LLM/RAG/agents)
- **12-17** : Modélisation comme mission importante (ex: ML supervisé classique en prod)
- **6-11** : Quelques mentions de modèles, mais ce n'est pas central (ex: "utiliser des modèles préentraînés")
- **0-5** : Pas de modélisation (data engineer pur, ops pur, etc.)

---

### Axe 4 — Déploiement / MLOps (/20)

**Que le programme couvre :** Docker, FastAPI, CI/CD, MLflow, BentoML, monitoring, détection de drift, cloud, Git/GitHub, Pytest, déploiement de modèles ML en production.

**Signaux à chercher :**
- Verbes : déployer, industrialiser, mettre en prod, monitorer, observer, monitorer drift
- Outils : Docker, Kubernetes, FastAPI, Flask, BentoML, MLflow, Weights & Biases, Sagemaker, Vertex AI, Azure ML, Kubeflow, Seldon, Argo
- CI/CD : GitHub Actions, GitLab CI, Jenkins, ArgoCD, Terraform
- Cloud : AWS, GCP, Azure, OVHcloud, Scaleway
- Concepts : MLOps, model serving, model monitoring, drift detection, feature store, model registry, A/B test de modèles

**Échelle indicative :**
- **18-20** : Poste MLOps explicite ou ML engineer focalisé prod (Docker + CI/CD + monitoring)
- **12-17** : Déploiement est une mission claire (sans être l'intégralité du poste)
- **6-11** : Mentions ponctuelles (ex: "déployer le modèle sur une API")
- **0-5** : Pas d'industrialisation (poste pure R&D ou analyse)

---

### Axe 5 — Cadrage / qualité / industrialisation (/20)

**Que le programme couvre :** Cadrage projet IA (COMEX, roadmap, KPIs), Pytest, great-expectations, Pydantic (validation), gouvernance des données, qualité, sécurité, éthique IA, alignement métier.

**Signaux à chercher :**
- Verbes : cadrer, scoper, défier, présenter au COMEX, prioriser, mesurer impact, KPI
- Outils : Pytest, unittest, great-expectations, Pydantic, OpenAPI/Swagger, Sphinx, MkDocs
- Concepts : gouvernance, qualité data, sécurité, RGPD, éthique IA, alignement métier, KPI ML, ROI projet IA, AB testing en prod, expérimentation, dataops, MLOps niveau orga

**Échelle indicative :**
- **18-20** : Poste avec interaction métier forte (cadrage, KPIs, présentation aux décideurs) + tests/qualité explicites
- **12-17** : Au moins un des deux fortement présent (soit qualité/tests, soit cadrage métier)
- **6-11** : Mentions implicites (ex: "écrire des tests" sans plus)
- **0-5** : Pas de mention (poste purement technique exécution)

---

## Buckets (label dérivé du total)

Calculé par `label_for_score()` dans `backend/models.py` :

| Score total | Label | Couleur UI | Action |
|---|---|---|---|
| **80-100** | Top | vert (emerald) | Postuler en priorité |
| **60-79** | Bon | jaune (yellow) | Postuler |
| **40-59** | Moyen | orange | À examiner manuellement |
| **0-39** | Faible | gris (slate) | Skip (sauf intérêt particulier) |

---

## Workflow batch (pas d'API key Anthropic)

L'app n'a pas de clé API. Le scoring se fait **dans le chat Claude Code Max** :

```
1. Scraper ajoute N nouvelles offres en DB (status=NULL, match_score=NULL)
                                ↓
2. python cli.py export-batch
   → écrit data/batches/{date}_to_score.json
                                ↓
3. Dans le chat : "score le dernier batch"
   → moi je lis le fichier JSON, j'applique la grille (cf prompt ci-dessous)
   → j'écris data/batches/{date}_scores.json
                                ↓
4. python cli.py apply-scores data/batches/{date}_scores.json
   → backend importe les scores en DB
                                ↓
5. UI à jour avec les nouveaux scores et labels
```

---

## Format I/O (JSON)

### Batch d'entrée — `data/batches/{date}_to_score.json`

```json
{
  "generated_at": "2026-05-12T16:00:00",
  "criteria_version": "1.0",
  "count": 12,
  "offers": [
    {
      "id": 195,
      "title": "Alternance ML Engineer H/F",
      "company": "Mistral AI",
      "city": "Paris",
      "department": "75",
      "source": "WTTJ",
      "url": "https://...",
      "description": "Vous rejoindrez l'équipe production pour déployer des modèles LLM via FastAPI + Docker. Stack : Python, PyTorch, MLflow, Kubernetes. Vous serez en lien direct avec le PM pour cadrer les KPIs métier...",
      "date_published": "2026-05-11"
    }
  ]
}
```

### Scores de sortie — `data/batches/{date}_scores.json`

```json
{
  "scored_at": "2026-05-12T16:30:00",
  "criteria_version": "1.0",
  "scores": [
    {
      "offer_id": 195,
      "score_pipeline": 6,
      "score_exploration": 8,
      "score_modelisation": 20,
      "score_deploiement": 18,
      "score_cadrage": 14,
      "match_reasoning": "Poste ML Engineer LLM, stack PyTorch/MLflow/Docker/K8s, missions = déploiement + monitoring modèles. Interaction métier explicite via PM (KPIs). Peu de pipeline data en amont, peu d'exploration pure. Total : 66/100 → Bon fit."
    }
  ]
}
```

→ Total calculé automatiquement (somme des 5 sous-scores). Le `match_label` aussi (via `label_for_score()`).

---

## Prompt de référence (à mon usage)

Quand le user me dit *"score le dernier batch"*, voici comment je procède :

1. Lire `data/batches/{date}_to_score.json` (le plus récent)
2. Pour chaque offre, lire titre + entreprise + description (et URL si la description est tronquée)
3. Appliquer la grille des 5 axes, en respectant les échelles indicatives
4. Rédiger `match_reasoning` en **1-2 phrases factuelles** qui justifient le score (mentionner les signaux concrets repérés)
5. Écrire le tout dans `data/batches/{date}_scores.json` au format ci-dessus

**Heuristiques que je dois suivre :**

- ✅ Lire la description entière, pas juste le titre. Un titre vague ("Stage IA") peut cacher une mission MLOps full.
- ✅ Si la description est très courte (<500 caractères), accepter un score plus prudent (réduire les scores extrêmes).
- ✅ Si une offre mentionne explicitement plusieurs technos OC (PyTorch, MLflow, Docker, FastAPI...), c'est un signal fort axe 4.
- ✅ Si l'offre mentionne RAG, agents, fine-tuning, LLM → bump axe 3 à 18-20.
- ❌ Ne pas pénaliser pour "alternance" (déjà filtré).
- ❌ Ne pas pénaliser pour la localisation (déjà filtré France).
- ❌ Ne pas mettre 0 sur tous les axes même si l'offre semble hors-sujet — re-lire, identifier au moins un axe pertinent (sauf vrai cas de pollution scraping).

**Anti-pattern :** scorer 100 à toutes les offres "AI Engineer". Discriminer entre Mistral (Top) et un poste data analyst déguisé en "data scientist alternance" (Faible-Moyen).

---

## Version & évolution

- **v1.0** (2026-05-12) : grille initiale, 5 axes /20.
- Si la grille évolue, bumper `criteria_version` dans les batches et noter le changement dans `CHANGELOG.md`.
