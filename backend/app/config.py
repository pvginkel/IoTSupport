"""Configuration management using Pydantic settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (parent of app/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Flask settings
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production")
    FLASK_ENV: str = Field(default="development")

    # ESP32 configuration directory
    ESP32_CONFIGS_DIR: Path = Field(
        description="Path to ESP32 configuration files directory"
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

    @property
    def is_testing(self) -> bool:
        """Check if the application is running in testing mode."""
        return self.FLASK_ENV == "testing"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Expects ESP32_CONFIGS_DIR to be set in environment.
    """
    return Settings()  # type: ignore[call-arg]
