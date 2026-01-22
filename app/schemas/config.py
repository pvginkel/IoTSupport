"""Configuration schemas for API request/response validation."""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfigSummarySchema(BaseModel):
    """Summary for list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Config surrogate ID")
    mac_address: str = Field(..., description="Device MAC address (colon-separated)")
    device_name: str | None = Field(None, description="Device name from config")
    device_entity_id: str | None = Field(None, description="Device entity ID")
    enable_ota: bool | None = Field(None, description="OTA update enabled")


class ConfigListResponseSchema(BaseModel):
    """Response for list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    configs: list[ConfigSummarySchema]
    count: int


class ConfigCreateRequestSchema(BaseModel):
    """Request for POST /api/configs (create new config)."""

    mac_address: str = Field(..., description="Device MAC address (colon-separated)")
    content: dict[str, Any] = Field(..., description="JSON configuration content")


class ConfigUpdateRequestSchema(BaseModel):
    """Request for PUT /api/configs/<id> (update existing config)."""

    content: dict[str, Any] = Field(..., description="JSON configuration content")


class ConfigResponseSchema(BaseModel):
    """Response for get/create/update endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Config surrogate ID")
    mac_address: str = Field(..., description="Device MAC address (colon-separated)")
    device_name: str | None = Field(None, description="Device name from config")
    device_entity_id: str | None = Field(None, description="Device entity ID")
    enable_ota: bool | None = Field(None, description="OTA update enabled")
    content: dict[str, Any] = Field(..., description="JSON configuration content")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    @field_validator("content", mode="before")
    @classmethod
    def parse_content_from_string(cls, v: Any) -> dict[str, Any]:
        """Parse content from JSON string if stored as text in database."""
        if isinstance(v, str):
            return json.loads(v)
        return v
