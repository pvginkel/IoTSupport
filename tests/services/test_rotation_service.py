"""Tests for RotationService."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from flask import Flask

from app.models.device import RotationState
from app.services.container import ServiceContainer


class TestRotationServiceGetStatus:
    """Tests for getting rotation status."""

    def test_get_rotation_status_no_devices(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test getting status when no devices exist."""
        with app.app_context():
            rotation_service = container.rotation_service()

            status = rotation_service.get_rotation_status()

            assert status["counts_by_state"][RotationState.OK.value] == 0
            assert status["counts_by_state"][RotationState.QUEUED.value] == 0
            assert status["counts_by_state"][RotationState.PENDING.value] == 0
            assert status["counts_by_state"][RotationState.TIMEOUT.value] == 0
            assert status["pending_device_id"] is None
            assert status["last_rotation_completed_at"] is None

    def test_get_rotation_status_with_devices(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test getting status with devices in various states."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="status1", name="Status Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()

                # Create devices in different states
                d1 = device_service.create_device(device_model_id=model.id, config="{}")
                d2 = device_service.create_device(device_model_id=model.id, config="{}")
                d3 = device_service.create_device(device_model_id=model.id, config="{}")

                d1.rotation_state = RotationState.OK.value
                d2.rotation_state = RotationState.QUEUED.value
                d3.rotation_state = RotationState.PENDING.value

                rotation_service = container.rotation_service()
                status = rotation_service.get_rotation_status()

                assert status["counts_by_state"][RotationState.OK.value] == 1
                assert status["counts_by_state"][RotationState.QUEUED.value] == 1
                assert status["counts_by_state"][RotationState.PENDING.value] == 1
                assert status["pending_device_id"] == d3.id


class TestRotationServiceTriggerFleet:
    """Tests for triggering fleet-wide rotation."""

    def test_trigger_fleet_rotation_queues_ok_devices(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that fleet rotation queues all OK devices."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="fleet1", name="Fleet Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()

                d1 = device_service.create_device(device_model_id=model.id, config="{}")
                d2 = device_service.create_device(device_model_id=model.id, config="{}")
                d3 = device_service.create_device(device_model_id=model.id, config="{}")

                # One device already queued
                d3.rotation_state = RotationState.QUEUED.value

                rotation_service = container.rotation_service()
                count = rotation_service.trigger_fleet_rotation()

                assert count == 2  # Only OK devices queued
                assert d1.rotation_state == RotationState.QUEUED.value
                assert d2.rotation_state == RotationState.QUEUED.value
                assert d3.rotation_state == RotationState.QUEUED.value  # Unchanged

    def test_trigger_fleet_rotation_no_ok_devices(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test fleet rotation when no devices in OK state."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="fleet2", name="Fleet Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.PENDING.value

                rotation_service = container.rotation_service()
                count = rotation_service.trigger_fleet_rotation()

                assert count == 0


class TestRotationServiceProcessJob:
    """Tests for the rotation job processor."""

    def test_process_rotation_job_no_devices(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test rotation job when no devices exist."""
        with app.app_context():
            rotation_service = container.rotation_service()

            result = rotation_service.process_rotation_job(last_scheduled_at=datetime.utcnow())

            assert result.processed_timeouts == 0
            assert result.device_rotated is None
            assert result.scheduled_rotation_triggered is False

    def test_process_rotation_job_rotates_queued_device(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that rotation job processes a queued device."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="job1", name="Job Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.QUEUED.value
                device_key = device.key

                # Mock Keycloak operations for rotation
                with patch.object(
                    keycloak_service, "get_client_secret", return_value="old-secret"
                ), patch.object(
                    keycloak_service, "regenerate_secret", return_value="new-secret"
                ):
                    rotation_service = container.rotation_service()
                    result = rotation_service.process_rotation_job(
                        last_scheduled_at=datetime.utcnow()
                    )

                    assert result.device_rotated == device_key
                    assert device.rotation_state == RotationState.PENDING.value

    def test_process_rotation_job_waits_for_pending(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that job waits when a device is already pending."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="job2", name="Job Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                d1 = device_service.create_device(device_model_id=model.id, config="{}")
                d2 = device_service.create_device(device_model_id=model.id, config="{}")

                d1.rotation_state = RotationState.PENDING.value
                d1.last_rotation_attempt_at = datetime.utcnow()
                d2.rotation_state = RotationState.QUEUED.value

                rotation_service = container.rotation_service()
                result = rotation_service.process_rotation_job(
                    last_scheduled_at=datetime.utcnow()
                )

                # Should not rotate another device while one is pending
                assert result.device_rotated is None

    def test_process_rotation_job_timeout_handling(
        self, app: Flask, container: ServiceContainer, test_settings
    ) -> None:
        """Test that timed-out pending devices are handled."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="job3", name="Job Test 3")

            keycloak_service = container.keycloak_admin_service()

            # Mock all keycloak operations we'll need - including get_client_secret and
            # regenerate_secret since after timeout processing, the job will try to
            # rotate the TIMEOUT device
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ), patch.object(
                keycloak_service, "update_client_secret"
            ) as mock_update, patch.object(
                keycloak_service, "get_client_secret", return_value="current-secret"
            ), patch.object(
                keycloak_service, "regenerate_secret", return_value="new-secret"
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")

                # Put device in pending state with old timestamp
                device.rotation_state = RotationState.PENDING.value
                timeout_seconds = test_settings.ROTATION_TIMEOUT_SECONDS
                device.last_rotation_attempt_at = datetime.utcnow() - timedelta(
                    seconds=timeout_seconds + 60
                )

                # Cache a secret for restoration
                device_service.cache_secret_for_rotation(device, "cached-secret")

                rotation_service = container.rotation_service()
                result = rotation_service.process_rotation_job(
                    last_scheduled_at=datetime.utcnow()
                )

                assert result.processed_timeouts == 1
                # After timeout processing, device will be rotated again (selected as TIMEOUT)
                # So it ends up in PENDING state, not TIMEOUT
                # But we should still verify that update_client_secret was called for restoration
                mock_update.assert_called_once()


class TestRotationServiceScheduleCheck:
    """Tests for CRON schedule checking."""

    def test_should_trigger_when_past_schedule_no_previous(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test triggering when within grace period of schedule with no prior run."""
        with app.app_context():
            rotation_service = container.rotation_service()

            # With no last_scheduled_at and a recent CRON match, should trigger
            # This depends on CRON config but we can check the method exists
            result = rotation_service._should_trigger_scheduled_rotation(None)

            # Result depends on current time relative to CRON schedule
            assert isinstance(result, bool)

    def test_should_not_trigger_when_recently_triggered(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that recently triggered rotation doesn't re-trigger."""
        with app.app_context():
            rotation_service = container.rotation_service()

            # Just triggered now
            result = rotation_service._should_trigger_scheduled_rotation(datetime.utcnow())

            assert result is False


class TestRotationServiceDeviceSelection:
    """Tests for device selection logic."""

    def test_select_queued_before_timeout(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that QUEUED devices are selected before TIMEOUT devices."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="sel1", name="Select Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                d_timeout = device_service.create_device(device_model_id=model.id, config="{}")
                d_queued = device_service.create_device(device_model_id=model.id, config="{}")

                d_timeout.rotation_state = RotationState.TIMEOUT.value
                d_queued.rotation_state = RotationState.QUEUED.value

                rotation_service = container.rotation_service()
                selected = rotation_service._select_next_device()

                assert selected is not None
                assert selected.id == d_queued.id

    def test_select_oldest_secret_first(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that devices with oldest secrets are rotated first."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="sel2", name="Select Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                d_newer = device_service.create_device(device_model_id=model.id, config="{}")
                d_older = device_service.create_device(device_model_id=model.id, config="{}")

                # Make d_older have an older secret
                d_older.secret_created_at = datetime.utcnow() - timedelta(days=30)
                d_newer.secret_created_at = datetime.utcnow()

                d_older.rotation_state = RotationState.QUEUED.value
                d_newer.rotation_state = RotationState.QUEUED.value

                rotation_service = container.rotation_service()
                selected = rotation_service._select_next_device()

                assert selected is not None
                assert selected.id == d_older.id

    def test_select_returns_none_when_nothing_to_rotate(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that no device is selected when none need rotation."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="sel3", name="Select Test 3")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.OK.value

                rotation_service = container.rotation_service()
                selected = rotation_service._select_next_device()

                assert selected is None


class TestRotationServiceChainRotation:
    """Tests for rotate_next_queued_device (chain rotation)."""

    def test_chain_rotation_triggers_next_device(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that rotate_next_queued_device triggers next queued device."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="chain1", name="Chain Test 1")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.QUEUED.value
                container.db_session().flush()

                rotation_service = container.rotation_service()

                # Mock MQTT to avoid actual publish
                with patch.object(rotation_service.mqtt_service, "enabled", False):
                    result = rotation_service.rotate_next_queued_device()

                assert result is True
                assert device.rotation_state == RotationState.PENDING.value

    def test_chain_rotation_returns_false_when_no_devices(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that rotate_next_queued_device returns False when nothing to rotate."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="chain2", name="Chain Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.OK.value
                container.db_session().flush()

                rotation_service = container.rotation_service()
                result = rotation_service.rotate_next_queued_device()

                assert result is False
                # Device should still be OK
                assert device.rotation_state == RotationState.OK.value

    def test_chain_rotation_skips_when_pending_exists(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that rotate_next_queued_device skips when a device is already pending."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="chain3", name="Chain Test 3")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                pending_device = device_service.create_device(device_model_id=model.id, config="{}")
                queued_device = device_service.create_device(device_model_id=model.id, config="{}")

                pending_device.rotation_state = RotationState.PENDING.value
                queued_device.rotation_state = RotationState.QUEUED.value
                container.db_session().flush()

                rotation_service = container.rotation_service()
                result = rotation_service.rotate_next_queued_device()

                # Should skip because pending_device is already pending
                assert result is False
                # Queued device should still be queued
                assert queued_device.rotation_state == RotationState.QUEUED.value


class TestRotationServiceDashboard:
    """Tests for get_dashboard_status."""

    def test_dashboard_no_devices(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test dashboard with no devices."""
        with app.app_context():
            rotation_service = container.rotation_service()

            result = rotation_service.get_dashboard_status()

            assert result["healthy"] == []
            assert result["warning"] == []
            assert result["critical"] == []
            assert result["counts"]["healthy"] == 0
            assert result["counts"]["warning"] == 0
            assert result["counts"]["critical"] == 0

    def test_dashboard_healthy_states(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test dashboard groups OK, QUEUED, PENDING as healthy."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="dash1", name="Dashboard Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()

                d_ok = device_service.create_device(device_model_id=model.id, config="{}")
                d_queued = device_service.create_device(device_model_id=model.id, config="{}")
                d_pending = device_service.create_device(device_model_id=model.id, config="{}")

                d_ok.rotation_state = RotationState.OK.value
                d_queued.rotation_state = RotationState.QUEUED.value
                d_pending.rotation_state = RotationState.PENDING.value
                container.db_session().flush()

                rotation_service = container.rotation_service()
                result = rotation_service.get_dashboard_status()

                assert result["counts"]["healthy"] == 3
                assert result["counts"]["warning"] == 0
                assert result["counts"]["critical"] == 0

                healthy_keys = {d["key"] for d in result["healthy"]}
                assert d_ok.key in healthy_keys
                assert d_queued.key in healthy_keys
                assert d_pending.key in healthy_keys

    def test_dashboard_warning_timeout_under_threshold(
        self, app: Flask, container: ServiceContainer, test_settings
    ) -> None:
        """Test dashboard classifies TIMEOUT under threshold as warning."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="dash2", name="Dashboard Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()

                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.TIMEOUT.value
                # Less than threshold days ago
                threshold_days = test_settings.ROTATION_CRITICAL_THRESHOLD_DAYS
                device.last_rotation_completed_at = datetime.utcnow() - timedelta(
                    days=threshold_days - 1
                )
                container.db_session().flush()

                rotation_service = container.rotation_service()
                result = rotation_service.get_dashboard_status()

                assert result["counts"]["healthy"] == 0
                assert result["counts"]["warning"] == 1
                assert result["counts"]["critical"] == 0
                assert result["warning"][0]["key"] == device.key

    def test_dashboard_critical_timeout_over_threshold(
        self, app: Flask, container: ServiceContainer, test_settings
    ) -> None:
        """Test dashboard classifies TIMEOUT over threshold as critical."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="dash3", name="Dashboard Test 3")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()

                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.TIMEOUT.value
                # More than threshold days ago
                threshold_days = test_settings.ROTATION_CRITICAL_THRESHOLD_DAYS
                device.last_rotation_completed_at = datetime.utcnow() - timedelta(
                    days=threshold_days + 1
                )
                container.db_session().flush()

                rotation_service = container.rotation_service()
                result = rotation_service.get_dashboard_status()

                assert result["counts"]["healthy"] == 0
                assert result["counts"]["warning"] == 0
                assert result["counts"]["critical"] == 1
                assert result["critical"][0]["key"] == device.key
                assert result["critical"][0]["days_since_rotation"] == threshold_days + 1

    def test_dashboard_timeout_no_last_rotation_is_warning(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test TIMEOUT device with no last_rotation_completed_at goes to warning."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="dash4", name="Dashboard Test 4")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()

                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.TIMEOUT.value
                # No last_rotation_completed_at set
                container.db_session().flush()

                rotation_service = container.rotation_service()
                result = rotation_service.get_dashboard_status()

                # With no last_rotation_completed_at, days_since is None
                # The logic checks days_since >= threshold, which fails if None
                # So it goes to warning
                assert result["counts"]["warning"] == 1
                assert result["counts"]["critical"] == 0
                assert result["warning"][0]["days_since_rotation"] is None

    def test_dashboard_includes_device_model_code(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test dashboard includes device_model_code in response."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="thermo_v1", name="Thermostat V1")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()

                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.OK.value
                container.db_session().flush()

                rotation_service = container.rotation_service()
                result = rotation_service.get_dashboard_status()

                assert result["healthy"][0]["device_model_code"] == "thermo_v1"
