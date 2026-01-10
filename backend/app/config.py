"""Configuration management using Pydantic settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Flask settings
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production")
    DEBUG: bool = Field(default=True)

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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Expects ESP32_CONFIGS_DIR to be set in environment.
    """
    return Settings()  # type: ignore[call-arg]
