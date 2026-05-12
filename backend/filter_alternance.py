"""Filtre les offres qui ne sont PAS alternance/apprentissage/contrat pro.

Règle métier :
- Garde TOUTES les offres qui mentionnent alternance/apprenti/professionnalisation
- Supprime les offres EXPLICITEMENT marquées CDI/CDD/stage seul/freelance/intérim
- En cas de doute (pas d'indicateur explicite) → garde (principe : on garde sauf si on est sûr de rejeter)

Pour les offres rejetées :
- status NULL → DELETE (cohérent avec la règle URL morte + sans statut)
- status NOT NULL → is_active=0 (préserve l'historique applicatif)

Idempotent : peut être relancé à chaque scrape.
"""
from __future__ import annotations

import re

from backend import queries
from backend.db import db


# Mots-clés alternance — PRÉSENT = on garde même si CDI cohabite
_KEEP_PATTERN = re.compile(
    r"\b(?:alternan[ct]e?s?|apprenti(?:[\(e]?[s]?)?|apprentissage|"
    r"contrat\s*pro(?:fessionnali[sz]ation)?|professionnali[sz]ation)\b",
    re.IGNORECASE,
)

# Marqueurs explicites de NON-alternance (titre prioritaire sur description).
# Si UN seul match dans le TITRE + pas de _KEEP_PATTERN → rejet.
_REJECT_TITLE_PATTERNS = [
    # Contrats explicites
    re.compile(r"\bCDI\b", re.IGNORECASE),
    re.compile(r"\bCDD\b(?!\s*[+/]\s*altern)", re.IGNORECASE),
    re.compile(r"\bcontrat\s+(?:de\s+)?travail\b", re.IGNORECASE),
    re.compile(r"\bfreelance\b|free-?lance", re.IGNORECASE),
    re.compile(r"\bint[ée]rim\b|\binterim\b", re.IGNORECASE),
    re.compile(r"\bmission\s+ind[ée]pendante?\b", re.IGNORECASE),
    re.compile(r"\bportage\s+salarial\b", re.IGNORECASE),
    # Niveaux qui excluent l'alternance étudiant
    re.compile(r"\bSenior\b|\bSr\.?\b(?!\s*Architect)", re.IGNORECASE),
    re.compile(r"\bConfirm[ée]?\b", re.IGNORECASE),
    re.compile(r"\bExp[ée]riment[ée]?\b", re.IGNORECASE),
    re.compile(r"\bLead\s+(?:Data|ML|AI|Dev|Tech|Engineer)\b", re.IGNORECASE),
    re.compile(r"\bTech\s+Lead\b", re.IGNORECASE),
    re.compile(r"\bDirecteur\b|\bDirectrice\b|\bDirector\b", re.IGNORECASE),
    re.compile(r"\bResponsable\s+(?!.*alternan)", re.IGNORECASE),
    re.compile(r"\bManager\b", re.IGNORECASE),
    re.compile(r"\bChief\b|\bCxO\b|\bC[TIO]O\b", re.IGNORECASE),
    re.compile(r"\bPrincipal\s+Engineer\b", re.IGNORECASE),
    # Stage SEUL (sans alternance)
    re.compile(r"\bstage\b(?!\s*[/+&]\s*altern)", re.IGNORECASE),
]

# Marqueurs dans la DESCRIPTION (plus prudent, on n'utilise que les très explicites)
_REJECT_DESC_PATTERNS = [
    # Salaires annuels (CDI typique)
    re.compile(r"\b\d{2,3}\s*[k€]\s*(?:€|EUR|brut|annuel)", re.IGNORECASE),
    re.compile(r"package\s+\d{2,3}\s*[k€]", re.IGNORECASE),
    re.compile(r"\bsalaire\s+annuel\b", re.IGNORECASE),
    # Niveau d'expérience
    re.compile(r"\b(?:5|6|7|8|10)\+?\s+(?:ans?|years?)\s+(?:d['e]\s*)?exp[ée]rience", re.IGNORECASE),
    re.compile(r"\bminimum\s+\d+\s+ans?\s+(?:d['e]\s*)?exp[ée]rience", re.IGNORECASE),
]


