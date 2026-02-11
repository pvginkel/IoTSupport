"""Tests for FirmwareService ZIP support and versioned storage."""

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from app.exceptions import RecordNotFoundException, ValidationException
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


class TestFirmwareServiceZipSave:
    """Tests for FirmwareService.save_firmware_zip()."""

    def test_save_firmware_zip_valid(self, tmp_path: Path) -> None:
        """Test saving a valid firmware ZIP creates versioned ZIP and legacy .bin."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"
        zip_content = _create_test_zip(model_code, b"1.2.3")

        version = service.save_firmware_zip(model_code, zip_content)

        assert version == "1.2.3"

        # Versioned ZIP should exist
        zip_path = tmp_path / model_code / "firmware-1.2.3.zip"
        assert zip_path.exists()

        # Legacy flat .bin should also be updated
        legacy_path = tmp_path / f"firmware-{model_code}.bin"
        assert legacy_path.exists()

        # Verify the legacy .bin has valid ESP32 header
        bin_data = legacy_path.read_bytes()
        extracted_version = service.extract_version(bin_data)
        assert extracted_version == "1.2.3"

    def test_save_firmware_zip_missing_elf(self, tmp_path: Path) -> None:
        """Test that ZIP missing .elf file raises ValidationException."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"
        zip_content = _create_test_zip(model_code, b"1.0.0", omit_files={f"{model_code}.elf"})

        with pytest.raises(ValidationException, match="missing.*elf"):
            service.save_firmware_zip(model_code, zip_content)

    def test_save_firmware_zip_missing_map(self, tmp_path: Path) -> None:
        """Test that ZIP missing .map file raises ValidationException."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"
        zip_content = _create_test_zip(model_code, b"1.0.0", omit_files={f"{model_code}.map"})

        with pytest.raises(ValidationException, match="missing.*map"):
            service.save_firmware_zip(model_code, zip_content)

    def test_save_firmware_zip_missing_sdkconfig(self, tmp_path: Path) -> None:
        """Test that ZIP missing sdkconfig file raises ValidationException."""
        service = FirmwareService(assets_dir=tmp_path)
        zip_content = _create_test_zip("tempsensor", b"1.0.0", omit_files={"sdkconfig"})

        with pytest.raises(ValidationException, match="missing.*sdkconfig"):
            service.save_firmware_zip("tempsensor", zip_content)

    def test_save_firmware_zip_missing_version_json(self, tmp_path: Path) -> None:
        """Test that ZIP missing version.json raises ValidationException."""
        service = FirmwareService(assets_dir=tmp_path)
        zip_content = _create_test_zip("tempsensor", b"1.0.0", omit_files={"version.json"})

        with pytest.raises(ValidationException, match="missing.*version.json"):
            service.save_firmware_zip("tempsensor", zip_content)

    def test_save_firmware_zip_missing_bin(self, tmp_path: Path) -> None:
        """Test that ZIP missing .bin file raises ValidationException."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"
        zip_content = _create_test_zip(model_code, b"1.0.0", omit_files={f"{model_code}.bin"})

        with pytest.raises(ValidationException, match="missing.*bin"):
            service.save_firmware_zip(model_code, zip_content)

    def test_save_firmware_zip_extra_files(self, tmp_path: Path) -> None:
        """Test that ZIP with extra unexpected files raises ValidationException."""
        service = FirmwareService(assets_dir=tmp_path)
        zip_content = _create_test_zip(
            "tempsensor", b"1.0.0",
            extra_files={"unexpected.txt": b"oops"}
        )

        with pytest.raises(ValidationException, match="unexpected files.*unexpected.txt"):
            service.save_firmware_zip("tempsensor", zip_content)

    def test_save_firmware_zip_invalid_bin(self, tmp_path: Path) -> None:
        """Test that ZIP with invalid .bin raises ValidationException."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"

        # Build a ZIP with garbage in place of the .bin
        version_json = json.dumps({
            "git_commit": "abc123",
            "idf_version": "v5.0",
            "firmware_version": "1.0.0",
        }).encode()

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"{model_code}.bin", b"\x00" * 10)  # Invalid binary
            zf.writestr(f"{model_code}.elf", b"\x7fELF")
            zf.writestr(f"{model_code}.map", b"map")
            zf.writestr("sdkconfig", b"config")
            zf.writestr("version.json", version_json)

        with pytest.raises(ValidationException, match="Invalid firmware"):
            service.save_firmware_zip(model_code, buf.getvalue())

    def test_save_firmware_zip_invalid_version_json(self, tmp_path: Path) -> None:
        """Test that ZIP with malformed version.json raises ValidationException."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"
        bin_content = create_test_firmware(b"1.0.0")

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"{model_code}.bin", bin_content)
            zf.writestr(f"{model_code}.elf", b"\x7fELF")
            zf.writestr(f"{model_code}.map", b"map")
            zf.writestr("sdkconfig", b"config")
            zf.writestr("version.json", b"not json")

        with pytest.raises(ValidationException, match="version.json is not valid JSON"):
            service.save_firmware_zip(model_code, buf.getvalue())

    def test_save_firmware_zip_version_json_missing_fields(self, tmp_path: Path) -> None:
        """Test that version.json missing required fields raises ValidationException."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"
        bin_content = create_test_firmware(b"1.0.0")

        # version.json missing git_commit
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
            service.save_firmware_zip(model_code, buf.getvalue())

    def test_save_firmware_zip_not_a_zip(self, tmp_path: Path) -> None:
        """Test that non-ZIP content raises ValidationException."""
        service = FirmwareService(assets_dir=tmp_path)

        with pytest.raises(ValidationException, match="Invalid firmware ZIP"):
            service.save_firmware_zip("tempsensor", b"not a zip file at all")

    def test_save_firmware_zip_overwrites_same_version(self, tmp_path: Path) -> None:
        """Test that re-uploading the same version overwrites the ZIP."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"

        zip1 = _create_test_zip(model_code, b"1.0.0")
        zip2 = _create_test_zip(model_code, b"1.0.0")

        service.save_firmware_zip(model_code, zip1)
        service.save_firmware_zip(model_code, zip2)

        # Should still exist without error
        zip_path = tmp_path / model_code / "firmware-1.0.0.zip"
        assert zip_path.exists()


