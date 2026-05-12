"""Helper Playwright avec contexte persistant.

Le `user_data_dir` est dans `data/.playwright_profile/` (gitignored car `data/` l'est déjà).
Les cookies/sessions de login (LinkedIn Premium notamment) sont conservés entre runs.

Lock guard : Chromium verrouille le `user_data_dir` quand il l'utilise. Si 2 process
essaient d'ouvrir le même profil simultanément (ex : double-clic sur "Scraper"),
Chromium crash bas niveau. Pour éviter ça, on check la présence du `SingletonLock`
avant `launch_persistent_context` et on raise une exception claire.

Usage :
    from backend.scrapers._playwright import persistent_browser, PlaywrightProfileLocked

    try:
        with persistent_browser(headless=True) as ctx:
            page = ctx.new_page()
            ...
    except PlaywrightProfileLocked:
        # un autre scrape utilise déjà le profil, attendre ou abandonner
        ...
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path

from backend._logging import logger

ROOT = Path(__file__).resolve().parent.parent.parent
PROFILE_DIR = ROOT / "data" / ".playwright_profile"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


class PlaywrightProfileLocked(RuntimeError):
    """Levée quand le user_data_dir Chromium est déjà verrouillé par un autre process."""


def _is_profile_locked(profile_dir: Path) -> bool:
    """Détecte si Chromium a déjà ce profil ouvert (lock files présents).

    Chromium pose typiquement plusieurs fichiers de lock :
    - SingletonLock (lien symbolique Linux/Mac, fichier Windows)
    - SingletonCookie
    - SingletonSocket
    - lockfile (Windows)
    """
    if not profile_dir.exists():
        return False
    for lock_name in ("SingletonLock", "lockfile", "SingletonSocket"):
        if (profile_dir / lock_name).exists():
            return True
    return False


@contextmanager
def persistent_browser(
    *,
    headless: bool = True,
    slow_mo: int = 0,
    user_data_dir: Path | None = None,
    wait_for_lock_release: float = 0.0,
):
    """Context manager pour un Chromium avec profil persistant + lock guard.

    Args:
        headless: True (défaut) = browser en background. False = visible (debug/login).
        slow_mo: ms de pause entre actions (utile en debug).
        user_data_dir: override du profil par défaut.
        wait_for_lock_release: si > 0, attend jusqu'à N secondes que le lock se libère
            avant de raise `PlaywrightProfileLocked`. Si 0 (défaut), raise immédiat.

    Raises:
        PlaywrightProfileLocked: si un autre Chromium utilise déjà ce profil.
    """
    from playwright.sync_api import sync_playwright

    profile = user_data_dir or PROFILE_DIR
    profile.mkdir(parents=True, exist_ok=True)

    # Lock guard : check si déjà ouvert ailleurs
    if _is_profile_locked(profile):
        if wait_for_lock_release > 0:
            logger.info(
                "Profil Playwright verrouillé, attente jusqu'à {s}s...",
                s=wait_for_lock_release,
            )
            start = time.time()
            while _is_profile_locked(profile) and (time.time() - start) < wait_for_lock_release:
                time.sleep(0.5)
        if _is_profile_locked(profile):
            logger.error(
                "PlaywrightProfileLocked : {dir} est déjà utilisé par un autre process. "
                "Vérifie qu'aucun Chromium / scrape n'est en cours, sinon supprime manuellement "
                "les fichiers SingletonLock/lockfile dans ce dossier.",
                dir=profile,
            )
            raise PlaywrightProfileLocked(
                f"Profil Playwright {profile} déjà verrouillé. "
                f"Un autre scrape utilise ce profil ?"
            )

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=headless,
            slow_mo=slow_mo,
            viewport={"width": 1280, "height": 800},
            user_agent=DEFAULT_USER_AGENT,
            locale="fr-FR",
            timezone_id="Europe/Paris",
            args=[
                "--disable-blink-features=AutomationControlled",  # réduit la détection bot
                "--no-default-browser-check",
            ],
        )
        try:
            yield ctx
        finally:
            ctx.close()
