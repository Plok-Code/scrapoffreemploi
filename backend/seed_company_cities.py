"""Migration one-shot : remplir target_companies.city pour les 65 entreprises
du xlsx historique + dupliquer les rows pour les entreprises multi-implantation.

Le user veut une ligne par (entreprise, ville). Donc :
- Airbus → Toulouse + Nantes (= 2 rows)
- Capgemini → Paris + Toulouse + Bordeaux + Nantes + Lyon (= 5 rows)
- Thales (différentes BU) → Toulouse + Paris + Bordeaux
- etc.

Source des localisations : connaissance domaine + extraction regex du nom.
"""
from __future__ import annotations

import re

from backend.db import db

# Mapping nom de l'entreprise → liste villes (parmi nos 5 cibles ou très proches).
# Pour les entreprises localisées dans une seule ville, une liste à 1 élément suffit.
# Les "alentours" sont préfixés (ex "Pau (Bordes)") pour rester rattachés à la ville cible.
COMPANY_CITIES: dict[str, list[str]] = {
    # === Aéronautique / spatial / défense (Toulouse + Bordeaux/Pau + Paris) ===
    "Airbus": ["Toulouse", "Nantes", "Paris (Saint-Cloud)"],
    "Thales Alenia Space": ["Toulouse", "Cannes"],
    "Thales DMS / Thales LAS": ["Toulouse", "Paris", "Bordeaux"],
    "Thales Research and Technology": ["Paris (Palaiseau)"],
    "Aumovio": ["Toulouse"],
    "IRT Saint Exupery": ["Toulouse"],
    "Latecoere": ["Toulouse"],
    "Liebherr Aerospace": ["Toulouse"],
    "Daher": ["Toulouse", "Paris", "Marseille"],
    "Donecle": ["Toulouse"],
    "Dassault Aviation": ["Paris (Saint-Cloud)", "Bordeaux (Mérignac)", "Toulouse"],
    "Safran Helicopter Engines (Bordes, ~10 km)": ["Pau (Bordes)"],
    "Alstom (Tarbes ~40 km TER)": ["Pau (Tarbes)"],
    "Soderel (Tarbes ~40 km TER)": ["Pau (Tarbes)"],

    # === ESN / Conseil (multi-implantation) ===
    "Capgemini": ["Paris", "Toulouse", "Bordeaux", "Nantes", "Lyon"],
    "Capgemini Engineering": ["Paris", "Toulouse", "Bordeaux", "Nantes", "Lyon"],
    "Capgemini Engineering (ex-Altran)": ["Paris", "Toulouse", "Bordeaux", "Nantes", "Lyon"],
    "Capgemini Invent": ["Paris"],
    "Capgemini Engineering (Pau)": ["Pau"],
    "Sopra Steria": ["Paris", "Toulouse", "Bordeaux", "Nantes", "Lyon", "Pau"],
    "Onepoint": ["Paris", "Bordeaux", "Toulouse", "Nantes"],
    "CGI": ["Paris", "Toulouse", "Bordeaux", "Lyon"],
    "CGI (Pau)": ["Pau"],
    "Atos / Eviden": ["Paris (Bezons)", "Toulouse", "Bordeaux"],
    "Davidson Consulting": ["Paris", "Toulouse", "Bordeaux", "Nantes", "Lyon"],
    "Bertin Technologies": ["Paris", "Aix-en-Provence"],
    "Smile (Open Source IT)": ["Paris", "Bordeaux", "Toulouse", "Nantes", "Lyon"],
    "Synchrone (Pau)": ["Pau"],
    "Ekimetrics": ["Paris"],
    "BCG GAMMA": ["Paris"],

    # === Tech / IT (Toulouse + Paris) ===
    "IBM Toulouse": ["Toulouse"],
    "ANITI (Artificial & Natural Intelligence Toulouse Institute)": ["Toulouse"],
    "UnaBiz (ex-Sigfox)": ["Toulouse"],
    "TellMePlus": ["Toulouse", "Paris"],
    "FieldBox.ai": ["Bordeaux"],
    "Synapse Medicine": ["Bordeaux"],
    "Cdiscount": ["Bordeaux"],
    "Lectra": ["Bordeaux"],

    # === Startups IA / sante / scaleups Paris ===
    "Mistral AI": ["Paris"],
    "Hugging Face": ["Paris"],
    "Owkin": ["Paris", "Nantes"],
    "Doctolib": ["Paris"],
    "Criteo AI Lab": ["Paris", "Grenoble"],
    "Datadog": ["Paris"],
    "Heuritech": ["Paris"],
    "Younited Credit": ["Paris"],

    # === Grands groupes IA/data (Paris + ouvertures province) ===
    "L'Oreal Beauty Tech": ["Paris"],
    "LVMH (Beauty/Fashion Tech)": ["Paris"],
    "Ubisoft La Forge": ["Paris", "Bordeaux", "Montpellier"],
    "Renault Software Factory": ["Paris (Boulogne)", "Toulouse"],
    "Sanofi": ["Paris (Gentilly)", "Montpellier", "Toulouse"],
    "Saint-Gobain Recherche": ["Paris (Aubervilliers)"],
    "Pierre Fabre": ["Toulouse (Castres)"],
    "Engie Lab CRIGEN": ["Paris (Stains)"],
    "EDF R&D Lab Paris-Saclay": ["Paris (Saclay)"],
    "CEA-LIST (Saclay)": ["Paris (Saclay)"],

    # === Recherche / labos Nancy ===
    "Inria Nancy Grand Est": ["Nancy"],
    "LORIA (CNRS / UL / Inria)": ["Nancy"],
    "Pharmagest (Equasens)": ["Nancy (Villers-lès-Nancy)"],

    # === Pau & alentours ===
    "TotalEnergies CSTJF (Pau-Jurancon)": ["Pau"],
    "UPPA - Universite Pau Pays Adour": ["Pau"],

    # === Auto/Industrie ===
    "Stellantis Tremery": ["Nancy (Trémery)"],
    "Soprema (Strasbourg ~1h30 TER)": ["Nancy (Strasbourg)"],

    # === Bordeaux ===
    "Adopt Parfums (Cestas)": ["Bordeaux (Cestas)"],

    # === SNCF ===
    "SNCF Reseau Sud-Ouest": ["Bordeaux", "Toulouse"],
}


