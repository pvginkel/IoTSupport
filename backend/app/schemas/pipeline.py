"""Pipeline API schemas for request/response validation."""

from pydantic import BaseModel, ConfigDict, Field


class FirmwareVersionResponseSchema(BaseModel):
    """Response schema for firmware version check."""

    model_config = ConfigDict(from_attributes=True)

    code: str = Field(
        description="Device model code",
        examples=["tempsensor"],
    )
    firmware_version: str | None = Field(
        description="Current firmware version, or null if no firmware uploaded",
        examples=["1.2.3"],
    )
