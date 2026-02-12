"""Coredump schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CoredumpBaseSchema(BaseModel):
    """Base schema with fields shared across coredump responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Coredump ID")
    device_id: int = Field(..., description="Device ID")
    filename: str = Field(..., description="Filename of the .dmp file on disk")
    chip: str = Field(..., description="Chip type (e.g., esp32s3)")
    firmware_version: str = Field(..., description="Firmware version at time of crash")
    size: int = Field(..., description="Size of the coredump binary in bytes")
    parse_status: str = Field(..., description="Parse status: PENDING, PARSED, or ERROR")
    uploaded_at: datetime = Field(..., description="When the coredump was uploaded")
    parsed_at: datetime | None = Field(None, description="When parsing completed")
    created_at: datetime = Field(..., description="Record creation timestamp")


class CoredumpSummarySchema(CoredumpBaseSchema):
    """Summary schema for coredump list responses (excludes parsed_output)."""


class CoredumpDetailSchema(CoredumpBaseSchema):
    """Detail schema for a single coredump (includes parsed_output)."""

    parsed_output: str | None = Field(None, description="Parsed crash analysis output")
    updated_at: datetime = Field(..., description="Record last update timestamp")


class CoredumpListResponseSchema(BaseModel):
    """Response schema for coredump list endpoint."""

    coredumps: list[CoredumpSummarySchema]
    count: int = Field(..., description="Total count of coredumps for this device")
