"""Tests de parsing offline des scrapers (HelloWork HTML, WTTJ Algolia, FT API).

Le parsing est la partie la plus fragile du scraping — un changement de
structure côté source casse silencieusement notre extraction. Ces tests
fixent le comportement attendu sur des **fixtures représentatives**
(structure réelle vue dans la nature), sans aucun appel réseau.

3 fichiers source couverts :
- `backend.scrapers.hellowork._parse_card` (DOM card + aria-label regex)
- `backend.scrapers.wttj._hit_to_raw` (mapping Algolia hit → RawOffer)
- `backend.scrapers.francetravail._parse_offer` (mapping FT API JSON → RawOffer)
"""
from __future__ import annotations

from bs4 import BeautifulSoup


# ============================================================
# HelloWork — _parse_card et _parse_aria_label
# ============================================================


_HW_CARD_TYPICAL = """
<div data-cy="serpCard">
    <a data-cy="offerTitle"
       href="/fr-fr/emplois/12345678.html"
       aria-label="Voir offre de Alternance Data Scientist H/F à Paris - 75, chez Acme Corp, pour un Alternance, avec un salaire de 1500€, en temps plein"
       title="Alternance Data Scientist H/F - Acme Corp">
        <p class="tw-typo-l">Alternance Data Scientist H/F</p>
        <p class="tw-typo-s">Acme Corp</p>
    </a>
</div>
"""

_HW_CARD_NO_DEPT = """
<div data-cy="serpCard">
    <a data-cy="offerTitle"
       href="/fr-fr/emplois/999.html"
       aria-label="Voir offre de Ingénieur MLOps à Lyon, chez Beta, pour un Alternance"
       title="Ingénieur MLOps - Beta">
        <p class="tw-typo-l">Ingénieur MLOps</p>
        <p class="tw-typo-s">Beta</p>
    </a>
</div>
"""

_HW_CARD_MINIMAL = """
<div data-cy="serpCard">
    <a data-cy="offerTitle" href="/fr-fr/emplois/777.html"
       aria-label="Voir offre de Data Engineer">
        <p class="tw-typo-l">Data Engineer</p>
    </a>
</div>
"""

_HW_CARD_BROKEN_NO_LINK = """
<div data-cy="serpCard">
    <p>No link inside, should return None silently</p>
</div>
"""


class TestHelloWorkParseCard:
    def _parse(self, html: str):
        from backend.scrapers.hellowork import HelloWorkScraper
        scraper = HelloWorkScraper()
        card = BeautifulSoup(html, "lxml").select_one("[data-cy=serpCard]")
        return scraper._parse_card(card)

    def test_typical_card_with_all_fields(self):
        off = self._parse(_HW_CARD_TYPICAL)
        assert off is not None
        assert off.title == "Alternance Data Scientist H/F"
        assert off.company == "Acme Corp"
        assert off.city == "Paris"
        assert off.department == "75"
        # contract et salary sont extraits de l'aria-label
        assert off.contract_type and "Alternance" in off.contract_type
        assert off.salary and "1500" in off.salary
        assert off.url and off.url.startswith("https://www.hellowork.com/")

    def test_city_without_department(self):
        off = self._parse(_HW_CARD_NO_DEPT)
        assert off is not None
        assert off.title == "Ingénieur MLOps"
        assert off.city == "Lyon"
        assert off.department is None

    def test_minimal_card_returns_offer_with_title_only(self):
        off = self._parse(_HW_CARD_MINIMAL)
        assert off is not None
        assert off.title == "Data Engineer"
        assert off.city is None
        assert off.department is None

    def test_card_without_link_returns_none(self):
        """Pas de `<a data-cy=offerTitle>` → on retourne None silencieusement."""
        off = self._parse(_HW_CARD_BROKEN_NO_LINK)
        assert off is None


