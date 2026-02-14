"""Application-specific configuration for IoT Support.

This module implements IoT-specific configuration that is separate from the
infrastructure configuration in config.py. Settings here cover MQTT, Elasticsearch,
Keycloak admin, device provisioning, rotation, coredumps, and firmware storage.
"""

import base64
import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _derive_fernet_key(secret_key: str) -> str:
    """Derive a Fernet-compatible key from SECRET_KEY."""
    key_bytes = hashlib.sha256(secret_key.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes).decode()


class AppEnvironment(BaseSettings):
    """Raw environment variable loading for IoT-specific settings."""

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Firmware storage directory
    ASSETS_DIR: Path | None = Field(default=None)
    # Coredump storage directory
    COREDUMPS_DIR: Path | None = Field(default=None)
    # Coredump parsing sidecar settings
    PARSE_SIDECAR_XFER_DIR: Path | None = Field(default=None)
    PARSE_SIDECAR_URL: str | None = Field(default=None)
    MAX_COREDUMPS: int = Field(default=20)

    # MQTT settings
    MQTT_URL: str | None = Field(default=None)
    DEVICE_MQTT_URL: str | None = Field(default=None)
    MQTT_USERNAME: str | None = Field(default=None)
    MQTT_PASSWORD: str | None = Field(default=None)
    MQTT_CLIENT_ID: str = Field(default="iotsupport-backend")

    # Keycloak Admin API Settings (for device provisioning)
    OIDC_TOKEN_URL: str | None = Field(default=None)
    KEYCLOAK_BASE_URL: str | None = Field(default=None)
    KEYCLOAK_REALM: str | None = Field(default=None)
    KEYCLOAK_ADMIN_CLIENT_ID: str | None = Field(default=None)
    KEYCLOAK_ADMIN_CLIENT_SECRET: str | None = Field(default=None)
    KEYCLOAK_DEVICE_SCOPE_NAME: str = Field(default="iot-device-audience")

    # Device base URL (for provisioning)
    DEVICE_BASEURL: str | None = Field(default=None)

    # WiFi Credentials for Provisioning
    WIFI_SSID: str | None = Field(default=None)
    WIFI_PASSWORD: str | None = Field(default=None)

    # Rotation Settings
    ROTATION_CRON: str | None = Field(default=None)
    ROTATION_TIMEOUT_SECONDS: int = Field(default=300)
    ROTATION_CRITICAL_THRESHOLD_DAYS: int | None = Field(default=None)

    # Elasticsearch Settings (for device logs)
    ELASTICSEARCH_URL: str | None = Field(default=None)
    ELASTICSEARCH_USERNAME: str | None = Field(default=None)
    ELASTICSEARCH_PASSWORD: str | None = Field(default=None)
    ELASTICSEARCH_INDEX_PATTERN: str = Field(default="logstash-http-*")


