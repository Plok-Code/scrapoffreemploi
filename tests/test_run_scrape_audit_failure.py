"""Test : `run_scrape` doit enregistrer dans `scrape_runs` même en cas d'échec.

Audit user (19 mai 2026, 3e passe) : si `scraper.fetch_list()` raise, l'ancien
code passait directement à l'exception sans appeler `record_scrape_run`.
Conséquence : table `scrape_runs` vide alors que l'utilisateur a déclenché
un scrape — audit historique incomplet.

Fix : try/finally autour du bloc scrape, `record_scrape_run` toujours appelé
avec `error=str(e)` en cas d'échec.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.db.DB_PATH", db_file)
    from backend.db import init_schema
    init_schema()
    yield db_file


def _count_scrape_runs() -> tuple[int, list[dict]]:
    from backend.db import db
    with db() as conn:
        rows = conn.execute(
            "SELECT sources, total_fetched, total_new, total_duplicates, error "
            "FROM scrape_runs ORDER BY id"
        ).fetchall()
    return len(rows), [dict(r) for r in rows]


class TestRunScrapeFailureIsAudited:
    def _patch_scraper(self, monkeypatch, scraper_factory):
        """Helper : remplace `get_scraper` par une factory qui retourne un mock."""
        monkeypatch.setattr(
            "backend.scrapers.runner.get_scraper",
            lambda source: scraper_factory(),
        )

    def test_fetch_list_failure_records_run_with_error(self, temp_db, monkeypatch):
        class FailingScraper:
            source_name = "test_fail"

            def fetch_list(self, **kwargs):
                raise RuntimeError("simulated network timeout")

            def fetch_detail(self, url):  # pragma: no cover
                return None

        self._patch_scraper(monkeypatch, FailingScraper)

        from backend.scrapers.runner import run_scrape
        with pytest.raises(RuntimeError, match="simulated network timeout"):
            run_scrape("test_fail", generate_batch=False)

        # Audit : la ligne doit être présente dans scrape_runs avec error remplie
        n, rows = _count_scrape_runs()
        assert n == 1, f"Attendu 1 audit row, vu {n}"
        assert rows[0]["sources"] == "test_fail"
        assert rows[0]["total_fetched"] == 0
        assert rows[0]["total_new"] == 0
        assert "simulated network timeout" in (rows[0]["error"] or "")

    def test_unknown_source_does_not_pollute_scrape_runs(self, temp_db, monkeypatch):
        """`get_scraper` raise KeyError AVANT toute tentative de scrape.
        On NE doit PAS polluer scrape_runs avec une config error."""
        # Pas de patch : la registry vraie est utilisée → "monster" inconnu
        from backend.scrapers.runner import run_scrape
        with pytest.raises(KeyError):
            run_scrape("monster", generate_batch=False)

        n, _ = _count_scrape_runs()
        assert n == 0, "KeyError source inconnue ne doit PAS écrire dans scrape_runs"

    def test_success_path_records_run_without_error(self, temp_db, monkeypatch):
        """Sanity : le chemin OK enregistre toujours, avec error=NULL."""
        from backend.scrapers.base import RawOffer

        class OkScraper:
            source_name = "test_ok"

            def fetch_list(self, **kwargs):
                return [
                    RawOffer(
                        title="ML Engineer alternance",
                        company="Acme",
                        city="Paris",
                        url="http://x/1",
                        source="test_ok",
                    ),
                ]

            def fetch_detail(self, url):  # pragma: no cover
                return None

        self._patch_scraper(monkeypatch, OkScraper)

        from backend.scrapers.runner import run_scrape
        result = run_scrape("test_ok", generate_batch=False)

        assert result.total_new == 1
        n, rows = _count_scrape_runs()
        assert n == 1
        assert rows[0]["sources"] == "test_ok"
        assert rows[0]["total_fetched"] == 1
        assert rows[0]["total_new"] == 1
        assert rows[0]["error"] is None

    def test_partial_failure_preserves_partial_counts(self, temp_db, monkeypatch):
        """Si fetch_list OK mais l'étape batch crashe, on enregistre les
        compteurs partiels (fetched, new, dup) + error."""
        from backend.scrapers.base import RawOffer

        class OkScraperBatchKO:
            source_name = "test_partial"

            def fetch_list(self, **kwargs):
                return [
                    RawOffer(
                        title="Partial alternance ML",
                        company="Beta",
                        city="Lyon",
                        url="http://x/partial",
                        source="test_partial",
                    ),
                ]

            def fetch_detail(self, url):  # pragma: no cover
                return None

        self._patch_scraper(monkeypatch, OkScraperBatchKO)
        # Patch export_batch_to_score pour qu'il crashe
        import backend.matching
        monkeypatch.setattr(
            backend.matching,
            "export_batch_to_score",
            lambda **kw: (_ for _ in ()).throw(RuntimeError("disk full")),
        )

        from backend.scrapers.runner import run_scrape
        with pytest.raises(RuntimeError, match="disk full"):
            run_scrape("test_partial", generate_batch=True)

        n, rows = _count_scrape_runs()
        assert n == 1
        # L'insert a réussi (1 fetched, 1 new) ; le crash est sur la
        # génération du batch → compteurs préservés.
        assert rows[0]["total_fetched"] == 1
        assert rows[0]["total_new"] == 1
        assert "disk full" in (rows[0]["error"] or "")
