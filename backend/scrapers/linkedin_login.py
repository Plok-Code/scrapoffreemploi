"""Script standalone pour se connecter à LinkedIn une seule fois.

Lance :
    python -m backend.scrapers.linkedin_login

Chromium s'ouvre en mode visible. Connecte-toi avec ton compte (Premium si possible).
Une fois loggué, reviens dans le terminal et appuie sur Entrée.
Les cookies sont sauvegardés dans `data/.playwright_profile/` et seront réutilisés
automatiquement par le scraper LinkedIn (Playwright).
"""
from __future__ import annotations

import sys

from backend.scrapers._playwright import PROFILE_DIR, persistent_browser


def main() -> int:
    print(f"Profile Playwright : {PROFILE_DIR}")
    print()
    print("== Connexion LinkedIn ==")
    print("1. Chromium va s'ouvrir sur la page LinkedIn login.")
    print("2. Connecte-toi avec ton compte (Premium si possible).")
    print("3. Une fois sur la home LinkedIn loggué, REVIENS ICI et appuie sur Entrée.")
    print()
    try:
        with persistent_browser(headless=False, slow_mo=30) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            input(">>> Quand tu es loggué, appuie sur Entrée ici pour finaliser et quitter Chromium... ")
            # Verification rapide : check si on a une cookie 'li_at' (auth token LinkedIn)
            cookies = ctx.cookies("https://www.linkedin.com")
            has_auth = any(c["name"] == "li_at" for c in cookies)
            if has_auth:
                print("OK : cookie 'li_at' detecte. Tu es bien loggue.")
            else:
                print("WARN : pas de cookie 'li_at' detecte. Tu n'es peut-etre pas loggue.")
        print()
        print(f"Profile sauve dans : {PROFILE_DIR}")
        print("Tu peux maintenant lancer :")
        print("  python cli.py enrich-descriptions --source linkedin")
        return 0
    except KeyboardInterrupt:
        print("\nAnnule.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
