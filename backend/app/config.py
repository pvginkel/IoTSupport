"""Configuration management using Pydantic settings.

This module implements a two-layer configuration system:
1. Environment: Loads raw values from environment variables (UPPER_CASE)
2. Settings: Clean application settings with lowercase fields and derived values

Usage:
    # Production: Load from environment
    settings = Settings.load()

    # Tests: Construct directly with test values
    settings = Settings(database_url="sqlite://", secret_key="test", ...)
"""

import base64
import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (parent of app/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default secret key that must be changed in production
_DEFAULT_SECRET_KEY = "dev-secret-key-change-in-production"


class ConfigurationError(Exception):
    """Raised when application configuration is invalid."""

    pass


def _derive_fernet_key(secret_key: str) -> str:
    """Derive a Fernet-compatible key from SECRET_KEY.

    Args:
        secret_key: Application SECRET_KEY

    Returns:
        URL-safe base64 encoded 32-byte key as string
    """
    # Use SHA256 to derive a 32-byte key from the secret
    key_bytes = hashlib.sha256(secret_key.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes).decode()


class Environment(BaseSettings):
    """Raw environment variable loading.

    This class loads values directly from environment variables with UPPER_CASE names.
    It should not contain any derived values or transformation logic.
    """

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Flask settings
    SECRET_KEY: str = Field(default=_DEFAULT_SECRET_KEY)
    FLASK_ENV: str = Field(default="development")
    DEBUG: bool = Field(default=True)

    # Database settings
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/iotsupport",
        description="PostgreSQL connection string",
    )

    # Firmware storage directory
    ASSETS_DIR: Path | None = Field(
        default=None,
        description="Path to firmware storage directory"
    )

    # CORS settings
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins"
    )

    # MQTT settings
    MQTT_URL: str | None = Field(
        default=None,
        description="MQTT broker URL (e.g., mqtt://localhost:1883, mqtts://broker:8883)"
    )
    MQTT_USERNAME: str | None = Field(
        default=None,
        description="MQTT broker username"
    )
    MQTT_PASSWORD: str | None = Field(
        default=None,
        description="MQTT broker password"
    )

    # OIDC Authentication Settings
    BASEURL: str = Field(
        default="http://localhost:3200",
        description="Base URL for the application (used for redirect URI and cookie security)"
    )
    DEVICE_BASEURL: str | None = Field(
        default=None,
        description="Base URL for device provisioning (defaults to BASEURL if not set)"
    )
    OIDC_ENABLED: bool = Field(
        default=False,
        description="Enable OIDC authentication"
    )
    OIDC_ISSUER_URL: str | None = Field(
        default=None,
        description="OIDC issuer URL (e.g., https://auth.example.com/realms/iot)"
    )
    OIDC_CLIENT_ID: str | None = Field(
        default=None,
        description="OIDC client ID"
    )
    OIDC_CLIENT_SECRET: str | None = Field(
        default=None,
        description="OIDC client secret (confidential client)"
    )
    OIDC_SCOPES: str = Field(
        default="openid profile email",
        description="Space-separated OIDC scopes"
    )
    OIDC_AUDIENCE: str | None = Field(
        default=None,
        description="Expected 'aud' claim in JWT (defaults to client_id if not set)"
    )
    OIDC_CLOCK_SKEW_SECONDS: int = Field(
        default=30,
        description="Clock skew tolerance for token validation"
    )
    OIDC_COOKIE_NAME: str = Field(
        default="access_token",
        description="Cookie name for storing JWT access token"
    )
    OIDC_COOKIE_SECURE: bool | None = Field(
        default=None,
        description="Secure flag for cookie (inferred from BASEURL if None)"
    )
    OIDC_COOKIE_SAMESITE: str = Field(
        default="Lax",
        description="SameSite attribute for cookie"
    )
    OIDC_REFRESH_COOKIE_NAME: str = Field(
        default="refresh_token",
        description="Cookie name for storing refresh token"
    )

    # Keycloak Admin API Settings (for device provisioning)
    OIDC_TOKEN_URL: str | None = Field(
        default=None,
        description="OIDC token endpoint URL (e.g., https://auth.example.com/realms/iot/protocol/openid-connect/token)"
    )
    KEYCLOAK_BASE_URL: str | None = Field(
        default=None,
        description="Keycloak base URL (e.g., https://keycloak.local)"
    )
    KEYCLOAK_REALM: str | None = Field(
        default=None,
        description="Keycloak realm name for device clients"
    )
    KEYCLOAK_ADMIN_CLIENT_ID: str | None = Field(
        default=None,
        description="Keycloak admin service account client ID"
    )
    KEYCLOAK_ADMIN_CLIENT_SECRET: str | None = Field(
        default=None,
        description="Keycloak admin service account client secret"
    )
    KEYCLOAK_DEVICE_SCOPE_NAME: str = Field(
        default="iot-device-audience",
        description="Client scope name to add to device clients (must contain audience mapper)"
    )

    # WiFi Credentials for Provisioning
    WIFI_SSID: str | None = Field(
        default=None,
        description="WiFi SSID for device provisioning"
    )
    WIFI_PASSWORD: str | None = Field(
        default=None,
        description="WiFi password for device provisioning"
    )

    # Logging Endpoint for Provisioning
    LOGGING_URL: str = Field(
        default="/api/iot/logging",
        description="Logging service endpoint URL for device metrics and logs. "
        "Relative paths are prefixed with DEVICE_BASEURL."
    )

    # Rotation Settings
    ROTATION_CRON: str | None = Field(
        default=None,
        description="CRON schedule for credential rotation (e.g., '0 8 1-7 * 6' for first Saturday of month at 8am)"
    )
    ROTATION_TIMEOUT_SECONDS: int = Field(
        default=300,
        description="Timeout for device to complete rotation before rollback"
    )
    ROTATION_CRITICAL_THRESHOLD_DAYS: int | None = Field(
        default=None,
        description="Days after which a timed-out device is considered critical"
    )



