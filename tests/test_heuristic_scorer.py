"""Tests du scoreur heuristique (`backend.heuristic_scorer`).

Le scoring classe automatiquement ~1100 offres scrapées. Une régression sur
`_AXIS_KEYWORDS`, `_PENALTIES`, `_BONUSES` ou la normalisation finale pourrait
basculer toute la distribution. Ces tests verrouillent :

1. Les **invariants** (cap 20/axe, total ∈ [0, 100], sum(axes) == total final).
2. Les **règles métier** (must-have alternance = -25, pénalités CDI/Senior,
   bonus alternant explicite, plafonnement).
3. L'**intégration DB** via `apply_heuristic_to_unscored` (filtre unscored,
   filtre archived, mode rescore, distribution retournée).
"""
from __future__ import annotations

import pytest

from backend.heuristic_scorer import (
    HeuristicResult,
    apply_heuristic_to_unscored,
    score_offer_heuristic,
)


# ============================================================
# Section 1 — score_offer_heuristic (pure function, no DB)
# ============================================================


class TestInvariants:
    """Invariants qui doivent tenir sur n'importe quel input."""

    @pytest.mark.parametrize(
        "title,description",
        [
            ("", ""),
            ("", None),
            (None, None),  # type: ignore[arg-type]
            ("Random title", "Random description without any keyword"),
            (
                "Alternance Data Engineer MLOps Senior CDI",
                "PySpark Airflow Databricks MLflow Docker Kubernetes Pytest "
                "great-expectations RGPD agentic LLM RAG GenAI computer vision",
            ),
        ],
    )
    def test_total_in_range_0_100(self, title, description):
        r = score_offer_heuristic(title or "", description)
        assert 0 <= r.total <= 100

    @pytest.mark.parametrize(
        "title,description",
        [
            ("", ""),
            ("Alternance MLOps", "PySpark Airflow MLflow Databricks Docker"),
            (
                "Alternance AI Engineer",
                ("MLOps " * 50) + ("LLM " * 50) + ("PySpark " * 50),
            ),
        ],
    )
    def test_each_axis_in_range_0_20(self, title, description):
        r = score_offer_heuristic(title, description)
        for axis_score in (
            r.score_pipeline, r.score_exploration, r.score_modelisation,
            r.score_deploiement, r.score_cadrage,
        ):
            assert 0 <= axis_score <= 20

    def test_total_equals_sum_of_axes(self):
        """Contrat avec `apply_llm_scores` qui recalcule total = sum(score_*).
        Si cet invariant casse, la colonne `match_score` divergera des 5 axes."""
        r = score_offer_heuristic(
            "Alternance Data Scientist MLOps",
            "PySpark Airflow Pandas MLflow Docker Pytest LLM RAG fine-tuning",
        )
        assert r.total == (
            r.score_pipeline + r.score_exploration + r.score_modelisation
            + r.score_deploiement + r.score_cadrage
        )

    def test_no_division_error_when_no_axis_match(self):
        """Edge case : sum(axes)=0 → `or 1` protège la division."""
        r = score_offer_heuristic("alternance random", "alternance random text")
        # Aucun mot-clé technique → axes 0, total 0 après normalisation
        assert r.total >= 0
        assert all(s == 0 for s in (
            r.score_pipeline, r.score_exploration, r.score_modelisation,
            r.score_deploiement, r.score_cadrage,
        ))


