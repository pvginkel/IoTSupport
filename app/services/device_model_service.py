"""Device model service for managing hardware types."""

import json
import logging
import re
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import (
    InvalidOperationException,
    RecordExistsException,
    RecordNotFoundException,
    ValidationException,
)
from app.models.device_model import DeviceModel

if TYPE_CHECKING:
    from io import BytesIO

    from app.services.firmware_service import FirmwareService
    from app.services.mqtt_service import MqttService

logger = logging.getLogger(__name__)

# Pattern for device model code: lowercase alphanumeric with underscores
MODEL_CODE_PATTERN = re.compile(r"^[a-z0-9_]+$")


class DeviceModelService:
    """Service for managing device models.

    Handles CRUD operations for device hardware types, including
    firmware upload and version extraction.
    """

    def __init__(
        self,
        db: Session,
        firmware_service: "FirmwareService",
        mqtt_service: "MqttService",
    ) -> None:
        """Initialize service with database session and dependent services.

        Args:
            db: SQLAlchemy database session
            firmware_service: Service for firmware file management
            mqtt_service: Service for MQTT messaging
        """
        self.db = db
        self.firmware_service = firmware_service
        self.mqtt_service = mqtt_service

    def list_device_models(self) -> list[DeviceModel]:
        """List all device models ordered by code.

        Returns:
            List of DeviceModel instances
        """
        stmt = select(DeviceModel).order_by(DeviceModel.code)
        return list(self.db.scalars(stmt).all())

    def get_device_model(self, model_id: int) -> DeviceModel:
        """Get a device model by ID.

        Args:
            model_id: Device model ID

        Returns:
            DeviceModel instance

        Raises:
            RecordNotFoundException: If model doesn't exist
        """
        stmt = select(DeviceModel).where(DeviceModel.id == model_id)
        model = self.db.scalars(stmt).one_or_none()

        if model is None:
            raise RecordNotFoundException("DeviceModel", str(model_id))

        return model

    def get_device_model_by_code(self, code: str) -> DeviceModel:
        """Get a device model by code.

        Args:
            code: Device model code

        Returns:
            DeviceModel instance

        Raises:
            RecordNotFoundException: If model doesn't exist
        """
        stmt = select(DeviceModel).where(DeviceModel.code == code)
        model = self.db.scalars(stmt).one_or_none()

        if model is None:
            raise RecordNotFoundException("DeviceModel", code)

        return model

    def create_device_model(
        self, code: str, name: str, config_schema: str | None = None
    ) -> DeviceModel:
        """Create a new device model.

        Args:
            code: Unique model code (lowercase alphanumeric with underscores)
            name: Human-readable model name
            config_schema: Optional JSON schema for validating device configurations

        Returns:
            Created DeviceModel instance

        Raises:
            ValidationException: If code format is invalid
            RecordExistsException: If code already exists
        """
        # Validate code format
        if not MODEL_CODE_PATTERN.match(code):
            raise ValidationException(
                "Model code must contain only lowercase letters, numbers, and underscores"
            )

        # Check for existing model with same code
        stmt = select(DeviceModel).where(DeviceModel.code == code)
        existing = self.db.scalars(stmt).one_or_none()

        if existing is not None:
            raise RecordExistsException("DeviceModel", code)

        # Create new model
        model = DeviceModel(code=code, name=name, config_schema=config_schema)
        self.db.add(model)
        self.db.flush()

        logger.info("Created device model: %s (%s)", model.code, model.name)
        return model

    def update_device_model(
        self,
        model_id: int,
        name: str | None = None,
        config_schema: str | None = None,
    ) -> DeviceModel:
        """Update a device model.

        Note: code is immutable and cannot be changed.

        Args:
            model_id: Device model ID
            name: New human-readable name (optional)
            config_schema: New JSON schema for config validation (optional)

        Returns:
            Updated DeviceModel instance

        Raises:
            RecordNotFoundException: If model doesn't exist
        """
        model = self.get_device_model(model_id)

        if name is not None:
            model.name = name
        if config_schema is not None:
            model.config_schema = config_schema

        self.db.flush()

        logger.info("Updated device model: %s (%s)", model.code, model.name)
        return model

    def delete_device_model(self, model_id: int) -> None:
        """Delete a device model.

        Also deletes associated firmware file.

        Args:
            model_id: Device model ID

        Raises:
            RecordNotFoundException: If model doesn't exist
            InvalidOperationException: If model has associated devices
        """
        model = self.get_device_model(model_id)

        # Check for associated devices
        if model.device_count > 0:
            raise InvalidOperationException(
                "delete device model",
                f"model has {model.device_count} associated device(s)"
            )

        # Delete firmware file (best-effort)
        self.firmware_service.delete_firmware(model.code)

        # Delete the model
        self.db.delete(model)
        self.db.flush()

        logger.info("Deleted device model: %s", model.code)

    def upload_firmware(self, model_id: int, content: bytes) -> DeviceModel:
        """Upload firmware for a device model.

        Extracts version from ESP32 binary, saves to filesystem, and notifies
        all devices using this model via MQTT.

        Args:
            model_id: Device model ID
            content: Firmware binary content

        Returns:
            Updated DeviceModel with firmware_version set

        Raises:
            RecordNotFoundException: If model doesn't exist
            ValidationException: If firmware format is invalid
        """
        from app.services.mqtt_service import MqttService

        model = self.get_device_model(model_id)

        # Save firmware and extract version
        version = self.firmware_service.save_firmware(model.code, content)

        # Update model with version
        model.firmware_version = version
        self.db.flush()

        # Refresh to ensure devices relationship is loaded
        self.db.refresh(model)

        # Publish MQTT notification for each device using this model
        for device in model.devices:
            payload = json.dumps({
                "client_id": device.client_id,
                "firmware_version": version,
            })
            self.mqtt_service.publish(f"{MqttService.TOPIC_UPDATES}/firmware", payload)

        logger.info(
            "Uploaded firmware for model %s: version %s, notified %d devices",
            model.code,
            version,
            len(model.devices),
        )
        return model

    def get_firmware_stream(self, model_id: int) -> tuple["BytesIO", str]:
        """Get firmware stream for a device model.

        Returns a BytesIO for use with Flask's send_file.

        Args:
            model_id: Device model ID

        Returns:
            Tuple of (BytesIO stream, model_code)

        Raises:
            RecordNotFoundException: If model or firmware doesn't exist
        """
        model = self.get_device_model(model_id)
        stream = self.firmware_service.get_firmware_stream(model.code)
        return stream, model.code

    def has_firmware(self, model_id: int) -> bool:
        """Check if a device model has firmware uploaded.

        Args:
            model_id: Device model ID

        Returns:
            True if firmware exists

        Raises:
            RecordNotFoundException: If model doesn't exist
        """
        model = self.get_device_model(model_id)
        return self.firmware_service.firmware_exists(model.code)
