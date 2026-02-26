"""Device schemas for API request/response validation."""

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeviceCreateSchema(BaseModel):
    """Request schema for creating a device."""

    device_model_id: int = Field(
        ...,
        description="ID of the device model this device belongs to",
    )
    config: str = Field(
        ...,
        description="Device configuration as JSON string",
    )

    @field_validator("config")
    @classmethod
    def validate_config_is_json(cls, v: str) -> str:
        """Validate that config is valid JSON."""
        try:
            json.loads(v)
        except json.JSONDecodeError as e:
            raise ValueError(f"config must be valid JSON: {e}") from e
        return v


class DeviceUpdateSchema(BaseModel):
    """Request schema for updating a device."""

    config: str = Field(
        ...,
        description="Device configuration as JSON string",
    )
    active: bool = Field(
        ...,
        description="Whether device participates in automatic fleet rotation",
    )

    @field_validator("config")
    @classmethod
    def validate_config_is_json(cls, v: str) -> str:
        """Validate that config is valid JSON."""
        try:
            json.loads(v)
        except json.JSONDecodeError as e:
            raise ValueError(f"config must be valid JSON: {e}") from e
        return v


class DeviceSummarySchema(BaseModel):
    """Summary schema for device list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Device ID")
    key: str = Field(..., description="Unique 8-character device key")
    device_model_id: int = Field(..., description="Device model ID")
    active: bool = Field(..., description="Whether device participates in automatic fleet rotation")
    device_name: str | None = Field(None, description="Device name from config")
    device_entity_id: str | None = Field(None, description="Device entity ID from config")
    enable_ota: bool | None = Field(None, description="OTA enabled flag from config")
    rotation_state: str = Field(..., description="Current rotation state")
    secret_created_at: datetime | None = Field(None, description="When current secret was created")
    last_coredump_at: datetime | None = Field(None, description="Timestamp of the most recent coredump")


class DeviceModelInfoSchema(BaseModel):
    """Embedded device model info in device responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Device model ID")
    code: str = Field(..., description="Device model code")
    name: str = Field(..., description="Device model name")
    firmware_version: str | None = Field(None, description="Firmware version if uploaded")


class DeviceResponseSchema(BaseModel):
    """Response schema for device details."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Device ID")
    key: str = Field(..., description="Unique 8-character device key")
    device_model_id: int = Field(..., description="Device model ID")
    device_model: DeviceModelInfoSchema = Field(..., description="Device model details")
    active: bool = Field(..., description="Whether device participates in automatic fleet rotation")
    config: str = Field(..., description="Device configuration as JSON string")
    device_name: str | None = Field(None, description="Device name from config")
    device_entity_id: str | None = Field(None, description="Device entity ID from config")
    enable_ota: bool | None = Field(None, description="OTA enabled flag from config")
    rotation_state: str = Field(..., description="Current rotation state")
    client_id: str = Field(..., description="Keycloak client ID")
    secret_created_at: datetime | None = Field(None, description="When current secret was created")
    last_rotation_attempt_at: datetime | None = Field(None, description="When last rotation was attempted")
    last_rotation_completed_at: datetime | None = Field(None, description="When last rotation completed")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")



class DeviceListResponseSchema(BaseModel):
    """Response schema for device list."""

    devices: list[DeviceSummarySchema]
    count: int = Field(..., description="Total count of devices")


class DeviceRotateResponseSchema(BaseModel):
    """Response schema for device rotation trigger."""

    status: str = Field(
        ...,
        description="Rotation status: 'queued' or 'already_pending'",
        examples=["queued", "already_pending"],
    )


class NvsProvisioningQuerySchema(BaseModel):
    """Query parameters for NVS provisioning request."""

    partition_size: int = Field(
        ...,
        description="NVS partition size in bytes. Must match the partition table "
        "on the device. Must be at least 12KB (0x3000) and a multiple of 4KB (0x1000). "
        "Common values: 0x4000 (16KB), 0x5000 (20KB), 0x6000 (24KB).",
        ge=0x3000,
        examples=[0x4000, 0x5000, 0x6000],
    )


class NvsProvisioningResponseSchema(BaseModel):
    """Response schema for NVS provisioning package.

    Returns the device provisioning data as an NVS binary blob
    that can be flashed directly to ESP32 devices.
    """

    size: int = Field(
        ...,
        description="Size of the NVS partition in bytes",
        examples=[0x4000, 0x5000, 0x6000],
    )
    data: str = Field(
        ...,
        description="Base64-encoded NVS binary blob of the specified size",
    )


class DeviceKeycloakStatusSchema(BaseModel):
    """Schema for Keycloak client status response."""

    model_config = ConfigDict(from_attributes=True)

    exists: bool = Field(..., description="Whether client exists in Keycloak")
    client_id: str = Field(..., description="Expected Keycloak client ID")
    keycloak_uuid: str | None = Field(None, description="Keycloak internal UUID if exists")
    console_url: str | None = Field(None, description="Deep link to Keycloak admin console")
