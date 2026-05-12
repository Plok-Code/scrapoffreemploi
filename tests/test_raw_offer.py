"""Tests de validation Pydantic `RawOffer`."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.scrapers.base import RawOffer


class TestRawOfferValidation:
    def test_basic_construction(self):
        o = RawOffer(title="Data Scientist", company="Acme")
        assert o.title == "Data Scientist"
        assert o.company == "Acme"
        assert o.url is None  # defaults to None

    def test_title_required(self):
        with pytest.raises(ValidationError):
            RawOffer(title="")

    def test_title_whitespace_only_rejected(self):
        with pytest.raises(ValidationError):
            RawOffer(title="   ")

    def test_title_stripped(self):
        o = RawOffer(title="  Hello  ")
        assert o.title == "Hello"

    def test_url_none_passes(self):
        o = RawOffer(title="X", url=None)
        assert o.url is None

    def test_url_empty_string_normalized_to_none(self):
        o = RawOffer(title="X", url="")
        assert o.url is None

    def test_date_iso_truncated_to_yyyy_mm_dd(self):
        """Date avec heure → tronquée à YYYY-MM-DD."""
        o = RawOffer(title="X", date_published="2026-05-12T10:30:00.000Z")
        assert o.date_published == "2026-05-12"

    def test_extra_fields_ignored(self):
        """Si un scraper renvoie un champ extra, Pydantic ignore (pas d'erreur)."""
        o = RawOffer(title="X", random_extra_field="foo")
        assert o.title == "X"
        assert not hasattr(o, "random_extra_field")

    def test_raw_dict_preserved(self):
        """`raw` blob accepte n'importe quel dict pour audit."""
        o = RawOffer(title="X", raw={"id": "ABC123", "weird_field": [1, 2, 3]})
        assert o.raw == {"id": "ABC123", "weird_field": [1, 2, 3]}

    def test_all_optional_none(self):
        """Tout sauf title doit être nullable."""
        o = RawOffer(title="X")
        for field in ["company", "city", "department", "url", "description",
                      "date_published", "contract_type", "salary", "remote", "raw"]:
            assert getattr(o, field) is None
