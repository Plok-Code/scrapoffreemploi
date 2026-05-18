"""Migration one-shot : normalise les valeurs `offers.remote` invalides.

Audit a identifié 4 valeurs hors enum `VALID_REMOTE = ("Oui", "Non", "Hybride")` :
- "Télétravail partiel" → "Hybride"
- "Hybride" → "Hybride" (déjà OK, no-op)
- "Temps partiel" → None (n'a rien à voir avec le remote)
- "Sur site industriel" → "Non"

Mapping conservateur : on prefère mettre à None que d'inventer une valeur.
Idempotent.
"""
from __future__ import annotations

from backend._logging import init_logging, logger
from backend.db import db

# Mapping valeur libre → valeur normalisée (None pour effacement)
REMOTE_NORMALIZATION: dict[str, str | None] = {
    "Télétravail partiel": "Hybride",
    "Telework partiel": "Hybride",
    "Temps partiel": None,                # pas une info "remote", on efface
    "Sur site industriel": "Non",
    "Sur site": "Non",
    "Remote": "Oui",
    "Télétravail complet": "Oui",
    "Télétravail": "Oui",
}


def normalize_remote_values() -> dict:
    init_logging()
    updated = 0
    cleared = 0
    untouched = 0
    with db() as conn:
        rows = conn.execute(
            "SELECT id, remote FROM offers WHERE remote IS NOT NULL AND remote != ''"
        ).fetchall()
        for r in rows:
            current = r["remote"]
            if current in ("Oui", "Non", "Hybride"):
                untouched += 1
                continue
            if current in REMOTE_NORMALIZATION:
                new_val = REMOTE_NORMALIZATION[current]
                conn.execute(
                    "UPDATE offers SET remote = :v WHERE id = :id",
                    {"v": new_val, "id": r["id"]},
                )
                if new_val is None:
                    cleared += 1
                else:
                    updated += 1
            else:
                # Valeur libre inconnue : on log et on efface (safer que de garder
                # une valeur invalide qui casse l'UI de filtre)
                logger.warning(
                    "Remote value invalide effacée offer_id={oid} val={v!r}",
                    oid=r["id"], v=current,
                )
                conn.execute(
                    "UPDATE offers SET remote = NULL WHERE id = :id",
                    {"id": r["id"]},
                )
                cleared += 1
    result = {"untouched": untouched, "updated": updated, "cleared": cleared, "total": len(rows)}
    logger.info("Normalize remote : {r}", r=result)
    return result


if __name__ == "__main__":
    r = normalize_remote_values()
    print(f"Normalize remote : {r}")
