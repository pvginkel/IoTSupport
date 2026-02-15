"""Tests for MigrationService (filesystem-to-S3 migration)."""

import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.coredump import CoreDump, ParseStatus
from app.models.device import Device
from app.models.device_model import DeviceModel
from app.models.firmware_version import FirmwareVersion
from app.services.container import ServiceContainer
from app.services.migration_service import MigrationService
from tests.conftest import create_test_firmware


def _create_legacy_firmware_zip(model_code: str, version: str) -> bytes:
    """Create a legacy firmware ZIP matching the old filesystem format.

    This mimics the ZIPs that were stored at ASSETS_DIR/{model_code}/firmware-{version}.zip
    """
    bin_content = create_test_firmware(version.encode())
    version_json = json.dumps({
        "git_commit": "a1b2c3d4",
        "idf_version": "v5.2.1",
        "firmware_version": version,
    }).encode("utf-8")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{model_code}.bin", bin_content)
        zf.writestr(f"{model_code}.elf", b"\x7fELF" + b"\x00" * 100)
        zf.writestr(f"{model_code}.map", b"Memory Map\n")
        zf.writestr("sdkconfig", b"CONFIG_IDF_TARGET=\"esp32s3\"\n")
        zf.writestr("version.json", version_json)
    return buf.getvalue()


class TestMigrationServiceFirmware:
    """Tests for firmware migration from ASSETS_DIR to S3."""

    def test_migrate_firmware_zips(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test migrating firmware ZIPs from filesystem to S3."""
        model_code = "migfw1"
        model = DeviceModel(code=model_code, name="Migration Test")
        session.add(model)
        session.flush()

        # Create legacy filesystem structure
        assets_dir = tmp_path / "assets"
        model_dir = assets_dir / model_code
        model_dir.mkdir(parents=True)

        # Write a legacy ZIP
        zip_content = _create_legacy_firmware_zip(model_code, "1.0.0")
        (model_dir / "firmware-1.0.0.zip").write_bytes(zip_content)

        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service,
            db=session,
            assets_dir=assets_dir,
            coredumps_dir=None,
            dry_run=False,
        )

        summary = migration.run()

        assert summary["firmware_zips"] == 1
        assert summary["firmware_skipped"] == 0

        # Verify S3 objects exist with generic names
        assert s3_service.file_exists(f"firmware/{model_code}/1.0.0/firmware.bin")
        assert s3_service.file_exists(f"firmware/{model_code}/1.0.0/firmware.elf")
        assert s3_service.file_exists(f"firmware/{model_code}/1.0.0/firmware.map")
        assert s3_service.file_exists(f"firmware/{model_code}/1.0.0/sdkconfig")
        assert s3_service.file_exists(f"firmware/{model_code}/1.0.0/version.json")

        # Verify firmware_versions DB record created
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id,
            FirmwareVersion.version == "1.0.0",
        )
        fv = session.execute(stmt).scalar_one()
        assert fv.uploaded_at is not None

    def test_migrate_multiple_firmware_versions(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test migrating multiple firmware versions for the same model."""
        model_code = "migfw2"
        model = DeviceModel(code=model_code, name="Multi Version Test")
        session.add(model)
        session.flush()

        assets_dir = tmp_path / "assets"
        model_dir = assets_dir / model_code
        model_dir.mkdir(parents=True)

        for version in ["1.0.0", "1.1.0", "2.0.0"]:
            zip_content = _create_legacy_firmware_zip(model_code, version)
            (model_dir / f"firmware-{version}.zip").write_bytes(zip_content)

        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=assets_dir, coredumps_dir=None,
        )

        summary = migration.run()

        assert summary["firmware_zips"] == 3
        assert summary["firmware_skipped"] == 0

        # All 3 versions should have DB records
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id
        )
        versions = session.execute(stmt).scalars().all()
        assert len(versions) == 3

    def test_migrate_firmware_no_matching_model(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that model directories with no matching DB record are skipped."""
        assets_dir = tmp_path / "assets"
        (assets_dir / "nomodel").mkdir(parents=True)
        (assets_dir / "nomodel" / "firmware-1.0.0.zip").write_bytes(
            _create_legacy_firmware_zip("nomodel", "1.0.0")
        )

        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=assets_dir, coredumps_dir=None,
        )

        summary = migration.run()

        assert summary["firmware_zips"] == 0
        assert summary["firmware_skipped"] == 1
        assert any("nomodel" in w for w in summary["warnings"])

    def test_migrate_firmware_skips_legacy_flat_bin(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that legacy flat .bin files in ASSETS_DIR root are skipped."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir(parents=True)
        (assets_dir / "firmware-legacy.bin").write_bytes(b"\x00" * 100)

        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=assets_dir, coredumps_dir=None,
        )

        summary = migration.run()

        assert summary["firmware_zips"] == 0
        assert summary["firmware_skipped"] == 1

    def test_migrate_firmware_dry_run(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that dry run does not upload to S3 or create DB records."""
        model_code = "migdry"
        model = DeviceModel(code=model_code, name="Dry Run Test")
        session.add(model)
        session.flush()

        assets_dir = tmp_path / "assets"
        model_dir = assets_dir / model_code
        model_dir.mkdir(parents=True)
        (model_dir / "firmware-1.0.0.zip").write_bytes(
            _create_legacy_firmware_zip(model_code, "1.0.0")
        )

        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=assets_dir, coredumps_dir=None,
            dry_run=True,
        )

        summary = migration.run()

        assert summary["firmware_zips"] == 1

        # S3 objects should NOT exist (dry run)
        assert not s3_service.file_exists(f"firmware/{model_code}/1.0.0/firmware.bin")

        # No DB records should be created
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id
        )
        assert session.execute(stmt).scalar_one_or_none() is None

    def test_migrate_firmware_idempotent(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that running migration twice is idempotent."""
        model_code = "migidem"
        model = DeviceModel(code=model_code, name="Idempotent Test")
        session.add(model)
        session.flush()

        assets_dir = tmp_path / "assets"
        model_dir = assets_dir / model_code
        model_dir.mkdir(parents=True)
        (model_dir / "firmware-1.0.0.zip").write_bytes(
            _create_legacy_firmware_zip(model_code, "1.0.0")
        )

        s3_service = container.s3_service()

        # Run migration twice
        for _ in range(2):
            migration = MigrationService(
                s3_service=s3_service, db=session,
                assets_dir=assets_dir, coredumps_dir=None,
            )
            summary = migration.run()
            assert summary["firmware_zips"] == 1

        # Should still have exactly one firmware_versions record
        stmt = select(FirmwareVersion).where(
            FirmwareVersion.device_model_id == model.id
        )
        versions = session.execute(stmt).scalars().all()
        assert len(versions) == 1

    def test_migrate_firmware_no_assets_dir(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that migration works when ASSETS_DIR is None."""
        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=None, coredumps_dir=None,
        )

        summary = migration.run()
        assert summary["firmware_zips"] == 0
        assert summary["firmware_skipped"] == 0


