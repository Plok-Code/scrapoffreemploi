"""Tests de la clé de dédup (`backend.db.make_dedup_key`)."""
from __future__ import annotations

from backend.db import make_dedup_key, normalize_city_for_dedup, normalize_for_dedup


class TestNormalizeForDedup:
    def test_basic_lowercase(self):
        assert normalize_for_dedup("Hello World") == "hello world"

    def test_strip_whitespace(self):
        assert normalize_for_dedup("  Acme  ") == "acme"

    def test_collapse_spaces(self):
        assert normalize_for_dedup("Acme    Corp") == "acme corp"

    def test_remove_special_chars(self):
        result = normalize_for_dedup("Acme & Co. (H/F)")
        assert "acme" in result
        assert "co" in result

    def test_empty_none(self):
        assert normalize_for_dedup("") == ""
        assert normalize_for_dedup(None) == ""


class TestNormalizeCityForDedup:
    """La ville doit matcher ses variantes communes."""

    def test_basic_lowercase(self):
        assert normalize_city_for_dedup("Paris") == "paris"

    def test_dept_code_stripped(self):
        """'75 - Paris' → 'paris'."""
        assert normalize_city_for_dedup("75 - Paris") == "paris"
        assert normalize_city_for_dedup("31 - Toulouse") == "toulouse"

    def test_paren_stripped(self):
        """'Pau (Bordes)' → 'pau'."""
        assert normalize_city_for_dedup("Pau (Bordes)") == "pau"
        assert normalize_city_for_dedup("Paris (Saint-Cloud)") == "paris"

    def test_france_suffix_stripped(self):
        """'Toulouse, France' → 'toulouse'."""
        assert normalize_city_for_dedup("Toulouse, France") == "toulouse"

    def test_all_variants_match(self):
        """Toutes les variantes Paris doivent collapse en 'paris'."""
        variants = ["Paris", "75 - Paris", "PARIS", "  Paris  ", "Paris, France",
                    "75 paris", "Paris (Saint-Cloud)", "Paris  (Center)"]
        normalized = [normalize_city_for_dedup(v) for v in variants]
        # Tous doivent commencer par "paris" (avec ou sans suffixe)
        for n in normalized:
            assert n.startswith("paris"), f"Variant failed: {n}"

    def test_empty_none(self):
        assert normalize_city_for_dedup("") == ""
        assert normalize_city_for_dedup(None) == ""


class TestMakeDedupKey:
    def test_basic_3_parts(self):
        k = make_dedup_key("Data Scientist", "Acme", "Paris")
        assert k == "data scientist|acme|paris"

    def test_no_city_backwards_compat(self):
        """Sans city : 3e partie vide."""
        k = make_dedup_key("Data Scientist", "Acme")
        assert k == "data scientist|acme|"

    def test_same_offer_diff_casing(self):
        k1 = make_dedup_key("Data Scientist", "Acme", "Paris")
        k2 = make_dedup_key("DATA SCIENTIST", "acme", "PARIS")
        assert k1 == k2

    def test_strip_special(self):
        k1 = make_dedup_key("Data Scientist (H/F)", "Acme Corp.", "75 - Paris")
        k2 = make_dedup_key("Data Scientist H F", "Acme Corp", "Paris")
        assert k1 == k2

    def test_critical_bug_paris_vs_toulouse(self):
        """BUG MÉTIER : la même offre Capgemini à Paris vs Toulouse
        doit produire des clés DIFFÉRENTES (= 2 offres distinctes)."""
        k_paris = make_dedup_key("AI Engineer", "Capgemini", "Paris")
        k_toulouse = make_dedup_key("AI Engineer", "Capgemini", "Toulouse")
        assert k_paris != k_toulouse, (
            "BUG CRITIQUE : Capgemini Paris et Capgemini Toulouse ont la même dedup_key. "
            "Une des 2 offres serait jetée silencieusement comme doublon !"
        )

    def test_paris_variants_match(self):
        """Mêmes variantes Paris doivent matcher (vraie dédup)."""
        k1 = make_dedup_key("AI Engineer", "Capgemini", "Paris")
        k2 = make_dedup_key("AI Engineer", "Capgemini", "75 - Paris")
        k3 = make_dedup_key("AI Engineer", "Capgemini", "Paris, France")
        assert k1 == k2 == k3

    def test_none_company(self):
        k = make_dedup_key("Data Scientist", None, "Paris")
        assert k == "data scientist||paris"

    def test_pipe_separators(self):
        k = make_dedup_key("X", "Y", "Z")
        assert k == "x|y|z"
        assert k.count("|") == 2
