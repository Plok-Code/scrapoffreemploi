"""Scoreur heuristique pour pré-classer les offres scrapées en masse.

Stratégie : compter les occurrences de mots-clés techniques par axe, capper à 20.
Le résultat sert de **pré-tri** pour identifier les offres prometteuses (>= 50)
qui méritent un scoring manuel précis dans le chat Claude.

Reasoning = "auto: heuristic v1" → identifiable, peut être ré-écrasé par un
scoring manuel ultérieur.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend import queries
from backend.db import db
from backend.models import label_for_score


# Mots-clés par axe avec poids. La présence (insensible casse) ajoute le poids.
# Capping à 20 max par axe.
_AXIS_KEYWORDS: dict[str, list[tuple[str, int]]] = {
    "pipeline": [
        (r"\bPySpark\b", 8), (r"\bSpark\b", 6),
        (r"\bAirbyte\b", 10), (r"\bKestra\b", 10),
        (r"\bKafka\b", 7), (r"\bSnowflake\b", 8),
        (r"\bdatalake\b|data\s+lake", 8), (r"\bETL\b|\bELT\b", 6),
        (r"\bAirflow\b", 7), (r"\bdbt\b", 6),
        (r"\bdata\s+engineer", 8), (r"data\s+pipeline", 7),
        (r"\bingestion\b", 6), (r"\bDatabricks\b", 9),
        (r"\bdata\s+warehouse\b", 6), (r"\bBigQuery\b", 6),
        (r"sources?\s+h[ée]t[ée]rog[èe]nes", 5),
        (r"data\s+preprocessing", 5),
    ],
    "exploration": [
        (r"\bPandas\b", 6), (r"\bNumpy\b", 5),
        (r"\bvisualisation\b|\bvisualization\b", 5),
        (r"data\s+viz", 5), (r"\bdashboard\b", 5),
        (r"\bPower\s+BI\b", 5), (r"\bTableau\b", 4),
        (r"analyse\s+statistique|stat\s+analysis", 6),
        (r"\bACP\b|\bPCA\b", 5), (r"\bA/B\s+test|AB\s+test", 5),
        (r"\bexploration\s+de?\s+donn[ée]es?", 5),
        (r"\banalyse\s+exploratoire\b|\bEDA\b", 6),
        (r"\bstatistiques?\s+descriptives?\b", 4),
        (r"\bdata\s+analyst\b", 5),
    ],
    "modelisation": [
        (r"\bdeep\s+learning\b|apprentissage\s+profond", 9),
        (r"\bmachine\s+learning\b|apprentissage\s+automatique", 7),
        (r"\bLLM\b|large\s+language\s+model", 10),
        (r"\bRAG\b|retrieval\s+augmented", 10),
        (r"\bGenAI\b|generative\s+AI|IA\s+g[ée]n[ée]rative", 9),
        (r"\bagent[ig]?\b\s*(?:IA|AI)?|agentic|agent[s]?\s+IA", 8),
        (r"\btransformer[s]?\b", 8), (r"\bBERT\b|\bGPT\b", 7),
        (r"\bPyTorch\b", 7), (r"\bTensorFlow\b", 7),
        (r"\bHugging\s*Face\b", 7), (r"\bsklearn\b|\bscikit-learn\b", 5),
        (r"\bNLP\b|natural\s+language|langage\s+naturel", 8),
        (r"computer\s+vision|vision\s+par\s+ordinateur", 8),
        (r"fine[\-\s]?tuning", 7),
        (r"\bdata\s+scientist\b", 6),
        (r"\bAI\s+engineer\b|\bML\s+engineer\b", 7),
        (r"recommendation\s+system|syst[èe]me\s+de\s+recommand", 7),
        (r"\bd[ée]tection\s+d[\'e]?\s*anomalies?\b", 6),
        (r"\bclassification\b|\br[ée]gression\b", 4),
        (r"\bsegmentation\b", 4),
        (r"\btime\s+series?\b|\bs[ée]ries?\s+temporelles?\b", 6),
    ],
    "deploiement": [
        (r"\bMLOps\b", 12), (r"\bMLflow\b", 9),
        (r"\bKubeflow\b", 9), (r"\bBentoML\b", 9),
        (r"\bDocker\b", 6), (r"\bKubernetes\b|\bk8s\b", 7),
        (r"\bFastAPI\b", 6), (r"\bFlask\b", 4),
        (r"\bCI/CD\b|CI\s+CD|GitLab\s+CI|GitHub\s+Actions", 7),
        (r"\bAWS\b|\bGCP\b|\bAzure\b", 5),
        (r"\bSageMaker\b|\bVertex\s+AI\b", 8),
        (r"model\s+monitoring|drift\s+detection|model\s+drift", 9),
        (r"\bdeployment\b|d[ée]ploiement\s+(?:de\s+)?mod[èe]les?", 7),
        (r"\bproduction\b\s+ML|industrialisation\s+ML", 8),
        (r"\bAPI\s+REST\b|\bendpoints?\s+REST\b", 5),
        (r"\bGenAI\b\s*Ops|LLMOps", 10),
    ],
    "cadrage": [
        (r"\bPytest\b", 6), (r"tests?\s+unitaires?", 5),
        (r"\bgreat[\-\s]?expectations?\b", 8),
        (r"\bagile\b|\bScrum\b", 4),
        (r"\bcadrage\b|\bspecif[a-z]+", 5),
        (r"\bgouvernance\b|gouvernance\s+IA", 6),
        (r"\bRGPD\b|\bGDPR\b", 5),
        (r"\b[Ll]ineage\b|data\s+lineage", 6),
        (r"\bdata\s+quality\b|qualit[ée]\s+de?\s+donn[ée]es?", 5),
        (r"documentation\s+technique|code\s+review", 4),
        (r"KPIs?\b|indicateurs?\s+(?:cl[ée]s)?", 4),
        (r"\bPOC\b|preuves?\s+de?\s+concept", 4),
        (r"\b[ée]thique?\s+IA|AI\s+ethics", 6),
    ],
}

# Pénalités appliquées au score TOTAL (pas par axe)
_PENALTIES = [
    # Stage = pas alternance — pénalité forte
    (r"\bstage\b(?!\s*/?\s*alternance)", -15, "stage (pas alternance)"),
    # Postes CDI/Senior/Confirmé — pas notre cible alternance étudiant
    (r"\b(?:Senior|Sr\.?)\b", -20, "senior"),
    (r"\bConfirm[ée]?\b", -18, "confirmé"),
    (r"\bTech\s+Lead\b", -18, "tech lead"),
    (r"\bLead\s+(?:Data|ML|AI)\b", -18, "lead data/ml/ai"),
    (r"\bManager\b", -15, "manager"),
    (r"\bArchitecte?\b", -12, "architecte"),
    (r"\bExpert\b(?!.{0,50}\balternance\b)", -12, "expert"),
    (r"\bDirecteur?\b|\bResponsable\b", -15, "directeur/responsable"),
    # BTS niveau bac+2 — penalité légère
    (r"\bBTS\s+SIO\b|\bBac\s*\+?\s*2\b\s+\(BTS", -8, "BTS bac+2"),
    (r"\bformation\s+(?:100\s*%\s*)?(?:à\s+)?distance\b", -5, "formation à distance"),
    # Pas d'alternance/apprentissage du tout dans le texte → pénalité (titre doit l'indiquer)
    # On vérifie via une logique custom plus bas car -X si NON MATCH
]

# Bonus : pour les vrais postes alternance avec niveau approprié
_BONUSES = [
    (r"\bBac\s*\+?\s*5\b|\bMaster\s+2?\b|\bMast[èe]re\b", 4, "bac+5"),
    (r"\balternance\b.*\b(?:AI|IA|ML|data)\s+engineer", 5, "ai engineer alternance"),
    (r"\b(?:alternant[\(e]?[s]?|apprenti[\(e]?[s]?)\b", 6, "alternant/apprenti explicite"),
    (r"\balternance\b", 3, "alternance mot"),
]

# Mots qui DOIVENT être présents quelque part (titre + desc), sinon pénalité
_MUST_HAVE_ALTERNANCE = re.compile(
    r"\balternan[ct]e?[s]?\b|\bapprenti[\(e]?[s]?\b|\bapprentissage\b"
    r"|\bcontrat\s+pro\b|\bprofessionnalisation\b",
    re.IGNORECASE,
)


@dataclass
class HeuristicResult:
    offer_id: int
    score_pipeline: int
    score_exploration: int
    score_modelisation: int
    score_deploiement: int
    score_cadrage: int
    total: int
    matched: list[str]


def _score_axis(text: str, keywords: list[tuple[str, int]]) -> tuple[int, list[str]]:
    """Score un axe donné en sommant les poids des mots-clés trouvés, cap à 20."""
    s = 0
    hits: list[str] = []
    for pattern, weight in keywords:
        if re.search(pattern, text, re.IGNORECASE):
            s += weight
            hits.append(pattern)
    return min(s, 20), hits


def score_offer_heuristic(title: str, description: str | None) -> HeuristicResult:
    """Calcule un score heuristique pour une offre.

    Retourne un HeuristicResult avec scores par axe (cappés à 20) et total.
    """
    text = f"{title or ''}\n{description or ''}"
    all_hits: list[str] = []

    axis_scores: dict[str, int] = {}
    for axis, kws in _AXIS_KEYWORDS.items():
        s, hits = _score_axis(text, kws)
        axis_scores[axis] = s
        all_hits.extend(hits)

    total = sum(axis_scores.values())

    # Bonuses / pénalités sur le total
    title_text = title or ""
    for pat, weight, _ in _PENALTIES:
        # Les pénalités CDI/Senior/etc se basent surtout sur le TITRE (plus discriminant)
        if re.search(pat, title_text, re.IGNORECASE):
            total += weight  # weight négatif
    for pat, weight, _ in _BONUSES:
        if re.search(pat, text, re.IGNORECASE):
            total += weight

    # Pénalité si "alternance/apprentissage" absent COMPLÈTEMENT du texte
    if not _MUST_HAVE_ALTERNANCE.search(text):
        total -= 25  # forte pénalité, probablement pas un poste alternance

    total = max(0, min(total, 100))

    # Re-distribution des bonus/pénalités proportionnellement aux axes (simple cap)
    # En réalité on garde les axis_scores tels quels et le total est ajusté.
    # Mais la DB attend total = somme des 5 axes. On normalise donc :
    sum_axes = sum(axis_scores.values()) or 1
    if total != sum_axes:
        factor = total / sum_axes
        for k in axis_scores:
            axis_scores[k] = max(0, min(int(axis_scores[k] * factor), 20))
        total = sum(axis_scores.values())

    return HeuristicResult(
        offer_id=0,  # set by caller
        score_pipeline=axis_scores["pipeline"],
        score_exploration=axis_scores["exploration"],
        score_modelisation=axis_scores["modelisation"],
        score_deploiement=axis_scores["deploiement"],
        score_cadrage=axis_scores["cadrage"],
        total=total,
        matched=all_hits,
    )


def apply_heuristic_to_unscored(
    *, limit: int | None = None, rescore_heuristic: bool = False
) -> dict:
    """Applique le scoring heuristique aux offres avec match_score IS NULL.

    Args:
        rescore_heuristic: si True, ré-écrase aussi les offres déjà scorées
            par une heuristique antérieure (`match_reasoning LIKE 'auto:heuristic%'`).

    Returns:
        Stats : total candidates, updated, distribution par label.
    """
    if rescore_heuristic:
        where = """
            (match_score IS NULL OR match_reasoning LIKE 'auto:heuristic%')
            AND (is_active IS NULL OR is_active = 1)
        """
    else:
        where = """
            match_score IS NULL
            AND (is_active IS NULL OR is_active = 1)
        """
    # `where` est une string littérale constante (if/else interne) et `limit`
    # passe par `int()`. Pas d'input user dans le SQL.
    sql = f"SELECT id, title, description FROM offers WHERE {where} ORDER BY id"  # nosec B608
    if limit:
        sql += f" LIMIT {int(limit)}"

    with db() as conn:
        candidates = [dict(r) for r in conn.execute(sql).fetchall()]

    scores: list[dict] = []
    for off in candidates:
        h = score_offer_heuristic(off["title"], off["description"])
        scores.append({
            "offer_id": off["id"],
            "score_pipeline": h.score_pipeline,
            "score_exploration": h.score_exploration,
            "score_modelisation": h.score_modelisation,
            "score_deploiement": h.score_deploiement,
            "score_cadrage": h.score_cadrage,
            "match_reasoning": f"auto:heuristic-v1 (total={h.total}, axes={h.score_pipeline}+{h.score_exploration}+{h.score_modelisation}+{h.score_deploiement}+{h.score_cadrage})",
        })

    updated = queries.apply_llm_scores(scores) if scores else 0

    # Distribution post-scoring
    with db() as conn:
        dist = {
            r["match_label"] or "sans label": r["n"]
            for r in conn.execute(
                """
                SELECT match_label, COUNT(*) AS n
                FROM offers
                WHERE match_reasoning LIKE 'auto:heuristic-v1%'
                  AND (is_active IS NULL OR is_active = 1)
                GROUP BY match_label
                """
            ).fetchall()
        }

    return {
        "total_candidates": len(candidates),
        "updated": updated,
        "distribution": dist,
    }


if __name__ == "__main__":
    import sys
    rescore = "--rescore" in sys.argv
    result = apply_heuristic_to_unscored(rescore_heuristic=rescore)
    mode = "rescore" if rescore else "initial"
    print(f"Heuristic scoring applied (mode={mode}):")
    print(f"  Candidates : {result['total_candidates']}")
    print(f"  Updated    : {result['updated']}")
    print(f"  Distribution : {result['distribution']}")
