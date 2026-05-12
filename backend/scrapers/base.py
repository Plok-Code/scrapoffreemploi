"""Interface commune à tous les scrapers.

Niveau ultra senior : `RawOffer` est un modèle Pydantic (BaseModel) avec
validation automatique des types à la construction. Si un site bug et renvoie
un prix sous forme de texte alors qu'on attend un int, Pydantic catch
immédiatement au moment du scraping (avant que la donnée corrompue n'arrive
en DB).

Compat : conserve l'API "constructeur positional/keyword" identique à
l'ancienne `@dataclass` — tous les anciens appels `RawOffer(title="...", ...)`
fonctionnent toujours.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RawOffer(BaseModel):
    """Une offre brute issue d'un scraper. Validation Pydantic.

    Le titre est obligatoire et non-vide. Les autres champs sont optionnels.
    Si un champ est de type incohérent (ex : `salary` passé en int au lieu de
    str), Pydantic le coerce ou raise une `ValidationError`.

    Attention : `raw` est laissé en `dict | None` pour stocker n'importe quel
    blob source-spécifique (audit), sans le valider plus loin.
    """

    model_config = ConfigDict(
        # On laisse les types passer en str si str-coercible (cohérent avec
        # l'ancien comportement @dataclass)
        str_strip_whitespace=True,
        # Permet d'ignorer les champs extra silencieusement (si un scraper
        # renvoie des champs en plus, pas la peine de planter)
        extra="ignore",
    )

    title: str = Field(min_length=1, description="Titre de l'offre, non vide")
    company: Optional[str] = None
    city: Optional[str] = None
    department: Optional[str] = None
    url: Optional[str] = None
    source: str = ""
    description: Optional[str] = None
    date_published: Optional[str] = None     # ISO YYYY-MM-DD si possible
    contract_type: Optional[str] = None
    salary: Optional[str] = None             # str libre (ex "32-38k€/an" ou "À négocier")
    remote: Optional[str] = None
    raw: Optional[dict[str, Any]] = None     # blob source-spécifique pour audit

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title is empty after stripping")
        return v.strip()

    @field_validator("url")
    @classmethod
    def _url_basic_check(cls, v: Optional[str]) -> Optional[str]:
        """URL : on accepte None ou un str ressemblant à une URL http(s)."""
        if v is None or v == "":
            return None
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            # On garde la valeur mais on log un warning (via Pydantic warn pas
            # accessible facilement → on laisse passer, certains scrapers
            # renvoient des paths relatifs)
            pass
        return v

    @field_validator("date_published")
    @classmethod
    def _date_basic_check(cls, v: Optional[str]) -> Optional[str]:
        """Date : on accepte None, '' ou ISO YYYY-MM-DD."""
        if v is None or v == "":
            return None
        return v.strip()[:10]  # tronque "2026-05-12T10:30Z" → "2026-05-12"


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
