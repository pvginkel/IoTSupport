"""Tests for CoredumpService."""

import json
from pathlib import Path

import pytest

from app.exceptions import InvalidOperationException, ValidationException
from app.services.coredump_service import MAX_COREDUMP_SIZE, CoredumpService


class TestCoredumpServiceSave:
    """Tests for CoredumpService.save_coredump()."""

    def test_save_coredump_creates_files(self, tmp_path: Path) -> None:
        """Test that save_coredump creates both .dmp and .json sidecar files."""
        service = CoredumpService(coredumps_dir=tmp_path)
        content = b"\x00" * 256

        filename = service.save_coredump(
            device_key="abc12345",
            model_code="tempsensor",
            chip="esp32s3",
            firmware_version="1.2.3",
            content=content,
        )

        # Verify .dmp file exists and has correct content
        assert filename.startswith("coredump_")
        assert filename.endswith(".dmp")

        dmp_path = tmp_path / "abc12345" / filename
        assert dmp_path.exists()
        assert dmp_path.read_bytes() == content

        # Verify .json sidecar exists with correct metadata
        json_path = dmp_path.with_suffix(".json")
        assert json_path.exists()

        sidecar = json.loads(json_path.read_text())
        assert sidecar["chip"] == "esp32s3"
        assert sidecar["firmware_version"] == "1.2.3"
        assert sidecar["device_key"] == "abc12345"
        assert sidecar["model_code"] == "tempsensor"
        assert "uploaded_at" in sidecar

    def test_save_coredump_creates_device_directory(self, tmp_path: Path) -> None:
        """Test that save_coredump creates the per-device directory if it does not exist."""
        service = CoredumpService(coredumps_dir=tmp_path)
        content = b"\x01\x02\x03"

        device_dir = tmp_path / "newdev01"
        assert not device_dir.exists()

        service.save_coredump(
            device_key="newdev01",
            model_code="relay_4ch",
            chip="esp32",
            firmware_version="0.9.0",
            content=content,
        )

        assert device_dir.exists()
        assert device_dir.is_dir()

    def test_save_coredump_empty_content_raises(self, tmp_path: Path) -> None:
        """Test that empty content raises ValidationException."""
        service = CoredumpService(coredumps_dir=tmp_path)

        with pytest.raises(ValidationException, match="No coredump content provided"):
            service.save_coredump(
                device_key="abc12345",
                model_code="tempsensor",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"",
            )

    def test_save_coredump_exceeds_max_size_raises(self, tmp_path: Path) -> None:
        """Test that content exceeding 1MB raises ValidationException."""
        service = CoredumpService(coredumps_dir=tmp_path)
        oversized = b"\x00" * (MAX_COREDUMP_SIZE + 1)

        with pytest.raises(ValidationException, match="exceeds maximum size of 1MB"):
            service.save_coredump(
                device_key="abc12345",
                model_code="tempsensor",
                chip="esp32s3",
                firmware_version="1.0.0",
                content=oversized,
            )

    def test_save_coredump_exactly_max_size_succeeds(self, tmp_path: Path) -> None:
        """Test that content exactly at 1MB limit is accepted."""
        service = CoredumpService(coredumps_dir=tmp_path)
        content = b"\x00" * MAX_COREDUMP_SIZE

        filename = service.save_coredump(
            device_key="abc12345",
            model_code="tempsensor",
            chip="esp32s3",
            firmware_version="1.0.0",
            content=content,
        )

        assert filename.endswith(".dmp")
        dmp_path = tmp_path / "abc12345" / filename
        assert dmp_path.exists()
        assert len(dmp_path.read_bytes()) == MAX_COREDUMP_SIZE

    def test_save_coredump_no_coredumps_dir_raises(self) -> None:
        """Test that saving when coredumps_dir is None raises InvalidOperationException."""
        service = CoredumpService(coredumps_dir=None)

        with pytest.raises(InvalidOperationException, match="COREDUMPS_DIR is not configured"):
            service.save_coredump(
                device_key="abc12345",
                model_code="tempsensor",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00" * 10,
            )

    def test_save_coredump_sidecar_has_correct_uploaded_at(self, tmp_path: Path) -> None:
        """Test that the JSON sidecar uploaded_at is a valid ISO 8601 timestamp."""
        from datetime import datetime

        service = CoredumpService(coredumps_dir=tmp_path)

        filename = service.save_coredump(
            device_key="abc12345",
            model_code="tempsensor",
            chip="esp32",
            firmware_version="1.0.0",
            content=b"\xDE\xAD\xBE\xEF",
        )

        json_path = tmp_path / "abc12345" / filename.replace(".dmp", ".json")
        sidecar = json.loads(json_path.read_text())

        # Verify uploaded_at parses as valid ISO 8601
        uploaded_at = datetime.fromisoformat(sidecar["uploaded_at"])
        assert uploaded_at is not None

    def test_save_coredump_unique_filenames(self, tmp_path: Path) -> None:
        """Test that consecutive saves produce unique filenames."""
        service = CoredumpService(coredumps_dir=tmp_path)

        filenames = set()
        for _ in range(5):
            filename = service.save_coredump(
                device_key="abc12345",
                model_code="tempsensor",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00",
            )
            filenames.add(filename)

        # All filenames should be unique (microsecond precision)
        assert len(filenames) == 5

    def test_save_coredump_invalid_device_key_raises(self, tmp_path: Path) -> None:
        """Test that a non-alphanumeric device key raises ValidationException."""
        service = CoredumpService(coredumps_dir=tmp_path)

        with pytest.raises(ValidationException, match="Invalid device key format"):
            service.save_coredump(
                device_key="../../etc",
                model_code="tempsensor",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00" * 10,
            )

    def test_save_coredump_device_key_with_special_chars_raises(self, tmp_path: Path) -> None:
        """Test that device keys with special characters are rejected."""
        service = CoredumpService(coredumps_dir=tmp_path)

        with pytest.raises(ValidationException, match="Invalid device key format"):
            service.save_coredump(
                device_key="abc-1234",
                model_code="tempsensor",
                chip="esp32",
                firmware_version="1.0.0",
                content=b"\x00" * 10,
            )

    def test_save_coredump_multiple_devices(self, tmp_path: Path) -> None:
        """Test that coredumps from different devices go to separate directories."""
        service = CoredumpService(coredumps_dir=tmp_path)

        service.save_coredump(
            device_key="device01",
            model_code="tempsensor",
            chip="esp32",
            firmware_version="1.0.0",
            content=b"\x01",
        )
        service.save_coredump(
            device_key="device02",
            model_code="relay_4ch",
            chip="esp32s3",
            firmware_version="2.0.0",
            content=b"\x02",
        )

        assert (tmp_path / "device01").is_dir()
        assert (tmp_path / "device02").is_dir()
        assert len(list((tmp_path / "device01").glob("*.dmp"))) == 1
        assert len(list((tmp_path / "device02").glob("*.dmp"))) == 1


class TestCoredumpServiceInit:
    """Tests for CoredumpService initialization."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that initialization creates the coredumps directory."""
        coredumps_dir = tmp_path / "new_coredumps"
        assert not coredumps_dir.exists()

        CoredumpService(coredumps_dir=coredumps_dir)

        assert coredumps_dir.exists()
        assert coredumps_dir.is_dir()

    def test_init_with_none_does_not_fail(self) -> None:
        """Test that initialization with None coredumps_dir does not raise."""
        service = CoredumpService(coredumps_dir=None)
        assert service.coredumps_dir is None
