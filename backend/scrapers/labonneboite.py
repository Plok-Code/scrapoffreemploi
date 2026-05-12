"""Client API La Bonne Boite v2 (France Travail).

https://francetravail.io/data/api/la-bonne-boite

Renvoie les entreprises avec le plus fort potentiel d'embauche pour un métier
(code ROME) et une zone géographique (code INSEE commune ou département).

Auth : OAuth2 client_credentials, scope `api_labonneboitev2`.
Réutilise les credentials FRANCETRAVAIL_CLIENT_ID/SECRET déjà dans `.env`.
"""
from __future__ import annotations

import time

import httpx

# Réutilise le flow OAuth de francetravail.py mais avec un scope différent
from backend.scrapers.francetravail import (
    TOKEN_URL,
    _TOKEN_CACHE,
    _load_env,
)

LBB_SEARCH_URL = "https://api.francetravail.io/partenaire/labonneboite/v2/company/"
LBB_SCOPE = "api_labonneboitev2"

# Codes ROME data/IA pertinents pour AI Engineer
ROME_CODES_AI_ENGINEER = [
    "M1805",  # Études et développement informatique (data scientist / ML eng)
    "M1810",  # Production et exploitation de systèmes d'information
    "M1802",  # Expertise et support en systèmes d'information
    "M1811",  # Conseil et maîtrise d'ouvrage en systèmes d'information
]

# Coordonnées GPS des principales métropoles (API LBB v2 attend lat/lng, pas INSEE)
COORDS = {
    "Toulouse":  (43.6047, 1.4442),
    "Paris":     (48.8566, 2.3522),
    "Lyon":      (45.7640, 4.8357),
    "Bordeaux":  (44.8378, -0.5792),
    "Nantes":    (47.2184, -1.5536),
    "Rennes":    (48.1173, -1.6778),
    "Marseille": (43.2965, 5.3698),
    "Lille":     (50.6293, 3.0573),
    "Montpellier": (43.6108, 3.8767),
    "Grenoble":  (45.1885, 5.7245),
}


