"""Pydantic schemas for asset upload API."""

from pydantic import BaseModel, ConfigDict, Field


class AssetUploadResponseSchema(BaseModel):
    """Response schema for successful asset upload."""

    model_config = ConfigDict(from_attributes=True)

    filename: str = Field(description="Name of the uploaded file", examples=["firmware.bin"])
    size: int = Field(description="File size in bytes", examples=[1048576])
    uploaded_at: str = Field(
        description="ISO 8601 timestamp when upload was processed",
        examples=["2026-01-09T14:30:05.123456+00:00"],
    )
