"""Modèles Pydantic et constantes métier."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

# --- Constantes métier ---

VALID_STATUSES = (
    "Postulé",
    "Relancé",
    "Entretien",
    "Test technique",
    "Refusé",
    "Accepté",
    "Sans réponse",
    "Abandonné",
)
Status = Literal[
    "Postulé", "Relancé", "Entretien", "Test technique",
    "Refusé", "Accepté", "Sans réponse", "Abandonné",
]

VALID_PRIORITIES = ("Haute", "Moyenne", "Basse")
Priority = Literal["Haute", "Moyenne", "Basse"]

VALID_REMOTE = ("Oui", "Non", "Hybride")
Remote = Literal["Oui", "Non", "Hybride"]

MATCH_LABELS = ("Top", "Bon", "Moyen", "Faible")


def label_for_score(score: int | None) -> str | None:
    if score is None:
        return None
    if score >= 80:
        return "Top"
    if score >= 60:
        return "Bon"
    if score >= 40:
        return "Moyen"
    return "Faible"


# --- Modèles ---

class OfferBase(BaseModel):
    title: str
    company: Optional[str] = None
    city: Optional[str] = None
    department: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    date_published: Optional[str] = None
    remote: Optional[str] = None
    contract_type: Optional[str] = None
    salary: Optional[str] = None


class Offer(OfferBase):
    id: int

    # scoring
    match_score: Optional[int] = None
    score_pipeline: Optional[int] = None
    score_exploration: Optional[int] = None
    score_modelisation: Optional[int] = None
    score_deploiement: Optional[int] = None
    score_cadrage: Optional[int] = None
    match_label: Optional[str] = None
    match_reasoning: Optional[str] = None
    scored_at: Optional[str] = None

    # tracking
    status: Optional[str] = None
    application_method: Optional[str] = None
    date_applied: Optional[str] = None
    date_followup: Optional[str] = None
    date_interview: Optional[str] = None
    notes: Optional[str] = None
    priority: Optional[str] = None

    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    scraped_at: Optional[str] = None


class OfferUpdate(BaseModel):
    """Patch d'une offre via UI."""
    status: Optional[str] = None
    application_method: Optional[str] = None
    date_applied: Optional[str] = None
    date_followup: Optional[str] = None
    date_interview: Optional[str] = None
    notes: Optional[str] = None
    priority: Optional[str] = None


class LLMScoreBreakdown(BaseModel):
    """Output attendu du LLM (toi) pour une offre."""
    offer_id: int
    score_pipeline: int = Field(ge=0, le=20)
    score_exploration: int = Field(ge=0, le=20)
    score_modelisation: int = Field(ge=0, le=20)
    score_deploiement: int = Field(ge=0, le=20)
    score_cadrage: int = Field(ge=0, le=20)
    match_reasoning: str

    @property
    def total(self) -> int:
        return (
            self.score_pipeline
            + self.score_exploration
            + self.score_modelisation
            + self.score_deploiement
            + self.score_cadrage
        )
