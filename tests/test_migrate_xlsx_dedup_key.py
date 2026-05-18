"""Test de la clé dédup générée par `migrate_xlsx`.

Bug audit (19 mai 2026, 3e passe) : `migrate_xlsx` appelait
`make_dedup_key(titre, entreprise)` SANS le 3e argument `city`. La clé
générée était `"titre|entreprise|"` (city vide) alors que les scrapers
HelloWork/WTTJ/FT produisent `"titre|entreprise|paris"`. Après réimport
xlsx, les futures inserts par scrape ne déduplicaient PAS contre l'offre
xlsx (clés différentes) → doublons silencieux.
"""
from __future__ import annotations


class TestMakeDedupKeyIncludesCity:
    """La clé doit varier selon la ville (bug critique : Paris vs Toulouse)."""

    def test_dedup_key_includes_city_normalized(self):
        from backend.db import make_dedup_key
        paris = make_dedup_key("AI Engineer", "Acme", "Paris")
        toulouse = make_dedup_key("AI Engineer", "Acme", "Toulouse")
        assert paris != toulouse
        assert paris.endswith("|paris")
        assert toulouse.endswith("|toulouse")

    def test_migrate_xlsx_signature_passes_3_args(self):
        """Garde-fou : le code source de migrate_xlsx doit appeler
        make_dedup_key avec EXACTEMENT 3 arguments (titre, entreprise, ville).
        Une régression à 2 args ferait passer ce test à False.
        """
        import inspect
        import re
        from backend import migrate_xlsx

        src = inspect.getsource(migrate_xlsx)
        # On cherche l'appel `make_dedup_key(...)` dans le source.
        # Acceptable :
        #   make_dedup_key(titre, entreprise, ville)
        #   make_dedup_key(titre, entreprise, ville=ville)
        # PAS acceptable :
        #   make_dedup_key(titre, entreprise)
        matches = re.findall(r"make_dedup_key\s*\(([^)]+)\)", src)
        assert matches, "Pas d'appel à make_dedup_key trouvé dans migrate_xlsx"
        for call_args in matches:
            # Comptage simple des virgules au top-level (pas de nesting ici)
            n_args = call_args.count(",") + 1
            assert n_args >= 3, (
                f"migrate_xlsx appelle make_dedup_key avec {n_args} arg(s) : "
                f"`make_dedup_key({call_args})`. La ville doit être incluse "
                f"(audit : sinon doublons xlsx vs scrapers)."
            )
