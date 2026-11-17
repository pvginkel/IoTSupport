"""Tests for pipeline API endpoints."""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.app_config import AppSettings
from app.services.container import ServiceContainer
from tests.conftest import create_test_firmware
from tests.services.test_firmware_service import (
    FlashFile,
    _create_test_zip,
    _flash_image,
    _flasher_args_json,
    _standard_flash_files,
    _stored_flash_manifest,
)


class TestPipelineFirmwareUpload:
    """Tests for POST /api/pipeline/models/<code>/firmware."""

    def test_upload_firmware_by_code_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test uploading firmware ZIP using model code."""
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code="pipetest", name="Pipeline Test")
            container.db_session().commit()

        zip_content = _create_test_zip("pipetest", b"1.0.0")

        response = client.post(
            "/api/pipeline/models/pipetest/firmware",
            data=zip_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["firmware_version"] == "1.0.0"
        assert data["code"] == "pipetest"

    def test_upload_firmware_raw_bin_rejected(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that raw .bin upload is rejected (only ZIP accepted)."""
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code="rawbin", name="Raw Bin Test")
            container.db_session().commit()

        firmware_content = create_test_firmware(b"1.0.0")

        response = client.post(
            "/api/pipeline/models/rawbin/firmware",
            data=firmware_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 400

    def test_upload_firmware_model_not_found(
        self, client: FlaskClient
    ) -> None:
        """Test uploading firmware for non-existent model returns 404."""
        zip_content = _create_test_zip("nonexistent", b"1.0.0")

        response = client.post(
            "/api/pipeline/models/nonexistent/firmware",
            data=zip_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 404
        data = response.get_json()
        assert "nonexistent" in data["error"]

    def test_upload_firmware_publishes_mqtt_for_devices(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that firmware upload publishes MQTT notifications for all devices."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="mqtttest", name="MQTT Test")

            # Create a device for this model
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
                device = device_service.create_device(
                    device_model_id=model.id, config="{}"
                )
                expected_client_id = device.client_id

            container.db_session().commit()

        zip_content = _create_test_zip("mqtttest", b"2.0.0")
        mqtt_service = app.container.mqtt_service()

        with patch.object(mqtt_service, "publish") as mock_publish:
            response = client.post(
                "/api/pipeline/models/mqtttest/firmware",
                data=zip_content,
                content_type="application/octet-stream",
            )

            assert response.status_code == 200

            # Verify MQTT was published
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args[0]
            topic = call_args[0]
            payload_str = call_args[1]

            assert topic == "iotsupport/updates/firmware"
            payload = json.loads(payload_str)
            assert payload["client_id"] == expected_client_id
            assert payload["firmware_version"] == "2.0.0"

    def test_upload_firmware_no_content_returns_400(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test uploading empty firmware returns 400."""
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code="emptytest", name="Empty Test")
            container.db_session().commit()

        response = client.post(
            "/api/pipeline/models/emptytest/firmware",
            data=b"",
            content_type="application/octet-stream",
        )

        assert response.status_code == 400


class TestPipelineFirmwareZipUpload:
    """Tests for ZIP firmware upload via POST /api/pipeline/models/<code>/firmware."""

    def test_upload_firmware_zip_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test uploading firmware as a ZIP bundle via pipeline."""
        model_code = "ziptest"
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code=model_code, name="ZIP Test")
            container.db_session().commit()

        zip_content = _create_test_zip(model_code, b"3.0.0")

        response = client.post(
            f"/api/pipeline/models/{model_code}/firmware",
            data=zip_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["firmware_version"] == "3.0.0"
        assert data["code"] == model_code

    def test_upload_firmware_zip_invalid_structure(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test uploading ZIP with wrong structure returns 400."""
        model_code = "zipbad"
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code=model_code, name="Bad ZIP Test")
            container.db_session().commit()

        # Create a ZIP missing required files
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("random.txt", b"not firmware")
        bad_zip = buf.getvalue()

        response = client.post(
            f"/api/pipeline/models/{model_code}/firmware",
            data=bad_zip,
            content_type="application/octet-stream",
        )

        assert response.status_code == 400

    def test_upload_firmware_zip_creates_s3_objects(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that ZIP upload creates artifacts in S3."""
        model_code = "zips3"
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code=model_code, name="ZIP S3 Test")
            container.db_session().commit()

        zip_content = _create_test_zip(model_code, b"4.1.0")

        response = client.post(
            f"/api/pipeline/models/{model_code}/firmware",
            data=zip_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 200

        # Verify S3 artifacts exist
        s3 = container.s3_service()
        assert s3.file_exists(f"firmware/{model_code}/4.1.0/firmware.bin")
        assert s3.file_exists(f"firmware/{model_code}/4.1.0/firmware.elf")

    def test_upload_firmware_zip_with_flash_images(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that a ZIP with the build's flash images stores them with the version."""
        model_code = "zipflash"
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code=model_code, name="ZIP Flash Test")
            container.db_session().commit()

        zip_content = _create_test_zip(
            model_code, b"4.2.0", flash_files=_standard_flash_files(model_code)
        )

        response = client.post(
            f"/api/pipeline/models/{model_code}/firmware",
            data=zip_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 200
        manifest = _stored_flash_manifest(container.s3_service(), model_code, "4.2.0")
        assert manifest is not None
        assert [image.offset for image in manifest.images] == [0x0, 0x8000, 0xD000, 0x10000]

    def test_upload_firmware_zip_partial_flash_images_rejected(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that a ZIP lacking an image its build lists returns 400."""
        model_code = "zipflashpart"
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code=model_code, name="ZIP Partial Flash Test")
            container.db_session().commit()

        zip_content = _create_test_zip(
            model_code,
            b"4.2.0",
            flash_files=_standard_flash_files(model_code),
            omit_files={"bootloader.bin"},
        )

        response = client.post(
            f"/api/pipeline/models/{model_code}/firmware",
            data=zip_content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 400
        assert "missing bootloader.bin" in response.get_json()["error"]


class TestPipelineFirmwareVersion:
    """Tests for GET /api/pipeline/models/<code>/firmware-version."""

    def test_get_firmware_version_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting firmware version by model code."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="vertest", name="Version Test")
            model.firmware_version = "3.2.1"
            container.db_session().commit()

        response = client.get("/api/pipeline/models/vertest/firmware-version")

        assert response.status_code == 200
        data = response.get_json()
        assert data["code"] == "vertest"
        assert data["firmware_version"] == "3.2.1"

    def test_get_firmware_version_no_firmware(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting firmware version when none uploaded."""
        with app.app_context():
            model_service = container.device_model_service()
            model_service.create_device_model(code="nofwtest", name="No Firmware Test")
            container.db_session().commit()

        response = client.get("/api/pipeline/models/nofwtest/firmware-version")

        assert response.status_code == 200
        data = response.get_json()
        assert data["code"] == "nofwtest"
        assert data["firmware_version"] is None

    def test_get_firmware_version_model_not_found(
        self, client: FlaskClient
    ) -> None:
        """Test getting firmware version for non-existent model returns 404."""
        response = client.get("/api/pipeline/models/nonexistent/firmware-version")

        assert response.status_code == 404
        data = response.get_json()
        assert "nonexistent" in data["error"]


class TestPipelineFleetProjection:
    """Tests for GET /api/pipeline/fleet-projection."""

    def test_fleet_projection_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Pipeline client gets a schema-valid projection body (200)."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="projapi", name="Proj API")
            model.firmware_version = "9.9.9"

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(keycloak_service, "update_client_metadata"):
                container.device_service().create_device(
                    device_model_id=model.id, config='{"deviceName": "Dev One"}'
                )
            container.db_session().commit()

        response = client.get("/api/pipeline/fleet-projection")

        assert response.status_code == 200
        data = response.get_json()
        assert "devices" in data
        assert "fleet" in data
        assert len(data["devices"]) == 1
        device = data["devices"][0]
        assert device["model_code"] == "projapi"
        assert device["firmware_version"] == "9.9.9"
        assert device["device_name"] == "Dev One"
        assert device["created_at"] is not None
        assert "mqtt_url" in data["fleet"]
        assert "oidc_issuer_url" in data["fleet"]

    def test_fleet_projection_empty(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Empty fleet returns 200 with an empty device list (no 404)."""
        response = client.get("/api/pipeline/fleet-projection")
        assert response.status_code == 200
        assert response.get_json()["devices"] == []

    def test_fleet_projection_no_token_unauthorized(
        self, oidc_client: FlaskClient
    ) -> None:
        """No bearer token -> 401 when OIDC is enabled."""
        response = oidc_client.get("/api/pipeline/fleet-projection")
        assert response.status_code == 401

    def test_fleet_projection_wrong_role_forbidden(
        self, oidc_client: FlaskClient, generate_test_jwt: Any
    ) -> None:
        """Token without 'pipeline' role -> 403."""
        token = generate_test_jwt(roles=["viewer"])
        response = oidc_client.get(
            "/api/pipeline/fleet-projection",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_fleet_projection_pipeline_role_allowed(
        self, oidc_client: FlaskClient, generate_test_jwt: Any
    ) -> None:
        """Token with 'pipeline' role -> 200 + schema-valid body."""
        token = generate_test_jwt(roles=["pipeline"])
        response = oidc_client.get(
            "/api/pipeline/fleet-projection",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "devices" in data
        assert "fleet" in data


class TestPipelineUploadScript:
    """Tests for GET /api/pipeline/upload.sh."""

    def test_get_upload_script_returns_shell_script(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that upload script endpoint returns a valid shell script."""
        response = client.get("/api/pipeline/upload.sh")

        assert response.status_code == 200
        assert response.content_type == "text/x-shellscript; charset=utf-8"

        script = response.data.decode("utf-8")
        assert script.startswith("#!/bin/sh")
        assert "IOTSUPPORT_CLIENT_ID" in script
        assert "IOTSUPPORT_CLIENT_SECRET" in script

    def test_get_upload_script_contains_backend_url(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains the inferred backend URL."""
        response = client.get("/api/pipeline/upload.sh")

        script = response.data.decode("utf-8")
        # Flask test client uses localhost by default
        assert 'BACKEND_URL="http://localhost"' in script

    def test_get_upload_script_contains_token_url(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that the script contains the token URL from config."""
        # Get the configured token URL
        app_config: AppSettings = container.app_config()
        expected_token_url = app_config.oidc_token_url or ""

        response = client.get("/api/pipeline/upload.sh")

        script = response.data.decode("utf-8")
        assert f'TOKEN_URL="{expected_token_url}"' in script

    def test_get_upload_script_respects_forwarded_headers(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script uses X-Forwarded-* headers when present."""
        response = client.get(
            "/api/pipeline/upload.sh",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "iotsupport.example.com",
            },
        )

        script = response.data.decode("utf-8")
        assert 'BACKEND_URL="https://iotsupport.example.com"' in script

    def test_get_upload_script_is_public(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that upload script endpoint is accessible without authentication."""
        # This test verifies the @public decorator works
        # The client fixture doesn't set up auth, so if this returns 200
        # it means the endpoint is correctly marked as public
        response = client.get("/api/pipeline/upload.sh")
        assert response.status_code == 200

    def test_get_upload_script_contains_usage_instructions(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains usage instructions."""
        response = client.get("/api/pipeline/upload.sh")

        script = response.data.decode("utf-8")
        assert "Usage:" in script
        assert "model_code" in script
        assert "firmware.bin" in script

    def test_get_upload_script_contains_auto_detect_logic(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains auto-detection from project_description.json."""
        response = client.get("/api/pipeline/upload.sh")

        script = response.data.decode("utf-8")
        assert "project_description.json" in script
        assert "project_name" in script
        assert "Auto-detected" in script

    def test_get_upload_script_contains_zip_packaging(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the shell script contains ZIP packaging logic."""
        response = client.get("/api/pipeline/upload.sh")

        script = response.data.decode("utf-8")
        assert "version.json" in script
        assert "zip" in script.lower()
        assert "sdkconfig" in script
        assert ".elf" in script
        assert ".map" in script


class TestPipelineUploadScriptPowerShell:
    """Tests for GET /api/pipeline/upload.ps1."""

    def test_get_upload_script_returns_powershell_script(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that upload script endpoint returns a valid PowerShell script."""
        response = client.get("/api/pipeline/upload.ps1")

        assert response.status_code == 200
        assert response.content_type == "text/plain; charset=utf-8"

        script = response.data.decode("utf-8")
        assert "function Upload-Firmware" in script
        assert "IOTSUPPORT_CLIENT_ID" in script
        assert "IOTSUPPORT_CLIENT_SECRET" in script

    def test_get_upload_script_contains_backend_url(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains the inferred backend URL."""
        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        # Flask test client uses localhost by default
        assert '$BackendUrl = "http://localhost"' in script

    def test_get_upload_script_contains_token_url(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that the script contains the token URL from config."""
        app_config: AppSettings = container.app_config()
        expected_token_url = app_config.oidc_token_url or ""

        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        assert f'$TokenUrl = "{expected_token_url}"' in script

    def test_get_upload_script_respects_forwarded_headers(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script uses X-Forwarded-* headers when present."""
        response = client.get(
            "/api/pipeline/upload.ps1",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "iotsupport.example.com",
            },
        )

        script = response.data.decode("utf-8")
        assert '$BackendUrl = "https://iotsupport.example.com"' in script

    def test_get_upload_script_is_public(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that upload script endpoint is accessible without authentication."""
        response = client.get("/api/pipeline/upload.ps1")
        assert response.status_code == 200

    def test_get_upload_script_contains_usage_instructions(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains usage instructions."""
        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        assert "Usage:" in script
        assert "model_code" in script
        assert "firmware.bin" in script

    def test_get_upload_script_contains_auto_detect_logic(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the script contains auto-detection from project_description.json."""
        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        assert "project_description.json" in script
        assert "project_name" in script
        assert "Auto-detected" in script

    def test_get_upload_script_contains_zip_packaging(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the PowerShell script contains ZIP packaging logic."""
        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        assert "version.json" in script
        assert "Compress-Archive" in script
        assert "sdkconfig" in script
        assert ".elf" in script
        assert ".map" in script

    def test_get_upload_script_packs_flash_images(
        self, app: Flask, client: FlaskClient
    ) -> None:
        """Test that the PowerShell script packs the flash images upload.sh packs."""
        response = client.get("/api/pipeline/upload.ps1")

        script = response.data.decode("utf-8")
        assert 'Join-Path $BuildDir "flasher_args.json"' in script
        assert ".flash_files.PSObject.Properties" in script
        assert "$zipFiles += @($flasherArgsFile) + $flashImages" in script
        assert "Compress-Archive -Path $zipFiles" in script


# Stand-ins for the two tools the served script needs that the run replaces (R3):
# zip, which the suite's containers lack, and curl, whose two calls are recorded
# and answered; the ZIP posted is handed to the real upload afterwards.
ZIP_STANDIN = """\
import os
import sys
import zipfile

# Info-ZIP's `zip -j ARCHIVE FILE...`: each file stored under its own name
args = sys.argv[1:]
if len(args) < 3 or args[0] != "-j" or os.path.exists(args[1]):
    sys.exit(f"zip stand-in: unsupported call: {args}")
archive, files = args[1], args[2:]
names = [os.path.basename(file) for file in files]
if len(set(names)) != len(names):
    sys.exit("zip error: Invalid command arguments (cannot repeat names in zip file)")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
    for file, name in zip(files, names, strict=True):
        zf.write(file, name)
        print(f"  adding: {name}")
"""

CURL_STANDIN = """\
import json
import os
import shutil
import sys

capture = os.environ["STANDIN_CAPTURE_DIR"]
args = sys.argv[1:]
with open(os.path.join(capture, "curl_calls.jsonl"), "a") as calls:
    calls.write(json.dumps(args) + "\\n")
if "--data-binary" in args:
    body = args[args.index("--data-binary") + 1]
    shutil.copyfile(body.removeprefix("@"), os.path.join(capture, "upload.zip"))
    print('{"firmware_version":"stand-in"}')
else:
    print('{"access_token":"stand-in-token","token_type":"Bearer"}')
"""

# What the script runs besides the stand-ins and the shell's builtins
POSIX_TOOLS = ("basename", "cat", "dirname", "grep", "mktemp", "rm", "sed")

REQUIRED_MEMBERS = {"{code}.bin", "{code}.elf", "{code}.map", "sdkconfig", "version.json"}


def _esp_idf_project(
    root: Path, model_code: str, version: str, flash_files: list[FlashFile] | None
) -> Path:
    """Lay out an ESP-IDF project as `idf.py build` leaves it for the upload step."""
    build = root / "build"
    build.mkdir(parents=True)
    (build / "project_description.json").write_text(
        json.dumps(
            {
                "version": "1.2",
                "project_name": model_code,
                "project_version": version,
                "project_path": "/workspace",
                "idf_path": "/opt/esp/idf",
                "build_dir": "/workspace/build",
                "app_elf": f"{model_code}.elf",
                "app_bin": f"{model_code}.bin",
                "git_revision": "v5.5.3",
                "target": "esp32s3",
            },
            indent=4,
        )
    )
    (build / f"{model_code}.bin").write_bytes(create_test_firmware(version.encode("utf-8")))
    (build / f"{model_code}.elf").write_bytes(b"\x7fELF" + bytes(100))
    (build / f"{model_code}.map").write_text("Memory Map\n")
    (root / "sdkconfig").write_text('CONFIG_IDF_TARGET="esp32s3"\n')
    if flash_files is not None:
        (build / "flasher_args.json").write_bytes(_flasher_args_json(flash_files))
        for _, _, file in flash_files:
            if file != f"{model_code}.bin":
                image = build / file
                image.parent.mkdir(parents=True, exist_ok=True)
                image.write_bytes(_flash_image(file))
    return root


def _run_upload_script(
    client: FlaskClient, project: Path, tmp_path: Path, posix_only: bool
) -> tuple[str, list[list[str]], bytes]:
    """Run the served upload.sh in a project, as the firmware repos' stub does.

    Returns:
        The script's output, the arguments of each curl call, and the ZIP it posted
    """
    script = client.get("/api/pipeline/upload.sh").data

    standins = tmp_path / "standins"
    standins.mkdir()
    for name, source in (("zip", ZIP_STANDIN), ("curl", CURL_STANDIN)):
        standin = standins / name
        standin.write_text(f"#!{sys.executable}\n{source}")
        standin.chmod(0o755)

    if posix_only:
        tools = tmp_path / "tools"
        tools.mkdir()
        for tool in POSIX_TOOLS:
            found = shutil.which(tool)
            assert found is not None, f"{tool} is not installed"
            (tools / tool).symlink_to(found)
        search_path = f"{standins}:{tools}"
    else:
        search_path = f"{standins}:{os.environ['PATH']}"

    capture = tmp_path / "capture"
    capture.mkdir()
    result = subprocess.run(
        ["/bin/sh", "-s", "--"],
        input=script,
        cwd=project,
        env={
            "PATH": search_path,
            "TMPDIR": str(tmp_path),
            "IOTSUPPORT_CLIENT_ID": "ci-client",
            "IOTSUPPORT_CLIENT_SECRET": "ci-secret",
            "STANDIN_CAPTURE_DIR": str(capture),
        },
        capture_output=True,
        timeout=60,
        check=False,
    )
    output = result.stdout.decode("utf-8") + result.stderr.decode("utf-8")
    assert result.returncode == 0, output

    calls = [json.loads(line) for line in (capture / "curl_calls.jsonl").read_text().splitlines()]
    return output, calls, (capture / "upload.zip").read_bytes()


def _replay_upload(client: FlaskClient, upload_call: list[str], zip_content: bytes) -> Any:
    """Hand the ZIP the script posted to the real upload, at the URL it posted to."""
    url = next(arg for arg in upload_call if arg.startswith("http"))
    return client.post(
        urlparse(url).path,
        data=zip_content,
        content_type="application/octet-stream",
    )


def _zip_members(zip_content: bytes) -> set[str]:
    with zipfile.ZipFile(BytesIO(zip_content)) as zf:
        return set(zf.namelist())


class TestPipelineUploadScriptRun:
    """Tests that run the served upload.sh on an ESP-IDF build directory."""

    @pytest.mark.parametrize("posix_only", [False, True], ids=["system-tools", "without-jq"])
    def test_upload_script_posts_build_flash_images(
        self,
        app: Flask,
        client: FlaskClient,
        container: ServiceContainer,
        tmp_path: Path,
        posix_only: bool,
    ) -> None:
        """Test that the ZIP the script posts carries the flash images and is accepted."""
        model_code = "scriptjq" if not posix_only else "scriptposix"
        with app.app_context():
            container.device_model_service().create_device_model(code=model_code, name="Script")
            container.db_session().commit()
        project = _esp_idf_project(
            tmp_path / "project", model_code, "2.1.0", _standard_flash_files(model_code)
        )

        _, calls, zip_content = _run_upload_script(client, project, tmp_path, posix_only)

        token_call, upload_call = calls
        assert container.app_config().oidc_token_url in token_call
        assert "client_id=ci-client" in token_call
        assert "client_secret=ci-secret" in token_call
        assert f"http://localhost/api/pipeline/models/{model_code}/firmware" in upload_call
        assert "Authorization: Bearer stand-in-token" in upload_call
        assert _zip_members(zip_content) == {
            *(member.format(code=model_code) for member in REQUIRED_MEMBERS),
            "flasher_args.json",
            "bootloader.bin",
            "partition-table.bin",
            "ota_data_initial.bin",
        }

        response = _replay_upload(client, upload_call, zip_content)

        assert response.status_code == 200, response.get_json()
        assert response.get_json()["firmware_version"] == "2.1.0"
        s3 = container.s3_service()
        manifest = _stored_flash_manifest(s3, model_code, "2.1.0")
        assert manifest is not None
        assert manifest.chip == "esp32s3"
        build = project / "build"
        for image in manifest.images:
            stored = s3.download_file(f"firmware/{model_code}/2.1.0/{image.artifact}").read()
            assert stored == (build / image.file).read_bytes(), image.file
        assert [(image.offset, image.file) for image in manifest.images] == [
            (0x0, "bootloader/bootloader.bin"),
            (0x8000, "partition_table/partition-table.bin"),
            (0xD000, "ota_data_initial.bin"),
            (0x10000, f"{model_code}.bin"),
        ]

    def test_upload_script_posts_every_listed_image(
        self, app: Flask, client: FlaskClient, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that images beyond today's four, in the build or outside it, come along."""
        model_code = "scriptmore"
        with app.app_context():
            container.device_model_service().create_device_model(code=model_code, name="Script")
            container.db_session().commit()
        flash_files = [
            *_standard_flash_files(model_code),
            ("storage", "0x310000", "storage.bin"),
            ("voice", "0x410000", "../models/voice.bin"),
        ]
        project = _esp_idf_project(tmp_path / "project", model_code, "2.2.0", flash_files)

        _, calls, zip_content = _run_upload_script(client, project, tmp_path, posix_only=True)

        assert {"storage.bin", "voice.bin"} <= _zip_members(zip_content)
        response = _replay_upload(client, calls[1], zip_content)
        assert response.status_code == 200, response.get_json()
        manifest = _stored_flash_manifest(container.s3_service(), model_code, "2.2.0")
        assert manifest is not None
        assert [image.offset for image in manifest.images] == [
            0x0, 0x8000, 0xD000, 0x10000, 0x310000, 0x410000,
        ]

    def test_upload_script_without_flash_outputs(
        self, app: Flask, client: FlaskClient, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that a build without flasher_args.json uploads the five artifacts, as before."""
        model_code = "scriptnoflash"
        with app.app_context():
            container.device_model_service().create_device_model(code=model_code, name="Script")
            container.db_session().commit()
        project = _esp_idf_project(tmp_path / "project", model_code, "2.3.0", None)

        output, calls, zip_content = _run_upload_script(client, project, tmp_path, posix_only=True)

        assert "Note: packaging without flash images (build/flasher_args.json not found)" in output
        assert _zip_members(zip_content) == {
            member.format(code=model_code) for member in REQUIRED_MEMBERS
        }
        response = _replay_upload(client, calls[1], zip_content)
        assert response.status_code == 200, response.get_json()
        assert _stored_flash_manifest(container.s3_service(), model_code, "2.3.0") is None

    def test_upload_script_with_incomplete_flash_outputs(
        self, app: Flask, client: FlaskClient, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that a build missing a listed image uploads the five artifacts, not part of the set."""
        model_code = "scriptpartial"
        with app.app_context():
            container.device_model_service().create_device_model(code=model_code, name="Script")
            container.db_session().commit()
        project = _esp_idf_project(
            tmp_path / "project", model_code, "2.4.0", _standard_flash_files(model_code)
        )
        (project / "build" / "partition_table" / "partition-table.bin").unlink()

        output, calls, zip_content = _run_upload_script(client, project, tmp_path, posix_only=True)

        assert (
            "Note: packaging without flash images "
            "(build/partition_table/partition-table.bin not found)" in output
        )
        assert _zip_members(zip_content) == {
            member.format(code=model_code) for member in REQUIRED_MEMBERS
        }
        response = _replay_upload(client, calls[1], zip_content)
        assert response.status_code == 200, response.get_json()
        assert _stored_flash_manifest(container.s3_service(), model_code, "2.4.0") is None

    def test_upload_script_with_clashing_flash_name(
        self, app: Flask, client: FlaskClient, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that two images of one file name upload the five artifacts, not part of the set."""
        model_code = "scriptclash"
        with app.app_context():
            container.device_model_service().create_device_model(code=model_code, name="Script")
            container.db_session().commit()
        flash_files = [
            *_standard_flash_files(model_code),
            ("extra", "0x310000", "extra/bootloader.bin"),
        ]
        project = _esp_idf_project(tmp_path / "project", model_code, "2.5.0", flash_files)

        output, calls, zip_content = _run_upload_script(client, project, tmp_path, posix_only=True)

        assert (
            "Note: packaging without flash images "
            "(two members would be named bootloader.bin)" in output
        )
        assert _zip_members(zip_content) == {
            member.format(code=model_code) for member in REQUIRED_MEMBERS
        }
        response = _replay_upload(client, calls[1], zip_content)
        assert response.status_code == 200, response.get_json()
        assert _stored_flash_manifest(container.s3_service(), model_code, "2.5.0") is None

    def test_upload_script_without_app_in_flasher_args(
        self, app: Flask, client: FlaskClient, container: ServiceContainer, tmp_path: Path
    ) -> None:
        """Test that a flasher_args.json not flashing the app uploads the five artifacts only."""
        model_code = "scriptnoapp"
        with app.app_context():
            container.device_model_service().create_device_model(code=model_code, name="Script")
            container.db_session().commit()
        flash_files = [
            flash_file
            for flash_file in _standard_flash_files(model_code)
            if flash_file[2] != f"{model_code}.bin"
        ]
        project = _esp_idf_project(tmp_path / "project", model_code, "2.6.0", flash_files)

        output, calls, zip_content = _run_upload_script(client, project, tmp_path, posix_only=True)

        assert (
            "Note: packaging without flash images "
            f"(build/flasher_args.json does not flash {model_code}.bin)" in output
        )
        assert _zip_members(zip_content) == {
            member.format(code=model_code) for member in REQUIRED_MEMBERS
        }
        response = _replay_upload(client, calls[1], zip_content)
        assert response.status_code == 200, response.get_json()
        assert _stored_flash_manifest(container.s3_service(), model_code, "2.6.0") is None
