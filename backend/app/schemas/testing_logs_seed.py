"""Schemas for the testing device log seed endpoint."""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, model_validator


class SeedLogsRequestSchema(BaseModel):
    """Request schema for seeding device logs in memory."""

    device_entity_id: str = Field(
        ...,
        description="Device entity ID to seed logs for",
        examples=["sensor.living_room"],
    )
    count: int = Field(
        ...,
        ge=1,
        le=15000,
        description="Number of log entries to generate",
        examples=[1500],
    )
    start_time: datetime | None = Field(
        default=None,
        description="Timestamp of the first entry (defaults to end_time - 1h)",
        examples=["2026-02-01T14:00:00Z"],
    )
    end_time: datetime | None = Field(
        default=None,
        description="Timestamp of the last entry (defaults to now)",
        examples=["2026-02-01T15:00:00Z"],
    )

    @model_validator(mode="after")
    def _apply_defaults_and_validate(self) -> "SeedLogsRequestSchema":
        if self.end_time is None:
            self.end_time = datetime.now(UTC)
        if self.start_time is None:
            self.start_time = self.end_time - timedelta(hours=1)
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class SeedLogsResponseSchema(BaseModel):
    """Response schema for the seed logs endpoint."""

    seeded: int = Field(..., description="Number of log entries seeded")
    window_start: datetime = Field(
        ..., description="Timestamp of first seeded entry"
    )
    window_end: datetime = Field(
        ..., description="Timestamp of last seeded entry"
    )
