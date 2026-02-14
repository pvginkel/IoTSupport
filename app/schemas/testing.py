"""Schemas for domain-specific testing API endpoints."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.coredump import ParseStatus


class KeycloakCleanupSchema(BaseModel):
    """Request schema for Keycloak client cleanup by pattern."""

    model_config = ConfigDict(from_attributes=True)

    pattern: str = Field(
        ...,
        min_length=1,
        description="Regular expression pattern to match against Keycloak client IDs",
        examples=["^iotdevice-test_.*", ".*-playwright-.*"],
    )


class TestCoredumpCreateSchema(BaseModel):
    """Request schema for creating a test coredump record."""

    model_config = ConfigDict(from_attributes=True)

    device_id: int = Field(..., description="Device ID to associate the coredump with")
    chip: str = Field("esp32s3", description="Chip type")
    firmware_version: str = Field("0.0.0-test", description="Firmware version at time of crash")
    size: int = Field(262144, description="Size of the coredump binary in bytes")
    parse_status: str = Field("PARSED", description="Parse status: PENDING, PARSED, or ERROR")
    parsed_output: str | None = Field(None, description="Parsed crash analysis output")

    @field_validator("parse_status")
    @classmethod
    def validate_parse_status(cls, v: str) -> str:
        """Validate parse_status is a valid ParseStatus enum value."""
        try:
            ParseStatus(v)
        except ValueError:
            valid = ", ".join(s.value for s in ParseStatus)
            raise ValueError(f"Invalid parse_status '{v}'. Must be one of: {valid}") from None
        return v