class TestMigrationServiceCoredumps:
    """Tests for coredump migration from COREDUMPS_DIR to S3."""

    def test_migrate_coredumps(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test migrating coredump .dmp files from filesystem to S3."""
        # Create model and device
        model = DeviceModel(code="migcd1", name="CD Migration Test")
        session.add(model)
        session.flush()

        device = Device(
            key="migcd001",
            device_model_id=model.id,
            config="{}",
            rotation_state="OK",
        )
        session.add(device)
        session.flush()

        # Create a coredump DB record with a legacy filename
        coredump = CoreDump(
            device_id=device.id,
            filename="coredump_20260101T120000_123456Z.dmp",
            chip="esp32s3",
            firmware_version="1.0.0",
            size=256,
            parse_status=ParseStatus.PARSED.value,
            parsed_output="crash info",
            uploaded_at=datetime.now(UTC),
        )
        session.add(coredump)
        session.flush()

        # Create legacy filesystem structure
        coredumps_dir = tmp_path / "coredumps"
        device_dir = coredumps_dir / "migcd001"
        device_dir.mkdir(parents=True)
        dmp_content = b"\xDE\xAD\xBE\xEF" * 64
        (device_dir / "coredump_20260101T120000_123456Z.dmp").write_bytes(dmp_content)

        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=None, coredumps_dir=coredumps_dir,
        )

        summary = migration.run()

        assert summary["coredumps_migrated"] == 1
        assert summary["coredumps_skipped"] == 0

        # Verify S3 object exists with ID-based key
        s3_key = f"coredumps/migcd001/{coredump.id}.dmp"
        assert s3_service.file_exists(s3_key)
        stream = s3_service.download_file(s3_key)
        assert stream.read() == dmp_content

        # Verify filename column was cleared
        session.expire(coredump)
        assert coredump.filename is None

    def test_migrate_coredumps_orphaned_file(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that orphaned .dmp files (no DB record) are skipped."""
        model = DeviceModel(code="migcd2", name="Orphan Test")
        session.add(model)
        session.flush()

        device = Device(
            key="migcd002",
            device_model_id=model.id,
            config="{}",
            rotation_state="OK",
        )
        session.add(device)
        session.flush()

        coredumps_dir = tmp_path / "coredumps"
        device_dir = coredumps_dir / "migcd002"
        device_dir.mkdir(parents=True)
        (device_dir / "orphaned_coredump.dmp").write_bytes(b"\x00" * 10)

        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=None, coredumps_dir=coredumps_dir,
        )

        summary = migration.run()

        assert summary["coredumps_migrated"] == 0
        assert summary["coredumps_skipped"] == 1
        assert any("Orphaned" in w for w in summary["warnings"])

    def test_migrate_coredumps_no_matching_device(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that device directories with no matching DB record are skipped."""
        coredumps_dir = tmp_path / "coredumps"
        (coredumps_dir / "nodevice").mkdir(parents=True)
        (coredumps_dir / "nodevice" / "test.dmp").write_bytes(b"\x00" * 10)

        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=None, coredumps_dir=coredumps_dir,
        )

        summary = migration.run()

        assert summary["coredumps_migrated"] == 0
        assert summary["coredumps_skipped"] == 1
        assert any("nodevice" in w for w in summary["warnings"])

    def test_migrate_coredumps_dry_run(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that dry run does not upload or modify DB records."""
        model = DeviceModel(code="migcd3", name="Dry Run CD Test")
        session.add(model)
        session.flush()

        device = Device(
            key="migcd003",
            device_model_id=model.id,
            config="{}",
            rotation_state="OK",
        )
        session.add(device)
        session.flush()

        coredump = CoreDump(
            device_id=device.id,
            filename="test_cd.dmp",
            chip="esp32",
            firmware_version="1.0.0",
            size=10,
            parse_status=ParseStatus.PENDING.value,
            uploaded_at=datetime.now(UTC),
        )
        session.add(coredump)
        session.flush()

        coredumps_dir = tmp_path / "coredumps"
        device_dir = coredumps_dir / "migcd003"
        device_dir.mkdir(parents=True)
        (device_dir / "test_cd.dmp").write_bytes(b"\x00" * 10)

        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=None, coredumps_dir=coredumps_dir,
            dry_run=True,
        )

        summary = migration.run()

        assert summary["coredumps_migrated"] == 1

        # S3 should NOT have the object
        assert not s3_service.file_exists(f"coredumps/migcd003/{coredump.id}.dmp")

        # Filename should NOT have been cleared
        session.expire(coredump)
        assert coredump.filename == "test_cd.dmp"

    def test_migrate_coredumps_no_coredumps_dir(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """Test that migration works when COREDUMPS_DIR is None."""
        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=None, coredumps_dir=None,
        )

        summary = migration.run()
        assert summary["coredumps_migrated"] == 0
        assert summary["coredumps_skipped"] == 0


