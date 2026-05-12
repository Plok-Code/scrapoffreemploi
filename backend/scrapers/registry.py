"""Registre des scrapers disponibles, indexés par nom court."""
from __future__ import annotations

from backend.scrapers._generic import GenericScraper
from backend.scrapers.base import Scraper
from backend.scrapers.francetravail import FranceTravailScraper
from backend.scrapers.hellowork import HelloWorkScraper
from backend.scrapers.linkedin import LinkedInScraper
from backend.scrapers.wttj import WTTJScraper

SCRAPERS: dict[str, type[Scraper]] = {
    "hellowork": HelloWorkScraper,
    "francetravail": FranceTravailScraper,
    "linkedin": LinkedInScraper,
    "wttj": WTTJScraper,
    "generic": GenericScraper,
    # À venir : apec, indeed, jobteaser (anti-bot)
}


def get_scraper(name: str) -> Scraper:
    """Instancie un scraper depuis son nom court (case-insensitive)."""
    key = name.strip().lower()
    if key not in SCRAPERS:
        available = ", ".join(sorted(SCRAPERS))
        raise KeyError(f"Scraper inconnu : '{name}'. Disponibles : {available}")
    return SCRAPERS[key]()


def list_scrapers() -> list[str]:
    return sorted(SCRAPERS)
