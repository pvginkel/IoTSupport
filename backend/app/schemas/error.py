"""Error response schema."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponseSchema(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error message")
    code: str | None = Field(None, description="Error code")
    details: dict[str, Any] | None = Field(None, description="Additional error details")
    correlation_id: str | None = Field(None, alias="correlationId", description="Request correlation ID")
