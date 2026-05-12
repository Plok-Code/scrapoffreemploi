"""Tests du filtre non-alternance (`backend.filter_alternance`)."""
from __future__ import annotations

import pytest

from backend.filter_alternance import classify_offer


class TestClassifyOffer:
    """classify_offer décide keep/reject/doubt pour chaque offre."""

    def test_keep_explicit_alternance(self):
        v, _ = classify_offer("Alternance Data Scientist H/F", "Mission alternance")
        assert v == "keep"

    def test_keep_apprenti(self):
        v, _ = classify_offer("Apprenti ingénieur IA", None)
        assert v == "keep"

    def test_keep_contrat_pro(self):
        v, _ = classify_offer("Data Engineer", "Contrat pro 12 mois")
        assert v == "keep"

    def test_keep_professionnalisation(self):
        v, _ = classify_offer("ML Engineer", "Contrat de professionnalisation")
        assert v == "keep"

    def test_reject_cdi(self):
        v, reason = classify_offer("Senior Data Scientist (H/F) CDI", "Salaire 65k€")
        assert v == "reject"
        assert "CDI" in reason or "salaire" in reason.lower() or "Senior" in reason

    def test_reject_senior_title(self):
        v, _ = classify_offer("Senior Machine Learning Engineer", "AI for production")
        assert v == "reject"

    def test_reject_tech_lead(self):
        v, _ = classify_offer("Tech Lead Data Engineer", "Manage a team")
        assert v == "reject"

    def test_reject_manager(self):
        v, _ = classify_offer("Data Manager (H/F)", "Lead the team")
        assert v == "reject"

    def test_reject_stage_seul(self):
        v, _ = classify_offer("Stage Data Scientist", "6 mois")
        assert v == "reject"

    def test_keep_stage_alternance(self):
        """'Stage/Alternance' = OK car alternance mentionné."""
        v, _ = classify_offer("Stage / Alternance Data Engineer", "")
        assert v == "keep"

    def test_reject_freelance(self):
        v, _ = classify_offer("Mission freelance Data Scientist", "")
        assert v == "reject"

    def test_reject_contract_type_cdi(self):
        v, _ = classify_offer("Ingénieur IA", "Belle mission", contract_type="CDI")
        assert v == "reject"

    def test_doubt_no_indicator(self):
        """Aucun indicateur → doubt → on garde."""
        v, _ = classify_offer("Ingénieur Data", "Belle mission data")
        assert v == "doubt"

    def test_keep_overrides_reject(self):
        """Si 'alternance' mentionné, ça override la pénalité 'CDI' dans desc."""
        v, _ = classify_offer(
            "Alternance Ingénieur IA",
            "Contrat de travail CDI à l'issue de l'alternance possible",
        )
        assert v == "keep"

    def test_reject_5plus_ans_experience(self):
        v, _ = classify_offer(
            "Ingénieur Data",
            "Vous avez 5+ ans d'expérience en data engineering",
        )
        assert v == "reject"
