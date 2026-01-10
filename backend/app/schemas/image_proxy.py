"""Pydantic schemas for image proxy API."""

from pydantic import BaseModel, Field, HttpUrl


class LvglImageQuerySchema(BaseModel):
    """Query parameters for LVGL image proxy endpoint."""

    url: HttpUrl = Field(
        ...,
        description="URL of the image to fetch and convert",
        examples=["https://example.com/image.png"],
    )

    headers: str | None = Field(
        None,
        description="Comma-separated list of header names to forward from the request",
        examples=["Authorization,X-API-Key"],
    )

    width: int | None = Field(
        None,
        gt=0,
        description="Target width for resizing (downscale only, maintains aspect ratio)",
        examples=[240],
    )

    height: int | None = Field(
        None,
        gt=0,
        description="Target height for resizing (downscale only, maintains aspect ratio)",
        examples=[240],
    )

    model_config = {"extra": "forbid"}
