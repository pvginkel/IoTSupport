"""Tests for FirmwareService S3-based firmware storage and version tracking."""

import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO

import pytest
from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import RecordNotFoundException, ValidationException
from app.models.coredump import CoreDump, ParseStatus
from app.models.device_model import DeviceModel
from app.models.firmware_version import FirmwareVersion
from app.services.container import ServiceContainer
from app.services.firmware_service import FirmwareService, is_zip_content
from tests.conftest import create_test_firmware


def _create_test_zip(model_code: str, version: bytes, extra_files: dict[str, bytes] | None = None, omit_files: set[str] | None = None) -> bytes:
    """Create a valid firmware ZIP for testing.

    Args:
        model_code: Model code used in filenames
        version: Version bytes for the firmware binary
        extra_files: Additional files to include beyond the required set
        omit_files: Files to exclude from the required set
    """
    bin_content = create_test_firmware(version)

    version_json = json.dumps({
        "git_commit": "a1b2c3d4e5f6",
        "idf_version": "v5.2.1",
        "firmware_version": version.decode("utf-8"),
    }).encode("utf-8")

    files: dict[str, bytes] = {
        f"{model_code}.bin": bin_content,
        f"{model_code}.elf": b"\x7fELF" + b"\x00" * 100,
        f"{model_code}.map": b"Memory Map\n",
        "sdkconfig": b"CONFIG_IDF_TARGET=\"esp32s3\"\n",
        "version.json": version_json,
    }

    # Remove omitted files
    if omit_files:
        for name in omit_files:
            files.pop(name, None)

    # Add extra files
    if extra_files:
        files.update(extra_files)

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)

    return buf.getvalue()


def _create_model(session: Session, code: str, name: str = "Test Model") -> DeviceModel:
    """Helper to create a DeviceModel record directly."""
    model = DeviceModel(code=code, name=name)
    session.add(model)
    session.flush()
    return model


class TestIsZipContent:
    """Tests for is_zip_content()."""

    def test_zip_content_detected(self) -> None:
        """Test that ZIP magic bytes are correctly detected."""
        zip_data = _create_test_zip("test", b"1.0.0")
        assert is_zip_content(zip_data) is True

    def test_binary_content_not_detected(self) -> None:
        """Test that raw firmware binary is not detected as ZIP."""
        bin_data = create_test_firmware(b"1.0.0")
        assert is_zip_content(bin_data) is False

    def test_empty_content_not_detected(self) -> None:
        """Test that empty content is not detected as ZIP."""
        assert is_zip_content(b"") is False

    def test_short_content_not_detected(self) -> None:
        """Test that content shorter than 4 bytes is not detected as ZIP."""
        assert is_zip_content(b"PK") is False


