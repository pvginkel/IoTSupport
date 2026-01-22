"""Rotation service for managing device credential rotation.

This service implements the rotation state machine and handles:
- Fleet-wide rotation scheduling based on CRON expression
- Processing rotation timeouts
- Rotating one device at a time
- MQTT notifications for rotation triggers
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from croniter import croniter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.exceptions import ExternalServiceException
from app.models.device import Device, RotationState

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.device_service import DeviceService
    from app.services.keycloak_admin_service import KeycloakAdminService
    from app.services.metrics_service import MetricsService
    from app.services.mqtt_service import MqttService

logger = logging.getLogger(__name__)


@dataclass
class RotationJobResult:
    """Result of a rotation job execution."""

    processed_timeouts: int
    device_rotated: str | None
    scheduled_rotation_triggered: bool


class RotationService:
    """Service for managing device credential rotation.

    This is a Factory service (requires database session) that handles
    the rotation state machine and scheduled rotation processing.
    """

    # MQTT topic for rotation notifications
    ROTATION_TOPIC_PREFIX = "iotsupport"
    ROTATION_TOPIC_SUFFIX = "rotation"

    def __init__(
        self,
        db: Session,
        config: "Settings",
        device_service: "DeviceService",
        keycloak_admin_service: "KeycloakAdminService",
        mqtt_service: "MqttService",
        metrics_service: "MetricsService",
    ) -> None:
        """Initialize rotation service.

        Args:
            db: SQLAlchemy database session
            config: Application settings
            device_service: Device service for device operations
            keycloak_admin_service: Keycloak service for secret management
            mqtt_service: MQTT service for notifications
            metrics_service: Metrics service for recording operations
        """
        self.db = db
        self.config = config
        self.device_service = device_service
        self.keycloak_admin_service = keycloak_admin_service
        self.mqtt_service = mqtt_service
        self.metrics_service = metrics_service

    def get_rotation_status(self) -> dict[str, Any]:
        """Get current rotation status across all devices.

        Returns:
            Dict with counts_by_state, pending_device_id, and last_rotation_completed_at
        """
        # Count devices by state
        counts_by_state = {}
        for state in RotationState:
            stmt = select(func.count()).select_from(Device).where(
                Device.rotation_state == state.value
            )
            count = self.db.execute(stmt).scalar() or 0
            counts_by_state[state.value] = count

        # Get currently pending device
        pending_stmt = select(Device).where(
            Device.rotation_state == RotationState.PENDING.value
        )
        pending_device = self.db.scalars(pending_stmt).first()
        pending_device_id = pending_device.id if pending_device else None

        # Get most recent rotation completion
        last_completion_stmt = select(func.max(Device.last_rotation_completed_at))
        last_completion = self.db.execute(last_completion_stmt).scalar()

        # Calculate next scheduled rotation
        next_scheduled = None
        try:
            cron_iter = croniter(self.config.ROTATION_CRON, datetime.utcnow())
            next_time = cron_iter.get_next(datetime)
            next_scheduled = next_time.isoformat() + "Z"
        except Exception as e:
            logger.warning("Failed to calculate next rotation time: %s", e)

        return {
            "counts_by_state": counts_by_state,
            "pending_device_id": pending_device_id,
            "last_rotation_completed_at": last_completion,
            "next_scheduled_rotation": next_scheduled,
        }

    def trigger_fleet_rotation(self) -> int:
        """Queue all OK devices for rotation.

        Sets all devices with OK state to QUEUED.

        Returns:
            Number of devices queued
        """
        stmt = select(Device).where(Device.rotation_state == RotationState.OK.value)
        devices = list(self.db.scalars(stmt).all())

        for device in devices:
            device.rotation_state = RotationState.QUEUED.value

        self.db.flush()

        logger.info("Queued %d devices for rotation", len(devices))
        return len(devices)

    def process_rotation_job(self, last_scheduled_at: datetime | None = None) -> RotationJobResult:
        """Execute a single rotation job cycle.

        This method is designed to be called by the CLI rotation job.

        Steps:
        1. Check CRON schedule and queue all devices if triggered
        2. Process any timed-out PENDING devices
        3. Select and rotate one device (QUEUED first, then TIMEOUT)

        Args:
            last_scheduled_at: Last time the scheduled rotation was triggered
                (used to avoid re-triggering within same CRON window)

        Returns:
            RotationJobResult with details of what was done
        """
        start_time = time.perf_counter()
        result = RotationJobResult(
            processed_timeouts=0,
            device_rotated=None,
            scheduled_rotation_triggered=False,
        )

        try:
            # Step 1: Check CRON schedule
            if self._should_trigger_scheduled_rotation(last_scheduled_at):
                queued_count = self.trigger_fleet_rotation()
                result.scheduled_rotation_triggered = True
                logger.info("Scheduled rotation triggered, queued %d devices", queued_count)

            # Step 2: Process timeouts
            result.processed_timeouts = self._process_timeouts()

            # Step 3: Check if there's a pending device
            pending = self._get_pending_device()
            if pending is not None:
                # Wait for current device to complete or timeout
                logger.debug("Device %s is currently pending rotation", pending.key)
                return result

            # Step 4: Select next device to rotate
            device = self._select_next_device()
            if device is not None:
                self._rotate_device(device)
                result.device_rotated = device.key

            # Record metrics
            duration = time.perf_counter() - start_time
            self.metrics_service.increment_counter(
                "iot_rotation_job_runs_total",
                labels={"result": "success"}
            )
            logger.info(
                "Rotation job completed in %.3fs: timeouts=%d, rotated=%s, scheduled=%s",
                duration,
                result.processed_timeouts,
                result.device_rotated,
                result.scheduled_rotation_triggered,
            )

            return result

        except Exception as e:
            duration = time.perf_counter() - start_time
            self.metrics_service.increment_counter(
                "iot_rotation_job_runs_total",
                labels={"result": "error"}
            )
            logger.error("Rotation job failed after %.3fs: %s", duration, e)
            raise

    def _should_trigger_scheduled_rotation(self, last_scheduled_at: datetime | None) -> bool:
        """Check if CRON schedule triggers a new rotation cycle.

        Args:
            last_scheduled_at: When the last scheduled rotation was triggered

        Returns:
            True if a new rotation should be triggered
        """
        try:
            now = datetime.utcnow()
            cron_iter = croniter(self.config.ROTATION_CRON, now)

            # Get the most recent scheduled time before now
            prev_time = cron_iter.get_prev(datetime)

            # If we haven't triggered since the last scheduled time, trigger now
            if last_scheduled_at is None:
                # First run, trigger if we're within 5 minutes of a scheduled time
                diff = abs((now - prev_time).total_seconds())
                return diff < 300  # 5 minutes grace period

            return prev_time > last_scheduled_at

        except Exception as e:
            logger.warning("Failed to check CRON schedule: %s", e)
            return False

    def _process_timeouts(self) -> int:
        """Process devices that have timed out during rotation.

        Devices in PENDING state past the timeout threshold have their
        old secret restored and are moved to TIMEOUT state.

        Returns:
            Number of devices processed
        """
        timeout_seconds = self.config.ROTATION_TIMEOUT_SECONDS
        now = datetime.utcnow()

        # Find timed-out devices
        stmt = select(Device).where(
            Device.rotation_state == RotationState.PENDING.value
        )
        pending_devices = list(self.db.scalars(stmt).all())

        processed = 0
        for device in pending_devices:
            if device.last_rotation_attempt_at is None:
                continue

            elapsed = (now - device.last_rotation_attempt_at).total_seconds()
            if elapsed <= timeout_seconds:
                continue

            # Device has timed out
            logger.warning(
                "Device %s rotation timed out after %.0fs (threshold: %ds)",
                device.key,
                elapsed,
                timeout_seconds,
            )

            # Restore old secret if cached
            cached_secret = self.device_service.get_cached_secret(device)
            if cached_secret:
                try:
                    self.keycloak_admin_service.update_client_secret(
                        device.client_id, cached_secret
                    )
                    logger.info("Restored old secret for device %s", device.key)
                except ExternalServiceException as e:
                    # Log but continue - device stays in PENDING, will retry
                    logger.error(
                        "Failed to restore secret for device %s: %s - will retry",
                        device.key,
                        e,
                    )
                    continue

            # Move to TIMEOUT state
            device.rotation_state = RotationState.TIMEOUT.value
            self.device_service.clear_cached_secret(device)
            processed += 1

        self.db.flush()
        return processed

    def _get_pending_device(self) -> Device | None:
        """Get the currently pending device if any.

        Returns:
            Device in PENDING state or None
        """
        stmt = select(Device).where(
            Device.rotation_state == RotationState.PENDING.value
        )
        return self.db.scalars(stmt).first()

    def _select_next_device(self) -> Device | None:
        """Select the next device to rotate.

        Priority:
        1. QUEUED device with oldest secret_created_at
        2. TIMEOUT device (retry)

        Returns:
            Device to rotate or None if no devices need rotation
        """
        # Try QUEUED devices first (oldest secret first)
        queued_stmt = (
            select(Device)
            .where(Device.rotation_state == RotationState.QUEUED.value)
            .order_by(Device.secret_created_at.asc())
            .limit(1)
        )
        device = self.db.scalars(queued_stmt).first()

        if device is not None:
            return device

        # Fall back to TIMEOUT devices
        timeout_stmt = (
            select(Device)
            .where(Device.rotation_state == RotationState.TIMEOUT.value)
            .order_by(Device.last_rotation_attempt_at.asc())
            .limit(1)
        )
        return self.db.scalars(timeout_stmt).first()

    def _rotate_device(self, device: Device) -> None:
        """Initiate rotation for a device.

        1. Cache current secret for rollback
        2. Regenerate secret in Keycloak
        3. Update device state to PENDING
        4. Send MQTT notification

        Args:
            device: Device to rotate
        """
        client_id = device.client_id

        logger.info("Starting rotation for device %s (client: %s)", device.key, client_id)

        # Get and cache current secret
        try:
            current_secret = self.keycloak_admin_service.get_client_secret(client_id)
            self.device_service.cache_secret_for_rotation(device, current_secret)
        except ExternalServiceException as e:
            logger.error("Failed to cache secret for device %s: %s", device.key, e)
            raise

        # Regenerate secret in Keycloak
        try:
            self.keycloak_admin_service.regenerate_secret(client_id)
            logger.debug("Regenerated secret for device %s", device.key)
        except ExternalServiceException as e:
            # Rollback cached secret
            self.device_service.clear_cached_secret(device)
            logger.error("Failed to regenerate secret for device %s: %s", device.key, e)
            raise

        # Update device state
        device.rotation_state = RotationState.PENDING.value
        device.last_rotation_attempt_at = datetime.utcnow()
        self.db.flush()

        # Send MQTT notification (fire-and-forget)
        topic = f"{self.ROTATION_TOPIC_PREFIX}/{client_id}/{self.ROTATION_TOPIC_SUFFIX}"
        self._publish_rotation_notification(topic)

        logger.info("Device %s rotation initiated, MQTT notification sent", device.key)

    def _publish_rotation_notification(self, topic: str) -> None:
        """Publish MQTT rotation notification.

        Args:
            topic: MQTT topic to publish to
        """
        if not self.mqtt_service.enabled:
            logger.debug("MQTT disabled, skipping rotation notification")
            return

        try:
            # Publish empty payload - device just needs the trigger
            if self.mqtt_service.client is not None:
                result = self.mqtt_service.client.publish(
                    topic, payload="", qos=1, retain=False
                )
                if result.rc != 0:
                    logger.warning("MQTT publish failed for %s: rc=%d", topic, result.rc)
        except Exception as e:
            # Fire-and-forget - log but don't fail
            logger.error("Exception publishing MQTT to %s: %s", topic, e)
