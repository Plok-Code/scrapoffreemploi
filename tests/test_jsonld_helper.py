"""Tests du helper `backend.scrapers._jsonld`.

Verrouille le comportement consolidé (anciennement dupliqué dans 3 scrapers) :
- Formats supportés : dict unique, list, `@graph`.
- Description trop courte (< min_len) ignorée.
- HTML dans la description bien stripé.
- Whitespace normalisé (3+ newlines → 2).
- JSON malformé → silent skip (pas de crash).
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from backend.scrapers._jsonld import (
    extract_jobposting_description,
    normalize_whitespace,
)


# Description longue (> 200 chars) que les helpers acceptent
_LONG_DESC_HTML = (
    "<p>Vous serez en charge du développement de modèles d'IA pour la prédiction "
    "de séries temporelles dans le contexte de l'assurance santé. "
    "Stack : PyTorch, MLflow, FastAPI, Docker, Kubernetes. "
    "Vous travaillerez avec une équipe de 8 data scientists et 3 ML engineers, "
    "en étroite collaboration avec les métiers actuariat.</p>"
)
_LONG_DESC_TEXT = (
    "Vous serez en charge du développement de modèles d'IA pour la prédiction "
    "de séries temporelles dans le contexte de l'assurance santé. "
    "Stack : PyTorch, MLflow, FastAPI, Docker, Kubernetes. "
    "Vous travaillerez avec une équipe de 8 data scientists et 3 ML engineers, "
    "en étroite collaboration avec les métiers actuariat."
)


def _soup(jsonld_str: str) -> BeautifulSoup:
    """Wrap un JSON-LD string dans un HTML minimal."""
    html = f"""
    <!DOCTYPE html>
    <html><head><title>Job</title></head>
    <body>
        <script type="application/ld+json">{jsonld_str}</script>
        <main>Some other content</main>
    </body></html>
    """
    return BeautifulSoup(html, "lxml")


class TestNormalizeWhitespace:
    def test_collapses_triple_newlines(self):
        assert normalize_whitespace("a\n\n\nb") == "a\n\nb"
        assert normalize_whitespace("a\n\n\n\n\nb") == "a\n\nb"

    def test_preserves_double_newlines(self):
        assert normalize_whitespace("a\n\nb") == "a\n\nb"

    def test_preserves_single_newline(self):
        assert normalize_whitespace("a\nb") == "a\nb"

    def test_no_newlines_unchanged(self):
        assert normalize_whitespace("hello world") == "hello world"


class TestExtractJobPostingDict:
    """Format 1 : un dict JSON-LD unique avec @type JobPosting."""

    def test_extracts_description_from_single_dict(self):
        ld = '{"@type": "JobPosting", "title": "ML Engineer", "description": "' \
             + _LONG_DESC_HTML.replace('"', '\\"') + '"}'
        soup = _soup(ld)
        text = extract_jobposting_description(soup)
        assert text == _LONG_DESC_TEXT

    def test_returns_none_when_no_jobposting(self):
        ld = '{"@type": "Organization", "name": "Acme"}'
        soup = _soup(ld)
        assert extract_jobposting_description(soup) is None

    def test_returns_none_when_description_too_short(self):
        ld = '{"@type": "JobPosting", "description": "too short"}'
        soup = _soup(ld)
        assert extract_jobposting_description(soup) is None

    def test_custom_min_len_threshold(self):
        ld = '{"@type": "JobPosting", "description": "Short job desc."}'
        soup = _soup(ld)
        assert extract_jobposting_description(soup, min_len=5) == "Short job desc."


class TestExtractJobPostingList:
    """Format 2 : une liste de JSON-LD objects (parfois 2 scripts, parfois 1 array)."""

    def test_extracts_jobposting_from_list(self):
        ld = (
            '[{"@type": "Organization", "name": "Acme"}, '
            '{"@type": "JobPosting", "description": "'
            + _LONG_DESC_HTML.replace('"', '\\"') + '"}]'
        )
        soup = _soup(ld)
        text = extract_jobposting_description(soup)
        assert text == _LONG_DESC_TEXT

    def test_first_jobposting_in_list_wins(self):
        """Si plusieurs JobPosting (rare), on prend le premier valide."""
        desc1 = "FIRST: " + _LONG_DESC_HTML.replace('"', '\\"')
        desc2 = "SECOND: " + _LONG_DESC_HTML.replace('"', '\\"')
        ld = (
            f'[{{"@type": "JobPosting", "description": "{desc1}"}}, '
            f'{{"@type": "JobPosting", "description": "{desc2}"}}]'
        )
        soup = _soup(ld)
        text = extract_jobposting_description(soup)
        assert text and text.startswith("FIRST:")


class TestExtractJobPostingGraph:
    """Format 3 : `@graph` (utilisé par Workday-like et certains ATS)."""

    def test_extracts_jobposting_from_graph(self):
        ld = (
            '{"@context": "https://schema.org", "@graph": ['
            '{"@type": "Organization", "name": "Acme"}, '
            '{"@type": "JobPosting", "description": "'
            + _LONG_DESC_HTML.replace('"', '\\"') + '"}'
            ']}'
        )
        soup = _soup(ld)
        text = extract_jobposting_description(soup)
        assert text == _LONG_DESC_TEXT


class TestRobustness:
    """Le helper doit jamais crasher, même sur input pourri."""

    def test_malformed_json_skipped(self):
        soup = _soup("{not valid json")
        assert extract_jobposting_description(soup) is None

    def test_empty_script_skipped(self):
        soup = _soup("")
        assert extract_jobposting_description(soup) is None

    def test_jsonld_is_array_of_primitives(self):
        """Edge case : `["foo", 1, null]` → skip les non-dicts sans crash."""
        soup = _soup('["foo", 1, null]')
        assert extract_jobposting_description(soup) is None

    def test_no_script_tag_at_all(self):
        soup = BeautifulSoup("<html><body><p>Hello</p></body></html>", "lxml")
        assert extract_jobposting_description(soup) is None

    def test_jobposting_with_empty_description(self):
        ld = '{"@type": "JobPosting", "description": ""}'
        soup = _soup(ld)
        assert extract_jobposting_description(soup) is None

    def test_strips_html_tags_from_description(self):
        """La description JSON-LD est en HTML — doit être stripée."""
        # 30 répétitions × 17 chars (texte strippé) = ~510 chars, bien au-dessus du min_len
        html_desc = "<p><strong>Bold</strong> and <em>italic</em>. " * 30
        ld = f'{{"@type": "JobPosting", "description": "{html_desc}"}}'
        soup = _soup(ld)
        text = extract_jobposting_description(soup)
        assert text is not None
        assert "<strong>" not in text
        assert "<em>" not in text
        # Le contenu textuel doit être présent
        assert "Bold" in text and "italic" in text
