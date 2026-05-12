"""Helper Playwright avec contexte persistant.

Le `user_data_dir` est dans `data/.playwright_profile/` (gitignored car `data/` l'est déjà).
Les cookies/sessions de login (LinkedIn Premium notamment) sont conservés entre runs.

Usage :
    from backend.scrapers._playwright import persistent_browser

    with persistent_browser(headless=True) as ctx:
        page = ctx.new_page()
        page.goto("https://www.linkedin.com/jobs/view/...")
        ...
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PROFILE_DIR = ROOT / "data" / ".playwright_profile"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


@contextmanager
def persistent_browser(
    *,
    headless: bool = True,
    slow_mo: int = 0,
    user_data_dir: Path | None = None,
):
    """Context manager pour un Chromium avec profil persistant.

    Args:
        headless: True (défaut) = browser en background. False = visible (pour debug/login).
        slow_mo: ms de pause entre actions (utile en debug).
        user_data_dir: override du profil par défaut.
    """
    from playwright.sync_api import sync_playwright

    profile = user_data_dir or PROFILE_DIR
    profile.mkdir(parents=True, exist_ok=True)

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
