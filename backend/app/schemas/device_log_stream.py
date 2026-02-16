"""Pydantic schemas for device log stream subscribe/unsubscribe endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class DeviceLogSubscribeRequest(BaseModel):
    """Request body for subscribing to a device's log stream."""

    request_id: str = Field(
        ..., description="SSE connection request ID", examples=["abc123"]
    )
    device_id: int = Field(
        ..., description="Device ID to subscribe to", examples=[42]
    )

    model_config = ConfigDict(extra="forbid")


class DeviceLogSubscribeResponse(BaseModel):
    """Response body for a successful subscribe."""

    status: str = Field(
        default="subscribed", description="Operation result"
    )
    device_entity_id: str = Field(
        ..., description="Resolved device entity ID used for log matching"
    )

    model_config = ConfigDict(extra="forbid")


class DeviceLogUnsubscribeRequest(BaseModel):
    """Request body for unsubscribing from a device's log stream."""

    request_id: str = Field(
        ..., description="SSE connection request ID", examples=["abc123"]
    )
    device_id: int = Field(
        ..., description="Device ID to unsubscribe from", examples=[42]
    )

    model_config = ConfigDict(extra="forbid")


class DeviceLogUnsubscribeResponse(BaseModel):
    """Response body for a successful unsubscribe."""

    status: str = Field(
        default="unsubscribed", description="Operation result"
    )

    model_config = ConfigDict(extra="forbid")