class TestFirmwareServiceGetStream:
    """Tests for FirmwareService.get_firmware_stream() with ZIP fallback."""

    def test_get_stream_from_versioned_zip(self, tmp_path: Path) -> None:
        """Test that get_firmware_stream extracts .bin from versioned ZIP when available."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"
        zip_content = _create_test_zip(model_code, b"2.0.0")

        version = service.save_firmware_zip(model_code, zip_content)

        stream = service.get_firmware_stream(model_code, firmware_version=version)
        bin_data = stream.read()

        # Should be a valid firmware binary
        extracted_version = service.extract_version(bin_data)
        assert extracted_version == "2.0.0"

    def test_get_stream_falls_back_to_legacy_bin(self, tmp_path: Path) -> None:
        """Test that get_firmware_stream falls back to legacy .bin when no ZIP exists."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"

        # Save only a legacy .bin (no ZIP)
        bin_content = create_test_firmware(b"1.0.0")
        service.save_firmware(model_code, bin_content)

        # Request with a version that has no ZIP
        stream = service.get_firmware_stream(model_code, firmware_version="1.0.0")
        data = stream.read()
        assert data == bin_content

    def test_get_stream_no_version_uses_legacy(self, tmp_path: Path) -> None:
        """Test that get_firmware_stream with no firmware_version uses legacy .bin."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"

        bin_content = create_test_firmware(b"1.0.0")
        service.save_firmware(model_code, bin_content)

        stream = service.get_firmware_stream(model_code)
        assert stream.read() == bin_content

    def test_get_stream_neither_zip_nor_legacy_raises(self, tmp_path: Path) -> None:
        """Test that RecordNotFoundException is raised when no firmware exists."""
        service = FirmwareService(assets_dir=tmp_path)

        with pytest.raises(RecordNotFoundException):
            service.get_firmware_stream("nonexistent")

    def test_get_stream_version_provided_no_zip_falls_back(self, tmp_path: Path) -> None:
        """Test fallback when firmware_version is given but no ZIP exists."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"

        # Only legacy .bin, no ZIP for this version
        bin_content = create_test_firmware(b"1.0.0")
        service.save_firmware(model_code, bin_content)

        stream = service.get_firmware_stream(model_code, firmware_version="999.0.0")
        assert stream.read() == bin_content

    def test_get_stream_version_provided_no_zip_no_legacy_raises(self, tmp_path: Path) -> None:
        """Test that error is raised when version given but neither ZIP nor legacy exist."""
        service = FirmwareService(assets_dir=tmp_path)

        with pytest.raises(RecordNotFoundException):
            service.get_firmware_stream("nonexistent", firmware_version="1.0.0")


