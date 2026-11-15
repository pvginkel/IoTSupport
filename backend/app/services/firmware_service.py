"""Firmware management service for device models.

Stores firmware artifacts in S3 and tracks versions in the database.
Individual artifacts are stored under firmware/{model_code}/{version}/
with generic names (firmware.bin, firmware.elf, firmware.map, sdkconfig,
version.json). A version uploaded with its build's flash images also holds
each image but the app under flash/, and flash.json, the FlashManifest that
lists every image with its offset.
"""

import json
import logging
import posixpath
import struct
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from itertools import pairwise
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, StringConstraints
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import RecordNotFoundException, ValidationException
from app.models.coredump import CoreDump, ParseStatus
from app.models.firmware_version import FirmwareVersion

if TYPE_CHECKING:
    from app.services.s3_service import S3Service

logger = logging.getLogger(__name__)

# ESP32 AppInfo structure constants
# The AppInfo structure is located at offset 32 in the firmware binary
# (24-byte image header + 8-byte segment header)
APP_INFO_OFFSET = 32

# Magic number 0xABCD5432 (little-endian) identifies valid AppInfo
APP_INFO_MAGIC = 0xABCD5432

# Version string is at offset 16 within the AppInfo structure
# (32 bytes total: offset 48-79 in the binary)
VERSION_OFFSET_IN_APPINFO = 16
VERSION_MAX_LENGTH = 32

# Minimum file size to contain valid AppInfo header
MIN_FIRMWARE_SIZE = APP_INFO_OFFSET + VERSION_OFFSET_IN_APPINFO + VERSION_MAX_LENGTH

# ZIP magic bytes (PK\x03\x04)
ZIP_MAGIC = b"\x50\x4b\x03\x04"

# Required files in a firmware ZIP (model_code is substituted at validation time)
REQUIRED_ZIP_FILES = {"{model_code}.bin", "{model_code}.elf", "{model_code}.map", "sdkconfig", "version.json"}

# The app image's member in a firmware ZIP
APP_ZIP_FILE = "{model_code}.bin"

# Mapping from model-specific filenames to generic S3 object names
ARTIFACT_RENAMES = {
    "{model_code}.bin": "firmware.bin",
    "{model_code}.elf": "firmware.elf",
    "{model_code}.map": "firmware.map",
    "sdkconfig": "sdkconfig",
    "version.json": "version.json",
}

# The build's flash manifest, which ESP-IDF writes to the build directory. A ZIP
# that carries it also carries every file it lists for flashing, by file name.
FLASHER_ARGS_FILE = "flasher_args.json"

# The stored flash set: the manifest and the directory of the images beside the app
FLASH_MANIFEST_ARTIFACT = "flash.json"
FLASH_IMAGES_DIR = "flash"


class _FlashSettings(BaseModel):
    flash_mode: str
    flash_size: str
    flash_freq: str


class _ExtraEsptoolArgs(BaseModel):
    chip: str


class _FlasherArgs(BaseModel):
    """The part of a build's flasher_args.json a flash needs."""

    flash_settings: _FlashSettings
    flash_files: dict[Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]+$")], str]
    extra_esptool_args: _ExtraEsptoolArgs


class FlashImage(BaseModel):
    """One image a flash of a firmware version writes."""

    offset: int
    file: str  # as the build names it, relative to its build directory
    artifact: str  # the S3 artifact under the version's prefix
    size: int


class FlashManifest(BaseModel):
    """Everything a flash of a firmware version writes, stored as flash.json."""

    chip: str
    flash_mode: str
    flash_size: str
    flash_freq: str
    images: list[FlashImage]  # ascending offset


@dataclass
class _FirmwareBundle:
    version: str
    files: dict[str, bytes]  # artifact name -> content, the flash images included
    flash_manifest: FlashManifest | None


def is_zip_content(content: bytes) -> bool:
    """Check if content starts with ZIP magic bytes.

    Args:
        content: Raw binary content

    Returns:
        True if the content starts with the ZIP magic header
    """
    return len(content) >= 4 and content[:4] == ZIP_MAGIC


