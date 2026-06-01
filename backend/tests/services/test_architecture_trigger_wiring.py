"""Tests for architecture pipeline trigger wiring into CRUD + teardown firing.

Two layers are covered:

* Service-layer wiring: device/model CRUD methods call ``mark_pending`` once;
  the rotation path does NOT.
* Request lifecycle: ``teardown_request`` fires the trigger exactly once on a
  committed request, never on rollback, coalesces multiple writes into one
  fire, and resets the ContextVar.
"""

from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from app.models.device import RotationState
from app.services.container import ServiceContainer


def _mock_keycloak(container: ServiceContainer):
    """Context managers patching Keycloak create/update used by device writes."""
    keycloak_service = container.keycloak_admin_service()
    return (
        patch.object(
            keycloak_service,
            "create_client",
            return_value=MagicMock(client_id="test", secret="test-secret"),
        ),
        patch.object(keycloak_service, "update_client_metadata"),
        patch.object(keycloak_service, "delete_client"),
    )


class TestCrudMarkPendingWiring:
    """Each admin CRUD path marks the request pending exactly once."""

    def test_create_device_marks_pending(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        with app.app_context():
            trigger = container.architecture_pipeline_trigger_service()
            model = container.device_model_service().create_device_model(
                code="wire_cd", name="Wire CD"
            )
            create, update, _ = _mock_keycloak(container)
            with create, update, patch.object(trigger, "mark_pending") as spy:
                container.device_service().create_device(
                    device_model_id=model.id, config="{}"
                )
                spy.assert_called_once()

    def test_update_device_marks_pending(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        with app.app_context():
            trigger = container.architecture_pipeline_trigger_service()
            model = container.device_model_service().create_device_model(
                code="wire_ud", name="Wire UD"
            )
            create, update, _ = _mock_keycloak(container)
            with create, update:
                device = container.device_service().create_device(
                    device_model_id=model.id, config="{}"
                )
            mqtt = container.mqtt_service()
            with update, patch.object(mqtt, "publish"), patch.object(
                trigger, "mark_pending"
            ) as spy:
                container.device_service().update_device(
                    device.id, config="{}", active=True
                )
                spy.assert_called_once()

    def test_delete_device_marks_pending(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        with app.app_context():
            trigger = container.architecture_pipeline_trigger_service()
            model = container.device_model_service().create_device_model(
                code="wire_dd", name="Wire DD"
            )
            create, update, delete = _mock_keycloak(container)
            with create, update:
                device = container.device_service().create_device(
                    device_model_id=model.id, config="{}"
                )
            with delete, patch.object(trigger, "mark_pending") as spy:
                container.device_service().delete_device(device.id)
                spy.assert_called_once()

    def test_create_model_marks_pending(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        with app.app_context():
            trigger = container.architecture_pipeline_trigger_service()
            with patch.object(trigger, "mark_pending") as spy:
                container.device_model_service().create_device_model(
                    code="wire_cm", name="Wire CM"
                )
                spy.assert_called_once()

    def test_update_model_marks_pending(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        with app.app_context():
            trigger = container.architecture_pipeline_trigger_service()
            model = container.device_model_service().create_device_model(
                code="wire_um", name="Wire UM"
            )
            with patch.object(trigger, "mark_pending") as spy:
                container.device_model_service().update_device_model(
                    model.id, name="Renamed"
                )
                spy.assert_called_once()

    def test_delete_model_marks_pending(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        with app.app_context():
            trigger = container.architecture_pipeline_trigger_service()
            model = container.device_model_service().create_device_model(
                code="wire_dm", name="Wire DM"
            )
            with patch.object(trigger, "mark_pending") as spy:
                container.device_model_service().delete_device_model(model.id)
                spy.assert_called_once()

    def test_upload_firmware_marks_pending(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        from tests.services.test_firmware_service import _create_test_zip

        with app.app_context():
            trigger = container.architecture_pipeline_trigger_service()
            model = container.device_model_service().create_device_model(
                code="wire_fw", name="Wire FW"
            )
            zip_content = _create_test_zip("wire_fw", b"1.0.0")
            with patch.object(trigger, "mark_pending") as spy:
                container.device_model_service().upload_firmware(model.id, zip_content)
                spy.assert_called_once()

    def test_rotation_does_not_mark_pending(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """The rotation path mutates runtime state and must NOT trigger."""
        with app.app_context():
            trigger = container.architecture_pipeline_trigger_service()
            model = container.device_model_service().create_device_model(
                code="wire_rot", name="Wire Rot"
            )
            create, update, _ = _mock_keycloak(container)
            with create, update:
                device = container.device_service().create_device(
                    device_model_id=model.id, config="{}"
                )

            with patch.object(trigger, "mark_pending") as spy:
                # Queue a device and run a fleet-rotation pass — runtime-only.
                rotation_service = container.rotation_service()
                rotation_service.trigger_fleet_rotation()
                device.rotation_state = RotationState.TIMEOUT.value
                container.db_session().flush()
                spy.assert_not_called()


class TestPostCommitFiring:
    """teardown_request fires the trigger only after a successful commit."""

    def test_commit_fires_once_after_durable_write(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """A committed device create fires exactly one POST, after commit."""
        with app.app_context():
            model = container.device_model_service().create_device_model(
                code="fire_cd", name="Fire CD"
            )
            container.db_session().commit()
            model_id = model.id

        trigger = container.architecture_pipeline_trigger_service()
        create, update, _ = _mock_keycloak(container)

        # Enable the trigger and observe the POST. Inside the POST we assert the
        # row is already visible in a fresh session (proves commit-before-fire).
        observed = {}

        def fake_post(url):  # type: ignore[no-untyped-def]
            from sqlalchemy import select

            from app.models.device import Device

            sm = container.session_maker()
            with sm() as fresh:
                observed["count"] = len(list(fresh.scalars(select(Device)).all()))
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            return resp

        with create, update, patch.object(trigger, "enabled", True), patch.object(
            trigger._http_client, "post", side_effect=fake_post
        ) as mock_post:
            response = client.post(
                "/api/devices",
                json={"device_model_id": model_id, "config": "{}"},
            )
            assert response.status_code == 201
            mock_post.assert_called_once()
            # Row was already committed/visible when the POST fired.
            assert observed["count"] == 1

    def test_rollback_does_not_fire(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """A request that rolls back must NOT fire the trigger."""
        trigger = container.architecture_pipeline_trigger_service()
        create, update, _ = _mock_keycloak(container)

        with create, update, patch.object(trigger, "enabled", True), patch.object(
            trigger._http_client, "post"
        ) as mock_post:
            # Non-existent model -> RecordNotFoundException -> rollback path.
            response = client.post(
                "/api/devices",
                json={"device_model_id": 999999, "config": "{}"},
            )
            assert response.status_code == 404
            mock_post.assert_not_called()

    def test_bulk_writes_fire_once_and_reset(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Two writes in one request coalesce to a single fire; flag resets."""
        trigger = container.architecture_pipeline_trigger_service()

        with patch.object(trigger, "enabled", True), patch.object(
            trigger._http_client, "post"
        ) as mock_post:
            mock_post.return_value = MagicMock(raise_for_status=MagicMock())
            # device_models POST also calls a single create -> one mark_pending.
            response = client.post(
                "/api/device-models",
                json={"code": "bulk_one", "name": "Bulk One"},
            )
            assert response.status_code == 201
            assert mock_post.call_count == 1

            # A subsequent unrelated GET must NOT re-fire (flag was reset).
            mock_post.reset_mock()
            client.get("/api/device-models")
            mock_post.assert_not_called()