class TestFirmwareServiceDelete:
    """Tests for FirmwareService.delete_firmware()."""

    def test_delete_firmware_removes_legacy_bin(self, tmp_path: Path) -> None:
        """Test that delete_firmware removes the legacy .bin file."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"

        bin_content = create_test_firmware(b"1.0.0")
        service.save_firmware(model_code, bin_content)
        assert service.get_firmware_path(model_code).exists()

        service.delete_firmware(model_code)
        assert not service.get_firmware_path(model_code).exists()

    def test_delete_firmware_removes_versioned_zip_directory(self, tmp_path: Path) -> None:
        """Test that delete_firmware removes the versioned ZIP directory."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"

        zip_content = _create_test_zip(model_code, b"1.0.0")
        service.save_firmware_zip(model_code, zip_content)

        # Both legacy and versioned should exist
        assert service.get_firmware_path(model_code).exists()
        model_dir = tmp_path / model_code
        assert model_dir.exists()

        service.delete_firmware(model_code)

        # Both should be gone
        assert not service.get_firmware_path(model_code).exists()
        assert not model_dir.exists()

    def test_delete_firmware_no_file_no_error(self, tmp_path: Path) -> None:
        """Test that deleting non-existent firmware does not raise."""
        service = FirmwareService(assets_dir=tmp_path)
        service.delete_firmware("nonexistent")  # Should not raise


class TestFirmwareServiceExists:
    """Tests for FirmwareService.firmware_exists()."""

    def test_firmware_exists_legacy_only(self, tmp_path: Path) -> None:
        """Test firmware_exists returns True when only legacy .bin exists."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"

        bin_content = create_test_firmware(b"1.0.0")
        service.save_firmware(model_code, bin_content)

        assert service.firmware_exists(model_code) is True

    def test_firmware_exists_versioned_zip_only(self, tmp_path: Path) -> None:
        """Test firmware_exists returns True when only versioned ZIP exists (no legacy)."""
        service = FirmwareService(assets_dir=tmp_path)
        model_code = "tempsensor"

        # Manually create only the versioned ZIP (no legacy .bin)
        zip_content = _create_test_zip(model_code, b"1.0.0")
        service.save_firmware_zip(model_code, zip_content)

        # Remove the legacy .bin to simulate a ZIP-only scenario
        service.get_firmware_path(model_code).unlink()
        assert not service.get_firmware_path(model_code).exists()

        # firmware_exists should still return True via the versioned ZIP
        assert service.firmware_exists(model_code) is True

    def test_firmware_exists_nothing(self, tmp_path: Path) -> None:
        """Test firmware_exists returns False when no firmware exists."""
        service = FirmwareService(assets_dir=tmp_path)
        assert service.firmware_exists("nonexistent") is False
