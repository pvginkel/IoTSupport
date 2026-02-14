"""Tests for CoredumpService."""

import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.app_config import AppSettings
from app.exceptions import (
    InvalidOperationException,
    RecordNotFoundException,
    ValidationException,
)
from app.models.coredump import CoreDump, ParseStatus
from app.services.container import ServiceContainer
from app.services.coredump_service import MAX_COREDUMP_SIZE, CoredumpService
from tests.api.test_iot import create_test_device


def _create_coredump_record(
    session: Session,
    device_id: int,
    filename: str = "coredump_test.dmp",
    chip: str = "esp32s3",
    firmware_version: str = "1.0.0",
    size: int = 256,
    parse_status: str = ParseStatus.PENDING.value,
    parsed_output: str | None = None,
    uploaded_at: datetime | None = None,
) -> CoreDump:
    """Helper to create a CoreDump record directly in the DB."""
    coredump = CoreDump(
        device_id=device_id,
        filename=filename,
        chip=chip,
        firmware_version=firmware_version,
        size=size,
        parse_status=parse_status,
        parsed_output=parsed_output,
        uploaded_at=uploaded_at or datetime.now(UTC),
    )
    session.add(coredump)
    session.flush()
    return coredump


class TestCoredumpServiceSave:
    """Tests for CoredumpService.save_coredump()."""

    def test_save_coredump_creates_file_and_record(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that save_coredump creates a .dmp file and a DB record."""
        device_id, device_key, _ = create_test_device(app, container, model_code="sv1")
        service = container.coredump_service()
        content = b"\x00" * 256

        filename, coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="sv1",
            chip="esp32s3",
            firmware_version="1.2.3",
            content=content,
        )

        # Verify filename format
        assert filename.startswith("coredump_")
        assert filename.endswith(".dmp")

        # Verify .dmp file exists
        config = container.app_config()
        assert config.coredumps_dir is not None
        dmp_path = config.coredumps_dir / device_key / filename
        assert dmp_path.exists()
        assert dmp_path.read_bytes() == content

        # Verify no JSON sidecar file was created
        json_files = list((config.coredumps_dir / device_key).glob("*.json"))
        assert len(json_files) == 0

        # Verify DB record
        stmt = select(CoreDump).where(CoreDump.id == coredump_id)
        coredump = session.execute(stmt).scalar_one()
        assert coredump.device_id == device_id
        assert coredump.filename == filename
        assert coredump.chip == "esp32s3"
        assert coredump.firmware_version == "1.2.3"
        assert coredump.size == 256
        assert coredump.parse_status == ParseStatus.PENDING.value
        assert coredump.parsed_output is None
        assert coredump.uploaded_at is not None

    def test_save_coredump_empty_content_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that empty content raises ValidationException."""
        device_id, device_key, _ = create_test_device(app, container, model_code="sv2")
        service = container.coredump_service()

        with pytest.raises(ValidationException, match="No coredump content provided"):
            service.save_coredump(
                device_id=device_id,
                device_key=device_key,
                model_code="sv2",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"",
            )

    def test_save_coredump_exceeds_max_size_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that content exceeding 1MB raises ValidationException."""
        device_id, device_key, _ = create_test_device(app, container, model_code="sv3")
        service = container.coredump_service()
        oversized = b"\x00" * (MAX_COREDUMP_SIZE + 1)

        with pytest.raises(ValidationException, match="exceeds maximum size of 1MB"):
            service.save_coredump(
                device_id=device_id,
                device_key=device_key,
                model_code="sv3",
                chip="esp32s3",
                firmware_version="1.0.0",
                content=oversized,
            )

    def test_save_coredump_exactly_max_size_succeeds(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that content exactly at 1MB limit is accepted."""
        device_id, device_key, _ = create_test_device(app, container, model_code="sv4")
        service = container.coredump_service()
        content = b"\x00" * MAX_COREDUMP_SIZE

        filename, _ = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="sv4",
            chip="esp32s3",
            firmware_version="1.0.0",
            content=content,
        )

        assert filename.endswith(".dmp")

    def test_save_coredump_no_coredumps_dir_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that saving when coredumps_dir is None raises InvalidOperationException."""
        # Create a service with None coredumps_dir
        service = CoredumpService(
            coredumps_dir=None,
            config=container.app_config(),
            firmware_service=container.firmware_service(),
            metrics_service=container.metrics_service(),
        )
        service.container = container

        with pytest.raises(InvalidOperationException, match="COREDUMPS_DIR is not configured"):
            service.save_coredump(
                device_id=1,
                device_key="abc12345",
                model_code="test",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00" * 10,
            )

    def test_save_coredump_invalid_device_key_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that a non-alphanumeric device key raises ValidationException."""
        service = container.coredump_service()

        with pytest.raises(ValidationException, match="Invalid device key format"):
            service.save_coredump(
                device_id=1,
                device_key="../../etc",
                model_code="test",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00" * 10,
            )

    def test_save_coredump_unique_filenames(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that consecutive saves produce unique filenames."""
        device_id, device_key, _ = create_test_device(app, container, model_code="sv5")
        service = container.coredump_service()

        filenames = set()
        for _ in range(5):
            filename, _ = service.save_coredump(
                device_id=device_id,
                device_key=device_key,
                model_code="sv5",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00",
            )
            filenames.add(filename)

        assert len(filenames) == 5


class TestCoredumpServiceRetention:
    """Tests for CoredumpService retention enforcement."""

    def test_retention_deletes_oldest_when_exceeded(
        self, app: Flask, session: Session, container: ServiceContainer,
    ) -> None:
        """Test that exceeding MAX_COREDUMPS deletes the oldest records and files."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ret1")

        service = container.coredump_service()
        config = container.app_config()

        # Override max_coredumps to a small value for testing
        original_max = config.max_coredumps
        config.max_coredumps = 3

        # Create 3 coredumps (at the limit)
        created_filenames = []
        for i in range(3):
            filename, _ = service.save_coredump(
                device_id=device_id,
                device_key=device_key,
                model_code="ret1",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00" * (i + 1),
            )
            created_filenames.append(filename)

        # Adding one more should delete the oldest
        filename_new, _ = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ret1",
            chip="esp32",
            firmware_version="1.0.0",
            content=b"\xFF" * 10,
        )

        # Verify we now have exactly 3 records
        stmt = select(CoreDump).where(CoreDump.device_id == device_id)
        remaining = session.execute(stmt).scalars().all()
        assert len(remaining) == 3

        # The oldest file should be gone from disk
        assert config.coredumps_dir is not None
        assert not (config.coredumps_dir / device_key / created_filenames[0]).exists()

        # The newest should exist
        assert (config.coredumps_dir / device_key / filename_new).exists()

        # Restore original
        config.max_coredumps = original_max

    def test_retention_not_triggered_when_within_limit(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that retention is not triggered when within the limit."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ret2")
        service = container.coredump_service()

        # Save 2 coredumps (default limit is 20)
        for _ in range(2):
            service.save_coredump(
                device_id=device_id,
                device_key=device_key,
                model_code="ret2",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00",
            )

        stmt = select(CoreDump).where(CoreDump.device_id == device_id)
        count = len(session.execute(stmt).scalars().all())
        assert count == 2


