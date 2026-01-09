"""Configuration schemas for API request/response validation."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConfigSummarySchema(BaseModel):
    """Summary for list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    mac_address: str = Field(..., description="Device MAC address (filename)")
    device_name: str | None = Field(None, description="Device name from config")
    device_entity_id: str | None = Field(None, description="Device entity ID")
    enable_ota: bool | None = Field(None, description="OTA update enabled")


class ConfigListResponseSchema(BaseModel):
    """Response for list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    configs: list[ConfigSummarySchema]
    count: int


class ConfigDetailSchema(BaseModel):
    """Full config detail."""

    model_config = ConfigDict(from_attributes=True)

    mac_address: str
    content: dict[str, Any]  # Raw JSON content


class ConfigSaveRequestSchema(BaseModel):
    """Request for save endpoint."""

    content: dict[str, Any] = Field(..., description="JSON configuration content")


class ConfigResponseSchema(BaseModel):
    """Response for get/save endpoints."""

    model_config = ConfigDict(from_attributes=True)

    mac_address: str
    device_name: str | None = None
    device_entity_id: str | None = None
    enable_ota: bool | None = None
    content: dict[str, Any]
