"""Scraper France Travail via API officielle Offres d'emploi v2.

Docs : https://francetravail.io/data/api/offres-emploi

Auth : OAuth2 client_credentials, scope `api_offresdemploiv2 o2dsoffre`.
Les credentials sont lus depuis `.env` (FRANCETRAVAIL_CLIENT_ID, FRANCETRAVAIL_CLIENT_SECRET)
et JAMAIS hardcodés. Le `.env` est gitignored.

Pagination : `range=0-49` (max 0-149 par requête, plafond absolu 1150 offres par recherche).
Rate limit : 3 req/s. Token bearer valide 25 minutes (~1500s), on cache en mémoire.

Filtres alternance : `natureContrat=E1` (apprentissage) ou `E2` (professionnalisation).
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx

from backend._logging import logger
from backend.scrapers._keywords import matches_keywords
from backend.scrapers.base import RawOffer, Scraper


# --- Config ---

# Endpoint OAuth (pas un secret — c'est l'URL publique documentée de France Travail)
TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"  # nosec B105
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
DETAIL_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/{id}"
SCOPE = "api_offresdemploiv2 o2dsoffre"

# Codes alternance
NATURE_APPRENTISSAGE = "E1"
NATURE_PROFESSIONNALISATION = "E2"

# Politesse : on reste à 8 req/s alors que le plafond est 10/s (marge de sécurité)
_MIN_INTERVAL_S = 0.125

# Cache token en mémoire (par process). Le contenu réel est rempli au runtime
# via _get_token() — jamais hardcodé.
_TOKEN_CACHE: dict[str, Any] = {"token": None, "expires_at": 0.0}  # nosec B105


def _load_env() -> tuple[str, str]:
    """Charge les credentials depuis `.env` à la racine du projet, sans dotenv.

    Format attendu : `KEY=VALUE` une par ligne, # pour commentaire.
    Variables prises en charge :
        FRANCETRAVAIL_CLIENT_ID
        FRANCETRAVAIL_CLIENT_SECRET
    Priorité : variables d'environnement déjà définies > .env.
    """
    cid = os.environ.get("FRANCETRAVAIL_CLIENT_ID")
    csec = os.environ.get("FRANCETRAVAIL_CLIENT_SECRET")
    if cid and csec:
        return cid, csec

    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        raise RuntimeError(
            f"FRANCETRAVAIL_CLIENT_ID / FRANCETRAVAIL_CLIENT_SECRET introuvables. "
            f"Définir dans {env_path} ou comme variables d'environnement."
        )
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k == "FRANCETRAVAIL_CLIENT_ID" and not cid:
            cid = v
        elif k == "FRANCETRAVAIL_CLIENT_SECRET" and not csec:
            csec = v
    if not cid or not csec:
        raise RuntimeError("FRANCETRAVAIL_CLIENT_ID/SECRET manquant dans .env")
    return cid, csec


def _get_token(client: httpx.Client) -> str:
    """Renvoie un access_token valide (cache en mémoire, refresh auto)."""
    now = time.time()
    if _TOKEN_CACHE["token"] and now < _TOKEN_CACHE["expires_at"] - 30:
        return _TOKEN_CACHE["token"]

    client_id, client_secret = _load_env()
    resp = client.post(
        TOKEN_URL,
        params={"realm": "/partenaire"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != 200:
        logger.error(
            "FT OAuth token request failed : status={s} body={b}",
            s=resp.status_code, b=resp.text[:200],
        )
    resp.raise_for_status()
    data = resp.json()
    token = data["access_token"]
    expires_in = int(data.get("expires_in", 1499))
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expires_at"] = now + expires_in
    logger.debug("FT OAuth token refreshed (expires in {e}s)", e=expires_in)
    return token


# --- Mapping JSON → RawOffer ---

def _parse_offer(item: dict) -> RawOffer:
    """Convertit la réponse JSON d'une offre FT en RawOffer."""
    offer_id = item.get("id", "")
    lieu = item.get("lieuTravail") or {}
    entreprise = item.get("entreprise") or {}
    salaire = item.get("salaire") or {}

    # Date au format ISO "2026-05-12T10:30:00.000Z" → on prend juste YYYY-MM-DD
    raw_date = item.get("dateCreation") or ""
    date_pub = raw_date[:10] if raw_date else None

    # Lieu : libellé + codePostal (souvent "75 - PARIS 02" → on garde libellé brut,
    # et on tente d'extraire le département depuis codePostal)
    libelle_lieu = lieu.get("libelle") or ""
    code_postal = lieu.get("codePostal") or ""
    department = code_postal[:2] if code_postal and len(code_postal) >= 2 else None

    # Nature du contrat (alternance E1/E2 → libellé)
    nature_code = item.get("natureContrat") or ""
    contract_label = {
        "E1": "Alternance (apprentissage)",
        "E2": "Alternance (professionnalisation)",
    }.get(nature_code, item.get("typeContratLibelle") or "Alternance")

    # URL canonique vers le site candidat France Travail
    url = item.get("origineOffre", {}).get("urlOrigine") or (
        f"https://candidat.francetravail.fr/offres/recherche/detail/{offer_id}"
    )

    return RawOffer(
        title=item.get("intitule", "").strip(),
        company=entreprise.get("nom") or None,
        city=libelle_lieu or None,
        department=department,
        url=url,
        source="France Travail",
        description=item.get("description") or None,
        date_published=date_pub,
        contract_type=contract_label,
        salary=salaire.get("libelle") or None,
        remote=None,
        raw={"id": offer_id, "natureContrat": nature_code},
    )


