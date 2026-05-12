"""Migration one-shot : recalcule les `offers.dedup_key` pour inclure la ville.

Bug fixé : `make_dedup_key` ne prenait pas la ville en compte. Conséquence : une
même offre Capgemini "AI Engineer" à Paris ET à Toulouse était considérée comme
doublon → la 2e était jetée silencieusement.

Après ce script :
- Tous les `offers.dedup_key` existants sont recalculés avec (title, company, city)
- Les futurs INSERT utilisent automatiquement la nouvelle formule (`insert_offer`)

Note : SQLite ne lève pas d'erreur si plusieurs lignes finissent avec le même
dedup_key (l'index est sur `idx_offers_dedup_key` non-UNIQUE). Mais en cas de
doublon vrai (par ex. import xlsx + scrape), la dédup à l'insert va consolider.
"""
from __future__ import annotations

from backend._logging import init_logging, logger
from backend.db import db, make_dedup_key


def recompute_dedup_keys() -> dict:
    init_logging()
    updated = 0
    unchanged = 0
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, company, city, dedup_key FROM offers"
        ).fetchall()
        for r in rows:
            new_key = make_dedup_key(r["title"], r["company"], r["city"])
            if new_key != r["dedup_key"]:
                conn.execute(
                    "UPDATE offers SET dedup_key = :k WHERE id = :id",
                    {"k": new_key, "id": r["id"]},
                )
                updated += 1
            else:
                unchanged += 1
    result = {"total": len(rows), "updated": updated, "unchanged": unchanged}
    logger.info("Recompute dedup_keys : {r}", r=result)
    return result


if __name__ == "__main__":
    r = recompute_dedup_keys()
    print(f"Recompute dedup_keys : {r}")
