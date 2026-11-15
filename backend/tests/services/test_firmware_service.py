"""Tests for FirmwareService S3-based firmware storage and version tracking."""

import hashlib
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
from app.services.firmware_service import (
    FirmwareService,
    FlashImage,
    FlashManifest,
    is_zip_content,
)
from app.services.s3_service import S3Service
from tests.conftest import create_test_firmware

# A flash file as an ESP-IDF build lists it: (image name, offset, file)
FlashFile = tuple[str, str, str]


def _standard_flash_files(model_code: str) -> list[FlashFile]:
    """The flash files of every firmware build today, in flasher_args.json's order."""
    return [
        ("bootloader", "0x0", "bootloader/bootloader.bin"),
        ("app", "0x10000", f"{model_code}.bin"),
        ("partition-table", "0x8000", "partition_table/partition-table.bin"),
        ("otadata", "0xd000", "ota_data_initial.bin"),
    ]


def _flasher_args_json(flash_files: list[FlashFile], chip: str = "esp32s3") -> bytes:
    """Render flasher_args.json as ESP-IDF v5.5.3's flasher_args.json.in lays it out."""
    files = ",\n        ".join(f'"{offset}" : "{file}"' for _, offset, file in flash_files)
    entries = "".join(
        f'    "{name}" : {{ "offset" : "{offset}", "file" : "{file}", "encrypted" : "false" }},\n'
        for name, offset, file in flash_files
    )
    return (
        "{\n"
        '    "write_flash_args" : [ "--flash_mode", "dio",\n'
        '                           "--flash_size", "16MB",\n'
        '                           "--flash_freq", "80m" ],\n'
        '    "flash_settings" : {\n'
        '        "flash_mode": "dio",\n'
        '        "flash_size": "16MB",\n'
        '        "flash_freq": "80m"\n'
        "    },\n"
        '    "flash_files" : {\n'
        f"        {files}\n"
        "    },\n"
        f"{entries}"
        '    "extra_esptool_args" : {\n'
        '        "after"  : "hard_reset",\n'
        '        "before" : "default_reset",\n'
        '        "stub"   : true,\n'
        f'        "chip"   : "{chip}"\n'
        "    }\n"
        "}\n"
    ).encode()


def _flash_image(file: str) -> bytes:
    """Content for a flash image other than the app: 1 KiB, distinct per file."""
    return hashlib.sha256(file.encode("utf-8")).digest() * 32


def _stored_flash_manifest(s3: S3Service, model_code: str, version: str) -> FlashManifest | None:
    """The FlashManifest stored for a firmware version, or None."""
    key = f"firmware/{model_code}/{version}/flash.json"
    if not s3.file_exists(key):
        return None
    return FlashManifest.model_validate_json(s3.download_file(key).read())


def _stored_flash_images(s3: S3Service, model_code: str, version: str) -> list[str]:
    """The S3 keys under a firmware version's flash/ directory."""
    return sorted(s3.list_objects(f"firmware/{model_code}/{version}/flash/"))