class FirmwareService:
    """Service for managing firmware files stored in S3.

    Handles firmware upload (ZIP bundles only), download, version tracking,
    and retention pruning. Each firmware version is stored as individual
    artifacts in S3 under firmware/{model_code}/{version}/, its flash images
    among them when the upload carried them.

    This is a Factory service (request-scoped) because it needs DB access
    for firmware_versions tracking and coredump PENDING guard queries.
    """

    def __init__(self, db: Session, s3_service: "S3Service", max_firmwares: int) -> None:
        """Initialize firmware service.

        Args:
            db: SQLAlchemy database session (request-scoped)
            s3_service: S3 service for storage operations
            max_firmwares: Maximum firmware versions to retain per model
        """
        self.db = db
        self.s3_service = s3_service
        self.max_firmwares = max_firmwares

    def _s3_prefix(self, model_code: str, version: str) -> str:
        """Build the S3 key prefix for a firmware version."""
        return f"firmware/{model_code}/{version}/"

    def _s3_key(self, model_code: str, version: str, artifact: str) -> str:
        """Build a full S3 key for a specific artifact."""
        return f"firmware/{model_code}/{version}/{artifact}"

    def firmware_exists(self, model_code: str) -> bool:
        """Check if any firmware version exists for a model in the DB.

        Args:
            model_code: The device model code

        Returns:
            True if at least one firmware_versions record exists
        """
        from app.models.device_model import DeviceModel

        stmt = (
            select(FirmwareVersion)
            .join(DeviceModel)
            .where(DeviceModel.code == model_code)
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none() is not None

    def get_firmware_stream(
        self, model_code: str, firmware_version: str | None = None
    ) -> BytesIO:
        """Get firmware .bin as a BytesIO stream from S3.

        Args:
            model_code: The device model code
            firmware_version: Firmware version to download (required)

        Returns:
            BytesIO containing the firmware .bin data (seeked to position 0)

        Raises:
            RecordNotFoundException: If firmware doesn't exist in S3
        """
        if not firmware_version:
            raise RecordNotFoundException("Firmware", model_code)

        s3_key = self._s3_key(model_code, firmware_version, "firmware.bin")
        try:
            return self.s3_service.download_file(s3_key)
        except Exception as e:
            raise RecordNotFoundException("Firmware", model_code) from e

    def save_firmware(self, model_code: str, model_id: int, content: bytes) -> str:
        """Save a firmware ZIP bundle: validate, upload artifacts to S3, track version.

        The ZIP is validated, individual artifacts are renamed to generic names
        and uploaded to S3 under firmware/{model_code}/{version}/. A ZIP that
        carries the build's flasher_args.json stores its flash images and
        FlashManifest too; one without it stores a version without them. A
        firmware_versions DB record is created (upsert). Retention pruning
        is then applied.

        Golden rule: flush DB first, then upload to S3. If S3 fails, the
        transaction rolls back.

        Args:
            model_code: The device model code
            model_id: The device model DB ID (for firmware_versions FK)
            content: ZIP file content

        Returns:
            Extracted firmware version string

        Raises:
            ValidationException: If content is not a ZIP or ZIP structure is invalid
        """
        if not is_zip_content(content):
            raise ValidationException("Firmware must be uploaded as a ZIP bundle")

        # Validate ZIP structure and extract artifacts
        bundle = self._validate_and_extract_zip(model_code, content)
        version = bundle.version

        # Create or update firmware_versions record (flush to DB first -- golden rule)
        self._upsert_firmware_version(model_id, version)
        self.db.flush()

        # A re-upload replaces the stored flash set whole. The manifest is deleted
        # first and written last, so a version is flashable only while every image
        # it lists is in place.
        manifest_key = self._s3_key(model_code, version, FLASH_MANIFEST_ARTIFACT)
        self.s3_service.delete_file(manifest_key)
        self.s3_service.delete_prefix(self._s3_key(model_code, version, f"{FLASH_IMAGES_DIR}/"))

        # Upload each artifact to S3
        for artifact_name, artifact_data in bundle.files.items():
            s3_key = self._s3_key(model_code, version, artifact_name)
            self.s3_service.upload_file(
                BytesIO(artifact_data),
                s3_key,
                content_type="application/octet-stream",
            )

        if bundle.flash_manifest is not None:
            self.s3_service.upload_file(
                BytesIO(bundle.flash_manifest.model_dump_json().encode("utf-8")),
                manifest_key,
                content_type="application/json",
            )

        # Enforce retention (prune old versions)
        self._enforce_retention(model_id, model_code)

        logger.info(
            "Saved firmware for model %s, version %s (%d artifacts uploaded to S3, %s)",
            model_code,
            version,
            len(bundle.files),
            "flashable" if bundle.flash_manifest is not None else "without flash images",
        )

        return version

    def delete_firmware(self, model_code: str, model_id: int) -> None:
        """Delete all firmware for a model (DB records + S3 objects).

        DB records are deleted first, then S3 objects (best-effort).

        Args:
            model_code: The device model code
            model_id: The device model DB ID
        """
        # Delete all firmware_versions records for this model
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model_id
        )
        versions = self.db.execute(stmt).scalars().all()
        for fv in versions:
            self.db.delete(fv)
        self.db.flush()

        # Best-effort S3 prefix deletion
        prefix = f"firmware/{model_code}/"
        try:
            deleted = self.s3_service.delete_prefix(prefix)
            logger.info(
                "Deleted %d S3 objects for model %s firmware", deleted, model_code
            )
        except Exception as e:
            logger.warning(
                "Failed to delete S3 firmware for model %s: %s", model_code, e
            )

    def _validate_and_extract_zip(
        self, model_code: str, content: bytes
    ) -> _FirmwareBundle:
        """Validate a firmware ZIP and extract artifacts with generic names.

        Args:
            model_code: The device model code
            content: ZIP file content

        Returns:
            The version, its artifacts and, when the ZIP carries the build's
            flash images, their FlashManifest

        Raises:
            ValidationException: If ZIP structure is invalid
        """
        try:
            zf = zipfile.ZipFile(BytesIO(content), "r")
        except zipfile.BadZipFile as e:
            raise ValidationException(f"Invalid firmware ZIP: {e}") from e

        with zf:
            # Build the expected file set for this model
            expected_files = {
                name.format(model_code=model_code) for name in REQUIRED_ZIP_FILES
            }
            actual_files = set(zf.namelist())

            # The build's flasher_args.json brings every file it lists into the set
            flasher_args = None
            flash_members: dict[str, str] = {}
            if FLASHER_ARGS_FILE in actual_files:
                flasher_args = self._parse_flasher_args(zf.read(FLASHER_ARGS_FILE))
                flash_members = self._flash_members(model_code, flasher_args)
                expected_files |= {FLASHER_ARGS_FILE, *flash_members.values()}

            # Check for missing files
            missing = expected_files - actual_files
            if missing:
                raise ValidationException(
                    f"Invalid firmware ZIP: missing {', '.join(sorted(missing))}"
                )

            # Check for extra unexpected files
            extra = actual_files - expected_files
            if extra:
                raise ValidationException(
                    f"Invalid firmware ZIP: unexpected files: {', '.join(sorted(extra))}"
                )

            # Validate version.json
            try:
                version_json_data = json.loads(zf.read("version.json"))
            except (json.JSONDecodeError, KeyError) as e:
                raise ValidationException(
                    f"Invalid firmware ZIP: version.json is not valid JSON: {e}"
                ) from e

            required_fields = {"git_commit", "idf_version", "firmware_version"}
            missing_fields = required_fields - set(version_json_data.keys())
            if missing_fields:
                raise ValidationException(
                    f"Invalid firmware ZIP: version.json missing fields: {', '.join(sorted(missing_fields))}"
                )

            # Extract .bin and validate ESP32 format / extract version
            bin_name = f"{model_code}.bin"
            bin_content = zf.read(bin_name)
            version = self.extract_version(bin_content)

            # Build artifact map with generic names
            files: dict[str, bytes] = {}
            for zip_name_template, generic_name in ARTIFACT_RENAMES.items():
                zip_name = zip_name_template.format(model_code=model_code)
                files[generic_name] = zf.read(zip_name)

            flash_manifest = None
            if flasher_args is not None:
                flash_manifest = self._extract_flash_images(
                    zf, model_code, flasher_args, flash_members, files
                )

        return _FirmwareBundle(version=version, files=files, flash_manifest=flash_manifest)

    def _parse_flasher_args(self, content: bytes) -> _FlasherArgs:
        """Parse the build's flasher_args.json.

        Raises:
            ValidationException: If it is not JSON or lacks what a flash needs
        """
        try:
            return _FlasherArgs.model_validate_json(content)
        except PydanticValidationError as e:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in error['loc']) or 'document'}: {error['msg']}"
                for error in e.errors()
            )
            raise ValidationException(
                f"Invalid firmware ZIP: {FLASHER_ARGS_FILE} is invalid: {problems}"
            ) from e

    def _flash_members(self, model_code: str, flasher_args: _FlasherArgs) -> dict[str, str]:
        """Map each file the build lists for flashing to the ZIP member carrying it.

        A member is named after its file. The app is the ZIP's {model_code}.bin,
        which ESP-IDF names after the project, so the app a flash writes is the
        one /iot/firmware serves.

        Raises:
            ValidationException: If the build does not flash the app, or two
                members would share a name
        """
        app_file = APP_ZIP_FILE.format(model_code=model_code)
        if app_file not in flasher_args.flash_files.values():
            raise ValidationException(
                f"Invalid firmware ZIP: {FLASHER_ARGS_FILE} does not flash {app_file}"
            )

        taken = {name.format(model_code=model_code) for name in REQUIRED_ZIP_FILES}
        taken.add(FLASHER_ARGS_FILE)
        members = {app_file: app_file}
        for file in flasher_args.flash_files.values():
            if file in members:
                continue
            member = posixpath.basename(file)
            if member in taken:
                raise ValidationException(
                    f"Invalid firmware ZIP: flash file {file} shares its name with another member"
                )
            taken.add(member)
            members[file] = member
        return members

    def _extract_flash_images(
        self,
        zf: zipfile.ZipFile,
        model_code: str,
        flasher_args: _FlasherArgs,
        flash_members: dict[str, str],
        files: dict[str, bytes],
    ) -> FlashManifest:
        """Add the flash images to the artifacts and build their FlashManifest.

        Each image but the app is stored as flash/<offset>.bin; the app is
        firmware.bin, already among the artifacts.

        Raises:
            ValidationException: If an image is empty or two images overlap
        """
        app_file = APP_ZIP_FILE.format(model_code=model_code)
        images: list[FlashImage] = []
        for offset_text, file in flasher_args.flash_files.items():
            offset = int(offset_text, 16)
            data = zf.read(flash_members[file])
            if not data:
                raise ValidationException(f"Invalid firmware ZIP: flash image {file} is empty")

            if file == app_file:
                artifact = ARTIFACT_RENAMES[APP_ZIP_FILE]
            else:
                artifact = f"{FLASH_IMAGES_DIR}/{offset:#x}.bin"
                files[artifact] = data
            images.append(FlashImage(offset=offset, file=file, artifact=artifact, size=len(data)))

        images.sort(key=lambda image: image.offset)
        for before, after in pairwise(images):
            if before.offset + before.size > after.offset:
                raise ValidationException(
                    f"Invalid firmware ZIP: flash images overlap: {before.file} at "
                    f"{before.offset:#x} ({before.size} bytes) runs into {after.file} "
                    f"at {after.offset:#x}"
                )

        return FlashManifest(
            chip=flasher_args.extra_esptool_args.chip,
            flash_mode=flasher_args.flash_settings.flash_mode,
            flash_size=flasher_args.flash_settings.flash_size,
            flash_freq=flasher_args.flash_settings.flash_freq,
            images=images,
        )

    def _upsert_firmware_version(self, model_id: int, version: str) -> FirmwareVersion:
        """Create or update a firmware_versions record.

        Args:
            model_id: Device model DB ID
            version: Firmware version string

        Returns:
            The created or updated FirmwareVersion record
        """
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model_id,
            FirmwareVersion.version == version,
        )
        existing = self.db.execute(stmt).scalar_one_or_none()

        if existing is not None:
            existing.uploaded_at = datetime.now(UTC)
            return existing

        fv = FirmwareVersion(
            device_model_id=model_id,
            version=version,
            uploaded_at=datetime.now(UTC),
        )
        self.db.add(fv)
        return fv

    def _enforce_retention(self, model_id: int, model_code: str) -> None:
        """Prune firmware versions beyond MAX_FIRMWARES for a model.

        Versions referenced by PENDING coredumps are protected from pruning.

        Args:
            model_id: Device model DB ID
            model_code: Device model code (for S3 key construction)
        """
        # Get all versions ordered by uploaded_at descending (newest first)
        stmt = (
            select(FirmwareVersion)
            .where(FirmwareVersion.device_model_id == model_id)
            .order_by(FirmwareVersion.uploaded_at.desc())
        )
        all_versions = self.db.execute(stmt).scalars().all()

        if len(all_versions) <= self.max_firmwares:
            return

        # Identify excess versions (oldest beyond limit)
        excess = all_versions[self.max_firmwares:]
        pruned_count = 0
        skipped_pending = 0

        for fv in excess:
            # Check if any PENDING coredumps reference this version
            pending_stmt = (
                select(CoreDump)
                .where(
                    CoreDump.firmware_version == fv.version,
                    CoreDump.parse_status == ParseStatus.PENDING.value,
                )
                .limit(1)
            )
            has_pending = self.db.execute(pending_stmt).scalar_one_or_none() is not None

            if has_pending:
                skipped_pending += 1
                logger.info(
                    "Skipping retention prune of %s/%s: referenced by PENDING coredump",
                    model_code,
                    fv.version,
                )
                continue

            # Delete DB record
            self.db.delete(fv)
            pruned_count += 1

            # Best-effort S3 prefix deletion
            prefix = self._s3_prefix(model_code, fv.version)
            try:
                self.s3_service.delete_prefix(prefix)
            except Exception as e:
                logger.warning(
                    "Failed to delete S3 prefix %s: %s", prefix, e
                )

        if pruned_count > 0 or skipped_pending > 0:
            self.db.flush()
            logger.info(
                "Firmware retention for %s: pruned %d, skipped %d (PENDING coredumps)",
                model_code,
                pruned_count,
                skipped_pending,
            )

    def extract_version(self, content: bytes) -> str:
        """Extract firmware version from ESP32 binary.

        Parses the ESP-IDF AppInfo structure to extract the version string.

        Args:
            content: Firmware binary content

        Returns:
            Version string

        Raises:
            ValidationException: If firmware format is invalid
        """
        # Check minimum size
        if len(content) < MIN_FIRMWARE_SIZE:
            raise ValidationException(
                f"Invalid firmware: binary too short (minimum {MIN_FIRMWARE_SIZE} bytes required)"
            )

        # Read and verify magic number at AppInfo offset
        magic_offset = APP_INFO_OFFSET
        magic_bytes = content[magic_offset:magic_offset + 4]
        magic = struct.unpack("<I", magic_bytes)[0]

        if magic != APP_INFO_MAGIC:
            raise ValidationException(
                f"Invalid firmware: magic number mismatch (expected 0x{APP_INFO_MAGIC:08X}, "
                f"got 0x{magic:08X})"
            )

        # Extract version string from AppInfo structure
        version_start = APP_INFO_OFFSET + VERSION_OFFSET_IN_APPINFO
        version_end = version_start + VERSION_MAX_LENGTH
        version_bytes = content[version_start:version_end]

        # Decode as UTF-8 and strip null terminators
        try:
            version = version_bytes.split(b"\x00")[0].decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValidationException(
                f"Invalid firmware: cannot decode version string: {e}"
            ) from e

        if not version:
            raise ValidationException("Invalid firmware: empty version string")

        logger.debug("Extracted firmware version: %s", version)
        return version
