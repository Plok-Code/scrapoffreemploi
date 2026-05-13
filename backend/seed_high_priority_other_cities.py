"""Seed des entreprises priorité Haute hors-5 villes cibles.

Règle métier :
- 5 villes cibles (Toulouse, Bordeaux, Pau, Paris, Nancy) → toutes les priorités
- Autres villes France → uniquement priorité Haute (offres data/IA score ≥ 70)

Sélectionne les entreprises ayant au moins une offre Bon+ (≥70) dans une ville
hors-5, dédup par (entreprise, ville), insère en target_companies avec
`priority='Haute'` et `source='haute-priorite-autre-ville'`.

Idempotent : peut être relancé, ne crée pas de doublons.
"""
from __future__ import annotations

from backend import queries
from backend.db import db

# Seuil de score pour qu'une entreprise hors-5-villes soit considérée Haute priorité
MIN_SCORE_HIGH_PRIORITY = 70

# Villes à exclure (les 5 cibles déjà gérées par seed_company_cities + import depuis offres)
EXCLUDED_CITY_PATTERNS = ["toulouse", "bordeaux", "pau", "paris", "nancy"]


def fetch_high_priority_other_cities(*, min_score: int = MIN_SCORE_HIGH_PRIORITY) -> list[dict]:
    """Retourne les couples (entreprise, ville) avec offres ≥ min_score, hors-5-villes."""
    # `exclusions` est construit depuis la constante EXCLUDED_CITY_PATTERNS
    # (liste hardcodée module-level). Les valeurs des villes passent via params
    # nommés `:ex{i}` (jamais concaténées dans le SQL). On utilise .format()
    # sur un template constant pour garder le multi-line lisible ET permettre
    # le marqueur de skip B608 sur une seule ligne.
    exclusions = " AND ".join(f"LOWER(city) NOT LIKE :ex{i}" for i in range(len(EXCLUDED_CITY_PATTERNS)))
    sql_template = """
        SELECT
            company AS name,
            city,
            MAX(match_score) AS max_score,
            COUNT(*) AS n_offers,
            MAX(source) AS source,
            MAX(url) AS sample_url
        FROM offers
        WHERE company IS NOT NULL AND company != ''
          AND city IS NOT NULL AND city != ''
          AND match_score >= :min_score
          AND (is_active IS NULL OR is_active = 1)
          AND {exclusions}
        GROUP BY LOWER(company), LOWER(city)
        ORDER BY max_score DESC, n_offers DESC
    """
    sql = sql_template.format(exclusions=exclusions)  # nosec B608
    params: dict = {"min_score": min_score}
    for i, p in enumerate(EXCLUDED_CITY_PATTERNS):
        params[f"ex{i}"] = f"%{p}%"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def import_high_priority_other_cities(*, min_score: int = MIN_SCORE_HIGH_PRIORITY) -> dict:
    """Importe en target_companies les entreprises haute priorité hors-5-villes."""
    candidates = fetch_high_priority_other_cities(min_score=min_score)
    inserted = 0
    skipped = 0
    for c in candidates:
        sample_url = c.get("sample_url") or ""
        data = {
            "name": c["name"],
            "city": c["city"],
            "sector": None,
            "relevance": (
                f"Entreprise haute priorité hors-5-villes : {c['n_offers']} offre(s) "
                f"score max {c['max_score']} sur ce bassin. Ville {c['city']}."
            ),
            "priority": "Haute",
            "contact_channel": "Candidature spontanée (site corporate, LinkedIn, email RH)",
            "notes": f"Offre type vue : {sample_url}",
            "source": "haute-priorite-autre-ville",
        }
        _id, was_new = queries.insert_target_company(data)
        if was_new:
            inserted += 1
        else:
            skipped += 1
    return {"candidates": len(candidates), "inserted": inserted, "skipped_dup": skipped}


if __name__ == "__main__":
    result = import_high_priority_other_cities()
    print(f"Import haute priorité hors-5 villes : {result}")
    # Stats
    with db() as conn:
        n_total = conn.execute("SELECT COUNT(*) AS n FROM target_companies").fetchone()["n"]
        n_haute = conn.execute(
            "SELECT COUNT(*) AS n FROM target_companies WHERE priority = 'Haute'"
        ).fetchone()["n"]
        # Hors 5 villes haute priorité
        n_others_haute = conn.execute(
            "SELECT COUNT(*) AS n FROM target_companies "
            "WHERE priority = 'Haute' "
            "AND LOWER(city) NOT LIKE '%toulouse%' "
            "AND LOWER(city) NOT LIKE '%bordeaux%' "
            "AND LOWER(city) NOT LIKE '%pau%' "
            "AND LOWER(city) NOT LIKE '%paris%' "
            "AND LOWER(city) NOT LIKE '%nancy%'"
        ).fetchone()["n"]
    print(f"target_companies total : {n_total}")
    print(f"  dont priorité Haute   : {n_haute}")
    print(f"  dont Haute hors-5     : {n_others_haute}")
