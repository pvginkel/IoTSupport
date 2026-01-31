"""Device service for managing IoT devices."""

import base64
import json
import logging
import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Any

import jsonschema  # type: ignore[import-untyped]
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import (
    ExternalServiceException,
    InvalidOperationException,
    RecordNotFoundException,
    ValidationException,
)
from app.models.device import Device, RotationState

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.device_model_service import DeviceModelService
    from app.services.keycloak_admin_service import KeycloakAdminService
    from app.services.mqtt_service import MqttService

logger = logging.getLogger(__name__)


class DeviceService:
    """Service for managing IoT devices.

    Handles device CRUD operations, Keycloak client lifecycle,
    and provisioning package generation.
    """

    def __init__(
        self,
        db: Session,
        config: "Settings",
        device_model_service: "DeviceModelService",
        keycloak_admin_service: "KeycloakAdminService",
        mqtt_service: "MqttService",
    ) -> None:
        """Initialize service with dependencies.

        Args:
            db: SQLAlchemy database session
            config: Application settings
            device_model_service: Service for device model operations
            keycloak_admin_service: Service for Keycloak operations
            mqtt_service: Service for MQTT messaging
        """
        self.db = db
        self.config = config
        self.device_model_service = device_model_service
        self.keycloak_admin_service = keycloak_admin_service
        self.mqtt_service = mqtt_service

        # Initialize Fernet cipher for secret encryption
        self._fernet = Fernet(config.fernet_key.encode())

    def _generate_device_key(self, max_attempts: int = 3) -> str:
        """Generate a unique 8-character device key.

        Uses cryptographically secure random bytes encoded as base32.

        Args:
            max_attempts: Maximum retry attempts for uniqueness

        Returns:
            Unique 8-character lowercase alphanumeric key

        Raises:
            InvalidOperationException: If unable to generate unique key
        """
        for _ in range(max_attempts):
            # Generate 5 random bytes (40 bits), encode as base32 (8 chars)
            random_bytes = secrets.token_bytes(5)
            key = base64.b32encode(random_bytes).decode().lower()[:8]

            # Verify uniqueness
            stmt = select(Device).where(Device.key == key)
            existing = self.db.scalars(stmt).one_or_none()

            if existing is None:
                return key

        raise InvalidOperationException(
            "generate device key",
            "unable to generate unique key after multiple attempts"
        )

    def _encrypt_secret(self, secret: str) -> str:
        """Encrypt a secret for storage in cached_secret.

        Args:
            secret: Plain text secret

        Returns:
            Encrypted secret string
        """
        return self._fernet.encrypt(secret.encode()).decode()

    def _decrypt_secret(self, encrypted: str) -> str:
        """Decrypt a cached secret.

        Args:
            encrypted: Encrypted secret string

        Returns:
            Plain text secret
        """
        return self._fernet.decrypt(encrypted.encode()).decode()

    def _extract_config_fields(
        self, config: str
    ) -> tuple[str | None, str | None, bool | None]:
        """Extract display fields from JSON config string.

        Args:
            config: JSON string containing configuration

        Returns:
            Tuple of (device_name, device_entity_id, enable_ota)
        """
        try:
            parsed = json.loads(config)
            return (
                parsed.get("deviceName"),
                parsed.get("deviceEntityId"),
                parsed.get("enableOTA"),
            )
        except (json.JSONDecodeError, AttributeError):
            return (None, None, None)

    def _validate_config_schema(self, config: str, schema: str | None) -> None:
        """Validate config against JSON schema if schema is set.

        Args:
            config: JSON config string
            schema: JSON schema string (optional)

        Raises:
            ValidationException: If config doesn't match schema
        """
        if schema is None:
            return

        try:
            config_data = json.loads(config)
            schema_data = json.loads(schema)
            jsonschema.validate(instance=config_data, schema=schema_data)
        except json.JSONDecodeError as e:
            raise ValidationException(f"Invalid JSON in config or schema: {e}") from e
        except jsonschema.ValidationError as e:
            raise ValidationException(f"Config validation failed: {e.message}") from e
        except jsonschema.SchemaError as e:
            raise ValidationException(f"Invalid JSON schema: {e.message}") from e

    def _apply_config_fields(self, device: Device, config: str) -> None:
        """Extract and apply config fields to device.

        Args:
            device: Device to update
            config: JSON config string
        """
        device_name, device_entity_id, enable_ota = self._extract_config_fields(config)
        device.device_name = device_name
        device.device_entity_id = device_entity_id
        device.enable_ota = enable_ota

    def list_devices(
        self,
        model_id: int | None = None,
        rotation_state: str | None = None,
    ) -> list[Device]:
        """List devices with optional filtering.

        Args:
            model_id: Filter by device model ID
            rotation_state: Filter by rotation state

        Returns:
            List of Device instances
        """
        stmt = select(Device).order_by(Device.key)

        if model_id is not None:
            stmt = stmt.where(Device.device_model_id == model_id)

        if rotation_state is not None:
            stmt = stmt.where(Device.rotation_state == rotation_state)

        return list(self.db.scalars(stmt).all())

    def get_device(self, device_id: int) -> Device:
        """Get a device by ID.

        Args:
            device_id: Device ID

        Returns:
            Device instance

        Raises:
            RecordNotFoundException: If device doesn't exist
        """
        stmt = select(Device).where(Device.id == device_id)
        device = self.db.scalars(stmt).one_or_none()

        if device is None:
            raise RecordNotFoundException("Device", str(device_id))

        return device

    def get_device_by_key(self, key: str) -> Device:
        """Get a device by key.

        Args:
            key: Device key

        Returns:
            Device instance

        Raises:
            RecordNotFoundException: If device doesn't exist
        """
        stmt = select(Device).where(Device.key == key)
        device = self.db.scalars(stmt).one_or_none()

        if device is None:
            raise RecordNotFoundException("Device", key)

        return device

    def create_device(self, device_model_id: int, config: str) -> Device:
        """Create a new device with Keycloak client.

        Args:
            device_model_id: ID of the device model
            config: Device configuration JSON string

        Returns:
            Created Device instance

        Raises:
            RecordNotFoundException: If model doesn't exist
            ValidationException: If config is invalid JSON or fails schema validation
            ExternalServiceException: If Keycloak client creation fails
        """
        # Validate model exists
        model = self.device_model_service.get_device_model(device_model_id)

        # Validate config JSON
        try:
            json.loads(config)
        except json.JSONDecodeError as e:
            raise ValidationException(f"config must be valid JSON: {e}") from e

        # Validate against schema if model has one
        self._validate_config_schema(config, model.config_schema)

        # Generate unique device key
        key = self._generate_device_key()

        # Build client ID
        client_id = f"iotdevice-{model.code}-{key}"

        # Create Keycloak client first
        try:
            self.keycloak_admin_service.create_client(client_id)
        except ExternalServiceException as e:
            logger.error("Failed to create Keycloak client for device: %s", e)
            raise

        # Create device record
        try:
            device = Device(
                key=key,
                device_model_id=device_model_id,
                config=config,
                rotation_state=RotationState.OK.value,
                secret_created_at=datetime.utcnow(),
            )
            # Extract and apply config fields for display
            self._apply_config_fields(device, config)

            self.db.add(device)
            self.db.flush()

            # Sync metadata to Keycloak
            self.keycloak_admin_service.update_client_metadata(
                client_id,
                name=device.device_name,
                description="This device is being managed in IoT Support.",
            )

            logger.info("Created device %s for model %s", key, model.code)
            return device

        except Exception as e:
            # Attempt to clean up Keycloak client on failure
            logger.warning("DB insert failed, attempting to cleanup Keycloak client %s", client_id)
            try:
                self.keycloak_admin_service.delete_client(client_id)
                logger.info("Cleaned up orphaned Keycloak client %s", client_id)
            except ExternalServiceException as cleanup_error:
                logger.warning(
                    "Failed to cleanup Keycloak client %s: %s - manual cleanup may be required",
                    client_id,
                    cleanup_error,
                )
            raise ExternalServiceException(
                "create device",
                f"database operation failed: {e}"
            ) from e

    def update_device(self, device_id: int, config: str) -> Device:
        """Update a device's configuration.

        Updates the config, syncs to Keycloak, and notifies the device via MQTT.

        Args:
            device_id: Device ID
            config: New configuration JSON string

        Returns:
            Updated Device instance

        Raises:
            RecordNotFoundException: If device doesn't exist
            ValidationException: If config is invalid JSON or fails schema validation
        """
        from app.services.mqtt_service import MqttService

        device = self.get_device(device_id)

        # Validate config JSON
        try:
            json.loads(config)
        except json.JSONDecodeError as e:
            raise ValidationException(f"config must be valid JSON: {e}") from e

        # Validate against schema if model has one
        self._validate_config_schema(config, device.device_model.config_schema)

        device.config = config
        # Extract and apply config fields for display
        self._apply_config_fields(device, config)
        self.db.flush()

        # Sync metadata to Keycloak
        self.keycloak_admin_service.update_client_metadata(
            device.client_id,
            name=device.device_name,
            description="This device is being managed in IoT Support.",
        )

        # Publish MQTT notification for config update
        payload = json.dumps({"client_id": device.client_id})
        self.mqtt_service.publish(f"{MqttService.TOPIC_UPDATES}/config", payload)

        logger.info("Updated device %s config", device.key)
        return device

    def delete_device(self, device_id: int) -> str:
        """Delete a device and its Keycloak client.

        Args:
            device_id: Device ID

        Returns:
            Deleted device key

        Raises:
            RecordNotFoundException: If device doesn't exist
            ExternalServiceException: If Keycloak client deletion fails
        """
        device = self.get_device(device_id)
        client_id = device.client_id
        key = device.key

        # Delete database record first
        self.db.delete(device)
        self.db.flush()

        # Delete Keycloak client (best-effort)
        try:
            self.keycloak_admin_service.delete_client(client_id)
            logger.info("Deleted device %s and Keycloak client %s", key, client_id)
        except ExternalServiceException as e:
            logger.warning(
                "Failed to delete Keycloak client %s: %s - may require manual cleanup",
                client_id,
                e,
            )

        return key

    def get_provisioning_package(self, device_id: int, partition_size: int) -> dict[str, Any]:
        """Generate provisioning package for a device as NVS binary blob.

        Retrieves the current client secret from Keycloak and generates
        an NVS partition binary that can be flashed directly to ESP32.

        Args:
            device_id: Device ID
            partition_size: NVS partition size in bytes. Must match the partition
                            table on the device. Must be at least 12KB (0x3000) and
                            a multiple of 4KB (0x1000).

        Returns:
            Dict with keys:
                - partition: "nvs" (partition name)
                - size: Size of the partition in bytes
                - data: Base64-encoded NVS binary blob

        Raises:
            RecordNotFoundException: If device doesn't exist
            ExternalServiceException: If Keycloak secret retrieval fails
            ValidationException: If partition_size is invalid
        """
        from app.utils.nvs_generator import generate_nvs_blob

        device = self.get_device(device_id)
        client_id = device.client_id

        # Get current secret from Keycloak
        secret = self.keycloak_admin_service.get_client_secret(client_id)

        # Build NVS key-value data matching /iot/provisioning JSON keys
        nvs_data: dict[str, str | None] = {
            "device_key": device.key,
            "client_id": client_id,
            "client_secret": secret,
            "token_url": self.config.oidc_token_url,
            "base_url": self.config.device_baseurl,
            "mqtt_url": self.config.device_mqtt_url,
            "wifi_ssid": self.config.wifi_ssid,
            "wifi_password": self.config.wifi_password,
            "logging_url": self.config.logging_url,
        }

        # Generate NVS binary blob with specified partition size
        nvs_blob = generate_nvs_blob(nvs_data, partition_size=partition_size)

        # Base64 encode for JSON transport
        nvs_base64 = base64.b64encode(nvs_blob).decode("ascii")

        return {
            "size": partition_size,
            "data": nvs_base64,
        }

    def trigger_rotation(self, device_id: int) -> str:
        """Trigger rotation for a single device.

        Sets the device to QUEUED state if currently OK or TIMEOUT.
        Does nothing if already QUEUED or PENDING.

        Args:
            device_id: Device ID

        Returns:
            "queued" if rotation was triggered, "already_pending" if already in progress

        Raises:
            RecordNotFoundException: If device doesn't exist
        """
        device = self.get_device(device_id)
        current_state = RotationState(device.rotation_state)

        if current_state in (RotationState.QUEUED, RotationState.PENDING):
            return "already_pending"

        device.rotation_state = RotationState.QUEUED.value
        self.db.flush()

        logger.info("Queued device %s for rotation", device.key)
        return "queued"

    def get_device_by_client_id(self, client_id: str) -> Device:
        """Get a device by its Keycloak client ID.

        Extracts the device key from the client ID and looks up the device.

        Args:
            client_id: Keycloak client ID (format: iotdevice-<model>-<key>)

        Returns:
            Device instance

        Raises:
            ValidationException: If client ID format is invalid
            RecordNotFoundException: If device doesn't exist
        """
        # Parse client ID: iotdevice-<model_code>-<device_key>
        if not client_id.startswith("iotdevice-"):
            raise ValidationException(
                f"Invalid client ID format: {client_id}"
            )

        parts = client_id.split("-")
        if len(parts) < 3:
            raise ValidationException(
                f"Invalid client ID format: {client_id}"
            )

        # Device key is the last part
        device_key = parts[-1]

        return self.get_device_by_key(device_key)

    def get_config_for_device(self, device: Device) -> str:
        """Get config for a device.

        Args:
            device: Device instance

        Returns:
            Config JSON string
        """
        return device.config

    def cache_secret_for_rotation(self, device: Device, secret: str) -> None:
        """Cache a secret for potential rollback during rotation.

        Args:
            device: Device instance
            secret: Secret to cache (will be encrypted)
        """
        device.cached_secret = self._encrypt_secret(secret)
        self.db.flush()

    def get_cached_secret(self, device: Device) -> str | None:
        """Get the cached secret for a device.

        Args:
            device: Device instance

        Returns:
            Decrypted cached secret or None if not set
        """
        if device.cached_secret is None:
            return None
        return self._decrypt_secret(device.cached_secret)

    def clear_cached_secret(self, device: Device) -> None:
        """Clear the cached secret for a device.

        Args:
            device: Device instance
        """
        device.cached_secret = None
        self.db.flush()

    def get_keycloak_status(self, device_id: int) -> dict[str, Any]:
        """Get Keycloak client status for a device.

        Returns status information about the device's Keycloak client,
        including whether it exists and a deep link to the admin console.
        Does not raise an error if the client is missing.

        Args:
            device_id: Device ID

        Returns:
            Dict with keys: exists, client_id, keycloak_uuid, console_url

        Raises:
            RecordNotFoundException: If device doesn't exist
            ExternalServiceException: If Keycloak API call fails
        """
        device = self.get_device(device_id)
        client_id = device.client_id

        exists, keycloak_uuid = self.keycloak_admin_service.get_client_status(client_id)

        console_url = None
        if exists and keycloak_uuid and self.config.keycloak_console_base_url:
            console_url = f"{self.config.keycloak_console_base_url}/{keycloak_uuid}/settings"

        return {
            "exists": exists,
            "client_id": client_id,
            "keycloak_uuid": keycloak_uuid,
            "console_url": console_url,
        }

    def sync_keycloak_client(self, device_id: int) -> dict[str, Any]:
        """Create Keycloak client for a device if missing and sync metadata.

        Idempotent operation - creates client if missing, then updates
        the client name and description to match the device.

        Args:
            device_id: Device ID

        Returns:
            Dict with keys: exists, client_id, keycloak_uuid, console_url

        Raises:
            RecordNotFoundException: If device doesn't exist
            ExternalServiceException: If Keycloak API call fails
        """
        device = self.get_device(device_id)
        client_id = device.client_id

        # create_client is idempotent - returns existing client if present
        self.keycloak_admin_service.create_client(client_id)

        # Sync device name and description to Keycloak
        self.keycloak_admin_service.update_client_metadata(
            client_id,
            name=device.device_name,
            description="This device is being managed in IoT Support.",
        )

        logger.info("Synced Keycloak client for device %s", device.key)

        # Return current status after sync
        return self.get_keycloak_status(device_id)
