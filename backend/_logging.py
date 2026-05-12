"""Logging centralisé pour scrapoffreemploi.

Utilise `loguru` pour un logging structuré, à la fois console (DEBUG en dev,
INFO en prod) et fichiers rotatifs sous `data/logs/`.

Usage :
    from backend._logging import logger
    logger.info("Scrape FT démarré : {keyword}", keyword=kw)
    logger.warning("URL non joignable : {url}", url=u)
    logger.error("Token FT expiré, retry échoué : {err}", err=str(e))

Configuration (appelée 1 fois au démarrage uvicorn dans `main.py`) :
    from backend._logging import init_logging
    init_logging()

Niveaux :
- DEBUG : détails verbeux (chaque requête HTTP)
- INFO : événements normaux (scrape démarré, X offres insérées)
- WARNING : anomalie non bloquante (URL morte, soft-404, doublon ignoré)
- ERROR : échec d'une opération (timeout après retries, parsing impossible)
- CRITICAL : panne grave (DB inaccessible, OAuth FT KO)

Format :
    2026-05-12 21:30:15.123 | INFO    | backend.scrapers.francetravail:fetch_list:142 |
    Scrape FT : 1070 offres fetched (15 nouvelles)
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

# Réexporte le logger global de loguru pour les imports
__all__ = ["logger", "init_logging"]


_INITIALIZED = False
ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "logs"


def init_logging(level: str = "INFO", quiet_console: bool = False) -> None:
    """Configure les sinks loguru (console + fichiers rotatifs).

    Idempotent : peut être appelé plusieurs fois sans dupliquer les handlers.

    Args:
        level: niveau minimum pour la console (DEBUG/INFO/WARNING/ERROR).
        quiet_console: si True, supprime le sink console (utile pour les tests).

    Fichiers générés (dans `data/logs/`) :
    - `app.log` : tous les events INFO+ (rotation 10 MB, 7 fichiers gardés)
    - `errors.log` : ERROR+ uniquement (rotation 5 MB, 30 fichiers gardés)
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Reset des handlers par défaut de loguru (sinon stderr est duplicate)
    logger.remove()

    # Sink 1 : console (niveau configurable, format coloré)
    if not quiet_console:
        logger.add(
            sys.stderr,
            level=level,
            colorize=True,
            format=(
                "<green>{time:HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
        )

    # Sink 2 : fichier rotatif INFO+
    logger.add(
        LOG_DIR / "app.log",
        level="INFO",
        rotation="10 MB",         # nouveau fichier après 10 MB
        retention=7,              # garde 7 anciens fichiers max
        compression="gz",         # compresse les rotations
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
    )

    # Sink 3 : fichier d'erreurs uniquement (utile pour audit)
    logger.add(
        LOG_DIR / "errors.log",
        level="ERROR",
        rotation="5 MB",
        retention=30,
        compression="gz",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}\n"
            "{exception}"
        ),
        backtrace=True,
        diagnose=True,
    )

    _INITIALIZED = True
    logger.info("Logging initialisé : level={level}, logs dans {dir}", level=level, dir=LOG_DIR)
