"""Tests for the firmware seeding of the Playwright suite."""

import json
import zipfile
from io import BytesIO

import pytest
from flask import Flask
from sqlalchemy.orm import Session

from app.exceptions import RecordNotFoundException
from app.models.device_model import DeviceModel
from app.schemas.device import FlashStatus
from app.services.container import ServiceContainer
from app.services.testing_firmware_service import build_firmware_zip


def _create_model(session: Session, code: str) -> DeviceModel:
    model = DeviceModel(code=code, name="Seed Model")
    session.add(model)
    session.flush()
    return model


class TestTestingFirmwareService:
    """Tests for TestingFirmwareService.seed_firmware()."""

    def test_seed_firmware_flashable(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A flashable seed is the model's current version, every image at its offset."""
        model = _create_model(session, "seedflash")

        seeded = container.testing_firmware_service().seed_firmware(
            model.id, version="2.0.0-seed", flash_images=True, chip="esp32s3"
        )

        assert seeded.id == model.id
        assert seeded.firmware_version == "2.0.0-seed"
        flash_set = container.firmware_service().get_flash_set("seedflash", "2.0.0-seed")
        assert flash_set.status == FlashStatus.FLASHABLE
        assert flash_set.manifest is not None
        assert flash_set.manifest.chip == "esp32s3"
        assert (
            flash_set.manifest.flash_mode,
            flash_set.manifest.flash_size,
            flash_set.manifest.flash_freq,
        ) == ("dio", "16MB", "80m")
        assert [(content.image.offset, content.image.file) for content in flash_set.images] == [
            (0x0, "bootloader/bootloader.bin"),
            (0x8000, "partition_table/partition-table.bin"),
            (0xD000, "ota_data_initial.bin"),
            (0x20000, "seedflash.bin"),
        ]
        contents = [content.data for content in flash_set.images]
        assert len(set(contents)) == len(contents)
        assert all(len(data) % 4 == 0 for data in contents)
        assert contents[3] == container.firmware_service().get_firmware_stream(
            "seedflash", "2.0.0-seed"
        ).read()

    def test_seed_firmware_without_flash_images(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A seed without flash images is a current version that cannot be flashed."""
        model = _create_model(session, "seedold")

        seeded = container.testing_firmware_service().seed_firmware(
            model.id, version="1.0.0", flash_images=False, chip="esp32s3"
        )

        assert seeded.firmware_version == "1.0.0"
        flash_set = container.firmware_service().get_flash_set("seedold", "1.0.0")
        assert flash_set.status == FlashStatus.NO_FLASH_IMAGES

    def test_seed_firmware_chip(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """The seeded build targets the given chip."""
        model = _create_model(session, "seedchip")

        container.testing_firmware_service().seed_firmware(
            model.id, version="1.0.0", flash_images=True, chip="esp32c3"
        )

        flash_set = container.firmware_service().get_flash_set("seedchip", "1.0.0")
        assert flash_set.manifest is not None
        assert flash_set.manifest.chip == "esp32c3"

    def test_seed_firmware_images_differ_per_version(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """A second seed becomes the current version, with images of its own."""
        model = _create_model(session, "seedtwice")
        service = container.testing_firmware_service()
        firmware_service = container.firmware_service()

        service.seed_firmware(model.id, version="1.0.0", flash_images=True, chip="esp32s3")
        first = firmware_service.get_flash_set("seedtwice", "1.0.0")
        seeded = service.seed_firmware(model.id, version="1.1.0", flash_images=True, chip="esp32s3")
        second = firmware_service.get_flash_set("seedtwice", "1.1.0")

        assert seeded.firmware_version == "1.1.0"
        assert not {content.data for content in first.images} & {
            content.data for content in second.images
        }

    def test_seed_firmware_unknown_model(
        self, app: Flask, session: Session, container: ServiceContainer
    ) -> None:
        """An unknown model raises RecordNotFoundException."""
        with pytest.raises(RecordNotFoundException):
            container.testing_firmware_service().seed_firmware(
                99999, version="1.0.0", flash_images=True, chip="esp32s3"
            )


class TestBuildFirmwareZip:
    """Tests for build_firmware_zip()."""

    def test_flashable_zip_members(self) -> None:
        """A flashable ZIP carries the five artifacts, flasher_args.json and its images."""
        content = build_firmware_zip("zipmodel", "1.0.0", flash_images=True, chip="esp32s3")

        with zipfile.ZipFile(BytesIO(content)) as zf:
            assert sorted(zf.namelist()) == [
                "bootloader.bin",
                "flasher_args.json",
                "ota_data_initial.bin",
                "partition-table.bin",
                "sdkconfig",
                "version.json",
                "zipmodel.bin",
                "zipmodel.elf",
                "zipmodel.map",
            ]
            flasher_args = json.loads(zf.read("flasher_args.json"))
        assert flasher_args["flash_files"] == {
            "0x0": "bootloader/bootloader.bin",
            "0x8000": "partition_table/partition-table.bin",
            "0xd000": "ota_data_initial.bin",
            "0x20000": "zipmodel.bin",
        }

    def test_zip_without_flash_images(self) -> None:
        """A ZIP without flash images carries the five artifacts alone."""
        content = build_firmware_zip("zipmodel", "1.0.0", flash_images=False, chip="esp32s3")

        with zipfile.ZipFile(BytesIO(content)) as zf:
            assert sorted(zf.namelist()) == [
                "sdkconfig",
                "version.json",
                "zipmodel.bin",
                "zipmodel.elf",
                "zipmodel.map",
            ]
