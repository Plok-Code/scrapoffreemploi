"""Tests du helper `is_alternance_indicator` + intégration dans les scrapers
portail (`backend.scrapers.company_portals._contract_type_for`).

Audit user (19 mai 2026, 4e passe) : avant ce helper, les scrapers portail
forçaient `contract_type="Alternance"` même sans evidence dans le titre/desc.
Conséquence : `filter_alternance.classify_offer()` voyait
`contract_type="Alternance"` et KEEP via la branche contract_type (étape 2),
ce qui faisait passer des "Data Engineer Senior CDI" entre les mailles.
"""
from __future__ import annotations

import pytest


class TestIsAlternanceIndicator:
    @pytest.mark.parametrize("text", [
        "Alternance Data Engineer H/F",
        "alternance ML engineer",
        "Apprenti ingénieur IA",
        "apprentissage data scientist",
        "Contrat pro ML",
        "Contrat professionnalisation",
        "Apprentie en machine learning",
    ])
    def test_indicator_present(self, text):
        from backend.filter_alternance import is_alternance_indicator
        assert is_alternance_indicator(text) is True

    @pytest.mark.parametrize("text", [
        "Senior Data Engineer (H/F) CDI",
        "Data Scientist - Paris",
        "Tech Lead ML",
        "ML Engineer Stage 6 mois",
        "",
        None,
    ])
    def test_indicator_absent(self, text):
        from backend.filter_alternance import is_alternance_indicator
        assert is_alternance_indicator(text) is False


class TestContractTypeForHelper:
    """Le helper `_contract_type_for` dans company_portals utilise
    `is_alternance_indicator` sur titre puis description."""

    def test_no_evidence_returns_none(self):
        from backend.scrapers.company_portals import _contract_type_for
        assert _contract_type_for("Data Engineer (H/F)") is None
        assert _contract_type_for("Senior ML Engineer", "5 ans d'expérience") is None

    def test_title_has_alternance_returns_alternance(self):
        from backend.scrapers.company_portals import _contract_type_for
        assert _contract_type_for("Alternance Data Engineer") == "Alternance"
        assert _contract_type_for("Apprenti ML Engineer", None) == "Alternance"

    def test_description_has_alternance_returns_alternance(self):
        """Si le titre est ambigu mais la desc dit "alternance" → keep."""
        from backend.scrapers.company_portals import _contract_type_for
        assert _contract_type_for(
            "Data Engineer (H/F)",
            "Mission de 12 mois en alternance, 2 jours école / 3 jours entreprise.",
        ) == "Alternance"

    def test_none_inputs_no_crash(self):
        from backend.scrapers.company_portals import _contract_type_for
        assert _contract_type_for(None) is None
        assert _contract_type_for(None, None) is None


class TestClassifyOfferNoLongerKeepsCdiViaForcedContractType:
    """Régression critique : avant ce fix, un portail forçait
    contract_type="Alternance" et classify_offer KEEPait via cette branche
    même pour un titre "Data Engineer Senior CDI". Vérifie qu'on rejette
    maintenant ce cas."""

    def test_senior_cdi_without_contract_type_is_rejected(self):
        from backend.filter_alternance import classify_offer
        # Pas de contract_type forcé (le scraper portail n'a pas trouvé d'evidence)
        verdict, reason = classify_offer(
            "Data Engineer Senior (H/F)",
            "Equipe data de 15 personnes, expérience minimum 5 ans...",
            contract_type=None,
        )
        assert verdict == "reject"
        assert "Senior" in reason or "ans" in reason or "expérience" in reason

    def test_senior_cdi_with_forced_alternance_would_have_been_kept(self):
        """Démonstration de l'ancien bug : si quelqu'un force
        contract_type='Alternance', classify_offer KEEP via la branche 2.
        C'est le comportement attendu de `classify_offer` (priorité au
        contract_type explicite), mais la BUG était que les portails
        forçaient cette valeur sans evidence. Le fix : les portails ne
        forcent plus."""
        from backend.filter_alternance import classify_offer
        verdict, _ = classify_offer(
            "Data Engineer Senior (H/F)",
            "Equipe data de 15 personnes, expérience minimum 5 ans...",
            contract_type="Alternance",
        )
        # classify_offer reste cohérent avec son contrat : si tu lui dis
        # explicitement "c'est de l'alternance", il fait confiance.
        # Le fix est en amont : que les scrapers ne mentent pas.
        assert verdict == "keep"
