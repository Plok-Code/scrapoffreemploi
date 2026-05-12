"""Mots-clés IA/data utilisés pour filtrer les offres au scraping.

Une offre est gardée si son titre OU sa description contient au moins UN match
(insensible à la casse, frontières de mot respectées).
"""
from __future__ import annotations

import re

# Mots-clés cœur (séparés en groupes pour lisibilité)
KEYWORDS_IA = [
    r"\bIA\b", r"\bAI\b",
    r"artificial intelligence", r"intelligence artificielle",
    r"\bIA\s+(?:engineer|générative|générative)\b",
    r"genAI", r"generative AI",
]
KEYWORDS_ML = [
    r"\bML\b", r"machine learning", r"apprentissage automatique",
    r"\bMLOps\b", r"\bML\s+Engineer\b",
]
KEYWORDS_DL = [
    r"deep learning", r"apprentissage profond",
    r"\bDL\b\s+engineer",
    r"\bNLP\b", r"natural language", r"langage naturel",
    r"computer vision", r"vision par ordinateur",
]
KEYWORDS_LLM = [
    r"\bLLM\b", r"large language model", r"\bRAG\b",
    r"retrieval augmented", r"agentic", r"agent\s+IA",
    r"fine[\-\s]?tuning",
]
KEYWORDS_DATA = [
    r"\bdata\b",
    r"\bdonnée[s]?\b",
    r"data scientist[e]?", r"data engineer", r"data architect",
    r"AI engineer", r"\bAI/ML\b",
]

ALL_KEYWORDS = (
    KEYWORDS_IA + KEYWORDS_ML + KEYWORDS_DL + KEYWORDS_LLM + KEYWORDS_DATA
)

# Pattern compilé combinant tout avec OR
_KW_PATTERN = re.compile("|".join(ALL_KEYWORDS), re.IGNORECASE)


def matches_keywords(*texts: str | None) -> bool:
    """True si au moins un des textes (titre, description, etc.) contient un mot-clé."""
    for t in texts:
        if t and _KW_PATTERN.search(t):
            return True
    return False
