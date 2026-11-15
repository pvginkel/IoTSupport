"""Seeds firmware versions for the Playwright suite, through the real firmware upload."""

import hashlib
import json
import struct
import zipfile
from io import BytesIO
from typing import TYPE_CHECKING

from app.services.firmware_service import APP_INFO_MAGIC

if TYPE_CHECKING:
    from app.models.device_model import DeviceModel
    from app.services.device_model_service import DeviceModelService

# The images a seeded build lists for flashing beside the app: (offset, file, size).
# The app sits at 0x20000, CalendarDisplay's offset, not the 0x10000 most builds use.
SEED_BOOTLOADER = (0x0, "bootloader/bootloader.bin", 0x1000)
SEED_PARTITION_TABLE = (0x8000, "partition_table/partition-table.bin", 0xC00)
SEED_OTADATA = (0xD000, "ota_data_initial.bin", 0x2000)
SEED_APP_OFFSET = 0x20000

SEED_FLASH_SETTINGS = {"flash_mode": "dio", "flash_size": "16MB", "flash_freq": "80m"}


class TestingFirmwareService:
    """Builds firmware ZIPs as the served upload script packs them, and uploads them."""

    def __init__(self, device_model_service: "DeviceModelService") -> None:
        """Initialize with the device model service whose upload stores the firmware.

        Args:
            device_model_service: Service whose upload_firmware stores the seeded ZIP
        """
        self.device_model_service = device_model_service

    def seed_firmware(
        self, model_id: int, version: str, flash_images: bool, chip: str
    ) -> "DeviceModel":
        """Upload a firmware version for a model, making it the model's current one.

        Args:
            model_id: Device model ID
            version: The firmware version the app image carries
            flash_images: Whether the ZIP carries the build's flash images, as
                every upload through the served upload script since they were
                packed does, or not, as every version stored before
            chip: The chip the build targets

        Returns:
            The device model, its firmware_version the seeded version

        Raises:
            RecordNotFoundException: If the model doesn't exist
        """
        model = self.device_model_service.get_device_model(model_id)
        content = build_firmware_zip(model.code, version, flash_images, chip)
        return self.device_model_service.upload_firmware(model_id, content)


def build_firmware_zip(model_code: str, version: str, flash_images: bool, chip: str) -> bytes:
    """Build a firmware ZIP as the served upload script packs it.

    Every image's content is distinct per model, version and file, and every
    size is a multiple of 4 bytes.
    """
    app_file = f"{model_code}.bin"
    files: dict[str, bytes] = {
        app_file: _app_image(version),
        f"{model_code}.elf": b"\x7fELF" + _filler(model_code, version, "elf", 256),
        f"{model_code}.map": b"Memory Map\n",
        "sdkconfig": f'CONFIG_IDF_TARGET="{chip}"\n'.encode(),
        "version.json": json.dumps({
            "git_commit": "0000000000000000000000000000000000000000",
            "idf_version": "v5.5.3",
            "firmware_version": version,
        }).encode(),
    }

    if flash_images:
        flash_files = {f"{SEED_APP_OFFSET:#x}": app_file}
        for offset, file, size in (SEED_BOOTLOADER, SEED_PARTITION_TABLE, SEED_OTADATA):
            flash_files[f"{offset:#x}"] = file
            files[file.rsplit("/", 1)[-1]] = _filler(model_code, version, file, size)
        files["flasher_args.json"] = json.dumps({
            "flash_settings": SEED_FLASH_SETTINGS,
            "flash_files": flash_files,
            "extra_esptool_args": {"chip": chip},
        }).encode()

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _app_image(version: str) -> bytes:
    """An app image whose AppInfo carries the version, as FirmwareService reads it."""
    # Image header (24 bytes) and first segment header (8 bytes), then the 256-byte AppInfo
    app_info = (
        struct.pack("<II", APP_INFO_MAGIC, 0)
        + bytes(8)
        + version.encode("utf-8").ljust(32, b"\x00")
        + b"seeded_firmware".ljust(32, b"\x00")
    )
    return bytes(32) + app_info.ljust(256, b"\x00")


def _filler(model_code: str, version: str, file: str, size: int) -> bytes:
    """Deterministic content of the given size, distinct per model, version and file."""
    block = hashlib.sha256(f"{model_code}/{version}/{file}".encode()).digest()
    return (block * (size // len(block) + 1))[:size]