class TestHelloWorkParseAriaLabel:
    """L'audit a flaggé cette regex comme fragile. On verrouille."""

    def _parse(self, aria: str):
        from backend.scrapers.hellowork import HelloWorkScraper
        return HelloWorkScraper._parse_aria_label(aria)

    def test_full_aria(self):
        city, dept, contract, salary = self._parse(
            "Voir offre de X à Paris - 75, chez Acme, pour un Alternance, avec un salaire de 1500€, en temps plein"
        )
        assert city == "Paris"
        assert dept == "75"
        assert contract == "Alternance"
        assert salary == "1500€"

    def test_no_salary(self):
        city, dept, contract, salary = self._parse(
            "Voir offre de X à Lyon - 69, chez Beta, pour un Apprentissage"
        )
        assert city == "Lyon" and dept == "69"
        assert contract == "Apprentissage"
        assert salary is None

    def test_only_city(self):
        city, dept, contract, salary = self._parse(
            "Voir offre de X à Toulouse"
        )
        assert city == "Toulouse"
        assert dept is None and contract is None and salary is None


# ============================================================
# WTTJ — _hit_to_raw
# ============================================================


class TestWTTJHitToRaw:
    def test_typical_hit(self):
        from backend.scrapers.wttj import _hit_to_raw
        hit = {
            "objectID": "abc-123",
            "name": "Alternance ML Engineer",
            "slug": "alt-ml-engineer-abc",
            "organization": {"name": "Acme", "slug": "acme"},
            "offices": [{"city": "Paris", "country_code": "FR"}],
            "summary": "Mission de 12 mois en alternance.",
            "profile": "Bac+5 école d'ingénieur, passionné par le ML.",
            "key_missions": ["Construire pipelines ML", "Déployer modèles"],
            "published_at": "2026-05-12",
        }
        off = _hit_to_raw(hit)
        assert off is not None
        assert off.title == "Alternance ML Engineer"
        assert off.company == "Acme"
        assert off.city == "Paris"
        assert off.source == "WelcomeToTheJungle"
        assert off.url == "https://www.welcometothejungle.com/fr/companies/acme/jobs/alt-ml-engineer-abc"
        # Description concaténée (summary + profile + key_missions)
        assert off.description is not None
        assert "Mission de 12 mois" in off.description
        assert "Bac+5" in off.description
        assert "Construire pipelines" in off.description

    def test_no_title_returns_none(self):
        """Garde-fou : un hit sans `name` ni `title` est rejeté."""
        from backend.scrapers.wttj import _hit_to_raw
        assert _hit_to_raw({"objectID": "x", "organization": {"name": "Y"}}) is None

    def test_offices_plural_field_used(self):
        """Bug historique : initialement le code lisait `office` (singulier),
        WTTJ utilise `offices` (pluriel). Verrouille la régression."""
        from backend.scrapers.wttj import _hit_to_raw
        hit = {
            "name": "X", "slug": "x",
            "organization": {"name": "A", "slug": "a"},
            "offices": [{"city": "Bordeaux"}],
        }
        off = _hit_to_raw(hit)
        assert off and off.city == "Bordeaux"

    def test_html_in_description_is_stripped(self):
        from backend.scrapers.wttj import _hit_to_raw
        long_html = "<p>" + ("Vraie mission technique en alternance. " * 10) + "</p>"
        hit = {
            "name": "X", "slug": "x",
            "organization": {"name": "A", "slug": "a"},
            "offices": [{"city": "Paris"}],
            "summary": long_html,
        }
        off = _hit_to_raw(hit)
        assert off is not None
        assert off.description is not None
        assert "<p>" not in off.description
        assert "Vraie mission technique" in off.description

    def test_description_too_short_becomes_none(self):
        """< 100 chars → description=None (le caller fait fetch_detail)."""
        from backend.scrapers.wttj import _hit_to_raw
        hit = {
            "name": "X", "slug": "x",
            "organization": {"name": "A", "slug": "a"},
            "offices": [{"city": "Paris"}],
            "summary": "trop court",
        }
        off = _hit_to_raw(hit)
        assert off is not None
        assert off.description is None

    def test_url_none_if_slugs_missing(self):
        """Sans org slug ou job slug, l'URL ne peut pas être construite → None."""
        from backend.scrapers.wttj import _hit_to_raw
        hit = {
            "name": "X",
            "organization": {"name": "A"},  # pas de slug
            "offices": [{"city": "Paris"}],
        }
        off = _hit_to_raw(hit)
        assert off is not None
        assert off.url is None


