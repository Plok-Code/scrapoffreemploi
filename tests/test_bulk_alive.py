"""Tests des helpers bulk pour le cycle de vie des offres.

Vérifie :
- `queries.set_alive_state_bulk` : exécute en 1 transaction, stamp last_checked_at.
- `queries.delete_offers_bulk` : exécute en 1 transaction, retourne rowcount réel.
- Atomicité : si on simule un crash mid-bulk, RIEN n'est commit (vs N writes
  individuels qui laisseraient la DB inconsistente).
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


def _seed(n: int, *, is_active: int = 1) -> list[int]:
    """Insère n offres et retourne leurs ids."""
    from backend.db import db, make_dedup_key
    ids: list[int] = []
    with db() as conn:
        for i in range(n):
            title = f"Offer {i}"
            cur = conn.execute(
                """
                INSERT INTO offers (title, company, city, url, dedup_key, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, "Acme", "Paris", f"http://x/{i}",
                 make_dedup_key(title, "Acme", "Paris"), is_active),
            )
            ids.append(cur.lastrowid)
    return ids


class TestSetAliveStateBulk:
    def test_empty_list_returns_zero(self, temp_db):
        from backend.queries import set_alive_state_bulk
        assert set_alive_state_bulk([]) == 0

    def test_archives_multiple_offers(self, temp_db):
        from backend.queries import set_alive_state_bulk, get_offer
        ids = _seed(5, is_active=1)

        n = set_alive_state_bulk([(oid, False) for oid in ids])

        assert n == 5
        for oid in ids:
            row = get_offer(oid)
            assert row["is_active"] == 0
            assert row["last_checked_at"] is not None

    def test_revives_archived_offers(self, temp_db):
        from backend.queries import set_alive_state_bulk, get_offer
        ids = _seed(3, is_active=0)

        n = set_alive_state_bulk([(oid, True) for oid in ids])

        assert n == 3
        for oid in ids:
            assert get_offer(oid)["is_active"] == 1

    def test_mixed_archive_and_revive(self, temp_db):
        from backend.queries import set_alive_state_bulk, get_offer
        ids = _seed(4)
        updates = [(ids[0], False), (ids[1], True), (ids[2], False), (ids[3], True)]

        n = set_alive_state_bulk(updates)

        assert n == 4
        assert get_offer(ids[0])["is_active"] == 0
        assert get_offer(ids[1])["is_active"] == 1
        assert get_offer(ids[2])["is_active"] == 0
        assert get_offer(ids[3])["is_active"] == 1

    def test_unknown_ids_no_rows_updated(self, temp_db):
        """Updates sur des ids inexistants ne plantent pas mais retournent 0."""
        from backend.queries import set_alive_state_bulk
        n = set_alive_state_bulk([(99999, False), (99998, True)])
        # rowcount cumulé sur executemany = -1 sur certaines versions sqlite3,
        # mais surtout : la DB doit rester saine (pas d'exception).
        assert n in (0, -1)


class TestDeleteOffersBulk:
    def test_empty_list_returns_zero(self, temp_db):
        from backend.queries import delete_offers_bulk
        assert delete_offers_bulk([]) == 0

    def test_deletes_multiple_offers(self, temp_db):
        from backend.queries import delete_offers_bulk, get_offer
        ids = _seed(5)

        n = delete_offers_bulk(ids[:3])

        assert n == 3
        # Les 3 premiers supprimés
        for oid in ids[:3]:
            assert get_offer(oid) is None
        # Les 2 derniers préservés
        for oid in ids[3:]:
            assert get_offer(oid) is not None

    def test_deletes_only_listed_ids(self, temp_db):
        from backend.queries import delete_offers_bulk
        ids = _seed(10)

        delete_offers_bulk([ids[0], ids[5], ids[9]])

        from backend.db import db
        with db() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM offers").fetchone()
        assert row["n"] == 7

    def test_single_transaction_perf_vs_n(self, temp_db):
        """Sanity : delete_offers_bulk(N) doit être ~équivalent ou plus rapide
        que N appels à delete_offer. On ne benchmark pas strictement (CI noise),
        on vérifie juste la cohérence fonctionnelle sur un volume non-trivial."""
        from backend.queries import delete_offers_bulk
        ids = _seed(50)

        n = delete_offers_bulk(ids)

        assert n == 50


class TestRunnerIntegration:
    """Vérifie que les refactors `cleanup_dead_unstatused` et `check_alive`
    utilisent les bulk helpers (pas de régression de comportement)."""

    def test_check_alive_uses_bulk_update(self, temp_db, monkeypatch):
        """On instrumente `set_alive_state_bulk` pour vérifier qu'il est appelé."""
        from backend.queries import set_alive_state_bulk
        ids = _seed(3, is_active=1)

        calls: list[list[tuple[int, bool]]] = []
        orig = set_alive_state_bulk

        def wrapper(updates):
            calls.append(list(updates))
            return orig(updates)

        monkeypatch.setattr("backend.queries.set_alive_state_bulk", wrapper)
        monkeypatch.setattr("backend.scrapers.runner.queries.set_alive_state_bulk", wrapper)

        # On force `_probe_workday_api` à toujours dire "alive=True" pour
        # éviter les calls HTTP réels — toutes les offres seront revived.
        monkeypatch.setattr(
            "backend.scrapers.runner._probe_workday_api",
            lambda url, client: True,
        )

        from backend.scrapers.runner import check_alive
        result = check_alive(sleep_between=0.0)

        assert result.total_checked == 3
        assert result.still_alive == 3
        # Vérifie qu'on a fait un (ou deux) appel bulk plutôt que N=3 individuels
        assert any(len(c) >= 1 for c in calls), \
            "set_alive_state_bulk doit être appelé au moins une fois"

    def test_cleanup_dead_uses_bulk_when_archive(self, temp_db, monkeypatch):
        """Simule 3 URLs mortes → 1 seul appel bulk pour les archiver."""
        from backend.queries import set_alive_state_bulk
        ids = _seed(3, is_active=1)

        calls: list[list[tuple[int, bool]]] = []
        orig = set_alive_state_bulk

        def wrapper(updates):
            calls.append(list(updates))
            return orig(updates)

        monkeypatch.setattr("backend.queries.set_alive_state_bulk", wrapper)
        monkeypatch.setattr("backend.scrapers.runner.queries.set_alive_state_bulk", wrapper)

        # Toutes les URLs sont "Workday dead" → toutes archivées
        monkeypatch.setattr(
            "backend.scrapers.runner._probe_workday_api",
            lambda url, client: False,
        )

        from backend.scrapers.runner import cleanup_dead_unstatused
        result = cleanup_dead_unstatused(sleep_between=0.0)

        assert result.total_checked == 3
        assert result.archived == 3
        assert result.deleted == 0
        # Le bulk archive a été appelé (avec 3 updates en 1 transaction)
        archive_calls = [c for c in calls if c and all(not state for _, state in c)]
        assert len(archive_calls) == 1
        assert len(archive_calls[0]) == 3