def classify_offer(title: str | None, description: str | None,
                   contract_type: str | None = None) -> tuple[str, str]:
    """Classifie une offre selon la règle métier.

    Returns:
        (verdict, reason) où verdict ∈ {"keep", "reject", "doubt"}
        - "keep" : alternance/apprentissage explicite
        - "reject" : CDI/CDD/stage seul/senior/etc. explicite
        - "doubt" : aucun indicateur → on garde (principe : on garde sauf si sûr)
    """
    title = title or ""
    description = description or ""
    contract_type = (contract_type or "").lower()

    # 1. Si KEEP pattern trouvé → on garde, peu importe le reste
    text = f"{title}\n{description}"
    if _KEEP_PATTERN.search(text):
        return "keep", "alternance/apprenti/contrat pro mentionné"

    # 2. Contract_type explicite "Alternance" → on garde
    if "alternance" in contract_type or "apprenti" in contract_type or "professionnalisation" in contract_type:
        return "keep", f"contract_type='{contract_type}'"

    # 3. Si REJECT pattern dans le titre → on rejette
    for pat in _REJECT_TITLE_PATTERNS:
        m = pat.search(title)
        if m:
            return "reject", f"titre contient '{m.group()}'"

    # 4. Si REJECT pattern fort dans la description (salaire annuel, années d'XP)
    for pat in _REJECT_DESC_PATTERNS:
        m = pat.search(description[:3000])  # limite pour perf
        if m:
            return "reject", f"description contient '{m.group()[:50]}'"

    # 5. Contract_type explicite CDI/CDD → on rejette
    if contract_type in {"cdi", "cdd"}:
        return "reject", f"contract_type='{contract_type}'"

    # 6. Aucun indicateur → DOUTE → on garde (principe du user)
    return "doubt", "pas d'indicateur explicite"


def filter_non_alternance_offers(*, dry_run: bool = False) -> dict:
    """Parcourt toutes les offres actives, supprime/archive les non-alternance.

    Args:
        dry_run: si True, ne touche pas la DB mais retourne les stats.
    """
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description, contract_type, status
            FROM offers
            WHERE (is_active IS NULL OR is_active = 1)
            ORDER BY id
            """
        ).fetchall()
        offers = [dict(r) for r in rows]

    stats = {
        "total": len(offers),
        "keep": 0,
        "doubt": 0,
        "reject_deleted": 0,
        "reject_archived": 0,
        "examples_rejected": [],  # quelques exemples pour audit
    }

    for off in offers:
        verdict, reason = classify_offer(
            off["title"], off["description"], off["contract_type"]
        )
        if verdict == "keep":
            stats["keep"] += 1
            continue
        if verdict == "doubt":
            stats["doubt"] += 1
            continue
        # verdict == "reject"
        has_status = bool(off["status"])
        if not dry_run:
            if has_status:
                queries.set_alive_state(off["id"], is_active=False)
                stats["reject_archived"] += 1
            else:
                queries.delete_offer(off["id"])
                stats["reject_deleted"] += 1
        else:
            if has_status:
                stats["reject_archived"] += 1
            else:
                stats["reject_deleted"] += 1
        if len(stats["examples_rejected"]) < 10:
            title_short = (off["title"] or "")[:60]
            stats["examples_rejected"].append({
                "id": off["id"],
                "title": title_short,
                "reason": reason,
                "deleted": not has_status,
            })

    return stats


if __name__ == "__main__":
    import sys
    dry = "--dry" in sys.argv or "--dry-run" in sys.argv
    result = filter_non_alternance_offers(dry_run=dry)
    print(f"Filtrage non-alternance ({'DRY RUN' if dry else 'LIVE'}) :")
    print(f"  Total offres actives : {result['total']}")
    print(f"  Gardes (alternance)  : {result['keep']}")
    print(f"  Doute (gardes)       : {result['doubt']}")
    print(f"  Rejet -> supprime    : {result['reject_deleted']}")
    print(f"  Rejet -> archive     : {result['reject_archived']}")
    print()
    if result["examples_rejected"]:
        print("Exemples rejetes :")
        for ex in result["examples_rejected"]:
            action = "DEL" if ex["deleted"] else "ARC"
            print(f"  [{action}] [{ex['id']:>4}] {ex['title']:<60} | {ex['reason']}")