# ============================================================
# France Travail — _parse_offer
# ============================================================


_FT_TYPICAL = {
    "id": "9876543",
    "intitule": "Alternance Data Engineer (H/F)",
    "lieuTravail": {"libelle": "75 - PARIS 02", "codePostal": "75002"},
    "entreprise": {"nom": "Acme SA"},
    "salaire": {"libelle": "Mensuel de 1500€ à 1700€"},
    "dateCreation": "2026-05-12T10:30:00.000Z",
    "natureContrat": "E1",
    "description": "Mission alternance 12 mois sur projet IA / data engineering.",
    "origineOffre": {"urlOrigine": "https://candidat.francetravail.fr/offres/recherche/detail/9876543"},
}


class TestFranceTravailParseOffer:
    def test_typical_e1_apprentissage(self):
        from backend.scrapers.francetravail import _parse_offer
        off = _parse_offer(_FT_TYPICAL)
        assert off.title == "Alternance Data Engineer (H/F)"
        assert off.company == "Acme SA"
        assert off.city == "75 - PARIS 02"
        assert off.department == "75"
        assert off.source == "France Travail"
        assert off.date_published == "2026-05-12"
        # Mapping nature E1 → libellé apprentissage
        assert off.contract_type == "Alternance (apprentissage)"
        assert off.url == "https://candidat.francetravail.fr/offres/recherche/detail/9876543"
        # raw conservé pour debug
        assert off.raw == {"id": "9876543", "natureContrat": "E1"}

    def test_e2_professionnalisation(self):
        from backend.scrapers.francetravail import _parse_offer
        item = {**_FT_TYPICAL, "natureContrat": "E2"}
        off = _parse_offer(item)
        assert off.contract_type == "Alternance (professionnalisation)"

    def test_unknown_nature_falls_back_to_alternance(self):
        from backend.scrapers.francetravail import _parse_offer
        item = {**_FT_TYPICAL, "natureContrat": "XX", "typeContratLibelle": None}
        off = _parse_offer(item)
        assert off.contract_type == "Alternance"

    def test_typeContratLibelle_used_when_nature_missing(self):
        from backend.scrapers.francetravail import _parse_offer
        item = {**_FT_TYPICAL, "natureContrat": "", "typeContratLibelle": "Contrat de pro"}
        off = _parse_offer(item)
        assert off.contract_type == "Contrat de pro"

    def test_missing_url_origine_falls_back_to_canonical(self):
        """Sans `origineOffre.urlOrigine`, on génère l'URL canonique FT."""
        from backend.scrapers.francetravail import _parse_offer
        item = {**_FT_TYPICAL, "origineOffre": {}}
        off = _parse_offer(item)
        assert off.url == "https://candidat.francetravail.fr/offres/recherche/detail/9876543"

    def test_date_truncated_to_iso_yyyy_mm_dd(self):
        from backend.scrapers.francetravail import _parse_offer
        # Pydantic field_validator tronque déjà à 10 chars (cf RawOffer)
        # mais _parse_offer le fait aussi pour ne pas trimballer la timezone.
        item = {**_FT_TYPICAL, "dateCreation": "2025-12-31T23:59:59+02:00"}
        off = _parse_offer(item)
        assert off.date_published == "2025-12-31"

    def test_empty_optional_fields_dont_crash(self):
        from backend.scrapers.francetravail import _parse_offer
        item = {
            "id": "1",
            "intitule": "Job",
            "lieuTravail": {},
            "entreprise": {},
            "salaire": {},
            "dateCreation": "",
            "natureContrat": "E1",
            "description": "x" * 250,  # Required by RawOffer
            "origineOffre": {},
        }
        off = _parse_offer(item)
        assert off.title == "Job"
        assert off.company is None
        assert off.city is None
        assert off.department is None
        assert off.salary is None
        assert off.date_published is None
