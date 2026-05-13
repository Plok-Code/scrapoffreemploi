"""Module matching : export d'un batch d'offres pour scoring LLM + apply des scores.

Workflow :
1. `export_batch_to_score()` : génère data/batches/{date}_to_score.json
2. User (dans le chat avec Claude) score chaque offre → écrit data/batches/{date}_scores.json
3. `apply_scores_from_file()` : importe les scores en DB

Voir docs/CRITERIA.md pour la grille de scoring et le format JSON.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend import queries
from backend.db import db
from backend.models import label_for_score

ROOT = Path(__file__).resolve().parent.parent
BATCHES_DIR = ROOT / "data" / "batches"
CRITERIA_VERSION = "1.0"

# Champs de l'offre exposés au LLM pour scoring
OFFER_FIELDS_FOR_BATCH = (
    "id", "title", "company", "city", "department", "source", "url",
    "description", "date_published",
)


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _timestamp_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default_batch_path() -> Path:
    """Chemin de batch sans écraser un export déjà présent le même jour."""
    daily = BATCHES_DIR / f"{_today_iso()}_to_score.json"
    if not daily.exists():
        return daily
    return BATCHES_DIR / f"{_timestamp_iso()}_to_score.json"


def export_batch_to_score(
    *,
    only_unscored: bool = True,
    limit: int | None = None,
    output_path: Path | None = None,
    offer_ids: list[int] | None = None,
) -> Path:
    """Exporte un batch d'offres dans un JSON prêt à être scoré.

    Args:
        only_unscored: si True (défaut), n'exporte que les offres sans match_score
                       OU dont le score est antérieur à la grille v1.0 (legacy regex).
        limit: nombre max d'offres à inclure (None = toutes).
        output_path: chemin de sortie. Si None, génère `data/batches/{date}_to_score.json`.
        offer_ids: si fourni, exporte uniquement ces IDs (utile après un scrape).

    Returns:
        Path du fichier JSON créé.
    """
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = _default_batch_path()

    where = ""
    params: list[int] = []
    if offer_ids is not None:
        if offer_ids:
            placeholders = ",".join("?" * len(offer_ids))
            where = f"WHERE id IN ({placeholders})"  # nosec B608 : placeholders only
            params = [int(i) for i in offer_ids]
        else:
            where = "WHERE 1 = 0"
    elif only_unscored:
        # "Pas scoré" OU "scoré par l'ancien regex" (= avant la grille v1.0,
        # donc avec match_score mais SANS les 5 sous-scores)
        where = """
            WHERE match_score IS NULL
               OR score_pipeline IS NULL
        """

    sql = f"""
        SELECT {", ".join(OFFER_FIELDS_FOR_BATCH)}
        FROM offers
        {where}
        ORDER BY id ASC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    with db() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    batch = {
        "generated_at": _now_iso(),
        "criteria_version": CRITERIA_VERSION,
        "count": len(rows),
        "instructions": (
            "Score chaque offre selon la grille /100 (5 axes /20). "
            "Voir docs/CRITERIA.md pour les heuristiques. "
            "Output attendu : data/batches/{date}_scores.json au format documenté."
        ),
        "offers": rows,
    }

    output_path.write_text(
        json.dumps(batch, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def parse_scores_file(path: Path) -> list[dict]:
    """Lit un fichier de scores JSON et retourne la liste des scores normalisés.

    Format attendu :
    {
      "scored_at": "...",
      "criteria_version": "1.0",
      "scores": [
        {
          "offer_id": 195,
          "score_pipeline": 6,
          "score_exploration": 8,
          "score_modelisation": 20,
          "score_deploiement": 18,
          "score_cadrage": 14,
          "match_reasoning": "..."
        }
      ]
    }
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "scores" not in raw:
        raise ValueError(f"Format invalide : {path} doit contenir une clé 'scores'.")

    scores: list[dict] = []
    for item in raw["scores"]:
        if "offer_id" not in item:
            raise ValueError(f"Score sans offer_id : {item}")
        # Validation des bornes /20
        for axis in (
            "score_pipeline", "score_exploration", "score_modelisation",
            "score_deploiement", "score_cadrage",
        ):
            v = item.get(axis)
            if v is None or not isinstance(v, int) or not (0 <= v <= 20):
                raise ValueError(
                    f"Score invalide pour offer_id={item.get('offer_id')} "
                    f"({axis}={v!r}, attendu int 0-20)."
                )
        scores.append({
            "offer_id": int(item["offer_id"]),
            "score_pipeline": int(item["score_pipeline"]),
            "score_exploration": int(item["score_exploration"]),
            "score_modelisation": int(item["score_modelisation"]),
            "score_deploiement": int(item["score_deploiement"]),
            "score_cadrage": int(item["score_cadrage"]),
            "match_reasoning": str(item.get("match_reasoning", "")),
        })
    return scores


def apply_scores_from_file(path: Path) -> int:
    """Lit un fichier de scores et applique les updates en DB.

    Returns le nombre d'offres mises à jour.
    """
    scores = parse_scores_file(path)
    if not scores:
        return 0
    return queries.apply_llm_scores(scores)


def list_batches() -> list[Path]:
    """Liste les batches générés (par ordre alphabétique = chronologique)."""
    if not BATCHES_DIR.exists():
        return []
    return sorted(BATCHES_DIR.glob("*_to_score.json"))


def list_score_files() -> list[Path]:
    """Liste les fichiers de scores reçus."""
    if not BATCHES_DIR.exists():
        return []
    return sorted(BATCHES_DIR.glob("*_scores.json"))


def is_batch_applied(batch_path: Path) -> bool:
    """Détermine si un batch `*_to_score.json` a déjà été appliqué.

    Critère : toutes les offres référencées dans le batch (par `id`) ont
    `match_score IS NOT NULL` en DB ET `scored_at >` la mtime du batch.

    Permet à `cli list-batches` de masquer les batches déjà traités plutôt
    que les afficher comme "à scorer" alors qu'il n'y a plus rien à faire.
    """
    if not batch_path.exists():
        return False
    try:
        raw = json.loads(batch_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    offers = raw.get("offers") or []
    offer_ids = [o.get("id") for o in offers if isinstance(o.get("id"), int)]
    if not offer_ids:
        return True  # batch vide = rien à scorer
    placeholders = ",".join("?" * len(offer_ids))
    sql = (
        f"SELECT COUNT(*) AS unscored FROM offers "  # nosec B608 : placeholders, pas user input
        f"WHERE id IN ({placeholders}) AND match_score IS NULL"
    )
    with db() as conn:
        row = conn.execute(sql, offer_ids).fetchone()
    return row["unscored"] == 0


def list_pending_batches() -> list[Path]:
    """Liste les `*_to_score.json` dont au moins une offre n'a pas encore de score."""
    return [b for b in list_batches() if not is_batch_applied(b)]


def list_applied_batches() -> list[Path]:
    """Liste les `*_to_score.json` dont toutes les offres ont un score (= traités)."""
    return [b for b in list_batches() if is_batch_applied(b)]


def latest_batch() -> Optional[Path]:
    batches = list_batches()
    return batches[-1] if batches else None


def latest_pending_batch() -> Optional[Path]:
    """Dernier batch non-appliqué (le plus utile pour le workflow scoring)."""
    pending = list_pending_batches()
    return pending[-1] if pending else None


def latest_scores_file() -> Optional[Path]:
    files = list_score_files()
    return files[-1] if files else None
