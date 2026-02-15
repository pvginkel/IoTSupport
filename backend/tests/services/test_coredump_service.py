"""Tests for CoredumpService (S3-backed storage)."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import (
    RecordNotFoundException,
    ValidationException,
)
from app.models.coredump import CoreDump, ParseStatus
from app.services.container import ServiceContainer
from app.services.coredump_service import MAX_COREDUMP_SIZE
from tests.api.test_iot import create_test_device


def _create_coredump_record(
    session: Session,
    device_id: int,
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

    def test_save_coredump_creates_s3_object_and_record(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that save_coredump uploads to S3 and creates a DB record."""
        device_id, device_key, _ = create_test_device(app, container, model_code="sv1")
        service = container.coredump_service()
        content = b"\x00" * 256

        coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="sv1",
            chip="esp32s3",
            firmware_version="1.2.3",
            content=content,
        )

        # Verify DB record
        stmt = select(CoreDump).where(CoreDump.id == coredump_id)
        coredump = session.execute(stmt).scalar_one()
        assert coredump.device_id == device_id
        assert coredump.chip == "esp32s3"
        assert coredump.firmware_version == "1.2.3"
        assert coredump.size == 256
        assert coredump.parse_status == ParseStatus.PENDING.value
        assert coredump.parsed_output is None
        assert coredump.uploaded_at is not None

        # Verify S3 object exists
        s3 = container.s3_service()
        s3_key = f"coredumps/{device_key}/{coredump_id}.dmp"
        assert s3.file_exists(s3_key)

        # Verify S3 content matches
        stream = s3.download_file(s3_key)
        assert stream.read() == content

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

        coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="sv4",
            chip="esp32s3",
            firmware_version="1.0.0",
            content=content,
        )

        assert coredump_id > 0

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

    def test_save_coredump_unique_ids(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that consecutive saves produce unique coredump IDs."""
        device_id, device_key, _ = create_test_device(app, container, model_code="sv5")
        service = container.coredump_service()

        ids = set()
        for _ in range(5):
            coredump_id = service.save_coredump(
                device_id=device_id,
                device_key=device_key,
                model_code="sv5",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00",
            )
            ids.add(coredump_id)

        assert len(ids) == 5


class TestCoredumpServiceRetention:
    """Tests for CoredumpService retention enforcement."""

    def test_retention_deletes_oldest_when_exceeded(
        self, app: Flask, session: Session, container: ServiceContainer,
    ) -> None:
        """Test that exceeding MAX_COREDUMPS deletes the oldest records and S3 objects."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ret1")

        service = container.coredump_service()
        config = container.app_config()

        # Override max_coredumps to a small value for testing
        original_max = config.max_coredumps
        config.max_coredumps = 3

        # Create 3 coredumps (at the limit)
        created_ids = []
        for i in range(3):
            coredump_id = service.save_coredump(
                device_id=device_id,
                device_key=device_key,
                model_code="ret1",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00" * (i + 1),
            )
            created_ids.append(coredump_id)

        # Adding one more should delete the oldest
        new_id = service.save_coredump(
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

        # The oldest S3 object should be gone
        s3 = container.s3_service()
        oldest_key = f"coredumps/{device_key}/{created_ids[0]}.dmp"
        assert not s3.file_exists(oldest_key)

        # The newest should exist
        newest_key = f"coredumps/{device_key}/{new_id}.dmp"
        assert s3.file_exists(newest_key)

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
            uploaded_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        newer = _create_coredump_record(
            session, device_id,
            uploaded_at=datetime(2026, 2, 1, tzinfo=UTC),
        )

        service = container.coredump_service()
        result = service.list_coredumps(device_id)

        assert len(result) == 2
        assert result[0].id == newer.id  # Newest first

    def test_get_coredump_success(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test getting a specific coredump by device_id and coredump_id."""
        device_id, _, _ = create_test_device(app, container, model_code="cr2")

        record = _create_coredump_record(
            session, device_id,
            parsed_output="crash info",
            parse_status=ParseStatus.PARSED.value,
        )

        service = container.coredump_service()
        coredump = service.get_coredump(device_id, record.id)

        assert coredump.id == record.id
        assert coredump.parsed_output == "crash info"

    def test_get_coredump_wrong_device_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that getting a coredump with wrong device_id raises RecordNotFoundException."""
        device_id_a, _, _ = create_test_device(app, container, model_code="cr3a")
        device_id_b, _, _ = create_test_device(app, container, model_code="cr3b")

        record = _create_coredump_record(session, device_id_a)

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

    def test_get_coredump_stream_success(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test downloading a coredump from S3 as a stream."""
        device_id, device_key, _ = create_test_device(app, container, model_code="cr5")
        service = container.coredump_service()
        content = b"\xDE\xAD\xBE\xEF" * 32

        coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="cr5",
            chip="esp32s3",
            firmware_version="1.0.0",
            content=content,
        )

        stream = service.get_coredump_stream(device_key, coredump_id)
        assert stream.read() == content

    def test_get_coredump_stream_not_found_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that get_coredump_stream raises when S3 object not found."""
        service = container.coredump_service()

        with pytest.raises(RecordNotFoundException):
            service.get_coredump_stream("abc12345", 99999)

    def test_delete_coredump_removes_record_and_s3(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that delete_coredump removes both DB record and S3 object."""
        device_id, device_key, _ = create_test_device(app, container, model_code="cr6")
        service = container.coredump_service()

        coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="cr6",
            chip="esp32s3",
            firmware_version="1.0.0",
            content=b"\x00" * 64,
        )

        service.delete_coredump(device_id, coredump_id, device_key)

        # Verify record deleted
        result = session.execute(
            select(CoreDump).where(CoreDump.id == coredump_id)
        ).scalar_one_or_none()
        assert result is None

        # Verify S3 object deleted
        s3 = container.s3_service()
        assert not s3.file_exists(f"coredumps/{device_key}/{coredump_id}.dmp")

    def test_delete_coredump_s3_missing_succeeds(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that deleting a coredump whose S3 object is missing succeeds."""
        device_id, device_key, _ = create_test_device(app, container, model_code="cr7")

        # Create a DB record directly (no S3 upload)
        record = _create_coredump_record(session, device_id)

        service = container.coredump_service()
        # Should not raise even though S3 object doesn't exist
        service.delete_coredump(device_id, record.id, device_key)

        result = session.execute(
            select(CoreDump).where(CoreDump.id == record.id)
        ).scalar_one_or_none()
        assert result is None

    def test_delete_all_coredumps(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that delete_all_coredumps removes all records and S3 objects for a device."""
        device_id, device_key, _ = create_test_device(app, container, model_code="cr8")
        service = container.coredump_service()

        coredump_ids = []
        for _ in range(5):
            cid = service.save_coredump(
                device_id=device_id,
                device_key=device_key,
                model_code="cr8",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00" * 10,
            )
            coredump_ids.append(cid)

        service.delete_all_coredumps(device_id, device_key)

        # All records gone
        remaining = session.execute(
            select(CoreDump).where(CoreDump.device_id == device_id)
        ).scalars().all()
        assert len(remaining) == 0

        # All S3 objects gone
        s3 = container.s3_service()
        for cid in coredump_ids:
            assert not s3.file_exists(f"coredumps/{device_key}/{cid}.dmp")


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
        )
        # No thread should be started -- we just verify no exception

    def test_parse_coredump_success(
        self, app: Flask, session: Session, container: ServiceContainer,
        tmp_path: Path,
    ) -> None:
        """Test successful parsing via sidecar (downloads from S3)."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ps1")
        service = container.coredump_service()
        config = container.app_config()

        # Save a coredump (goes to S3)
        content = b"\xDE\xAD" * 128
        coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ps1",
            chip="esp32s3",
            firmware_version="1.0.0",
            content=content,
        )
        session.commit()

        # Upload a firmware ELF to S3 (so parsing can find it)
        from io import BytesIO
        s3 = container.s3_service()
        elf_content = b"\x7fELF" + b"\x00" * 100
        s3.upload_file(
            BytesIO(elf_content),
            "firmware/ps1/1.0.0/firmware.elf",
            content_type="application/octet-stream",
        )

        # Configure sidecar settings
        xfer_dir = tmp_path / "xfer"
        xfer_dir.mkdir()
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

        coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ps2",
            chip="esp32",
            firmware_version="1.0.0",
            content=b"\x00" * 10,
        )
        session.commit()

        # Upload ELF to S3
        from io import BytesIO
        s3 = container.s3_service()
        s3.upload_file(
            BytesIO(b"\x7fELF" + b"\x00" * 100),
            "firmware/ps2/1.0.0/firmware.elf",
            content_type="application/octet-stream",
        )

        xfer_dir = tmp_path / "xfer"
        xfer_dir.mkdir()
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

        coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ps3",
            chip="esp32",
            firmware_version="1.0.0",
            content=b"\x00" * 10,
        )
        session.commit()

        # Upload ELF to S3
        from io import BytesIO
        s3 = container.s3_service()
        s3.upload_file(
            BytesIO(b"\x7fELF" + b"\x00" * 100),
            "firmware/ps3/1.0.0/firmware.elf",
            content_type="application/octet-stream",
        )

        xfer_dir = tmp_path / "xfer"
        xfer_dir.mkdir()
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

    def test_parse_coredump_firmware_elf_not_found(
        self, app: Flask, session: Session, container: ServiceContainer,
        tmp_path: Path,
    ) -> None:
        """Test that missing firmware ELF in S3 sets ERROR without retrying."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ps4")
        service = container.coredump_service()
        config = container.app_config()

        coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ps4",
            chip="esp32",
            firmware_version="9.9.9",  # No ELF exists for this version
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
        )

        with app.app_context():
            check_session = container.db_session()
            coredump = check_session.execute(
                select(CoreDump).where(CoreDump.id == coredump_id)
            ).scalar_one()
            assert coredump.parse_status == ParseStatus.ERROR.value
            assert "firmware ELF not found" in coredump.parsed_output  # type: ignore[operator]
            container.db_session.reset()

    def test_parse_coredump_cleans_up_xfer_files(
        self, app: Flask, session: Session, container: ServiceContainer,
        tmp_path: Path,
    ) -> None:
        """Test that xfer directory files are cleaned up after parsing."""
        device_id, device_key, _ = create_test_device(app, container, model_code="ps5")
        service = container.coredump_service()
        config = container.app_config()

        coredump_id = service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code="ps5",
            chip="esp32s3",
            firmware_version="1.0.0",
            content=b"\x00" * 10,
        )
        session.commit()

        # Upload ELF to S3
        from io import BytesIO
        s3 = container.s3_service()
        s3.upload_file(
            BytesIO(b"\x7fELF" + b"\x00" * 100),
            "firmware/ps5/1.0.0/firmware.elf",
            content_type="application/octet-stream",
        )

        xfer_dir = tmp_path / "xfer"
        xfer_dir.mkdir()
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
            )

        # Xfer files should be cleaned up
        assert len(list(xfer_dir.glob("*"))) == 0
