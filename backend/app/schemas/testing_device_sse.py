"""Pydantic schemas for device SSE testing endpoints.

Covers log injection, subscription status, and rotation nudge endpoints
used by Playwright tests to exercise SSE-driven features.
"""

from pydantic import BaseModel, ConfigDict, Field


class LogEntrySchema(BaseModel):
    """A single log entry to inject into the SSE pipeline."""

    model_config = ConfigDict(extra="allow")

    message: str = Field(
        ...,
        min_length=1,
        description="Log line content",
        examples=["Temperature reading: 22.5C"],
    )


class LogInjectRequestSchema(BaseModel):
    """Request body for POST /api/testing/devices/logs/inject."""

    device_entity_id: str = Field(
        ...,
        min_length=1,
        description="Device entity ID to target (matches the SSE subscription key)",
        examples=["sensor.living_room"],
    )
    logs: list[LogEntrySchema] = Field(
        ...,
        min_length=1,
        description="Log entries to forward into the SSE pipeline",
    )


class LogInjectResponseSchema(BaseModel):
    """Response for POST /api/testing/devices/logs/inject."""

    status: str = Field(
        ...,
        description="Always 'accepted' on success",
    )
    forwarded: int = Field(
        ...,
        description="Number of log entries passed to DeviceLogStreamService.forward_logs()",
    )


class SubscriptionsQuerySchema(BaseModel):
    """Query parameters for GET /api/testing/devices/logs/subscriptions."""

    device_entity_id: str | None = Field(
        None,
        description="Filter to subscriptions for this device entity ID. Omit to return all.",
        examples=["sensor.living_room"],
    )


class SubscriptionEntrySchema(BaseModel):
    """A single device subscription entry."""

    device_entity_id: str = Field(
        ...,
        description="Device entity ID with active subscriptions",
    )
    request_ids: list[str] = Field(
        ...,
        description="SSE connection request IDs subscribed to this device",
    )


class SubscriptionsResponseSchema(BaseModel):
    """Response for GET /api/testing/devices/logs/subscriptions."""

    subscriptions: list[SubscriptionEntrySchema] = Field(
        ...,
        description="Active SSE subscriptions, empty when none exist",
    )


class NudgeResponseSchema(BaseModel):
    """Response for POST /api/testing/rotation/nudge."""

    status: str = Field(
        ...,
        description="Always 'accepted' on success",
    )
