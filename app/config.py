"""Configuration management using Pydantic settings."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (parent of app/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default secret key that must be changed in production
_DEFAULT_SECRET_KEY = "dev-secret-key-change-in-production"


class ConfigurationError(Exception):
    """Raised when application configuration is invalid."""

    pass


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

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

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.FLASK_ENV == "production" or not self.DEBUG

    # Database settings
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/iotsupport",
        description="PostgreSQL connection string",
    )

    # Asset upload settings
    ASSETS_DIR: Path = Field(
        description="Path to assets upload directory"
    )
    SIGNING_KEY_PATH: Path = Field(
        description="Path to RSA signing key file"
    )
    TIMESTAMP_TOLERANCE_SECONDS: int = Field(
        default=300,
        description="Timestamp validation tolerance in seconds"
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
    OIDC_ADMIN_ROLE: str = Field(
        default="admin",
        description="Role name for full administrative access"
    )
    OIDC_ASSET_ROLE: str = Field(
        default="asset-uploader",
        description="Role name for asset upload access"
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

    # Keycloak Admin API Settings (for device provisioning)
    OIDC_TOKEN_URL: str | None = Field(
        default=None,
        description="OIDC token endpoint URL (e.g., https://auth.example.com/realms/iot/protocol/openid-connect/token)"
    )
    KEYCLOAK_ADMIN_URL: str | None = Field(
        default=None,
        description="Keycloak admin API URL (e.g., https://auth.example.com/admin/realms/iot)"
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

    # WiFi Credentials for Provisioning
    WIFI_SSID: str | None = Field(
        default=None,
        description="WiFi SSID for device provisioning"
    )
    WIFI_PASSWORD: str | None = Field(
        default=None,
        description="WiFi password for device provisioning"
    )

    # Rotation Settings
    ROTATION_CRON: str = Field(
        default="0 8 1-7 * 6",
        description="CRON schedule for credential rotation (default: first Saturday of month at 8am)"
    )
    ROTATION_TIMEOUT_SECONDS: int = Field(
        default=300,
        description="Timeout for device to complete rotation before rollback"
    )

    # Secret Encryption Key (for cached_secret encryption)
    # Derived from SECRET_KEY if not explicitly set
    FERNET_KEY: str | None = Field(
        default=None,
        description="Fernet encryption key for cached secrets (32-byte base64 encoded)"
    )

    @property
    def is_testing(self) -> bool:
        """Check if the application is running in testing mode."""
        return self.FLASK_ENV == "testing"

    # Internal override for test fixtures (not set via env)
    _engine_options_override: dict[str, Any] | None = None

    @model_validator(mode="after")
    def configure_environment_defaults(self) -> "Settings":
        """Apply environment-specific defaults after validation."""
        return self

    def validate_production_config(self) -> None:
        """Validate that required configuration is set for production.

        Raises:
            ConfigurationError: If required settings are missing or insecure
        """
        errors: list[str] = []

        # SECRET_KEY must be changed from default in production
        if self.is_production and self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            errors.append(
                "SECRET_KEY must be set to a secure value in production "
                "(current value is the insecure default)"
            )

        # FERNET_KEY should be set in production for cached secret encryption
        if self.is_production and not self.FERNET_KEY:
            errors.append(
                "FERNET_KEY must be set in production for encrypted secret storage"
            )

        # Keycloak settings required when provisioning is used
        keycloak_settings = [
            ("KEYCLOAK_ADMIN_URL", self.KEYCLOAK_ADMIN_URL),
            ("KEYCLOAK_REALM", self.KEYCLOAK_REALM),
            ("KEYCLOAK_ADMIN_CLIENT_ID", self.KEYCLOAK_ADMIN_CLIENT_ID),
            ("KEYCLOAK_ADMIN_CLIENT_SECRET", self.KEYCLOAK_ADMIN_CLIENT_SECRET),
        ]
        keycloak_missing = [name for name, value in keycloak_settings if not value]
        if keycloak_missing and self.is_production:
            errors.append(
                f"Keycloak settings required for device provisioning: {', '.join(keycloak_missing)}"
            )

        # WiFi settings required for provisioning
        if self.is_production and (not self.WIFI_SSID or not self.WIFI_PASSWORD):
            errors.append(
                "WIFI_SSID and WIFI_PASSWORD must be set for device provisioning"
            )

        # OIDC_TOKEN_URL required for provisioning
        if self.is_production and not self.OIDC_TOKEN_URL:
            errors.append(
                "OIDC_TOKEN_URL must be set for device provisioning"
            )

        if errors:
            raise ConfigurationError(
                "Configuration validation failed:\n  - " + "\n  - ".join(errors)
            )

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """SQLAlchemy database URI."""
        return self.DATABASE_URL

    @property
    def SQLALCHEMY_TRACK_MODIFICATIONS(self) -> bool:
        """Disable SQLAlchemy track modifications."""
        return False

    @property
    def SQLALCHEMY_ENGINE_OPTIONS(self) -> dict[str, Any]:
        """SQLAlchemy engine options with connection pool configuration."""
        # Allow test fixtures to fully override engine options (e.g., for SQLite)
        if self._engine_options_override is not None:
            return self._engine_options_override
        return {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_pre_ping": True,  # Verify connections before use
        }

    def set_engine_options_override(self, options: dict[str, Any]) -> None:
        """Override engine options (for test fixtures using SQLite)."""
        object.__setattr__(self, "_engine_options_override", options)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]
