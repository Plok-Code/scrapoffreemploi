"""Tests de la clé de dédup (`backend.db.make_dedup_key`)."""
from __future__ import annotations

from backend.db import make_dedup_key, normalize_for_dedup


class TestNormalizeForDedup:
    def test_basic_lowercase(self):
        assert normalize_for_dedup("Hello World") == "hello world"

    def test_strip_whitespace(self):
        assert normalize_for_dedup("  Acme  ") == "acme"

    def test_collapse_spaces(self):
        assert normalize_for_dedup("Acme    Corp") == "acme corp"

    def test_remove_special_chars(self):
        """Caractères spéciaux collapsés en espace."""
        result = normalize_for_dedup("Acme & Co. (H/F)")
        assert "acme" in result
        assert "co" in result

    def test_empty_none(self):
        assert normalize_for_dedup("") == ""
        assert normalize_for_dedup(None) == ""


class TestMakeDedupKey:
    def test_basic(self):
        k = make_dedup_key("Data Scientist", "Acme")
        assert k == "data scientist|acme"

    def test_same_offer_diff_casing(self):
        """'Data Scientist' / 'Acme' et 'DATA SCIENTIST' / 'acme' doivent
        produire la même clé (dédup case-insensitive)."""
        k1 = make_dedup_key("Data Scientist", "Acme")
        k2 = make_dedup_key("DATA SCIENTIST", "acme")
        assert k1 == k2

    def test_strip_special(self):
        """'Data Scientist (H/F)' / 'Acme Corp.' produit pareil que sans ponctuation."""
        k1 = make_dedup_key("Data Scientist (H/F)", "Acme Corp.")
        k2 = make_dedup_key("Data Scientist H F", "Acme Corp")
        assert k1 == k2

    def test_none_company(self):
        k = make_dedup_key("Data Scientist", None)
        assert k == "data scientist|"

    def test_pipe_separator(self):
        """Le séparateur '|' est entre title et company."""
        k = make_dedup_key("X", "Y")
        assert "|" in k
        title_part, company_part = k.split("|", 1)
        assert title_part == "x"
        assert company_part == "y"