class TestCoredumpServiceCRUD:
    """Tests for CoredumpService CRUD methods."""

    def test_list_coredumps_ordered_by_uploaded_at_desc(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that list_coredumps returns records ordered newest first."""
        device_id, device_key, _ = create_test_device(app, container, model_code="cr1")

        # Create records with different uploaded_at times
        _create_coredump_record(
            session, device_id,
            filename="old.dmp",
            uploaded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        _create_coredump_record(
            session, device_id,
            filename="new.dmp",
            uploaded_at=datetime(2026, 2, 1, tzinfo=UTC),
        )

        service = container.coredump_service()
        result = service.list_coredumps(device_id)

        assert len(result) == 2
        assert result[0].filename == "new.dmp"  # Newest first
        assert result[1].filename == "old.dmp"

    def test_get_coredump_success(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test getting a specific coredump by device_id and coredump_id."""
        device_id, _, _ = create_test_device(app, container, model_code="cr2")

        record = _create_coredump_record(
            session, device_id,
            filename="get_test.dmp",
            parsed_output="crash info",
            parse_status=ParseStatus.PARSED.value,
        )

        service = container.coredump_service()
        coredump = service.get_coredump(device_id, record.id)

        assert coredump.id == record.id
        assert coredump.filename == "get_test.dmp"
        assert coredump.parsed_output == "crash info"

    def test_get_coredump_wrong_device_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that getting a coredump with wrong device_id raises RecordNotFoundException."""
        device_id_a, _, _ = create_test_device(app, container, model_code="cr3a")
        device_id_b, _, _ = create_test_device(app, container, model_code="cr3b")

        record = _create_coredump_record(session, device_id_a, filename="wrong_dev.dmp")

        service = container.coredump_service()
        with pytest.raises(RecordNotFoundException):
            service.get_coredump(device_id_b, record.id)

    def test_get_coredump_nonexistent_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that getting a non-existent coredump raises RecordNotFoundException."""
        device_id, _, _ = create_test_device(app, container, model_code="cr4")
        service = container.coredump_service()

        with pytest.raises(RecordNotFoundException):
            service.get_coredump(device_id, 99999)

    def test_get_coredump_path_success(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test getting the filesystem path for a coredump file."""
        device_id, device_key, _ = create_test_device(app, container, model_code="cr5")

        # Create file on disk
        config = container.app_config()
        assert config.coredumps_dir is not None
        device_dir = config.coredumps_dir / device_key
        device_dir.mkdir(parents=True, exist_ok=True)
        (device_dir / "test.dmp").write_bytes(b"\x00")

        service = container.coredump_service()
        path = service.get_coredump_path(device_key, "test.dmp")
        assert path == device_dir / "test.dmp"

    def test_get_coredump_path_file_missing_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that get_coredump_path raises when file not on disk."""
        service = container.coredump_service()

        with pytest.raises(RecordNotFoundException):
            service.get_coredump_path("abc12345", "nonexistent.dmp")

    def test_delete_coredump_removes_record_and_file(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that delete_coredump removes both DB record and file."""
        device_id, device_key, _ = create_test_device(app, container, model_code="cr6")

        # Create file on disk
        config = container.app_config()
        assert config.coredumps_dir is not None
        device_dir = config.coredumps_dir / device_key
        device_dir.mkdir(parents=True, exist_ok=True)
        (device_dir / "del.dmp").write_bytes(b"\x00")

        record = _create_coredump_record(session, device_id, filename="del.dmp")

        service = container.coredump_service()
        service.delete_coredump(device_id, record.id, device_key)

        # Verify record deleted
        result = session.execute(
            select(CoreDump).where(CoreDump.id == record.id)
        ).scalar_one_or_none()
        assert result is None

        # Verify file deleted
        assert not (device_dir / "del.dmp").exists()

    def test_delete_coredump_file_already_missing(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that deleting a coredump whose file is missing succeeds."""
        device_id, device_key, _ = create_test_device(app, container, model_code="cr7")
        record = _create_coredump_record(session, device_id, filename="already_gone.dmp")

        service = container.coredump_service()
        # Should not raise even though file doesn't exist
        service.delete_coredump(device_id, record.id, device_key)

        result = session.execute(
            select(CoreDump).where(CoreDump.id == record.id)
        ).scalar_one_or_none()
        assert result is None

    def test_delete_all_coredumps(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that delete_all_coredumps removes all records and files for a device."""
        device_id, device_key, _ = create_test_device(app, container, model_code="cr8")

        config = container.app_config()
        assert config.coredumps_dir is not None
        device_dir = config.coredumps_dir / device_key
        device_dir.mkdir(parents=True, exist_ok=True)

        for i in range(5):
            fname = f"bulk_del_{i}.dmp"
            (device_dir / fname).write_bytes(b"\x00")
            _create_coredump_record(session, device_id, filename=fname)

        service = container.coredump_service()
        service.delete_all_coredumps(device_id, device_key)

        # All records gone
        remaining = session.execute(
            select(CoreDump).where(CoreDump.device_id == device_id)
        ).scalars().all()
        assert len(remaining) == 0

        # All files gone
        dmp_files = list(device_dir.glob("*.dmp"))
        assert len(dmp_files) == 0


class TestCoredumpServiceParsing:
    """Tests for CoredumpService background parsing."""

    def test_maybe_start_parsing_skips_when_not_configured(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that parsing is skipped when sidecar is not configured."""
        service = container.coredump_service()

        # Default test config has no sidecar URL/dir -- should not raise
        service.maybe_start_parsing(
            coredump_id=1,
            device_key="abc12345",
            model_code="test",
            chip="esp32",
            firmware_version="1.0.0",
            filename="test.dmp",
        )
        # No thread should be started -- we just verify no exception

    def test_parse_coredump_success(
        self, app: Flask, session: Session, container: ServiceContainer,
        tmp_path: Path,
    ) -> None:
        """Test successful parsing via sidecar."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ps1")
        service = container.coredump_service()
        config = container.app_config()

        # Save a coredump
        content = b"\xDE\xAD" * 128
        filename, coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ps1",
            chip="esp32s3",
            firmware_version="1.0.0",
            content=content,
        )
        session.commit()

        # Create a firmware ZIP with an .elf file
        xfer_dir = tmp_path / "xfer"
        xfer_dir.mkdir()

        self._create_firmware_zip(config, "ps1", "1.0.0")

        # Configure sidecar settings
        config.parse_sidecar_xfer_dir = xfer_dir
        config.parse_sidecar_url = "http://sidecar:8080"

        # Mock the sidecar HTTP call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"output": "Stack trace: crash at 0xDEAD"}

        with patch("app.services.coredump_service.httpx.get", return_value=mock_response):
            # Run parse synchronously (call the thread function directly)
            service._parse_coredump_thread(
                coredump_id=coredump_id,
                device_key=device_key,
                model_code="ps1",
                chip="esp32s3",
                firmware_version="1.0.0",
                filename=filename,
            )

        # Verify the DB record was updated
        with app.app_context():
            check_session = container.db_session()
            stmt = select(CoreDump).where(CoreDump.id == coredump_id)
            coredump = check_session.execute(stmt).scalar_one()
            assert coredump.parse_status == ParseStatus.PARSED.value
            assert coredump.parsed_output == "Stack trace: crash at 0xDEAD"
            assert coredump.parsed_at is not None
            container.db_session.reset()

    def test_parse_coredump_retries_then_succeeds(
        self, app: Flask, session: Session, container: ServiceContainer,
        tmp_path: Path,
    ) -> None:
        """Test that parsing retries on failure and succeeds on third attempt."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ps2")
        service = container.coredump_service()
        config = container.app_config()

        filename, coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ps2",
            chip="esp32",
            firmware_version="1.0.0",
            content=b"\x00" * 10,
        )
        session.commit()

        xfer_dir = tmp_path / "xfer"
        xfer_dir.mkdir()
        self._create_firmware_zip(config, "ps2", "1.0.0")

        config.parse_sidecar_xfer_dir = xfer_dir
        config.parse_sidecar_url = "http://sidecar:8080"

        # Fail twice, succeed on third attempt
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.raise_for_status = MagicMock()
        success_response.json.return_value = {"output": "parsed!"}

        call_count = 0

        def side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("sidecar down")
            return success_response

        with patch("app.services.coredump_service.httpx.get", side_effect=side_effect):
            service._parse_coredump_thread(
                coredump_id=coredump_id,
                device_key=device_key,
                model_code="ps2",
                chip="esp32",
                firmware_version="1.0.0",
                filename=filename,
            )

        with app.app_context():
            check_session = container.db_session()
            coredump = check_session.execute(
                select(CoreDump).where(CoreDump.id == coredump_id)
            ).scalar_one()
            assert coredump.parse_status == ParseStatus.PARSED.value
            assert coredump.parsed_output == "parsed!"
            container.db_session.reset()

    def test_parse_coredump_all_retries_fail(
        self, app: Flask, session: Session, container: ServiceContainer,
        tmp_path: Path,
    ) -> None:
        """Test that after 3 failures, parse_status is set to ERROR."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ps3")
        service = container.coredump_service()
        config = container.app_config()

        filename, coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ps3",
            chip="esp32",
            firmware_version="1.0.0",
            content=b"\x00" * 10,
        )
        session.commit()

        xfer_dir = tmp_path / "xfer"
        xfer_dir.mkdir()
        self._create_firmware_zip(config, "ps3", "1.0.0")

        config.parse_sidecar_xfer_dir = xfer_dir
        config.parse_sidecar_url = "http://sidecar:8080"

        with patch(
            "app.services.coredump_service.httpx.get",
            side_effect=ConnectionError("sidecar unreachable"),
        ):
            service._parse_coredump_thread(
                coredump_id=coredump_id,
                device_key=device_key,
                model_code="ps3",
                chip="esp32",
                firmware_version="1.0.0",
                filename=filename,
            )

        with app.app_context():
            check_session = container.db_session()
            coredump = check_session.execute(
                select(CoreDump).where(CoreDump.id == coredump_id)
            ).scalar_one()
            assert coredump.parse_status == ParseStatus.ERROR.value
            assert "Unable to parse coredump:" in coredump.parsed_output  # type: ignore[operator]
            assert "sidecar unreachable" in coredump.parsed_output  # type: ignore[operator]
            container.db_session.reset()

    def test_parse_coredump_firmware_zip_not_found(
        self, app: Flask, session: Session, container: ServiceContainer,
        tmp_path: Path,
    ) -> None:
        """Test that missing firmware ZIP sets ERROR without retrying."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ps4")
        service = container.coredump_service()
        config = container.app_config()

        filename, coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ps4",
            chip="esp32",
            firmware_version="9.9.9",  # No ZIP exists for this version
            content=b"\x00" * 10,
        )
        session.commit()

        xfer_dir = tmp_path / "xfer"
        xfer_dir.mkdir()
        config.parse_sidecar_xfer_dir = xfer_dir
        config.parse_sidecar_url = "http://sidecar:8080"

        service._parse_coredump_thread(
            coredump_id=coredump_id,
            device_key=device_key,
            model_code="ps4",
            chip="esp32",
            firmware_version="9.9.9",
            filename=filename,
        )

        with app.app_context():
            check_session = container.db_session()
            coredump = check_session.execute(
                select(CoreDump).where(CoreDump.id == coredump_id)
            ).scalar_one()
            assert coredump.parse_status == ParseStatus.ERROR.value
            assert "firmware ZIP not found" in coredump.parsed_output  # type: ignore[operator]
            container.db_session.reset()

    def test_parse_coredump_cleans_up_xfer_files(
        self, app: Flask, session: Session, container: ServiceContainer,
        tmp_path: Path,
    ) -> None:
        """Test that xfer directory files are cleaned up after parsing."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ps5")
        service = container.coredump_service()
        config = container.app_config()

        filename, coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ps5",
            chip="esp32s3",
            firmware_version="1.0.0",
            content=b"\x00" * 10,
        )
        session.commit()

        xfer_dir = tmp_path / "xfer"
        xfer_dir.mkdir()
        self._create_firmware_zip(config, "ps5", "1.0.0")

        config.parse_sidecar_xfer_dir = xfer_dir
        config.parse_sidecar_url = "http://sidecar:8080"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"output": "ok"}

        with patch("app.services.coredump_service.httpx.get", return_value=mock_response):
            service._parse_coredump_thread(
                coredump_id=coredump_id,
                device_key=device_key,
                model_code="ps5",
                chip="esp32s3",
                firmware_version="1.0.0",
                filename=filename,
            )

        # Xfer files should be cleaned up
        assert len(list(xfer_dir.glob("*"))) == 0

    def _create_firmware_zip(
        self, settings: AppSettings, model_code: str, version: str
    ) -> Path:
        """Create a minimal firmware ZIP containing a dummy .elf file."""
        assert settings.assets_dir is not None
        model_dir = settings.assets_dir / model_code
        model_dir.mkdir(parents=True, exist_ok=True)
        zip_path = model_dir / f"firmware-{version}.zip"

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(f"{model_code}.elf", b"\x7fELF" + b"\x00" * 100)

        return zip_path


class TestCoredumpServiceInit:
    """Tests for CoredumpService initialization."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that initialization creates the coredumps directory."""
        coredumps_dir = tmp_path / "new_coredumps"
        assert not coredumps_dir.exists()

        mock_config = MagicMock()
        mock_config.parse_sidecar_xfer_dir = None
        mock_config.parse_sidecar_url = None
        mock_config.max_coredumps = 20

        CoredumpService(
            coredumps_dir=coredumps_dir,
            config=mock_config,
            firmware_service=MagicMock(),
            metrics_service=MagicMock(),
        )

        assert coredumps_dir.exists()
        assert coredumps_dir.is_dir()

    def test_init_with_none_does_not_fail(self) -> None:
        """Test that initialization with None coredumps_dir does not raise."""
        mock_config = MagicMock()
        mock_config.parse_sidecar_xfer_dir = None
        mock_config.parse_sidecar_url = None
        mock_config.max_coredumps = 20

        service = CoredumpService(
            coredumps_dir=None,
            config=mock_config,
            firmware_service=MagicMock(),
            metrics_service=MagicMock(),
        )
        assert service.coredumps_dir is None