class AppSettings(BaseModel):
    """IoT Support application-specific settings."""

    model_config = ConfigDict(from_attributes=True)

    # Firmware storage
    assets_dir: Path | None = None
    # Coredump storage
    coredumps_dir: Path | None = None
    parse_sidecar_xfer_dir: Path | None = None
    parse_sidecar_url: str | None = None
    max_coredumps: int = 20

    # MQTT settings
    mqtt_url: str | None = None
    device_mqtt_url: str | None = None
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_client_id: str = "iotsupport-backend"

    # Keycloak Admin API Settings
    oidc_token_url: str | None = None
    keycloak_base_url: str | None = None
    keycloak_realm: str | None = None
    keycloak_admin_client_id: str | None = None
    keycloak_admin_client_secret: str | None = None
    keycloak_device_scope_name: str = "iot-device-audience"
    keycloak_admin_url: str | None = None
    keycloak_console_base_url: str | None = None

    # Device provisioning
    device_baseurl: str = "http://localhost:3200"

    # WiFi Credentials
    wifi_ssid: str | None = None
    wifi_password: str | None = None

    # Rotation Settings
    rotation_cron: str | None = None
    rotation_timeout_seconds: int = 300
    rotation_critical_threshold_days: int | None = None

    # Elasticsearch Settings
    elasticsearch_url: str | None = None
    elasticsearch_username: str | None = None
    elasticsearch_password: str | None = None
    elasticsearch_index_pattern: str = "logstash-http-*"

    # Secret Encryption Key (derived from secret_key)
    fernet_key: str = ""

    @classmethod
    def load(cls, env: "AppEnvironment | None" = None, flask_env: str = "development") -> "AppSettings":
        """Load app settings from environment variables."""
        if env is None:
            env = AppEnvironment()

        def strip_slashes(url: str | None) -> str | None:
            return url.rstrip("/") if url else url

        # Compute derived values
        device_mqtt_url = env.DEVICE_MQTT_URL or env.MQTT_URL

        # Compute Keycloak URLs
        keycloak_base_url = strip_slashes(env.KEYCLOAK_BASE_URL)
        keycloak_admin_url = None
        keycloak_console_base_url = None
        if keycloak_base_url and env.KEYCLOAK_REALM:
            keycloak_admin_url = f"{keycloak_base_url}/admin/realms/{env.KEYCLOAK_REALM}"
            keycloak_console_base_url = f"{keycloak_base_url}/admin/master/console/#/{env.KEYCLOAK_REALM}/clients"

        # Derive fernet key from SECRET_KEY (read from environment)
        from app.config import Environment
        infra_env = Environment()
        fernet_key = _derive_fernet_key(infra_env.SECRET_KEY)

        # Compute device_baseurl
        device_baseurl = strip_slashes(env.DEVICE_BASEURL) or strip_slashes(infra_env.BASEURL) or "http://localhost:3200"

        return cls(
            assets_dir=env.ASSETS_DIR,
            coredumps_dir=env.COREDUMPS_DIR,
            parse_sidecar_xfer_dir=env.PARSE_SIDECAR_XFER_DIR,
            parse_sidecar_url=strip_slashes(env.PARSE_SIDECAR_URL),
            max_coredumps=env.MAX_COREDUMPS,
            mqtt_url=env.MQTT_URL,
            device_mqtt_url=device_mqtt_url,
            mqtt_username=env.MQTT_USERNAME,
            mqtt_password=env.MQTT_PASSWORD,
            mqtt_client_id=env.MQTT_CLIENT_ID,
            oidc_token_url=strip_slashes(env.OIDC_TOKEN_URL),
            keycloak_base_url=keycloak_base_url,
            keycloak_realm=env.KEYCLOAK_REALM,
            keycloak_admin_client_id=env.KEYCLOAK_ADMIN_CLIENT_ID,
            keycloak_admin_client_secret=env.KEYCLOAK_ADMIN_CLIENT_SECRET,
            keycloak_device_scope_name=env.KEYCLOAK_DEVICE_SCOPE_NAME,
            keycloak_admin_url=keycloak_admin_url,
            keycloak_console_base_url=keycloak_console_base_url,
            device_baseurl=device_baseurl,
            wifi_ssid=env.WIFI_SSID,
            wifi_password=env.WIFI_PASSWORD,
            rotation_cron=env.ROTATION_CRON,
            rotation_timeout_seconds=env.ROTATION_TIMEOUT_SECONDS,
            rotation_critical_threshold_days=env.ROTATION_CRITICAL_THRESHOLD_DAYS,
            elasticsearch_url=strip_slashes(env.ELASTICSEARCH_URL),
            elasticsearch_username=env.ELASTICSEARCH_USERNAME,
            elasticsearch_password=env.ELASTICSEARCH_PASSWORD,
            elasticsearch_index_pattern=env.ELASTICSEARCH_INDEX_PATTERN,
            fernet_key=fernet_key,
        )