def _get_lbb_token(client: httpx.Client) -> str:
    """Token bearer pour La Bonne Boite. Cache séparé du scope FT offres."""
    cache_key = "lbb_token"
    cache_exp = "lbb_expires_at"
    now = time.time()
    if _TOKEN_CACHE.get(cache_key) and now < _TOKEN_CACHE.get(cache_exp, 0) - 30:
        return _TOKEN_CACHE[cache_key]

    client_id, client_secret = _load_env()
    resp = client.post(
        TOKEN_URL,
        params={"realm": "/partenaire"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": LBB_SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["access_token"]
    expires_in = int(data.get("expires_in", 1499))
    _TOKEN_CACHE[cache_key] = token
    _TOKEN_CACHE[cache_exp] = now + expires_in
    return token


def search_potential_hirings(
    *,
    rome_codes: list[str],
    latitude: float,
    longitude: float,
    distance_km: int = 30,
    contract: str | None = None,
) -> list[dict]:
    """Cherche les entreprises à fort potentiel d'embauche autour d'une zone GPS.

    Args:
        rome_codes: codes ROME (ex ["M1805"] pour data scientist/ML eng).
        latitude, longitude: coordonnées GPS (la doc LBB v2 exige du décimal).
        distance_km: rayon en km autour du point.
        contract: "alternance" pour filtrer alternance uniquement (optionnel).

    Returns:
        Liste de dicts entreprise (siret, raison_sociale, naf, ville, etc.).
    """
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        token = _get_lbb_token(client)
        # On envoie tous les codes ROME en une seule requête (séparés par virgule)
        params: dict = {
            "latitude": latitude,
            "longitude": longitude,
            "distance": distance_km,
            "rome_codes": ",".join(rome_codes),
        }
        if contract:
            params["contract"] = contract
        resp = client.get(
            LBB_SEARCH_URL,
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code == 401:
            _TOKEN_CACHE["lbb_expires_at"] = 0
            token = _get_lbb_token(client)
            resp = client.get(
                LBB_SEARCH_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        if resp.status_code not in (200, 206):
            return []
        payload = resp.json() if resp.text else {}
        items = (
            payload.get("companies")
            or payload.get("items")
            or payload.get("entreprises")
            or payload.get("results")
            or (payload if isinstance(payload, list) else [])
        )
        # On stock le ROME utilisé pour la note
        for item in items:
            item["_rome"] = params["rome_codes"]
        return items


def map_lbb_to_target_company(hit: dict, *, city_label: str) -> dict:
    """Convertit un hit La Bonne Boite en dict pour insert_target_company()."""
    # Champs typiques de la réponse LBB v2
    name = (
        hit.get("raison_sociale")
        or hit.get("name")
        or hit.get("enseigne")
        or hit.get("nom")
        or ""
    )
    naf = hit.get("naf") or hit.get("activite_principale") or ""
    naf_label = hit.get("naf_text") or hit.get("activite_principale_libelle") or ""
    sector = f"{naf} {naf_label}".strip() if naf else (naf_label or None)
    ville = hit.get("ville") or hit.get("commune") or city_label
    address = hit.get("adresse") or hit.get("address") or ""
    siret = hit.get("siret") or ""
    distance = hit.get("distance") or hit.get("distance_km") or None
    rome_used = hit.get("_rome", "")

    # On compose une note exploitable
    notes_parts = []
    if siret:
        notes_parts.append(f"SIRET {siret}")
    if address:
        notes_parts.append(address)
    if distance:
        notes_parts.append(f"~{distance} km de {city_label}")
    if rome_used:
        notes_parts.append(f"Métier ROME {rome_used} (potentiel d'embauche élevé)")

    return {
        "name": name.strip() if name else "Inconnu",
        "sector": sector,
        "city": ville,
        "relevance": (
            f"Entreprise détectée par La Bonne Boite (FT) sur "
            f"métiers data/IA ({rome_used}) à {city_label}. Bon potentiel d'embauche."
        ),
        "priority": "Moyenne",  # par défaut, l'utilisateur ajuste après
        "contact_channel": "Candidature spontanée directe (pas de portail dédié)",
        "contact_name": None,
        "notes": " | ".join(notes_parts) if notes_parts else None,
        "email": None,
        "reliability": "Source : La Bonne Boite v2 (FT)",
        "source_url": f"https://labonneboite.francetravail.fr/entreprise/{siret}" if siret else None,
        "source": "La Bonne Boite",
    }


def import_lbb_to_targets(
    *,
    city: str = "Toulouse",
    distance_km: int = 30,
    rome_codes: list[str] | None = None,
    contract: str | None = "alternance",
) -> dict:
    """Importe les entreprises LBB dans la table target_companies.

    Dédup sur LOWER(name). Retourne stats.
    """
    from backend import queries

    coords = COORDS.get(city)
    if coords is None:
        raise ValueError(f"Ville inconnue : {city}. Connues : {list(COORDS)}")
    lat, lon = coords

    hits = search_potential_hirings(
        rome_codes=rome_codes or ROME_CODES_AI_ENGINEER,
        latitude=lat,
        longitude=lon,
        distance_km=distance_km,
        contract=contract,
    )

    inserted = 0
    skipped = 0
    errors = 0
    for hit in hits:
        try:
            data = map_lbb_to_target_company(hit, city_label=city)
            if not data["name"] or data["name"] == "Inconnu":
                errors += 1
                continue
            _id, was_new = queries.insert_target_company(data)
            if was_new:
                inserted += 1
            else:
                skipped += 1
        except Exception:  # noqa: BLE001
            errors += 1

    return {
        "city": city,
        "total_hits": len(hits),
        "inserted": inserted,
        "skipped_dup": skipped,
        "errors": errors,
    }


if __name__ == "__main__":
    import sys
    city_arg = sys.argv[1] if len(sys.argv) > 1 else "Toulouse"
    if city_arg not in COORDS:
        print(f"Ville inconnue. Connues : {list(COORDS)}")
        sys.exit(1)
    result = import_lbb_to_targets(city=city_arg)
    print(f"Import LBB {city_arg}:")
    for k, v in result.items():
        print(f"  {k}: {v}")