class TestMigrationServiceFullMigration:
    """Tests for combined firmware + coredump migration."""

    def test_full_migration(
        self, app: Flask, session: Session, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test migrating both firmware and coredumps in a single run."""
        # Set up model, device, coredump
        model = DeviceModel(code="migfull", name="Full Migration")
        session.add(model)
        session.flush()

        device = Device(
            key="migful01",
            device_model_id=model.id,
            config="{}",
            rotation_state="OK",
        )
        session.add(device)
        session.flush()

        coredump = CoreDump(
            device_id=device.id,
            filename="cd_full.dmp",
            chip="esp32s3",
            firmware_version="1.0.0",
            size=32,
            parse_status=ParseStatus.PARSED.value,
            uploaded_at=datetime.now(UTC),
        )
        session.add(coredump)
        session.flush()

        # Firmware filesystem
        assets_dir = tmp_path / "assets"
        model_dir = assets_dir / "migfull"
        model_dir.mkdir(parents=True)
        (model_dir / "firmware-1.0.0.zip").write_bytes(
            _create_legacy_firmware_zip("migfull", "1.0.0")
        )

        # Coredump filesystem
        coredumps_dir = tmp_path / "coredumps"
        device_dir = coredumps_dir / "migful01"
        device_dir.mkdir(parents=True)
        (device_dir / "cd_full.dmp").write_bytes(b"\xAB" * 32)

        s3_service = container.s3_service()
        migration = MigrationService(
            s3_service=s3_service, db=session,
            assets_dir=assets_dir, coredumps_dir=coredumps_dir,
        )

        summary = migration.run()

        assert summary["firmware_zips"] == 1
        assert summary["coredumps_migrated"] == 1
        assert summary["firmware_skipped"] == 0
        assert summary["coredumps_skipped"] == 0
        assert len(summary["warnings"]) == 0

        # Verify firmware in S3
        assert s3_service.file_exists("firmware/migfull/1.0.0/firmware.bin")

        # Verify coredump in S3
        assert s3_service.file_exists(f"coredumps/migful01/{coredump.id}.dmp")
