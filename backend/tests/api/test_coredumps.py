"""Tests for coredump admin API endpoints."""

from datetime import UTC, datetime

from flask import Flask
from flask.testing import FlaskClient

from app.config import Settings
from app.models.coredump import CoreDump, ParseStatus
from app.services.container import ServiceContainer
from tests.api.test_iot import create_test_device


def _create_coredump(
    app: Flask,
    container: ServiceContainer,
    device_id: int,
    device_key: str,
    filename: str = "coredump_test.dmp",
    chip: str = "esp32s3",
    firmware_version: str = "1.0.0",
    size: int = 256,
    parse_status: str = ParseStatus.PENDING.value,
    parsed_output: str | None = None,
    write_file: bool = True,
) -> CoreDump:
    """Helper to create a coredump DB record and optionally a .dmp file."""
    with app.app_context():
        session = container.db_session()
        coredump = CoreDump(
            device_id=device_id,
            filename=filename,
            chip=chip,
            firmware_version=firmware_version,
            size=size,
            parse_status=parse_status,
            parsed_output=parsed_output,
            uploaded_at=datetime.now(UTC),
        )
        session.add(coredump)
        session.flush()

        if write_file:
            config = container.config()
            if config.coredumps_dir is not None:
                device_dir = config.coredumps_dir / device_key
                device_dir.mkdir(parents=True, exist_ok=True)
                (device_dir / filename).write_bytes(b"\x00" * size)

        return coredump