class TestFirmwareServiceSave:
    """Tests for FirmwareService.save_firmware() with S3 storage."""

    def test_save_firmware_valid_zip(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test saving a valid firmware ZIP creates S3 objects and DB record."""
        model_code = "tempsensor"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(model_code, b"1.2.3")

        version = service.save_firmware(model_code, model.id, zip_content)

        assert version == "1.2.3"

        # Verify firmware_versions DB record was created
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id,
            FirmwareVersion.version == "1.2.3",
        )
        fv = session.execute(stmt).scalar_one()
        assert fv.version == "1.2.3"
        assert fv.uploaded_at is not None

        # Verify S3 objects exist
        s3 = container.s3_service()
        assert s3.file_exists(f"firmware/{model_code}/1.2.3/firmware.bin")
        assert s3.file_exists(f"firmware/{model_code}/1.2.3/firmware.elf")
        assert s3.file_exists(f"firmware/{model_code}/1.2.3/firmware.map")
        assert s3.file_exists(f"firmware/{model_code}/1.2.3/sdkconfig")
        assert s3.file_exists(f"firmware/{model_code}/1.2.3/version.json")

    def test_save_firmware_non_zip_rejected(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that raw .bin content is rejected."""
        model = _create_model(session, "rawbin")
        service = container.firmware_service()
        bin_content = create_test_firmware(b"1.0.0")

        with pytest.raises(ValidationException, match="ZIP bundle"):
            service.save_firmware("rawbin", model.id, bin_content)

    def test_save_firmware_zip_missing_elf(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that ZIP missing .elf file raises ValidationException."""
        model_code = "noelf"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(model_code, b"1.0.0", omit_files={f"{model_code}.elf"})

        with pytest.raises(ValidationException, match="missing.*elf"):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_zip_missing_map(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that ZIP missing .map file raises ValidationException."""
        model_code = "nomap"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(model_code, b"1.0.0", omit_files={f"{model_code}.map"})

        with pytest.raises(ValidationException, match="missing.*map"):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_zip_extra_files(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that ZIP with extra unexpected files raises ValidationException."""
        model_code = "extrafiles"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(
            model_code, b"1.0.0",
            extra_files={"unexpected.txt": b"oops"}
        )

        with pytest.raises(ValidationException, match="unexpected files.*unexpected.txt"):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_zip_invalid_bin(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that ZIP with invalid .bin raises ValidationException."""
        model_code = "badbin"
        model = _create_model(session, model_code)
        service = container.firmware_service()

        version_json = json.dumps({
            "git_commit": "abc123",
            "idf_version": "v5.0",
            "firmware_version": "1.0.0",
        }).encode()

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"{model_code}.bin", b"\x00" * 10)
            zf.writestr(f"{model_code}.elf", b"\x7fELF")
            zf.writestr(f"{model_code}.map", b"map")
            zf.writestr("sdkconfig", b"config")
            zf.writestr("version.json", version_json)

        with pytest.raises(ValidationException, match="Invalid firmware"):
            service.save_firmware(model_code, model.id, buf.getvalue())

    def test_save_firmware_zip_invalid_version_json(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that ZIP with malformed version.json raises ValidationException."""
        model_code = "badvjson"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        bin_content = create_test_firmware(b"1.0.0")

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"{model_code}.bin", bin_content)
            zf.writestr(f"{model_code}.elf", b"\x7fELF")
            zf.writestr(f"{model_code}.map", b"map")
            zf.writestr("sdkconfig", b"config")
            zf.writestr("version.json", b"not json")

        with pytest.raises(ValidationException, match="version.json is not valid JSON"):
            service.save_firmware(model_code, model.id, buf.getvalue())

    def test_save_firmware_zip_version_json_missing_fields(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that version.json missing required fields raises ValidationException."""
        model_code = "missfld"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        bin_content = create_test_firmware(b"1.0.0")

        version_json = json.dumps({
            "idf_version": "v5.0",
            "firmware_version": "1.0.0",
        }).encode()

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"{model_code}.bin", bin_content)
            zf.writestr(f"{model_code}.elf", b"\x7fELF")
            zf.writestr(f"{model_code}.map", b"map")
            zf.writestr("sdkconfig", b"config")
            zf.writestr("version.json", version_json)

        with pytest.raises(ValidationException, match="version.json missing fields.*git_commit"):
            service.save_firmware(model_code, model.id, buf.getvalue())

    def test_save_firmware_zip_not_a_zip(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that non-ZIP content raises ValidationException."""
        model = _create_model(session, "notzip")
        service = container.firmware_service()

        with pytest.raises(ValidationException, match="ZIP bundle"):
            service.save_firmware("notzip", model.id, b"not a zip file at all")

    def test_save_firmware_zip_overwrites_same_version(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that re-uploading the same version updates the record and S3."""
        model_code = "overwrite"
        model = _create_model(session, model_code)
        service = container.firmware_service()

        zip1 = _create_test_zip(model_code, b"1.0.0")
        zip2 = _create_test_zip(model_code, b"1.0.0")

        service.save_firmware(model_code, model.id, zip1)
        service.save_firmware(model_code, model.id, zip2)

        # Should still have exactly one firmware_versions record
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id
        )
        versions = session.execute(stmt).scalars().all()
        assert len(versions) == 1
        assert versions[0].version == "1.0.0"


class TestFirmwareServiceGetStream:
    """Tests for FirmwareService.get_firmware_stream() from S3."""

    def test_get_stream_from_s3(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that get_firmware_stream downloads .bin from S3."""
        model_code = "dlmodel"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(model_code, b"2.0.0")

        version = service.save_firmware(model_code, model.id, zip_content)

        stream = service.get_firmware_stream(model_code, firmware_version=version)
        bin_data = stream.read()

        # Should be a valid firmware binary
        extracted_version = service.extract_version(bin_data)
        assert extracted_version == "2.0.0"

    def test_get_stream_no_version_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that get_firmware_stream without version raises."""
        service = container.firmware_service()

        with pytest.raises(RecordNotFoundException):
            service.get_firmware_stream("nonexistent")

    def test_get_stream_nonexistent_raises(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that RecordNotFoundException is raised when firmware not in S3."""
        service = container.firmware_service()

        with pytest.raises(RecordNotFoundException):
            service.get_firmware_stream("nonexistent", firmware_version="1.0.0")


class TestFirmwareServiceDelete:
    """Tests for FirmwareService.delete_firmware()."""

    def test_delete_firmware_removes_s3_and_db(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that delete_firmware removes S3 objects and DB records."""
        model_code = "delmodel"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(model_code, b"1.0.0")

        service.save_firmware(model_code, model.id, zip_content)

        # Verify firmware exists
        s3 = container.s3_service()
        assert s3.file_exists(f"firmware/{model_code}/1.0.0/firmware.bin")

        service.delete_firmware(model_code, model.id)

        # Verify DB records deleted
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id
        )
        assert session.execute(stmt).scalar_one_or_none() is None

        # Verify S3 objects deleted
        assert not s3.file_exists(f"firmware/{model_code}/1.0.0/firmware.bin")

    def test_delete_firmware_no_firmware_no_error(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that deleting non-existent firmware does not raise."""
        model = _create_model(session, "nofwdel")
        service = container.firmware_service()
        service.delete_firmware("nofwdel", model.id)  # Should not raise


class TestFirmwareServiceExists:
    """Tests for FirmwareService.firmware_exists()."""

    def test_firmware_exists_after_upload(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test firmware_exists returns True after upload."""
        model_code = "existchk"
        model = _create_model(session, model_code)
        service = container.firmware_service()

        assert service.firmware_exists(model_code) is False

        zip_content = _create_test_zip(model_code, b"1.0.0")
        service.save_firmware(model_code, model.id, zip_content)

        assert service.firmware_exists(model_code) is True

    def test_firmware_exists_nothing(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test firmware_exists returns False when no firmware exists."""
        service = container.firmware_service()
        assert service.firmware_exists("nonexistent") is False


class TestFirmwareRetention:
    """Tests for firmware version retention (MAX_FIRMWARES)."""

    def test_retention_prunes_oldest(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that exceeding MAX_FIRMWARES prunes the oldest version."""
        model_code = "retprune"
        model = _create_model(session, model_code)

        # Create firmware service with max_firmwares=3
        s3_service = container.s3_service()
        service = FirmwareService(db=session, s3_service=s3_service, max_firmwares=3)

        # Upload 4 versions (oldest should be pruned)
        for i in range(4):
            version = f"1.0.{i}"
            zip_content = _create_test_zip(model_code, version.encode())
            service.save_firmware(model_code, model.id, zip_content)

        # Should have exactly 3 firmware_versions records
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id
        )
        versions = session.execute(stmt).scalars().all()
        assert len(versions) == 3

        # The oldest (1.0.0) should be gone
        version_strings = {v.version for v in versions}
        assert "1.0.0" not in version_strings
        assert "1.0.1" in version_strings
        assert "1.0.2" in version_strings
        assert "1.0.3" in version_strings

        # S3 objects for pruned version should be gone
        assert not s3_service.file_exists(f"firmware/{model_code}/1.0.0/firmware.bin")

    def test_retention_protects_pending_coredumps(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that versions referenced by PENDING coredumps are not pruned.

        With max_firmwares=2, we upload 2 versions, create a PENDING coredump
        referencing 2.0.0, then upload a 3rd version. Retention finds 1 excess
        (2.0.0) but skips it due to the PENDING coredump. Then we upload a 4th
        version: retention now has 2 excess (2.0.0, 2.0.1). 2.0.0 is still
        protected, so only 2.0.1 is pruned.
        """
        from app.models.device import Device

        model_code = "retpend"
        model = _create_model(session, model_code)

        # Create a device directly in the test session for the coredump FK
        device = Device(
            key="retpend1",
            device_model_id=model.id,
            config="{}",
            rotation_state="OK",
        )
        session.add(device)
        session.flush()

        s3_service = container.s3_service()
        service = FirmwareService(db=session, s3_service=s3_service, max_firmwares=2)

        # Upload 2 versions (within limit, no retention triggers)
        for i in range(2):
            version = f"2.0.{i}"
            zip_content = _create_test_zip(model_code, version.encode())
            service.save_firmware(model_code, model.id, zip_content)

        # Create a PENDING coredump referencing 2.0.0 BEFORE exceeding the limit
        coredump = CoreDump(
            device_id=device.id,
            chip="esp32s3",
            firmware_version="2.0.0",
            size=256,
            parse_status=ParseStatus.PENDING.value,
            uploaded_at=datetime.now(UTC),
        )
        session.add(coredump)
        session.flush()

        # Upload 3rd version -- retention has 1 excess: 2.0.0, but it is
        # protected by the PENDING coredump. All 3 remain.
        zip_content = _create_test_zip(model_code, b"2.0.2")
        service.save_firmware(model_code, model.id, zip_content)

        # Upload 4th version -- retention has 2 excess: 2.0.0 and 2.0.1.
        # 2.0.0 is protected, so only 2.0.1 is pruned.
        zip_content = _create_test_zip(model_code, b"2.0.3")
        service.save_firmware(model_code, model.id, zip_content)

        # Should have 3 versions (2.0.1 was pruned; 2.0.0 was protected)
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id
        )
        versions = session.execute(stmt).scalars().all()
        version_strings = {v.version for v in versions}

        # 2.0.0 is protected (PENDING coredump), 2.0.1 is pruned
        assert "2.0.0" in version_strings
        assert "2.0.1" not in version_strings
        assert "2.0.2" in version_strings
        assert "2.0.3" in version_strings

    def test_retention_all_protected_no_prune(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that no versions are pruned when all excess have PENDING coredumps."""
        from app.models.device import Device

        model_code = "retall"
        model = _create_model(session, model_code)

        # Create a device directly in the test session for coredump FK
        device = Device(
            key="retall01",
            device_model_id=model.id,
            config="{}",
            rotation_state="OK",
        )
        session.add(device)
        session.flush()

        s3_service = container.s3_service()
        service = FirmwareService(db=session, s3_service=s3_service, max_firmwares=2)

        # Upload 2 versions
        for i in range(2):
            version = f"3.0.{i}"
            zip_content = _create_test_zip(model_code, version.encode())
            service.save_firmware(model_code, model.id, zip_content)

        # Create PENDING coredumps for both versions
        for v in ["3.0.0", "3.0.1"]:
            coredump = CoreDump(
                device_id=device.id,
                chip="esp32",
                firmware_version=v,
                size=100,
                parse_status=ParseStatus.PENDING.value,
                uploaded_at=datetime.now(UTC),
            )
            session.add(coredump)
        session.flush()

        # Upload a 3rd version -- should try to prune but all are protected
        zip_content = _create_test_zip(model_code, b"3.0.2")
        service.save_firmware(model_code, model.id, zip_content)

        # All 3 versions should remain (both excess are protected)
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id
        )
        versions = session.execute(stmt).scalars().all()
        assert len(versions) == 3

    def test_retention_within_limit_no_prune(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that no pruning occurs when version count is within limit."""
        model_code = "retok"
        model = _create_model(session, model_code)
        service = container.firmware_service()

        # Upload 2 versions (default limit is 5)
        for i in range(2):
            version = f"4.0.{i}"
            zip_content = _create_test_zip(model_code, version.encode())
            service.save_firmware(model_code, model.id, zip_content)

        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id
        )
        versions = session.execute(stmt).scalars().all()
        assert len(versions) == 2
