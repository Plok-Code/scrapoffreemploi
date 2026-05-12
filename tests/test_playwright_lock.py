"""Tests du lock guard Playwright (`_is_profile_locked`)."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.scrapers._playwright import _is_profile_locked


class TestPlaywrightLockGuard:
    def test_empty_dir_not_locked(self, tmp_path: Path):
        """Profil vide / inexistant → pas locked."""
        assert _is_profile_locked(tmp_path) is False

    def test_nonexistent_path(self, tmp_path: Path):
        nonexistent = tmp_path / "does-not-exist"
        assert _is_profile_locked(nonexistent) is False

    def test_singleton_lock_present(self, tmp_path: Path):
        """Si SingletonLock existe → locked."""
        (tmp_path / "SingletonLock").touch()
        assert _is_profile_locked(tmp_path) is True

    def test_lockfile_present(self, tmp_path: Path):
        """Si lockfile (Windows) existe → locked."""
        (tmp_path / "lockfile").touch()
        assert _is_profile_locked(tmp_path) is True

    def test_singleton_socket_present(self, tmp_path: Path):
        """Si SingletonSocket existe → locked."""
        (tmp_path / "SingletonSocket").touch()
        assert _is_profile_locked(tmp_path) is True

    def test_only_other_files_not_locked(self, tmp_path: Path):
        """Si profil a juste des fichiers de cookies normaux → pas locked."""
        (tmp_path / "Default").mkdir()
        (tmp_path / "Default" / "Cookies").touch()
        (tmp_path / "Default" / "Preferences").touch()
        assert _is_profile_locked(tmp_path) is False