class TestListCoredumps:
    """Tests for GET /api/devices/{device_id}/coredumps."""

    def test_list_coredumps_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test listing coredumps for a device."""
        device_id, device_key, _ = create_test_device(app, container, model_code="lc1")

        _create_coredump(
            app, container, device_id, device_key,
            filename="coredump_001.dmp",
            parse_status=ParseStatus.PARSED.value,
            parsed_output="crash info",
        )
        _create_coredump(
            app, container, device_id, device_key,
            filename="coredump_002.dmp",
        )

        response = client.get(f"/api/devices/{device_id}/coredumps")

        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 2
        assert len(data["coredumps"]) == 2

        # Summaries should not include parsed_output
        for summary in data["coredumps"]:
            assert "parsed_output" not in summary
            assert "id" in summary
            assert "filename" in summary
            assert "chip" in summary
            assert "parse_status" in summary

    def test_list_coredumps_empty(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test listing coredumps when device has none."""
        device_id, _, _ = create_test_device(app, container, model_code="lc2")

        response = client.get(f"/api/devices/{device_id}/coredumps")

        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 0
        assert data["coredumps"] == []

    def test_list_coredumps_device_not_found(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test listing coredumps for a non-existent device."""
        response = client.get("/api/devices/99999/coredumps")

        assert response.status_code == 404


class TestGetCoredump:
    """Tests for GET /api/devices/{device_id}/coredumps/{coredump_id}."""

    def test_get_coredump_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting coredump detail with parsed output."""
        device_id, device_key, _ = create_test_device(app, container, model_code="gc1")

        coredump = _create_coredump(
            app, container, device_id, device_key,
            filename="coredump_detail.dmp",
            parse_status=ParseStatus.PARSED.value,
            parsed_output="Guru Meditation Error: Core 0 panic'ed",
        )

        response = client.get(
            f"/api/devices/{device_id}/coredumps/{coredump.id}"
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == coredump.id
        assert data["filename"] == "coredump_detail.dmp"
        assert data["parse_status"] == "PARSED"
        assert data["parsed_output"] == "Guru Meditation Error: Core 0 panic'ed"
        assert data["chip"] == "esp32s3"
        assert data["firmware_version"] == "1.0.0"

    def test_get_coredump_wrong_device(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting a coredump that belongs to a different device."""
        device_id_a, device_key_a, _ = create_test_device(
            app, container, model_code="gc2a"
        )
        device_id_b, _, _ = create_test_device(app, container, model_code="gc2b")

        coredump = _create_coredump(
            app, container, device_id_a, device_key_a,
            filename="coredump_wrong.dmp",
        )

        # Try to access coredump via device B
        response = client.get(
            f"/api/devices/{device_id_b}/coredumps/{coredump.id}"
        )

        assert response.status_code == 404

    def test_get_coredump_not_found(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting a non-existent coredump."""
        device_id, _, _ = create_test_device(app, container, model_code="gc3")

        response = client.get(f"/api/devices/{device_id}/coredumps/99999")

        assert response.status_code == 404


class TestDownloadCoredump:
    """Tests for GET /api/devices/{device_id}/coredumps/{coredump_id}/download."""

    def test_download_coredump_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test downloading a coredump binary."""
        device_id, device_key, _ = create_test_device(app, container, model_code="dc1")

        coredump = _create_coredump(
            app, container, device_id, device_key,
            filename="coredump_dl.dmp",
            size=128,
        )

        response = client.get(
            f"/api/devices/{device_id}/coredumps/{coredump.id}/download"
        )

        assert response.status_code == 200
        assert response.content_type == "application/octet-stream"
        assert len(response.data) == 128

    def test_download_coredump_file_missing(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test downloading when .dmp file is missing from disk."""
        device_id, device_key, _ = create_test_device(app, container, model_code="dc2")

        # Create record but no file on disk
        coredump = _create_coredump(
            app, container, device_id, device_key,
            filename="coredump_missing.dmp",
            write_file=False,
        )

        response = client.get(
            f"/api/devices/{device_id}/coredumps/{coredump.id}/download"
        )

        assert response.status_code == 404

    def test_download_coredump_wrong_device(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test downloading a coredump that belongs to a different device."""
        device_id_a, device_key_a, _ = create_test_device(
            app, container, model_code="dc3a"
        )
        device_id_b, _, _ = create_test_device(app, container, model_code="dc3b")

        coredump = _create_coredump(
            app, container, device_id_a, device_key_a,
            filename="coredump_dl_wrong.dmp",
        )

        response = client.get(
            f"/api/devices/{device_id_b}/coredumps/{coredump.id}/download"
        )

        assert response.status_code == 404


class TestDeleteCoredump:
    """Tests for DELETE /api/devices/{device_id}/coredumps/{coredump_id}."""

    def test_delete_coredump_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer,
        test_settings: Settings,
    ) -> None:
        """Test deleting a single coredump removes record and file."""
        device_id, device_key, _ = create_test_device(app, container, model_code="del1")

        coredump = _create_coredump(
            app, container, device_id, device_key,
            filename="coredump_del.dmp",
        )

        response = client.delete(
            f"/api/devices/{device_id}/coredumps/{coredump.id}"
        )

        assert response.status_code == 204

        # Verify DB record deleted
        with app.app_context():
            from sqlalchemy import select

            session = container.db_session()
            result = session.execute(
                select(CoreDump).where(CoreDump.id == coredump.id)
            ).scalar_one_or_none()
            assert result is None

        # Verify file deleted
        assert test_settings.coredumps_dir is not None
        assert not (test_settings.coredumps_dir / device_key / "coredump_del.dmp").exists()

    def test_delete_coredump_wrong_device(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test deleting a coredump that belongs to a different device."""
        device_id_a, device_key_a, _ = create_test_device(
            app, container, model_code="del2a"
        )
        device_id_b, _, _ = create_test_device(app, container, model_code="del2b")

        coredump = _create_coredump(
            app, container, device_id_a, device_key_a,
            filename="coredump_del_wrong.dmp",
        )

        response = client.delete(
            f"/api/devices/{device_id_b}/coredumps/{coredump.id}"
        )

        assert response.status_code == 404


class TestDeleteAllCoredumps:
    """Tests for DELETE /api/devices/{device_id}/coredumps."""

    def test_delete_all_coredumps_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer,
        test_settings: Settings,
    ) -> None:
        """Test deleting all coredumps for a device."""
        device_id, device_key, _ = create_test_device(app, container, model_code="da1")

        _create_coredump(
            app, container, device_id, device_key,
            filename="coredump_da1.dmp",
        )
        _create_coredump(
            app, container, device_id, device_key,
            filename="coredump_da2.dmp",
        )

        response = client.delete(f"/api/devices/{device_id}/coredumps")

        assert response.status_code == 204

        # Verify all DB records deleted
        with app.app_context():
            from sqlalchemy import select

            session = container.db_session()
            results = session.execute(
                select(CoreDump).where(CoreDump.device_id == device_id)
            ).scalars().all()
            assert len(results) == 0

    def test_delete_all_coredumps_empty(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test deleting all coredumps when device has none (idempotent)."""
        device_id, _, _ = create_test_device(app, container, model_code="da2")

        response = client.delete(f"/api/devices/{device_id}/coredumps")

        assert response.status_code == 204

    def test_delete_all_coredumps_device_not_found(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test deleting all coredumps for a non-existent device."""
        response = client.delete("/api/devices/99999/coredumps")

        assert response.status_code == 404
