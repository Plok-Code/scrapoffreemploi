"""Tests du filtre mots-clés IA/data (`backend.scrapers._keywords`)."""
from __future__ import annotations

import pytest

from backend.scrapers._keywords import matches_keywords


class TestMatchesKeywords:
    """matches_keywords doit accepter les titres IA/data et rejeter les autres."""

    @pytest.mark.parametrize(
        "text",
        [
            "Alternance Machine Learning Engineer",
            "Apprenti Data Scientist H/F",
            "Stagiaire IA Computer Vision",
            "Alternance MLOps & LLM",
            "Data Engineer en alternance",
            "Apprenti AI Engineer chez Doctolib",
            "Ingénieur Intelligence Artificielle",
            "alternance NLP transformer",
            "GenAI Engineer junior",
            "RAG developer apprenti",
        ],
    )
    def test_keep_matches(self, text):
        assert matches_keywords(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Alternance Commercial B2B",
            "Apprenti boulanger Toulouse",
            "Stage Marketing digital",
            "Alternance Comptable",
            "Mécanicien automobile en alternance",
        ],
    )
    def test_reject_non_ia(self, text):
        assert matches_keywords(text) is False

    def test_empty_none(self):
        assert matches_keywords("") is False
        assert matches_keywords(None) is False
        assert matches_keywords(None, "") is False

    def test_multi_args(self):
        """matches_keywords accepte plusieurs textes (title + description)."""
        # Match dans la description seulement
        assert matches_keywords("Alternance commercial", "Mission : machine learning") is True
        # Aucun match
        assert matches_keywords("Alternance commercial", "Mission : vente terrain") is False
