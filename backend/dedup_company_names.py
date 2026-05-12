"""Dédoublonnage des noms d'entreprise dans target_companies.

Beaucoup de noms variants (parenthèses descriptives, "ex-X", "(Ville)" déjà
capturé dans city) créent des doublons sémantiques :
- `Capgemini Engineering (ex-Altran)` = `Capgemini Engineering`
- `CGI (Pau)` = `CGI` (l'info Pau est dans city)
- `MACIF (Covéa)` = `MACIF`
- `Pharmagest (Equasens)` = `Pharmagest`

Stratégie :
1. Canonicalize : mapping alias → nom canonique (hardcoded, cas évidents seulement)
2. Pour chaque alias avec rows :
   - Si une row canonique sur la même ville existe → supprime l'alias (fusion par ville)
   - Sinon → renomme l'alias en nom canonique

Idempotent : peut être relancé sans risque.
"""
from __future__ import annotations

from backend.db import db


# Mapping alias → nom canonique.
# IMPORTANT : ne fusionne PAS des BUs distinctes (Thales Alenia Space ≠ Thales DMS).
# Cible uniquement les variantes nominales d'une même entité juridique/marque.
ALIAS_TO_CANONICAL: dict[str, str] = {
    # Capgemini
    "Capgemini Engineering (ex-Altran)": "Capgemini Engineering",
    "Capgemini Engineering (Pau)": "Capgemini Engineering",
    # CGI
    "CGI (Pau)": "CGI",
    # Synchrone
    "Synchrone (Pau)": "Synchrone",
    # MACIF
    "MACIF (Covéa)": "MACIF",
    "MACIF (Cov?éa)": "MACIF",  # variant mojibake
    # SFR
    "SFR (Altice France)": "SFR",
    "SFR - Altice France": "SFR",
    # Pharmagest
    "Pharmagest (Equasens)": "Pharmagest",
    # UnaBiz
    "UnaBiz (ex-Sigfox)": "UnaBiz",
    # Adopt
    "Adopt Parfums (Cestas)": "Adopt Parfums",
    # Soprema
    "Soprema (Strasbourg ~1h30 TER)": "Soprema",
    # Alstom
    "Alstom (Tarbes ~40 km TER)": "Alstom",
    # Soderel
    "Soderel (Tarbes ~40 km TER)": "Soderel",
    # Safran (le BU Helicopter Engines reste distinct du groupe Safran)
    "Safran Helicopter Engines (Bordes, ~10 km)": "Safran Helicopter Engines",
    # TotalEnergies CSTJF
    "TotalEnergies CSTJF (Pau-Jurancon)": "TotalEnergies CSTJF",
    # LORIA
    "LORIA (CNRS / UL / Inria)": "LORIA",
    # ANITI
    "ANITI (Artificial & Natural Intelligence Toulouse Institute)": "ANITI",
    # CEA-LIST
    "CEA-LIST (Saclay)": "CEA-LIST",
    # LVMH (le BU Beauty/Fashion Tech est intégré au groupe LVMH côté candidature)
    "LVMH (Beauty/Fashion Tech)": "LVMH",
    # Smile
    "Smile (Open Source IT)": "Smile",
    # L'Oréal — la BU Beauty Tech ≠ groupe L'Oréal côté postes (on garde séparé)
    # mais L'Oréal Groupe sans précision == L'Oréal Beauty Tech ? On laisse pour l'instant
    # Atos / Eviden — Eviden est la division big-data d'Atos, mais elles cohabitent toujours
    # On garde "Atos / Eviden" distinct pour ne pas effacer l'info.
    # Radio France
    "Societe Nationale de Radiodiffusion Radio France": "Radio France",
    # Inria — pas de fusion car "Inria Nancy Grand Est" est explicite et distinct
    # de Inria (national)
    # SNCF — SNCF Reseau Sud-Ouest reste distinct (l'entité ≠ SNCF national)
}


def dedup_target_companies() -> dict:
    """Applique le mapping alias → canonical sur target_companies.

    Pour chaque alias :
    - Si une row canonique sur la même ville existe → DELETE l'alias
    - Sinon → UPDATE l'alias en nom canonique

    Returns:
        Stats : alias_processed, deleted, renamed.
    """
    deleted = 0
    renamed = 0
    processed = 0

    with db() as conn:
        for alias, canonical in ALIAS_TO_CANONICAL.items():
            alias_rows = conn.execute(
                "SELECT id, city FROM target_companies WHERE name = ?",
                (alias,),
            ).fetchall()
            if not alias_rows:
                continue
            processed += 1
            for row in alias_rows:
                alias_id = row["id"]
                alias_city = row["city"] or ""
                # Cherche une row canonique sur la même ville
                existing = conn.execute(
                    "SELECT id FROM target_companies "
                    "WHERE LOWER(name) = LOWER(?) AND LOWER(COALESCE(city, '')) = LOWER(?)",
                    (canonical, alias_city),
                ).fetchone()
                if existing:
                    # Doublon sur cette ville → supprime l'alias
                    conn.execute("DELETE FROM target_companies WHERE id = ?", (alias_id,))
                    deleted += 1
                else:
                    # Pas de doublon → renomme l'alias en canonical
                    conn.execute(
                        "UPDATE target_companies SET name = ? WHERE id = ?",
                        (canonical, alias_id),
                    )
                    renamed += 1

    return {"processed": processed, "deleted": deleted, "renamed": renamed}


if __name__ == "__main__":
    result = dedup_target_companies()
    print(f"Dédup noms : {result}")
    with db() as conn:
        n_total = conn.execute("SELECT COUNT(*) AS n FROM target_companies").fetchone()["n"]
        n_distinct_names = conn.execute(
            "SELECT COUNT(DISTINCT LOWER(name)) AS n FROM target_companies"
        ).fetchone()["n"]
    print(f"target_companies : {n_total} rows / {n_distinct_names} noms distincts")
