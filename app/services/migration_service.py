"""One-time migration service for filesystem-to-S3 data migration.

Moves firmware ZIPs and coredump .dmp files from legacy filesystem
directories (ASSETS_DIR, COREDUMPS_DIR) to S3-compatible storage.

This service is used by the CLI `migrate-to-s3` command and is not
registered in the DI container (it is instantiated directly by the CLI).
"""

import logging
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.coredump import CoreDump
from app.models.device import Device
from app.models.device_model import DeviceModel
from app.models.firmware_version import FirmwareVersion
from app.services.firmware_service import ARTIFACT_RENAMES

if TYPE_CHECKING:
    from app.services.s3_service import S3Service

logger = logging.getLogger(__name__)


class MigrationService:
    """Service for migrating firmware and coredump files from filesystem to S3.

    This is a one-time migration utility. It reads legacy filesystem paths
    and uploads data to S3, creating the corresponding DB records where needed.
    """

    def __init__(
        self,
        s3_service: "S3Service",
        db: Session,
        assets_dir: Path | None,
        coredumps_dir: Path | None,
        dry_run: bool = False,
    ) -> None:
        self.s3_service = s3_service
        self.db = db
        self.assets_dir = assets_dir
        self.coredumps_dir = coredumps_dir
        self.dry_run = dry_run
        self.warnings: list[str] = []

    def run(self) -> dict[str, Any]:
        """Run the full migration.

        Returns:
            Summary dict with counts and warnings.
        """
        firmware_zips = 0
        firmware_skipped = 0
        coredumps_migrated = 0
        coredumps_skipped = 0

        # Phase 1: Migrate firmware ZIPs
        if self.assets_dir and self.assets_dir.exists():
            fw_result = self._migrate_firmware()
            firmware_zips = fw_result["migrated"]
            firmware_skipped = fw_result["skipped"]
        else:
            logger.info("ASSETS_DIR not set or does not exist, skipping firmware migration")

        # Phase 2: Migrate coredumps
        if self.coredumps_dir and self.coredumps_dir.exists():
            cd_result = self._migrate_coredumps()
            coredumps_migrated = cd_result["migrated"]
            coredumps_skipped = cd_result["skipped"]
        else:
            logger.info("COREDUMPS_DIR not set or does not exist, skipping coredump migration")

        return {
            "firmware_zips": firmware_zips,
            "firmware_skipped": firmware_skipped,
            "coredumps_migrated": coredumps_migrated,
            "coredumps_skipped": coredumps_skipped,
            "warnings": self.warnings,
        }

    def _migrate_firmware(self) -> dict[str, int]:
        """Migrate firmware ZIPs from ASSETS_DIR to S3.

        Iterates model code directories under ASSETS_DIR. For each versioned
        ZIP file (firmware-{version}.zip), extracts artifacts, renames to
        generic names, and uploads to S3. Creates firmware_versions DB records.

        Returns:
            Dict with 'migrated' and 'skipped' counts.
        """
        assert self.assets_dir is not None
        migrated = 0
        skipped = 0

        for model_dir in sorted(self.assets_dir.iterdir()):
            if not model_dir.is_dir():
                # Skip non-directory entries (e.g., legacy flat .bin files)
                if model_dir.suffix == ".bin":
                    logger.info("Skipping legacy flat binary: %s", model_dir.name)
                    skipped += 1
                continue

            model_code = model_dir.name

            # Verify model exists in DB
            stmt = select(DeviceModel).where(DeviceModel.code == model_code)
            model = self.db.execute(stmt).scalar_one_or_none()
            if model is None:
                warning = f"Model directory '{model_code}' has no matching DB record, skipping"
                self.warnings.append(warning)
                logger.warning(warning)
                skipped += 1
                continue

            # Process ZIP files in model directory
            for zip_path in sorted(model_dir.glob("firmware-*.zip")):
                version = self._extract_version_from_zip_name(zip_path.name)
                if version is None:
                    warning = f"Cannot parse version from ZIP filename: {zip_path.name}"
                    self.warnings.append(warning)
                    logger.warning(warning)
                    skipped += 1
                    continue

                logger.info("Migrating firmware: %s/%s", model_code, version)

                if self.dry_run:
                    print(f"  [DRY RUN] Would migrate firmware: {model_code}/{version}")
                    migrated += 1
                    continue

                try:
                    self._upload_firmware_zip(model_code, model.id, zip_path, version)
                    migrated += 1
                except Exception as e:
                    warning = f"Failed to migrate firmware {model_code}/{version}: {e}"
                    self.warnings.append(warning)
                    logger.error(warning)
                    skipped += 1

        self.db.flush()
        logger.info("Firmware migration: %d migrated, %d skipped", migrated, skipped)
        return {"migrated": migrated, "skipped": skipped}

    def _extract_version_from_zip_name(self, filename: str) -> str | None:
        """Extract version from ZIP filename like 'firmware-1.2.3.zip'.

        Returns:
            Version string, or None if filename doesn't match expected pattern.
        """
        # Expected format: firmware-{version}.zip
        if not filename.startswith("firmware-") or not filename.endswith(".zip"):
            return None
        return filename[len("firmware-"):-len(".zip")]

    def _upload_firmware_zip(
        self, model_code: str, model_id: int, zip_path: Path, version: str
    ) -> None:
        """Extract artifacts from a firmware ZIP and upload to S3.

        Also creates a firmware_versions DB record (upsert).
        """
        content = zip_path.read_bytes()

        try:
            zf = zipfile.ZipFile(BytesIO(content), "r")
        except zipfile.BadZipFile as e:
            raise ValueError(f"Invalid ZIP file {zip_path}: {e}") from e

        with zf:
            actual_files = set(zf.namelist())

            # Upload each artifact that exists in the ZIP (tolerant of
            # legacy ZIPs that may be missing optional files)
            for zip_name_template, generic_name in ARTIFACT_RENAMES.items():
                zip_name = zip_name_template.format(model_code=model_code)
                if zip_name not in actual_files:
                    logger.warning(
                        "ZIP %s missing expected file %s, skipping artifact",
                        zip_path.name, zip_name,
                    )
                    continue

                artifact_data = zf.read(zip_name)
                s3_key = f"firmware/{model_code}/{version}/{generic_name}"
                self.s3_service.upload_file(
                    BytesIO(artifact_data),
                    s3_key,
                    content_type="application/octet-stream",
                )

        # Create or update firmware_versions record
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model_id,
            FirmwareVersion.version == version,
        )
        existing = self.db.execute(stmt).scalar_one_or_none()

        if existing is None:
            fv = FirmwareVersion(
                device_model_id=model_id,
                version=version,
                uploaded_at=datetime.now(UTC),
            )
            self.db.add(fv)
        else:
            existing.uploaded_at = datetime.now(UTC)

    def _migrate_coredumps(self) -> dict[str, int]:
        """Migrate coredump .dmp files from COREDUMPS_DIR to S3.

        Iterates device_key directories under COREDUMPS_DIR. For each .dmp
        file, looks up the matching CoreDump DB record using the filename
        column, then uploads to S3 as coredumps/{device_key}/{db_id}.dmp.

        After successful upload, sets filename = NULL on the DB record to
        signal migration completion.

        Returns:
            Dict with 'migrated' and 'skipped' counts.
        """
        assert self.coredumps_dir is not None
        migrated = 0
        skipped = 0

        for device_dir in sorted(self.coredumps_dir.iterdir()):
            if not device_dir.is_dir():
                continue

            device_key = device_dir.name

            # Verify device exists in DB
            stmt = select(Device).where(Device.key == device_key)
            device = self.db.execute(stmt).scalar_one_or_none()
            if device is None:
                warning = f"Device directory '{device_key}' has no matching DB record, skipping"
                self.warnings.append(warning)
                logger.warning(warning)
                skipped += 1
                continue

            # Process .dmp files
            for dmp_path in sorted(device_dir.glob("*.dmp")):
                dmp_filename = dmp_path.name

                # Look up coredump DB record by filename
                stmt = select(CoreDump).where(
                    CoreDump.device_id == device.id,
                    CoreDump.filename == dmp_filename,
                )
                coredump = self.db.execute(stmt).scalar_one_or_none()

                if coredump is None:
                    warning = f"Orphaned coredump file {device_key}/{dmp_filename}: no matching DB record"
                    self.warnings.append(warning)
                    logger.warning(warning)
                    skipped += 1
                    continue

                logger.info(
                    "Migrating coredump: %s/%s -> coredumps/%s/%d.dmp",
                    device_key, dmp_filename, device_key, coredump.id,
                )

                if self.dry_run:
                    print(f"  [DRY RUN] Would migrate coredump: {device_key}/{dmp_filename} -> {device_key}/{coredump.id}.dmp")
                    migrated += 1
                    continue

                try:
                    # Upload to S3 with the new ID-based key
                    s3_key = f"coredumps/{device_key}/{coredump.id}.dmp"
                    self.s3_service.upload_file(
                        BytesIO(dmp_path.read_bytes()),
                        s3_key,
                        content_type="application/octet-stream",
                    )

                    # Clear filename to signal migration complete
                    coredump.filename = None
                    migrated += 1

                except Exception as e:
                    warning = f"Failed to migrate coredump {device_key}/{dmp_filename}: {e}"
                    self.warnings.append(warning)
                    logger.error(warning)
                    skipped += 1

        self.db.flush()
        logger.info("Coredump migration: %d migrated, %d skipped", migrated, skipped)
        return {"migrated": migrated, "skipped": skipped}