class Settings(BaseModel):
    """Application settings with lowercase fields and derived values.

    This class represents the final, resolved application configuration.
    All field names are lowercase for consistency.

    For production, use Settings.load() to load from environment.
    For tests, construct directly with test values.
    """

    model_config = ConfigDict(from_attributes=True)

    # Flask settings
    secret_key: str
    flask_env: str
    debug: bool

    # Database settings
    database_url: str

    # Firmware storage directory
    assets_dir: Path | None

    # CORS settings
    cors_origins: list[str]

    # MQTT settings
    mqtt_url: str | None
    mqtt_username: str | None
    mqtt_password: str | None

    # OIDC Authentication Settings
    baseurl: str
    device_baseurl: str  # Resolved: DEVICE_BASEURL or BASEURL
    oidc_enabled: bool
    oidc_issuer_url: str | None
    oidc_client_id: str | None
    oidc_client_secret: str | None
    oidc_scopes: str
    oidc_audience: str | None  # Resolved: OIDC_AUDIENCE or OIDC_CLIENT_ID
    oidc_clock_skew_seconds: int
    oidc_cookie_name: str
    oidc_cookie_secure: bool  # Resolved: explicit or inferred from BASEURL
    oidc_cookie_samesite: str
    oidc_refresh_cookie_name: str

    # Keycloak Admin API Settings
    oidc_token_url: str | None
    keycloak_base_url: str | None
    keycloak_realm: str | None
    keycloak_admin_client_id: str | None
    keycloak_admin_client_secret: str | None
    keycloak_device_scope_name: str
    keycloak_admin_url: str | None  # Resolved: computed from base + realm
    keycloak_console_base_url: str | None  # Resolved: computed from base + realm

    # WiFi Credentials for Provisioning
    wifi_ssid: str | None
    wifi_password: str | None

    # Logging Endpoint for Provisioning
    logging_url: str

    # Rotation Settings
    rotation_cron: str | None
    rotation_timeout_seconds: int
    rotation_critical_threshold_days: int | None

    # Secret Encryption Key (derived from secret_key)
    fernet_key: str

    # SQLAlchemy engine options
    sqlalchemy_engine_options: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.flask_env == "production" or not self.debug

    @property
    def is_testing(self) -> bool:
        """Check if the application is running in testing mode."""
        return self.flask_env == "testing"

    def to_flask_config(self) -> "FlaskConfig":
        """Create Flask configuration object from settings."""
        return FlaskConfig(
            SECRET_KEY=self.secret_key,
            SQLALCHEMY_DATABASE_URI=self.database_url,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_ENGINE_OPTIONS=self.sqlalchemy_engine_options,
        )

    def validate_production_config(self) -> None:
        """Validate that required configuration is set for production.

        Raises:
            ConfigurationError: If required settings are missing or insecure
        """
        errors: list[str] = []

        # SECRET_KEY must be changed from default in production
        if self.is_production and self.secret_key == _DEFAULT_SECRET_KEY:
            errors.append(
                "SECRET_KEY must be set to a secure value in production "
                "(current value is the insecure default)"
            )


        # Keycloak settings required when provisioning is used
        keycloak_settings = [
            ("KEYCLOAK_BASE_URL", self.keycloak_base_url),
            ("KEYCLOAK_REALM", self.keycloak_realm),
            ("KEYCLOAK_ADMIN_CLIENT_ID", self.keycloak_admin_client_id),
            ("KEYCLOAK_ADMIN_CLIENT_SECRET", self.keycloak_admin_client_secret),
        ]
        keycloak_missing = [name for name, value in keycloak_settings if not value]
        if keycloak_missing and self.is_production:
            errors.append(
                f"Keycloak settings required for device provisioning: {', '.join(keycloak_missing)}"
            )

        # ASSETS_DIR required for firmware storage
        if self.is_production and not self.assets_dir:
            errors.append(
                "ASSETS_DIR must be set for firmware storage"
            )

        # MQTT_URL required for provisioning
        if self.is_production and not self.mqtt_url:
            errors.append(
                "MQTT_URL must be set for device provisioning"
            )

        # WiFi settings required for provisioning
        if self.is_production and (not self.wifi_ssid or not self.wifi_password):
            errors.append(
                "WIFI_SSID and WIFI_PASSWORD must be set for device provisioning"
            )

        # OIDC_TOKEN_URL required for provisioning
        if self.is_production and not self.oidc_token_url:
            errors.append(
                "OIDC_TOKEN_URL must be set for device provisioning"
            )

        # Rotation settings required for production
        if self.is_production and not self.rotation_cron:
            errors.append(
                "ROTATION_CRON must be set for credential rotation scheduling"
            )
        if self.is_production and self.rotation_critical_threshold_days is None:
            errors.append(
                "ROTATION_CRITICAL_THRESHOLD_DAYS must be set for dashboard status"
            )

        # OIDC settings required when OIDC is enabled
        if self.oidc_enabled:
            if not self.oidc_issuer_url:
                errors.append(
                    "OIDC_ISSUER_URL is required when OIDC_ENABLED=True"
                )
            if not self.oidc_client_id:
                errors.append(
                    "OIDC_CLIENT_ID is required when OIDC_ENABLED=True"
                )
            if not self.oidc_client_secret:
                errors.append(
                    "OIDC_CLIENT_SECRET is required when OIDC_ENABLED=True"
                )

        if errors:
            raise ConfigurationError(
                "Configuration validation failed:\n  - " + "\n  - ".join(errors)
            )

    @classmethod
    def load(cls, env: Environment | None = None) -> "Settings":
        """Load settings from environment variables.

        This method:
        1. Loads Environment from environment variables
        2. Computes derived values (device_baseurl, fernet_key, etc.)
        3. Strips trailing slashes from URLs
        4. Constructs and returns a Settings instance

        Args:
            env: Optional Environment instance (for testing). If None, loads from environment.

        Returns:
            Settings instance with all values resolved
        """
        if env is None:
            env = Environment()

        # Helper to strip trailing slashes from URLs
        def strip_slashes(url: str | None) -> str | None:
            return url.rstrip("/") if url else url

        # Compute derived values
        baseurl = strip_slashes(env.BASEURL) or "http://localhost:3200"
        device_baseurl = strip_slashes(env.DEVICE_BASEURL) or baseurl

        # Resolve logging_url: prefix relative paths with device_baseurl
        logging_url = env.LOGGING_URL
        if not logging_url.startswith(("http://", "https://")):
            logging_url = f"{device_baseurl}{logging_url}"

        # Derive Fernet key from SECRET_KEY for encrypting cached secrets
        fernet_key = _derive_fernet_key(env.SECRET_KEY)

        # Compute OIDC audience: use explicit value or fall back to client_id
        oidc_audience = env.OIDC_AUDIENCE or env.OIDC_CLIENT_ID

        # Compute cookie secure flag: use explicit value or infer from baseurl
        if env.OIDC_COOKIE_SECURE is not None:
            oidc_cookie_secure = env.OIDC_COOKIE_SECURE
        else:
            oidc_cookie_secure = baseurl.startswith("https://")

        # Compute Keycloak URLs
        keycloak_base_url = strip_slashes(env.KEYCLOAK_BASE_URL)
        keycloak_admin_url = None
        keycloak_console_base_url = None
        if keycloak_base_url and env.KEYCLOAK_REALM:
            keycloak_admin_url = f"{keycloak_base_url}/admin/realms/{env.KEYCLOAK_REALM}"
            keycloak_console_base_url = f"{keycloak_base_url}/admin/master/console/#/{env.KEYCLOAK_REALM}/clients"

        # Build default SQLAlchemy engine options
        sqlalchemy_engine_options = {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_pre_ping": True,
        }

        return cls(
            secret_key=env.SECRET_KEY,
            flask_env=env.FLASK_ENV,
            debug=env.DEBUG,
            database_url=env.DATABASE_URL,
            assets_dir=env.ASSETS_DIR,
            cors_origins=env.CORS_ORIGINS,
            mqtt_url=env.MQTT_URL,
            mqtt_username=env.MQTT_USERNAME,
            mqtt_password=env.MQTT_PASSWORD,
            baseurl=baseurl,
            device_baseurl=device_baseurl,
            oidc_enabled=env.OIDC_ENABLED,
            oidc_issuer_url=env.OIDC_ISSUER_URL,
            oidc_client_id=env.OIDC_CLIENT_ID,
            oidc_client_secret=env.OIDC_CLIENT_SECRET,
            oidc_scopes=env.OIDC_SCOPES,
            oidc_audience=oidc_audience,
            oidc_clock_skew_seconds=env.OIDC_CLOCK_SKEW_SECONDS,
            oidc_cookie_name=env.OIDC_COOKIE_NAME,
            oidc_cookie_secure=oidc_cookie_secure,
            oidc_cookie_samesite=env.OIDC_COOKIE_SAMESITE,
            oidc_refresh_cookie_name=env.OIDC_REFRESH_COOKIE_NAME,
            oidc_token_url=strip_slashes(env.OIDC_TOKEN_URL),
            keycloak_base_url=keycloak_base_url,
            keycloak_realm=env.KEYCLOAK_REALM,
            keycloak_admin_client_id=env.KEYCLOAK_ADMIN_CLIENT_ID,
            keycloak_admin_client_secret=env.KEYCLOAK_ADMIN_CLIENT_SECRET,
            keycloak_device_scope_name=env.KEYCLOAK_DEVICE_SCOPE_NAME,
            keycloak_admin_url=keycloak_admin_url,
            keycloak_console_base_url=keycloak_console_base_url,
            wifi_ssid=env.WIFI_SSID,
            wifi_password=env.WIFI_PASSWORD,
            logging_url=logging_url,
            rotation_cron=env.ROTATION_CRON,
            rotation_timeout_seconds=env.ROTATION_TIMEOUT_SECONDS,
            rotation_critical_threshold_days=env.ROTATION_CRITICAL_THRESHOLD_DAYS,
            fernet_key=fernet_key,
            sqlalchemy_engine_options=sqlalchemy_engine_options,
        )


class FlaskConfig:
    """Flask-specific configuration for app.config.from_object().

    This is a simple DTO with the UPPER_CASE attributes Flask and Flask-SQLAlchemy expect.
    Create via Settings.to_flask_config().
    """

    def __init__(
        self,
        SECRET_KEY: str,
        SQLALCHEMY_DATABASE_URI: str,
        SQLALCHEMY_TRACK_MODIFICATIONS: bool,
        SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any],
    ) -> None:
        self.SECRET_KEY = SECRET_KEY
        self.SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI
        self.SQLALCHEMY_TRACK_MODIFICATIONS = SQLALCHEMY_TRACK_MODIFICATIONS
        self.SQLALCHEMY_ENGINE_OPTIONS = SQLALCHEMY_ENGINE_OPTIONS
