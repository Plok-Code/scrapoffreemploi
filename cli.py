"""CLI scrapoffreemploi.

Usage :
    python cli.py stats
    python cli.py export-batch [--only-unscored] [--limit N] [-o PATH]
    python cli.py apply-scores PATH
    python cli.py scrape [SOURCE]    # placeholder

Sur Windows, préfixer si caractères Unicode :
    $env:PYTHONIOENCODING="utf-8"; python cli.py stats
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend import matching, queries


def cmd_stats(_args: argparse.Namespace) -> int:
    stats = queries.get_stats()
    print(f"Total offres       : {stats['total']}")
    print(f"À postuler         : {stats['to_apply']}")
    print(f"Postulé            : {stats['applied']}")
    print(f"Entretien          : {stats['interviews']}")
    print(f"Refusé             : {stats['refused']}")
    print(f"Top fit (80+)      : {stats['top_fit']}")
    print(f"Bon fit (60-79)    : {stats['bon_fit']}")
    print(f"Sans score         : {stats['unscored']}")
    return 0


def cmd_export_batch(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    path = matching.export_batch_to_score(
        only_unscored=args.only_unscored,
        limit=args.limit,
        output_path=output,
    )
    import json
    count = json.loads(path.read_text(encoding="utf-8"))["count"]
    print(f"Batch écrit : {path}")
    print(f"  Offres : {count}")
    if count > 0:
        print()
        print("Prochaine étape :")
        print(f"  Dans le chat Claude : 'score le batch {path.name}'")
        print(f"  Puis : python cli.py apply-scores data/batches/{path.stem.replace('_to_score', '_scores')}.json")
    return 0


def cmd_apply_scores(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"ERREUR : fichier introuvable : {path}", file=sys.stderr)
        return 1
    try:
        updated = matching.apply_scores_from_file(path)
    except ValueError as e:
        print(f"ERREUR de format : {e}", file=sys.stderr)
        return 1
    print(f"Scores appliqués : {updated} offres mises à jour.")
    return 0


def cmd_scrape(args: argparse.Namespace) -> int:
    from backend.scrapers.registry import list_scrapers
    from backend.scrapers.runner import run_scrape

    source = args.source
    if not source:
        print(f"Sources disponibles : {', '.join(list_scrapers())}")
        print("Usage : python cli.py scrape <source> [--max-pages N]")
        return 1
    print(f"Scraping de '{source}' (max-pages={args.max_pages})...")
    try:
        result = run_scrape(source, max_pages=args.max_pages)
    except KeyError as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        return 1
    print(f"  Fetched   : {result.total_fetched}")
    print(f"  Nouvelles : {result.total_new}")
    print(f"  Doublons  : {result.total_duplicates}")
    if result.batch_file:
        print(f"  Batch     : {result.batch_file}")
        print()
        print("Prochaine étape :")
        print(f"  Dans le chat : 'score le batch {result.batch_file.split('/')[-1].split(chr(92))[-1]}'")
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    from backend.scrapers.runner import enrich_descriptions
    print(f"Enrichissement des descriptions (source={args.source or 'toutes'}, limit={args.limit or 'none'})...")
    result = enrich_descriptions(source=args.source, limit=args.limit, sleep_between=args.sleep)
    print(f"  Candidats     : {result.total_candidates}")
    print(f"  Enrichies     : {result.updated}")
    print(f"  Échecs/vides  : {result.failed}")
    print(f"  Source inconnue : {result.skipped_no_scraper}")
    return 0


def cmd_check_alive(args: argparse.Namespace) -> int:
    from backend.scrapers.runner import check_alive
    print(
        f"Vérification des URLs (min_score={args.min_score or 'aucun'}, "
        f"limit={args.limit or 'none'})..."
    )
    result = check_alive(
        min_score=args.min_score,
        limit=args.limit,
        sleep_between=args.sleep,
    )
    print(f"  Vérifiées             : {result.total_checked}")
    print(f"  Toujours en ligne     : {result.still_alive}")
    print(f"  Archivées HTTP 404/410: {result.archived_http}")
    print(f"  Archivées soft-404    : {result.archived_soft}  (HTTP 200 mais 'offre supprimée')")
    print(f"  Non concluant         : {result.inconclusive}  (403 anti-bot / timeout)")
    return 0


def cmd_list_batches(_args: argparse.Namespace) -> int:
    batches = matching.list_batches()
    score_files = matching.list_score_files()
    print("Batches à scorer :")
    for p in batches:
        print(f"  {p}")
    if not batches:
        print("  (aucun)")
    print()
    print("Fichiers de scores reçus :")
    for p in score_files:
        print(f"  {p}")
    if not score_files:
        print("  (aucun)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="CLI scrapoffreemploi : stats, batches de scoring, scraping.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # stats
    p_stats = sub.add_parser("stats", help="Affiche les KPI de la base.")
    p_stats.set_defaults(func=cmd_stats)

    # export-batch
    p_export = sub.add_parser(
        "export-batch",
        help="Exporte les offres à scorer dans un JSON pour le chat Claude.",
    )
    p_export.add_argument(
        "--only-unscored",
        action="store_true",
        default=True,
        help="N'exporter que les offres sans score (défaut: True).",
    )
    p_export.add_argument(
        "--all",
        dest="only_unscored",
        action="store_false",
        help="Exporter toutes les offres (annule --only-unscored).",
    )
    p_export.add_argument("--limit", type=int, default=None, help="Nombre max d'offres.")
    p_export.add_argument("-o", "--output", type=str, default=None, help="Chemin de sortie.")
    p_export.set_defaults(func=cmd_export_batch)

    # apply-scores
    p_apply = sub.add_parser(
        "apply-scores",
        help="Importe les scores depuis un JSON produit par Claude dans le chat.",
    )
    p_apply.add_argument("path", help="Chemin vers le fichier _scores.json")
    p_apply.set_defaults(func=cmd_apply_scores)

    # scrape
    p_scrape = sub.add_parser("scrape", help="Lance le scraping d'une source (hellowork, ...).")
    p_scrape.add_argument("source", nargs="?", default=None, help="Source à scraper.")
    p_scrape.add_argument("--max-pages", type=int, default=3, help="Pages max par mot-clé (défaut 3).")
    p_scrape.set_defaults(func=cmd_scrape)

    # enrich-descriptions
    p_enrich = sub.add_parser(
        "enrich-descriptions",
        help="Re-fetch les descriptions manquantes pour les offres en DB (par source).",
    )
    p_enrich.add_argument("--source", default=None, help="Filtre source (ex hellowork). None = toutes.")
    p_enrich.add_argument("--limit", type=int, default=None, help="Nombre max d'offres à enrichir.")
    p_enrich.add_argument("--sleep", type=float, default=1.0, help="Pause entre 2 requêtes (sec).")
    p_enrich.set_defaults(func=cmd_enrich)

    # check-alive
    p_alive = sub.add_parser(
        "check-alive",
        help="Ping chaque URL et marque archivées (is_active=0) les 404/410.",
    )
    p_alive.add_argument("--min-score", type=int, default=None, help="Ne checker que les offres avec score >= N.")
    p_alive.add_argument("--limit", type=int, default=None, help="Max d'offres à pinguer.")
    p_alive.add_argument("--sleep", type=float, default=0.8, help="Pause entre 2 requêtes (sec).")
    p_alive.set_defaults(func=cmd_check_alive)

    # list-batches
    p_list = sub.add_parser("list-batches", help="Liste les batches générés et les scores reçus.")
    p_list.set_defaults(func=cmd_list_batches)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
