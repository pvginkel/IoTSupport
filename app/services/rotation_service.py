"""Rotation service for managing device credential rotation.

This service implements the rotation state machine and handles:
- Fleet-wide rotation scheduling based on CRON expression
- Processing rotation timeouts
- Rotating one device at a time
- MQTT notifications for rotation triggers
"""

import json
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
        if self.config.ROTATION_CRON:
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
            # Step 1: Check CRON schedule (only if configured)
            # Trigger if CRON is configured AND (never scheduled before OR schedule indicates it's time)
            if self.config.ROTATION_CRON and (
                not last_scheduled_at or self._should_trigger_scheduled_rotation(last_scheduled_at)
            ):
                queued_count = self.trigger_fleet_rotation()
                result.scheduled_rotation_triggered = True
                logger.info("Scheduled rotation triggered, queued %d devices", queued_count)

            # Step 2: Process timeouts
            result.processed_timeouts = self._process_timeouts()

            # Step 3: Check for pending device, or select and rotate next device
            result.device_rotated = self._rotate_next_queued_device()

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

    def _should_trigger_scheduled_rotation(self, last_scheduled_at: datetime) -> bool:
        """Check if CRON schedule triggers a new rotation cycle.

        This method requires last_scheduled_at to be non-None. The caller should
        handle the first-run case (when last_scheduled_at is None) separately.

        Args:
            last_scheduled_at: When the last scheduled rotation was triggered (required)

        Returns:
            True if a new rotation should be triggered based on CRON schedule
        """
        if not self.config.ROTATION_CRON:
            logger.debug("ROTATION_CRON not configured, skipping scheduled rotation")
            return False

        try:
            now = datetime.utcnow()
            cron_iter = croniter(self.config.ROTATION_CRON, now)

            # Get the most recent scheduled time before now
            prev_time = cron_iter.get_prev(datetime)

            # Trigger if there's a scheduled time after last_scheduled_at
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

        This method only sets up the rotation - the actual secret regeneration
        happens when the device calls /iot/provisioning. This prevents bricking
        devices that might be restarting when we change their credentials.

        Flow:
        1. Update device state to PENDING
        2. Send MQTT notification to trigger device
        3. Device calls /iot/provisioning where secret is cached and regenerated
        4. Device writes new secret, reboots, calls /iot/config to confirm

        Args:
            device: Device to rotate
        """
        client_id = device.client_id

        logger.info("Starting rotation for device %s (client: %s)", device.key, client_id)

        # Update device state to PENDING
        # Secret caching and regeneration happens in /iot/provisioning
        device.rotation_state = RotationState.PENDING.value
        device.last_rotation_attempt_at = datetime.utcnow()
        self.db.flush()

        # Send MQTT notification (fire-and-forget)
        # Device receives this, calls /iot/provisioning to get new credentials
        self._publish_provisioning_notification(client_id)

        logger.info("Device %s rotation initiated, MQTT notification sent", device.key)

    def _publish_provisioning_notification(self, client_id: str) -> None:
        """Publish MQTT provisioning notification.

        Args:
            client_id: Device client ID to notify
        """
        from app.services.mqtt_service import MqttService

        payload = json.dumps({"client_id": client_id})
        self.mqtt_service.publish(f"{MqttService.TOPIC_UPDATES}/provisioning", payload)

    def rotate_next_queued_device(self) -> bool:
        """Rotate the next queued device if one exists.

        Called after a device completes rotation to maintain momentum.
        This creates a chain reaction where devices rotate back-to-back
        without waiting for the next CRON tick.

        Returns:
            True if a device was rotated, False if no devices are queued
        """
        device_key = self._rotate_next_queued_device()
        if device_key is not None:
            logger.info(
                "Chain rotation: started rotating device %s after previous completion",
                device_key
            )
            return True

        return False

    def _rotate_next_queued_device(self) -> str | None:
        """Rotate the next queued device if one exists.

        Called to kick off device rotation and after a device completes
        rotation to maintain momentum. This creates a chain reaction
        where devices rotate back-to-back without waiting for the next
        CRON tick.

        Returns:
            The device key of the rotated device, or None if no device
            was rotated (either because one is already pending or none
            are queued).
        """

        # Step 3: Check if there's a pending device
        pending = self._get_pending_device()
        if pending is not None:
            # Wait for current device to complete or timeout
            logger.debug("Device %s is currently pending rotation", pending.key)
            return None

        # Step 4: Select next device to rotate
        device = self._select_next_device()
        if device is not None:
            self._rotate_device(device)
            return device.key

        logger.debug("No queued devices for chain rotation")

        return None

    def get_dashboard_status(self) -> dict[str, Any]:
        """Get device dashboard status grouped by health category.

        Groups devices into:
        - healthy: OK, QUEUED, or PENDING states
        - warning: TIMEOUT state, under critical threshold days
        - critical: TIMEOUT state, at or over critical threshold days

        Returns:
            Dict with healthy, warning, critical device lists and counts
        """
        from sqlalchemy.orm import joinedload

        now = datetime.utcnow()
        # Default to 7 days if not configured (for dev/test environments)
        threshold_days = self.config.ROTATION_CRITICAL_THRESHOLD_DAYS or 7

        # Fetch all devices with their model info
        stmt = select(Device).options(joinedload(Device.device_model))
        devices = list(self.db.scalars(stmt).all())

        healthy: list[dict[str, Any]] = []
        warning: list[dict[str, Any]] = []
        critical: list[dict[str, Any]] = []

        for device in devices:
            # Calculate days since rotation
            days_since: int | None = None
            if device.last_rotation_completed_at is not None:
                delta = now - device.last_rotation_completed_at
                days_since = delta.days

            device_data = {
                "id": device.id,
                "key": device.key,
                "device_name": device.device_name,
                "device_model_code": device.device_model.code,
                "rotation_state": device.rotation_state,
                "last_rotation_completed_at": device.last_rotation_completed_at,
                "days_since_rotation": days_since,
            }

            # Categorize by state
            if device.rotation_state == RotationState.TIMEOUT.value:
                # TIMEOUT devices go to warning or critical based on time
                if days_since is not None and days_since >= threshold_days:
                    critical.append(device_data)
                else:
                    warning.append(device_data)
            else:
                # OK, QUEUED, PENDING are all healthy
                healthy.append(device_data)

        return {
            "healthy": healthy,
            "warning": warning,
            "critical": critical,
            "counts": {
                "healthy": len(healthy),
                "warning": len(warning),
                "critical": len(critical),
            },
        }