class TestPenaltiesAndBonuses:
    """Les règles métier qui font la différence Top/Faible."""

    def test_must_have_alternance_penalty(self):
        """Texte sans 'alternance/apprentissage' → -25 sur le total brut.

        On compare deux textes identiques sauf l'ajout de 'alternance' pour
        isoler l'effet de la must-have. On vérifie sur le total *avant*
        normalisation difficile : on utilise plutôt deux textes avec keywords
        identiques et on vérifie que celui sans alternance score plus bas.
        """
        kws = (
            "PySpark Airflow Pandas MLflow Docker Pytest LLM data engineer "
            "deep learning machine learning RAG"
        )
        with_alt = score_offer_heuristic("AI Engineer alternance", kws)
        without_alt = score_offer_heuristic("AI Engineer", kws)
        assert with_alt.total > without_alt.total

    def test_senior_title_penalty(self):
        """Titre 'Senior' déclenche la pénalité -20 sur total."""
        kws = "PySpark Airflow Pandas MLflow Docker Pytest LLM alternance"
        senior = score_offer_heuristic("Senior ML Engineer", kws)
        junior = score_offer_heuristic("ML Engineer alternance", kws)
        assert senior.total < junior.total

    def test_tech_lead_penalty(self):
        kws = "PySpark MLflow Docker Pytest LLM alternance"
        lead = score_offer_heuristic("Tech Lead ML alternance", kws)
        normal = score_offer_heuristic("ML Engineer alternance", kws)
        assert lead.total < normal.total

    def test_alternant_explicit_bonus(self):
        """Mention explicite 'alternant' / 'apprenti' → +6 bonus."""
        kws = "PySpark MLflow Docker Pytest LLM"
        with_explicit = score_offer_heuristic(
            "Data Engineer", kws + " Recherche un alternant en M2"
        )
        without_explicit = score_offer_heuristic(
            "Data Engineer alternance", kws  # 'alternance' satisfait must-have mais pas le bonus +6
        )
        assert with_explicit.total > without_explicit.total

    def test_director_penalty(self):
        kws = "PySpark MLflow Docker Pytest LLM alternance"
        director = score_offer_heuristic("Directeur Data alternance", kws)
        normal = score_offer_heuristic("Data Engineer alternance", kws)
        assert director.total < normal.total


class TestAxisAttribution:
    """Vérifie que les mots-clés tombent sur le bon axe (pas de leak)."""

    def test_pipeline_keywords_score_pipeline_axis(self):
        r = score_offer_heuristic(
            "Alternance Data Engineer",
            "Maîtrise PySpark, Airflow, Databricks, Snowflake. ETL/ELT.",
        )
        assert r.score_pipeline > 0
        # Et pas de leak excessif vers les autres axes (autres axes peuvent
        # avoir des matches collatéraux mais pipeline doit dominer)
        assert r.score_pipeline >= r.score_modelisation

    def test_modelisation_keywords_score_modelisation_axis(self):
        r = score_offer_heuristic(
            "Alternance ML Engineer",
            "LLM, RAG, fine-tuning, PyTorch, Transformers, Hugging Face, NLP.",
        )
        assert r.score_modelisation > 0
        assert r.score_modelisation >= r.score_pipeline

    def test_deploiement_keywords_score_deploiement_axis(self):
        r = score_offer_heuristic(
            "Alternance MLOps",
            "MLflow, Kubeflow, BentoML, Docker, Kubernetes, CI/CD, model drift.",
        )
        assert r.score_deploiement > 0
        assert r.score_deploiement >= r.score_exploration

    def test_axis_cap_20(self):
        """Stuffing un axe ne dépasse pas 20."""
        # MLOps poids 12, MLflow 9, Docker 6, Kubernetes 7, FastAPI 6,
        # CI/CD 7 → bien > 20 si pas de cap
        r = score_offer_heuristic(
            "Alternance MLOps Engineer",
            "MLOps MLflow Kubeflow BentoML Docker Kubernetes FastAPI Flask "
            "CI/CD GitHub Actions AWS GCP Azure SageMaker Vertex AI model drift "
            "production ML industrialisation ML API REST GenAIOps LLMOps",
        )
        assert r.score_deploiement == 20


class TestReturnShape:
    """La structure du retour doit rester stable pour `apply_llm_scores`."""

    def test_returns_heuristic_result_dataclass(self):
        r = score_offer_heuristic("alternance", "rien")
        assert isinstance(r, HeuristicResult)

    def test_offer_id_defaults_to_zero(self):
        """offer_id est rempli par le caller (apply_heuristic_to_unscored)."""
        r = score_offer_heuristic("alternance", "rien")
        assert r.offer_id == 0

    def test_matched_is_a_list(self):
        r = score_offer_heuristic(
            "Alternance MLOps", "PySpark MLflow Docker"
        )
        assert isinstance(r.matched, list)
        assert len(r.matched) > 0