# --- Scraper ---

class FranceTravailScraper(Scraper):
    """Scraper France Travail via API officielle v2 (OAuth2 client_credentials)."""

    source_name = "France Travail"

    # Plafond absolu côté FT : range max 1000-1149 → on ne dépasse pas 1150 par mot-clé
    _MAX_TOTAL_PER_KEYWORD = 1150

    def fetch_list(
        self,
        *,
        keywords: list[str],
        max_pages: int = 5,
        range_size: int = 50,
    ) -> list[RawOffer]:
        """Pour chaque mot-clé, paginate jusqu'à `max_pages * range_size` ou plafond FT.

        Args:
            keywords: liste de mots-clés à passer en `motsCles` (un par requête).
            max_pages: nb max de pages de `range_size` offres par mot-clé.
            range_size: 50 par défaut (max API = 150 mais 50 plus prudent).
        """
        offers: list[RawOffer] = []
        seen_ids: set[str] = set()
        last_call = 0.0

        with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            token = _get_token(client)
            auth_headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            for kw in keywords:
                fetched_for_kw = 0
                for page in range(max_pages):
                    offset = page * range_size
                    if offset >= self._MAX_TOTAL_PER_KEYWORD:
                        break
                    end = min(offset + range_size - 1, self._MAX_TOTAL_PER_KEYWORD - 1)

                    # Rate limit : 3 req/s
                    elapsed = time.time() - last_call
                    if elapsed < _MIN_INTERVAL_S:
                        time.sleep(_MIN_INTERVAL_S - elapsed)

                    try:
                        resp = client.get(
                            SEARCH_URL,
                            headers=auth_headers,
                            params={
                                "motsCles": kw,
                                "natureContrat": f"{NATURE_APPRENTISSAGE},{NATURE_PROFESSIONNALISATION}",
                                "pays": "FR",
                                "range": f"{offset}-{end}",
                            },
                        )
                    except httpx.HTTPError:
                        break
                    last_call = time.time()

                    if resp.status_code == 401:
                        # Token expiré en cours de session → on force un refresh
                        _TOKEN_CACHE["expires_at"] = 0.0
                        token = _get_token(client)
                        auth_headers["Authorization"] = f"Bearer {token}"
                        continue
                    if resp.status_code not in (200, 206):
                        # 204 = no content, autres = erreur. On passe au mot-clé suivant.
                        break

                    payload = resp.json() if resp.text else {}
                    results = payload.get("resultats", [])
                    if not results:
                        break

                    for item in results:
                        offer_id = item.get("id")
                        if not offer_id or offer_id in seen_ids:
                            continue
                        seen_ids.add(offer_id)
                        raw = _parse_offer(item)
                        # Filtrage mots-clés IA/data (sur titre + description)
                        if not matches_keywords(raw.title, raw.description):
                            continue
                        offers.append(raw)
                        fetched_for_kw += 1

                    # Si moins de range_size offres dans la page, on a atteint la fin
                    if len(results) < range_size:
                        break

        return offers

    def fetch_detail(self, url: str) -> str | None:
        """Récupère la description complète d'une offre via l'API détail.

        Extrait l'ID FT depuis l'URL (suffixe de l'URL candidat) puis hit l'API.
        """
        offer_id = _extract_ft_id(url)
        if not offer_id:
            return None
        with httpx.Client(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
            token = _get_token(client)
            resp = client.get(
                DETAIL_URL.format(id=offer_id),
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            desc = data.get("description") or ""
            return desc if len(desc) > 200 else None


def _extract_ft_id(url: str) -> str | None:
    """Récupère l'ID France Travail depuis une URL d'offre.

    Patterns connus :
        https://candidat.francetravail.fr/offres/recherche/detail/{ID}
        https://candidat.pole-emploi.fr/offres/recherche/detail/{ID}
    """
    import re
    m = re.search(r"/(?:offres|recherche|detail)/(?:[^/]+/)*([0-9A-Z]+)", url, re.IGNORECASE)
    if m:
        return m.group(1)
    # Fallback : dernier segment de l'URL
    seg = url.rstrip("/").rsplit("/", 1)[-1]
    if seg and seg.isalnum():
        return seg
    return None