def _extract_city_from_name(name: str) -> list[str] | None:
    """Cherche une ville cible (Toulouse, Paris, Bordeaux, Pau, Nancy) dans le nom."""
    found = []
    for city in ["Toulouse", "Bordeaux", "Pau", "Paris", "Nancy"]:
        if re.search(rf"\b{city}\b", name, re.IGNORECASE):
            found.append(city)
    return found or None


def expand_cities() -> dict:
    """Pour chaque entreprise sans city :
       - Cherche dans COMPANY_CITIES par match exact du nom
       - Sinon, extrait depuis le nom via regex
       - Sinon, laisse city=NULL (entreprise nationale sans localisation précise)
    Pour les multi-villes (N > 1), DUPLIQUE la row (1 par ville).
    """
    inserted = 0
    updated = 0
    untouched = 0
    with db() as conn:
        # On désactive temporairement l'index UNIQUE pour permettre les duplicates
        # de (name, NULL) avant que le nouveau index (name, city) soit créé.
        # En pratique, l'ancien index est UNIQUE(LOWER(name)) — on doit le drop.
        try:
            conn.execute("DROP INDEX IF EXISTS idx_target_companies_name")
        except Exception as e:
            # OK si l'index n'existe pas déjà (migration déjà appliquée)
            from backend._logging import logger
            logger.debug("DROP INDEX idx_target_companies_name skipped : {err}", err=str(e))

        rows = conn.execute(
            "SELECT id, name FROM target_companies WHERE city IS NULL OR city = '' ORDER BY id"
        ).fetchall()

        for row in rows:
            row_id = row["id"]
            name = row["name"]

            cities = COMPANY_CITIES.get(name)
            if not cities:
                cities = _extract_city_from_name(name)

            if not cities:
                untouched += 1
                continue

            # 1ère ville → UPDATE la row existante
            conn.execute(
                "UPDATE target_companies SET city = :city WHERE id = :id",
                {"city": cities[0], "id": row_id},
            )
            updated += 1

            # Villes suivantes → INSERT de nouvelles rows clonées
            if len(cities) > 1:
                # Récupérer la row complète pour la cloner
                full = conn.execute(
                    "SELECT * FROM target_companies WHERE id = :id", {"id": row_id}
                ).fetchone()
                for extra_city in cities[1:]:
                    conn.execute(
                        """
                        INSERT INTO target_companies (
                            name, sector, city, relevance, priority,
                            contact_channel, contact_name, notes, feedback,
                            email, reliability, source_url, source, status
                        ) VALUES (
                            :name, :sector, :city, :relevance, :priority,
                            :contact_channel, :contact_name, :notes, :feedback,
                            :email, :reliability, :source_url, :source, NULL
                        )
                        """,
                        {
                            "name": full["name"],
                            "sector": full["sector"],
                            "city": extra_city,
                            "relevance": full["relevance"],
                            "priority": full["priority"],
                            "contact_channel": full["contact_channel"],
                            "contact_name": full["contact_name"],
                            "notes": full["notes"],
                            "feedback": full["feedback"],
                            "email": full["email"],
                            "reliability": full["reliability"],
                            "source_url": full["source_url"],
                            "source": full["source"],
                        },
                    )
                    inserted += 1

        # Recrée l'index avec (name, city) — autorise une row par couple
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_target_companies_name_city "
            "ON target_companies(LOWER(name), LOWER(COALESCE(city, '')))"
        )

    return {"updated": updated, "inserted": inserted, "untouched": untouched}


if __name__ == "__main__":
    result = expand_cities()
    print(f"Expansion villes : {result}")
    # Stats finales
    with db() as conn:
        n_total = conn.execute("SELECT COUNT(*) AS n FROM target_companies").fetchone()["n"]
        n_with_city = conn.execute(
            "SELECT COUNT(*) AS n FROM target_companies WHERE city IS NOT NULL AND city != ''"
        ).fetchone()["n"]
    print(f"target_companies : {n_total} (dont {n_with_city} avec ville)")
