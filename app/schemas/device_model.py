"""Device model schemas for API request/response validation."""

import json
import re
from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Pattern for device model code: lowercase alphanumeric with underscores
MODEL_CODE_PATTERN = re.compile(r"^[a-z0-9_]+$")


class DeviceModelCreateSchema(BaseModel):
    """Request schema for creating a device model."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Unique model code (lowercase alphanumeric with underscores)",
        examples=["thermostat", "motion_sensor"],
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable model name",
        examples=["Smart Thermostat", "Motion Sensor"],
    )
    config_schema: str | None = Field(
        None,
        description="JSON schema for validating device configurations (optional)",
    )

    @field_validator("code")
    @classmethod
    def validate_code_format(cls, v: str) -> str:
        """Validate that code matches required pattern."""
        if not MODEL_CODE_PATTERN.match(v):
            raise ValueError(
                "code must contain only lowercase letters, numbers, and underscores"
            )
        return v

    @field_validator("config_schema")
    @classmethod
    def validate_config_schema_is_json(cls, v: str | None) -> str | None:
        """Validate that config_schema is valid JSON if provided."""
        if v is None:
            return v
        try:
            json.loads(v)
        except json.JSONDecodeError as e:
            raise ValueError(f"config_schema must be valid JSON: {e}") from e
        return v


class DeviceModelUpdateSchema(BaseModel):
    """Request schema for updating a device model."""

    name: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Human-readable model name",
    )
    config_schema: str | None = Field(
        None,
        description="JSON schema for validating device configurations",
    )

    @field_validator("config_schema")
    @classmethod
    def validate_config_schema_is_json(cls, v: str | None) -> str | None:
        """Validate that config_schema is valid JSON if provided."""
        if v is None:
            return v
        try:
            json.loads(v)
        except json.JSONDecodeError as e:
            raise ValueError(f"config_schema must be valid JSON: {e}") from e
        return v


class DeviceModelSummarySchema(BaseModel):
    """Summary schema for device model list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Device model ID")
    code: str = Field(..., description="Unique model code")
    name: str = Field(..., description="Human-readable model name")
    firmware_version: str | None = Field(None, description="Firmware version if uploaded")
    has_config_schema: bool = Field(..., description="Whether model has a config schema")
    device_count: int = Field(..., description="Number of devices using this model")


class DeviceModelResponseSchema(BaseModel):
    """Response schema for device model details."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Device model ID")
    code: str = Field(..., description="Unique model code")
    name: str = Field(..., description="Human-readable model name")
    firmware_version: str | None = Field(None, description="Firmware version if uploaded")
    config_schema: dict[str, Any] | None = Field(None, description="JSON schema for config validation")
    has_config_schema: bool = Field(..., description="Whether model has a config schema")
    device_count: int = Field(..., description="Number of devices using this model")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    @field_validator("config_schema", mode="before")
    @classmethod
    def parse_config_schema_from_string(cls, v: Any) -> dict[str, Any] | None:
        """Parse config_schema from JSON string if stored as text."""
        if v is None:
            return None
        if isinstance(v, str):
            return cast(dict[str, Any], json.loads(v))
        return cast(dict[str, Any], v)


class DeviceModelListResponseSchema(BaseModel):
    """Response schema for device model list."""

    device_models: list[DeviceModelSummarySchema]
    count: int = Field(..., description="Total count of device models")


class DeviceModelFirmwareResponseSchema(BaseModel):
    """Response schema for firmware upload."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Device model ID")
    code: str = Field(..., description="Model code")
    firmware_version: str = Field(..., description="Extracted firmware version")