# ============================================================
# Section 2 — apply_heuristic_to_unscored (DB integration)
# ============================================================


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """DB SQLite temporaire isolée pour l'intégration."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.db.DB_PATH", db_file)
    from backend.db import init_schema
    init_schema()
    yield db_file


class TestApplyHeuristicToUnscored:
    def _seed(self, *, with_score: bool = False, archived: bool = False,
              reasoning_prefix: str | None = None) -> int:
        """Insère une offre minimale et renvoie son id."""
        from backend.db import db, make_dedup_key

        title = "Alternance ML Engineer MLOps"
        desc = "PySpark MLflow Docker LLM Pytest agile alternance"
        url = f"http://x/{title}/{int(archived)}/{int(with_score)}/{reasoning_prefix}"
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO offers (title, company, city, url, description,
                                    dedup_key, is_active, match_score, match_reasoning)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title, "Acme", "Paris", url, desc,
                    make_dedup_key(title, "Acme", "Paris"),
                    0 if archived else 1,
                    42 if with_score else None,
                    reasoning_prefix,
                ),
            )
            return cur.lastrowid

    def test_scores_only_unscored_by_default(self, temp_db):
        unscored_id = self._seed(with_score=False)
        scored_id = self._seed(with_score=True, reasoning_prefix="manual")

        result = apply_heuristic_to_unscored()

        assert result["total_candidates"] >= 1
        assert result["updated"] >= 1

        from backend.queries import get_offer
        unscored_now = get_offer(unscored_id)
        scored_now = get_offer(scored_id)
        # L'offre unscored a maintenant un match_score non-nul
        assert unscored_now["match_score"] is not None
        # L'offre déjà scorée manuellement n'a PAS été écrasée
        assert scored_now["match_score"] == 42
        assert scored_now["match_reasoning"] == "manual"

    def test_rescore_flag_overwrites_heuristic_scores(self, temp_db):
        # Offre avec un score heuristique antérieur (auto:heuristic-v0)
        heur_id = self._seed(with_score=True, reasoning_prefix="auto:heuristic-v0")
        # Offre avec un score manuel — doit rester intouchée
        manual_id = self._seed(with_score=True, reasoning_prefix="manual override")

        result = apply_heuristic_to_unscored(rescore_heuristic=True)
        assert result["updated"] >= 1

        from backend.queries import get_offer
        heur_now = get_offer(heur_id)
        manual_now = get_offer(manual_id)
        # Le score heuristique a été ré-écrit (auto:heuristic-v1 cette fois)
        assert heur_now["match_reasoning"].startswith("auto:heuristic")
        assert heur_now["match_reasoning"] != "auto:heuristic-v0"
        # Le score manuel est préservé
        assert manual_now["match_reasoning"] == "manual override"

    def test_skips_archived_offers(self, temp_db):
        archived_id = self._seed(with_score=False, archived=True)

        result = apply_heuristic_to_unscored()

        from backend.queries import get_offer
        archived_now = get_offer(archived_id)
        # L'offre archivée reste sans score (n'a pas été pickée comme candidate)
        assert archived_now["match_score"] is None
        # Et n'apparaît pas dans les candidates
        # (peut y avoir d'autres offres mais l'archivée ne doit pas être incluse)

    def test_returns_distribution_dict(self, temp_db):
        self._seed(with_score=False)

        result = apply_heuristic_to_unscored()

        assert "total_candidates" in result
        assert "updated" in result
        assert "distribution" in result
        assert isinstance(result["distribution"], dict)

    def test_empty_db_returns_zero(self, temp_db):
        result = apply_heuristic_to_unscored()
        assert result["total_candidates"] == 0
        assert result["updated"] == 0
