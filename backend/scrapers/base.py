"""Interface commune à tous les scrapers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RawOffer:
    """Une offre brute issue d'un scraper. Champs minimums + extras."""
    title: str
    company: str | None = None
    city: str | None = None
    department: str | None = None
    url: str | None = None
    source: str = ""
    description: str | None = None
    date_published: str | None = None     # ISO YYYY-MM-DD si possible, sinon raw
    contract_type: str | None = None
    salary: str | None = None
    remote: str | None = None
    raw: dict | None = None               # blob source-spécifique pour audit


class Scraper(ABC):
    """ABC pour tous les scrapers de sources."""

    source_name: str = ""  # ex: "Hellowork", "France Travail"

    @abstractmethod
    def fetch_list(
        self,
        *,
        keywords: list[str],
        max_pages: int = 5,
    ) -> list[RawOffer]:
        """Liste les offres correspondant aux mots-clés. Filtre alternance + France."""

    def fetch_detail(self, url: str) -> str | None:  # noqa: ARG002
        """Récupère la description complète d'une offre. Par défaut : non implémenté."""
        return None
