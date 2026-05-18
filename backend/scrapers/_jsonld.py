"""Helpers d'extraction JSON-LD JobPosting (Schema.org).

Le `<script type="application/ld+json">` contenant un `JobPosting` est le
moyen le plus stable et propre d'obtenir une description d'offre :
- Standard public Schema.org (https://schema.org/JobPosting).
- Présent sur 50%+ des career sites modernes (Workable, Lever, Workday,
  Greenhouse, HelloWork, WTTJ, ...).
- Non affecté par les refontes UI (les ATS le génèrent automatiquement).

Cette implémentation gère les 3 formats rencontrés dans la nature :
- Un objet dict unique : `{"@type": "JobPosting", "description": "..."}`
- Une liste d'objets : `[{...}, {"@type": "JobPosting", ...}, ...]`
- Un graphe : `{"@graph": [..., {"@type": "JobPosting", ...}]}`

Avant ce module, le code était dupliqué 3 fois (`_generic.py`, `hellowork.py`,
`wttj.py`) avec 3 niveaux de complétude différents — corrigé par P1.2.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup


# Seuil minimum pour considérer une description "valide" — en dessous
# c'est probablement un fragment vide / un placeholder.
_MIN_DESC_LEN = 200


def normalize_whitespace(text: str) -> str:
    """Normalise les espaces blancs : strip + collapse triple+ newlines en double.

    Utile sur la sortie de `BeautifulSoup.get_text(separator="\\n", strip=True)`
    qui peut accumuler des \\n vides quand des blocs imbriqués sont strippés.
    """
    return re.sub(r"\n{3,}", "\n\n", text)


def _iter_jsonld_objects(script_text: str | None) -> list[dict]:
    """Décode un script JSON-LD et aplatit les formats (dict / list / @graph).

    Retourne toujours une liste de `dict` (vide si parsing échoue ou pas de dicts).
    """
    if not script_text:
        return []
    try:
        data = json.loads(script_text)
    except (json.JSONDecodeError, TypeError):
        return []
    initial: list = data if isinstance(data, list) else [data]
    out: list[dict] = []
    for item in initial:
        if not isinstance(item, dict):
            continue
        out.append(item)
        # Aplatit également @graph (utilisé par certains ATS Workday-like)
        graph = item.get("@graph")
        if isinstance(graph, list):
            for g in graph:
                if isinstance(g, dict):
                    out.append(g)
    return out


def extract_jobposting_description(
    soup: BeautifulSoup,
    *,
    min_len: int = _MIN_DESC_LEN,
) -> str | None:
    """Cherche un `JobPosting` JSON-LD dans le DOM et retourne sa description.

    Args:
        soup: page parsée (`BeautifulSoup(html, "lxml")`).
        min_len: longueur min en chars pour qu'une description soit considérée
            valide. Sous ce seuil, on continue de chercher (page index sans
            détail réel, par exemple).

    Returns:
        Le texte propre de la description (HTML stripé, whitespace normalisé)
        ou `None` si pas de `JobPosting` trouvé ou description trop courte.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        for item in _iter_jsonld_objects(script.string):
            if item.get("@type") != "JobPosting":
                continue
            desc_html = item.get("description", "")
            if not desc_html:
                continue
            # La description JSON-LD est HTML — on la repasse dans soup pour stripper
            inner = BeautifulSoup(desc_html, "lxml")
            text = normalize_whitespace(inner.get_text(separator="\n", strip=True))
            if len(text) >= min_len:
                return text
    return None