def _create_test_zip(
    model_code: str,
    version: bytes,
    extra_files: dict[str, bytes] | None = None,
    omit_files: set[str] | None = None,
    flash_files: list[FlashFile] | None = None,
) -> bytes:
    """Create a valid firmware ZIP for testing.

    Args:
        model_code: Model code used in filenames
        version: Version bytes for the firmware binary
        extra_files: Additional files to include beyond the required set
        omit_files: Files to exclude from the required set
        flash_files: The build's flash files: adds its flasher_args.json and
            each image but the app, under its file name
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

    if flash_files is not None:
        files["flasher_args.json"] = _flasher_args_json(flash_files)
        for _, _, file in flash_files:
            if file != f"{model_code}.bin":
                files[file.rsplit("/", 1)[-1]] = _flash_image(file)

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


class TestFirmwareServiceFlashImages:
    """Tests for the build's flash images in FirmwareService.save_firmware()."""

    def test_save_firmware_stores_flash_images(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Every image the build lists is stored, with its offset and the flash settings."""
        model_code = "flashstore"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(
            model_code, b"1.2.0", flash_files=_standard_flash_files(model_code)
        )

        service.save_firmware(model_code, model.id, zip_content)

        s3 = container.s3_service()
        app_image = create_test_firmware(b"1.2.0")
        assert _stored_flash_manifest(s3, model_code, "1.2.0") == FlashManifest(
            chip="esp32s3",
            flash_mode="dio",
            flash_size="16MB",
            flash_freq="80m",
            images=[
                FlashImage(offset=0x0, file="bootloader/bootloader.bin", artifact="flash/0x0.bin", size=1024),
                FlashImage(offset=0x8000, file="partition_table/partition-table.bin", artifact="flash/0x8000.bin", size=1024),
                FlashImage(offset=0xD000, file="ota_data_initial.bin", artifact="flash/0xd000.bin", size=1024),
                FlashImage(offset=0x10000, file=f"{model_code}.bin", artifact="firmware.bin", size=len(app_image)),
            ],
        )
        prefix = f"firmware/{model_code}/1.2.0"
        assert s3.download_file(f"{prefix}/flash/0x0.bin").read() == _flash_image("bootloader/bootloader.bin")
        assert s3.download_file(f"{prefix}/flash/0x8000.bin").read() == _flash_image("partition_table/partition-table.bin")
        assert s3.download_file(f"{prefix}/flash/0xd000.bin").read() == _flash_image("ota_data_initial.bin")
        assert s3.download_file(f"{prefix}/firmware.bin").read() == app_image

    def test_save_firmware_stores_every_listed_image(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A build that lists more images than today's four brings them all."""
        model_code = "flashmore"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        flash_files = [
            *_standard_flash_files(model_code),
            ("storage", "0x310000", "storage.bin"),
            ("voice", "0x410000", "../models/voice.bin"),
        ]
        zip_content = _create_test_zip(model_code, b"1.0.0", flash_files=flash_files)

        service.save_firmware(model_code, model.id, zip_content)

        s3 = container.s3_service()
        manifest = _stored_flash_manifest(s3, model_code, "1.0.0")
        assert manifest is not None
        assert [(image.offset, image.file) for image in manifest.images] == [
            (0x0, "bootloader/bootloader.bin"),
            (0x8000, "partition_table/partition-table.bin"),
            (0xD000, "ota_data_initial.bin"),
            (0x10000, f"{model_code}.bin"),
            (0x310000, "storage.bin"),
            (0x410000, "../models/voice.bin"),
        ]
        prefix = f"firmware/{model_code}/1.0.0"
        assert s3.download_file(f"{prefix}/flash/0x410000.bin").read() == _flash_image("../models/voice.bin")

    def test_save_firmware_without_flash_images(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A five-member ZIP is stored as a version without flash images."""
        model_code = "flashnone"
        model = _create_model(session, model_code)
        service = container.firmware_service()

        version = service.save_firmware(model_code, model.id, _create_test_zip(model_code, b"1.0.0"))

        s3 = container.s3_service()
        assert version == "1.0.0"
        assert _stored_flash_manifest(s3, model_code, "1.0.0") is None
        assert _stored_flash_images(s3, model_code, "1.0.0") == []
        assert service.get_firmware_stream(model_code, "1.0.0").read() == create_test_firmware(b"1.0.0")

    def test_save_firmware_flash_image_missing(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A ZIP lacking an image its build lists is refused."""
        model_code = "flashmiss"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(
            model_code,
            b"1.0.0",
            flash_files=_standard_flash_files(model_code),
            omit_files={"partition-table.bin"},
        )

        with pytest.raises(ValidationException, match="missing partition-table.bin"):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_flash_images_without_flasher_args(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Flash images without the build's flasher_args.json are unexpected files."""
        model_code = "flashnoargs"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(
            model_code,
            b"1.0.0",
            flash_files=_standard_flash_files(model_code),
            omit_files={"flasher_args.json"},
        )

        with pytest.raises(
            ValidationException,
            match="unexpected files: bootloader.bin, ota_data_initial.bin, partition-table.bin",
        ):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_file_the_build_does_not_list(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A file beside the flash images that the build does not list is unexpected."""
        model_code = "flashunlisted"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(
            model_code,
            b"1.0.0",
            flash_files=_standard_flash_files(model_code),
            extra_files={"storage.bin": b"\x00" * 64},
        )

        with pytest.raises(ValidationException, match="unexpected files: storage.bin"):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_flasher_args_not_json(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A flasher_args.json that is not JSON is refused."""
        model_code = "flashbadjson"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(
            model_code,
            b"1.0.0",
            flash_files=_standard_flash_files(model_code),
            extra_files={"flasher_args.json": b"not json"},
        )

        with pytest.raises(ValidationException, match="flasher_args.json is invalid"):
            service.save_firmware(model_code, model.id, zip_content)

    @pytest.mark.parametrize(
        ("model_code", "drop"),
        [("flashnochip", "extra_esptool_args"), ("flashnosettings", "flash_settings")],
    )
    def test_save_firmware_flasher_args_incomplete(
        self, app: Flask, session: Session, container: ServiceContainer, model_code: str, drop: str
    ) -> None:
        """A flasher_args.json without the chip or the flash settings is refused."""
        model = _create_model(session, model_code)
        service = container.firmware_service()
        flasher_args = json.loads(_flasher_args_json(_standard_flash_files(model_code)))
        del flasher_args[drop]
        zip_content = _create_test_zip(
            model_code,
            b"1.0.0",
            flash_files=_standard_flash_files(model_code),
            extra_files={"flasher_args.json": json.dumps(flasher_args).encode("utf-8")},
        )

        with pytest.raises(ValidationException, match=f"flasher_args.json is invalid: {drop}: Field required"):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_flash_offset_invalid(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """An offset that is not hexadecimal is refused."""
        model_code = "flashbadoffset"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        flash_files = [
            ("bootloader", "0x0", "bootloader/bootloader.bin"),
            ("app", "65536", f"{model_code}.bin"),
        ]
        zip_content = _create_test_zip(model_code, b"1.0.0", flash_files=flash_files)

        with pytest.raises(ValidationException, match="flasher_args.json is invalid: flash_files.65536"):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_flash_files_without_app(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A build whose flash files leave out the app is refused."""
        model_code = "flashnoapp"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        flash_files = [
            ("bootloader", "0x0", "bootloader/bootloader.bin"),
            ("app", "0x10000", "other_project.bin"),
        ]
        zip_content = _create_test_zip(model_code, b"1.0.0", flash_files=flash_files)

        with pytest.raises(ValidationException, match="flasher_args.json does not flash flashnoapp.bin"):
            service.save_firmware(model_code, model.id, zip_content)

    @pytest.mark.parametrize("clash", ["spare/bootloader.bin", "data/sdkconfig"])
    def test_save_firmware_flash_files_share_a_name(
        self, app: Flask, session: Session, container: ServiceContainer, clash: str
    ) -> None:
        """Two flash files, or a flash file and a required file, cannot share a member."""
        model_code = f"flashclash{clash.split('/')[0]}"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        flash_files = [*_standard_flash_files(model_code), ("spare", "0x310000", clash)]
        zip_content = _create_test_zip(model_code, b"1.0.0", flash_files=flash_files)

        with pytest.raises(ValidationException, match=f"flash file {clash} shares its name"):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_flash_images_overlap(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Images whose extents overlap are refused."""
        model_code = "flashoverlap"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        flash_files = [
            ("bootloader", "0x0", "bootloader/bootloader.bin"),
            ("partition-table", "0x200", "partition_table/partition-table.bin"),
            ("app", "0x10000", f"{model_code}.bin"),
        ]
        zip_content = _create_test_zip(model_code, b"1.0.0", flash_files=flash_files)

        with pytest.raises(
            ValidationException,
            match="flash images overlap: bootloader/bootloader.bin at 0x0 \\(1024 bytes\\) "
            "runs into partition_table/partition-table.bin at 0x200",
        ):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_flash_image_empty(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """An empty image is refused."""
        model_code = "flashempty"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        zip_content = _create_test_zip(
            model_code,
            b"1.0.0",
            flash_files=_standard_flash_files(model_code),
            extra_files={"ota_data_initial.bin": b""},
        )

        with pytest.raises(ValidationException, match="flash image ota_data_initial.bin is empty"):
            service.save_firmware(model_code, model.id, zip_content)

    def test_save_firmware_reupload_without_flash_images(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Re-uploading a version without images leaves none of the earlier upload's."""
        model_code = "flashdrop"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        service.save_firmware(
            model_code,
            model.id,
            _create_test_zip(model_code, b"1.0.0", flash_files=_standard_flash_files(model_code)),
        )

        service.save_firmware(model_code, model.id, _create_test_zip(model_code, b"1.0.0"))

        s3 = container.s3_service()
        assert _stored_flash_manifest(s3, model_code, "1.0.0") is None
        assert _stored_flash_images(s3, model_code, "1.0.0") == []

    def test_save_firmware_reupload_with_other_flash_images(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Re-uploading a version with images replaces the earlier upload's set whole."""
        model_code = "flashreplace"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        service.save_firmware(
            model_code,
            model.id,
            _create_test_zip(
                model_code,
                b"1.0.0",
                flash_files=[*_standard_flash_files(model_code), ("storage", "0x310000", "storage.bin")],
            ),
        )

        service.save_firmware(
            model_code,
            model.id,
            _create_test_zip(model_code, b"1.0.0", flash_files=_standard_flash_files(model_code)),
        )

        s3 = container.s3_service()
        manifest = _stored_flash_manifest(s3, model_code, "1.0.0")
        assert manifest is not None
        assert [image.offset for image in manifest.images] == [0x0, 0x8000, 0xD000, 0x10000]
        prefix = f"firmware/{model_code}/1.0.0/flash"
        assert _stored_flash_images(s3, model_code, "1.0.0") == [
            f"{prefix}/0x0.bin",
            f"{prefix}/0x8000.bin",
            f"{prefix}/0xd000.bin",
        ]

    def test_save_firmware_refused_upload_keeps_flash_images(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A refused re-upload leaves the stored version flashable as it was."""
        model_code = "flashkeep"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        service.save_firmware(
            model_code,
            model.id,
            _create_test_zip(model_code, b"1.0.0", flash_files=_standard_flash_files(model_code)),
        )
        s3 = container.s3_service()
        stored = _stored_flash_manifest(s3, model_code, "1.0.0")

        with pytest.raises(ValidationException):
            service.save_firmware(
                model_code,
                model.id,
                _create_test_zip(
                    model_code,
                    b"1.0.0",
                    flash_files=_standard_flash_files(model_code),
                    omit_files={"bootloader.bin"},
                ),
            )

        assert stored is not None
        assert _stored_flash_manifest(s3, model_code, "1.0.0") == stored
        assert len(_stored_flash_images(s3, model_code, "1.0.0")) == 3


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

    def test_delete_firmware_removes_flash_images(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Deleting a model's firmware takes its versions' flash images along."""
        model_code = "delflash"
        model = _create_model(session, model_code)
        service = container.firmware_service()
        service.save_firmware(
            model_code,
            model.id,
            _create_test_zip(model_code, b"1.0.0", flash_files=_standard_flash_files(model_code)),
        )

        service.delete_firmware(model_code, model.id)

        s3 = container.s3_service()
        assert _stored_flash_manifest(s3, model_code, "1.0.0") is None
        assert _stored_flash_images(s3, model_code, "1.0.0") == []

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

    def test_retention_prunes_flash_images(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A pruned version's flash images go with it; a kept version keeps its own."""
        model_code = "retflash"
        model = _create_model(session, model_code)
        s3_service = container.s3_service()
        service = FirmwareService(db=session, s3_service=s3_service, max_firmwares=1)

        for version in ("1.0.0", "1.0.1"):
            service.save_firmware(
                model_code,
                model.id,
                _create_test_zip(model_code, version.encode(), flash_files=_standard_flash_files(model_code)),
            )

        assert _stored_flash_manifest(s3_service, model_code, "1.0.0") is None
        assert _stored_flash_images(s3_service, model_code, "1.0.0") == []
        assert _stored_flash_manifest(s3_service, model_code, "1.0.1") is not None
        assert len(_stored_flash_images(s3_service, model_code, "1.0.1")) == 3

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
