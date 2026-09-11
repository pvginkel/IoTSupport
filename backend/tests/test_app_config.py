"""Tests for loading IoT-specific settings from the environment."""

import tempfile
from pathlib import Path

import pytest

from app.app_config import AppEnvironment, AppSettings


class TestThumbnailStoragePath:
    """THUMBNAIL_STORAGE_PATH -> AppSettings.thumbnail_storage_path."""

    def test_defaults_to_temp_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Given no THUMBNAIL_STORAGE_PATH, the cache lives in the OS temp dir."""
        monkeypatch.delenv("THUMBNAIL_STORAGE_PATH", raising=False)

        # Skip backend/.env so a developer's local value cannot leak in
        settings = AppSettings.load(env=AppEnvironment(_env_file=None))

        assert settings.thumbnail_storage_path == Path(tempfile.gettempdir()) / "iotsupport-thumbnails"

    def test_env_var_reaches_settings(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Given THUMBNAIL_STORAGE_PATH, its value becomes thumbnail_storage_path."""
        monkeypatch.setenv("THUMBNAIL_STORAGE_PATH", str(tmp_path / "thumbnails"))

        settings = AppSettings.load(env=AppEnvironment(_env_file=None))

        assert settings.thumbnail_storage_path == tmp_path / "thumbnails"
