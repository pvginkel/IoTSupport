"""Coredump storage and parsing service for ESP32 device crash dumps."""

import logging
import shutil
import threading
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import (
    InvalidOperationException,
    RecordNotFoundException,
    ValidationException,
)
from app.models.coredump import CoreDump, ParseStatus
from app.utils.fs import atomic_write

if TYPE_CHECKING:
    from app.app_config import AppSettings
    from app.services.container import ServiceContainer
    from app.services.firmware_service import FirmwareService
    from app.services.metrics_service import MetricsService

logger = logging.getLogger(__name__)

# Maximum coredump size: 1MB
MAX_COREDUMP_SIZE = 1_048_576

# Timeout for sidecar HTTP requests (seconds)
SIDECAR_REQUEST_TIMEOUT = 120

# Maximum number of parse retry attempts
MAX_PARSE_RETRIES = 3


class CoredumpService:
    """Service for saving, parsing, and managing ESP32 coredump files.

    This is a singleton service that manages coredump storage on the filesystem,
    creates database records for tracking, and orchestrates background parsing
    via a sidecar container. Uses the container pattern for DB session management
    since it is a singleton (not per-request).
    """

    def __init__(
        self,
        coredumps_dir: Path | None,
        config: "AppSettings",
        firmware_service: "FirmwareService",
        metrics_service: "MetricsService",
    ) -> None:
        """Initialize coredump service.

        Args:
            coredumps_dir: Directory for storing coredump files, or None
                if coredump support is not configured.
            config: Application settings (for sidecar URL, xfer dir, max coredumps).
            firmware_service: Service for firmware ZIP operations (ELF extraction).
            metrics_service: Service for recording operational metrics.

        Note:
            The `container` attribute must be set post-init (in create_app) because
            providers.Self() resolves to None during Singleton construction.
            The container is needed for DB session access via the singleton pattern.
        """
        self.coredumps_dir = coredumps_dir
        self.config = config
        self.container: "ServiceContainer | None" = None
        self.firmware_service = firmware_service
        self.metrics_service = metrics_service

        if coredumps_dir is not None:
            coredumps_dir.mkdir(parents=True, exist_ok=True)
            logger.info("CoredumpService initialized with coredumps_dir: %s", coredumps_dir)
        else:
            logger.info("CoredumpService initialized without coredumps_dir (uploads disabled)")

    def _get_session(self) -> Session:
        """Get a DB session from the container.

        Returns the request-scoped session (for request context) or a new
        session (for background threads via the ContextLocalSingleton).

        Raises:
            RuntimeError: If the container reference has not been set.
        """
        if self.container is None:
            raise RuntimeError(
                "CoredumpService.container not set. "
                "Ensure it is assigned post-init in create_app()."
            )
        return self.container.db_session()  # type: ignore[no-any-return]

    # -------------------------------------------------------------------------
    # Upload flow (called within a request-scoped session)
    # -------------------------------------------------------------------------

    def save_coredump(
        self,
        device_id: int,
        device_key: str,
        model_code: str,
        chip: str,
        firmware_version: str,
        content: bytes,
    ) -> tuple[str, int]:
        """Save a coredump binary and create a DB record.

        The coredump is written atomically to the filesystem, a DB record
        is created with parse_status=PENDING, and retention is enforced.
        This method must be called within a request-scoped session.

        Args:
            device_id: Database ID of the device.
            device_key: 8-character device key (determines subdirectory).
            model_code: Device model code.
            chip: Chip type (e.g., 'esp32s3').
            firmware_version: Firmware version running on the device.
            content: Raw coredump binary data.

        Returns:
            Tuple of (filename, coredump_id).

        Raises:
            InvalidOperationException: If COREDUMPS_DIR is not configured.
            ValidationException: If content is empty, exceeds 1MB, or device key is invalid.
        """
        # Guard: coredumps_dir must be configured
        if self.coredumps_dir is None:
            raise InvalidOperationException(
                "upload coredump", "COREDUMPS_DIR is not configured"
            )

        # Validate content
        if not content:
            raise ValidationException("No coredump content provided")

        if len(content) > MAX_COREDUMP_SIZE:
            raise ValidationException("Coredump exceeds maximum size of 1MB")

        # Defense-in-depth: reject device keys with non-alphanumeric characters
        if not device_key.isalnum():
            raise ValidationException("Invalid device key format")

        # Create per-device directory
        device_dir = self.coredumps_dir / device_key
        device_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with microsecond precision to avoid collisions
        now = datetime.now(UTC)
        timestamp = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}Z"
        dmp_filename = f"coredump_{timestamp}.dmp"
        dmp_path = device_dir / dmp_filename

        # Write coredump binary atomically
        atomic_write(dmp_path, content, device_dir)

        # Create DB record via the request-scoped session (obtained from container)
        session = self._get_session()
        coredump = CoreDump(
            device_id=device_id,
            filename=dmp_filename,
            chip=chip,
            firmware_version=firmware_version,
            size=len(content),
            parse_status=ParseStatus.PENDING.value,
            uploaded_at=now,
        )
        session.add(coredump)
        session.flush()  # Get the ID immediately
        coredump_id = coredump.id

        # Enforce per-device retention limit
        self._enforce_retention(session, device_id, device_key)

        logger.info(
            "Saved coredump for device %s (id=%d, model=%s, chip=%s, fw=%s): %s",
            device_key,
            coredump_id,
            model_code,
            chip,
            firmware_version,
            dmp_filename,
        )

        return dmp_filename, coredump_id

    def _enforce_retention(
        self,
        session: Session,
        device_id: int,
        device_key: str,
    ) -> None:
        """Delete oldest coredumps if per-device limit is exceeded.

        Args:
            session: SQLAlchemy session (request-scoped).
            device_id: Device ID to check retention for.
            device_key: Device key for filesystem path resolution.
        """
        max_coredumps = self.config.max_coredumps

        # Query all coredumps for this device, ordered oldest first
        stmt = (
            select(CoreDump)
            .where(CoreDump.device_id == device_id)
            .order_by(CoreDump.uploaded_at.asc())
        )
        coredumps = session.execute(stmt).scalars().all()

        if len(coredumps) <= max_coredumps:
            return

        # Delete the oldest records beyond the limit
        excess = len(coredumps) - max_coredumps
        for coredump in coredumps[:excess]:
            # Best-effort file deletion
            self._delete_coredump_file(device_key, coredump.filename)
            session.delete(coredump)

        session.flush()
        logger.info(
            "Retention enforced for device %s: deleted %d oldest coredumps (limit=%d)",
            device_key,
            excess,
            max_coredumps,
        )

    # -------------------------------------------------------------------------
    # Background parsing
    # -------------------------------------------------------------------------

    def maybe_start_parsing(
        self,
        coredump_id: int,
        device_key: str,
        model_code: str,
        chip: str,
        firmware_version: str,
        filename: str,
    ) -> None:
        """Spawn a background thread to parse the coredump if sidecar is configured.

        If PARSE_SIDECAR_URL or PARSE_SIDECAR_XFER_DIR is not configured,
        parsing is skipped and the coredump stays in PENDING status.

        All data needed for parsing is passed as arguments so the thread
        does not need to read the initial record from the DB.

        Args:
            coredump_id: Database ID of the coredump record.
            device_key: Device key for filesystem path.
            model_code: Device model code (for ELF lookup in firmware ZIP).
            chip: Chip type.
            firmware_version: Firmware version (for ZIP path).
            filename: Name of the .dmp file.
        """
        if not self.config.parse_sidecar_url or not self.config.parse_sidecar_xfer_dir:
            logger.debug(
                "Sidecar not configured, skipping parse for coredump %d", coredump_id
            )
            return

        thread = threading.Thread(
            target=self._parse_coredump_thread,
            args=(coredump_id, device_key, model_code, chip, firmware_version, filename),
            daemon=True,
            name=f"coredump-parse-{coredump_id}",
        )
        thread.start()

    def _parse_coredump_thread(
        self,
        coredump_id: int,
        device_key: str,
        model_code: str,
        chip: str,
        firmware_version: str,
        filename: str,
    ) -> None:
        """Background thread that parses a coredump via the sidecar.

        Extracts the .elf from the firmware ZIP, copies it and the .dmp
        to the xfer directory, calls the sidecar, and updates the DB record.
        Retries up to MAX_PARSE_RETRIES times on failure.

        All arguments are passed in so no DB read is needed at the start.
        """
        # Brief pause to allow the request-scoped session to commit via
        # teardown_request before this thread touches the DB. The thread is
        # spawned inside the request handler (before teardown commits), so
        # without this delay the record might not yet be visible to the
        # thread's own session.
        time.sleep(0.5)

        start_time = time.perf_counter()
        xfer_dir = self.config.parse_sidecar_xfer_dir
        sidecar_url = self.config.parse_sidecar_url

        # These are guaranteed non-None by maybe_start_parsing guard
        assert xfer_dir is not None
        assert sidecar_url is not None

        xfer_dmp_path: Path | None = None
        xfer_elf_path: Path | None = None

        try:
            # Step 1: Locate the .dmp file
            assert self.coredumps_dir is not None
            dmp_source = self.coredumps_dir / device_key / filename
            if not dmp_source.exists():
                self._update_parse_status(
                    coredump_id,
                    ParseStatus.ERROR,
                    f"Unable to parse coredump: .dmp file not found at {dmp_source}",
                )
                return

            # Step 2: Extract .elf from firmware ZIP
            elf_name = f"{model_code}.elf"
            elf_bytes = self._extract_elf_from_firmware(model_code, firmware_version)
            if elf_bytes is None:
                # Error already logged; set ERROR status without retries
                self._update_parse_status(
                    coredump_id,
                    ParseStatus.ERROR,
                    f"Unable to parse coredump: firmware ZIP not found for {model_code} version {firmware_version}",
                )
                return

            # Step 3: Copy files to xfer directory
            xfer_dir.mkdir(parents=True, exist_ok=True)
            xfer_dmp_path = xfer_dir / filename
            xfer_elf_path = xfer_dir / elf_name
            shutil.copy2(dmp_source, xfer_dmp_path)
            xfer_elf_path.write_bytes(elf_bytes)

            # Step 4: Call sidecar with retries
            last_error: str | None = None
            for attempt in range(1, MAX_PARSE_RETRIES + 1):
                try:
                    logger.info(
                        "Parsing coredump %d (attempt %d/%d): core=%s, elf=%s, chip=%s",
                        coredump_id, attempt, MAX_PARSE_RETRIES,
                        filename, elf_name, chip,
                    )
                    resp = httpx.get(
                        f"{sidecar_url}/parse-coredump",
                        params={"core": filename, "elf": elf_name, "chip": chip},
                        timeout=SIDECAR_REQUEST_TIMEOUT,
                    )
                    resp.raise_for_status()
                    output = resp.json().get("output", "")

                    # Success -- update DB record
                    self._update_parse_status(
                        coredump_id, ParseStatus.PARSED, output
                    )
                    duration = time.perf_counter() - start_time
                    self.metrics_service.record_operation(
                        "coredump_parse", "success", duration
                    )
                    logger.info(
                        "Successfully parsed coredump %d in %.2fs", coredump_id, duration
                    )
                    return

                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        "Parse attempt %d/%d failed for coredump %d: %s",
                        attempt, MAX_PARSE_RETRIES, coredump_id, last_error,
                    )

            # All retries exhausted
            self._update_parse_status(
                coredump_id,
                ParseStatus.ERROR,
                f"Unable to parse coredump: {last_error}",
            )
            duration = time.perf_counter() - start_time
            self.metrics_service.record_operation("coredump_parse", "error", duration)

        except Exception as e:
            # Catch-all for unexpected errors in the thread
            logger.error(
                "Unexpected error parsing coredump %d: %s", coredump_id, e, exc_info=True,
            )
            self._update_parse_status(
                coredump_id,
                ParseStatus.ERROR,
                f"Unable to parse coredump: {e}",
            )
            duration = time.perf_counter() - start_time
            self.metrics_service.record_operation("coredump_parse", "error", duration)

        finally:
            # Best-effort cleanup of xfer directory files
            self._cleanup_xfer_files(xfer_dmp_path, xfer_elf_path)

    def _extract_elf_from_firmware(
        self, model_code: str, firmware_version: str
    ) -> bytes | None:
        """Extract the .elf file from a firmware ZIP.

        Args:
            model_code: Device model code.
            firmware_version: Firmware version string.

        Returns:
            ELF file bytes, or None if ZIP or ELF not found.
        """
        zip_path = self.firmware_service.get_versioned_zip_path(model_code, firmware_version)
        if not zip_path.exists():
            logger.warning(
                "Firmware ZIP not found for %s version %s at %s",
                model_code, firmware_version, zip_path,
            )
            return None

        elf_name = f"{model_code}.elf"
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                return zf.read(elf_name)
        except (zipfile.BadZipFile, KeyError) as e:
            logger.warning(
                "Failed to extract %s from %s: %s", elf_name, zip_path, e
            )
            return None

    def _update_parse_status(
        self, coredump_id: int, status: ParseStatus, output: str
    ) -> None:
        """Update a coredump record's parse status using the singleton DB pattern.

        Acquires a session from the container, updates the record, commits,
        and resets the session.

        Args:
            coredump_id: ID of the coredump to update.
            status: New parse status.
            output: Parsed output or error message.
        """
        session = self._get_session()
        try:
            stmt = select(CoreDump).where(CoreDump.id == coredump_id)
            coredump = session.execute(stmt).scalar_one_or_none()
            if coredump is None:
                logger.warning("Coredump %d not found for status update", coredump_id)
                return

            coredump.parse_status = status.value
            coredump.parsed_output = output
            coredump.parsed_at = datetime.now(UTC)
            session.commit()

        except Exception:
            session.rollback()
            raise

        finally:
            assert self.container is not None  # Guaranteed by _get_session() above
            self.container.db_session.reset()

    def _cleanup_xfer_files(
        self, dmp_path: Path | None, elf_path: Path | None
    ) -> None:
        """Best-effort removal of files from the xfer directory."""
        for path in (dmp_path, elf_path):
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning("Failed to clean up xfer file %s: %s", path, e)

    # -------------------------------------------------------------------------
    # CRUD methods (called from admin API via request-scoped session)
    # -------------------------------------------------------------------------

    def list_coredumps(self, device_id: int) -> list[CoreDump]:
        """List all coredumps for a device, ordered by uploaded_at descending.

        The caller must verify that the device exists before calling this method.

        Args:
            device_id: ID of the device.

        Returns:
            List of CoreDump records.
        """
        session = self._get_session()
        stmt = (
            select(CoreDump)
            .where(CoreDump.device_id == device_id)
            .order_by(CoreDump.uploaded_at.desc())
        )
        return list(session.execute(stmt).scalars().all())

    def get_coredump(self, device_id: int, coredump_id: int) -> CoreDump:
        """Get a specific coredump, verifying it belongs to the given device.

        Args:
            device_id: ID of the device (ownership check).
            coredump_id: ID of the coredump.

        Returns:
            CoreDump record.

        Raises:
            RecordNotFoundException: If coredump not found or does not belong to device.
        """
        session = self._get_session()
        stmt = (
            select(CoreDump)
            .where(CoreDump.id == coredump_id)
            .where(CoreDump.device_id == device_id)
        )
        coredump: CoreDump | None = session.execute(stmt).scalar_one_or_none()
        if coredump is None:
            raise RecordNotFoundException("Coredump", str(coredump_id))
        return coredump

    def get_coredump_path(self, device_key: str, filename: str) -> Path:
        """Get the filesystem path for a coredump .dmp file.

        Args:
            device_key: Device key for directory resolution.
            filename: Coredump filename.

        Returns:
            Path to the .dmp file.

        Raises:
            RecordNotFoundException: If the file does not exist on disk.
            InvalidOperationException: If COREDUMPS_DIR is not configured.
        """
        if self.coredumps_dir is None:
            raise InvalidOperationException(
                "download coredump", "COREDUMPS_DIR is not configured"
            )

        path = self.coredumps_dir / device_key / filename
        if not path.exists():
            raise RecordNotFoundException("Coredump file", filename)
        return path

    def delete_coredump(self, device_id: int, coredump_id: int, device_key: str) -> None:
        """Delete a single coredump record and its file.

        Args:
            device_id: ID of the device (ownership check).
            coredump_id: ID of the coredump to delete.
            device_key: Device key for filesystem path.

        Raises:
            RecordNotFoundException: If coredump not found or does not belong to device.
        """
        coredump = self.get_coredump(device_id, coredump_id)

        # Best-effort file deletion
        self._delete_coredump_file(device_key, coredump.filename)

        session = self._get_session()
        session.delete(coredump)
        session.flush()

        logger.info("Deleted coredump %d for device %s", coredump_id, device_key)

    def delete_all_coredumps(self, device_id: int, device_key: str) -> None:
        """Delete all coredumps for a device (records and files).

        Args:
            device_id: ID of the device.
            device_key: Device key for filesystem path.
        """
        coredumps = self.list_coredumps(device_id)

        session = self._get_session()
        for coredump in coredumps:
            self._delete_coredump_file(device_key, coredump.filename)
            session.delete(coredump)

        session.flush()

        logger.info(
            "Deleted all %d coredumps for device %s", len(coredumps), device_key
        )

    def _delete_coredump_file(self, device_key: str, filename: str) -> None:
        """Best-effort deletion of a coredump .dmp file from disk."""
        if self.coredumps_dir is None:
            return

        path = self.coredumps_dir / device_key / filename
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Failed to delete coredump file %s: %s", path, e)
