"""Pydantic schemas for request/response validation."""

from app.schemas.device import (
    DeviceCreateSchema,
    DeviceListResponseSchema,
    DeviceResponseSchema,
    DeviceRotateResponseSchema,
    DeviceSummarySchema,
    DeviceUpdateSchema,
    ProvisioningPackageSchema,
)
from app.schemas.device_model import (
    DeviceModelCreateSchema,
    DeviceModelFirmwareResponseSchema,
    DeviceModelListResponseSchema,
    DeviceModelResponseSchema,
    DeviceModelSummarySchema,
    DeviceModelUpdateSchema,
)
from app.schemas.error import ErrorResponseSchema
from app.schemas.rotation import (
    RotationJobResultSchema,
    RotationStatusSchema,
    RotationTriggerResponseSchema,
)

__all__ = [
    # Device schemas
    "DeviceCreateSchema",
    "DeviceListResponseSchema",
    "DeviceResponseSchema",
    "DeviceRotateResponseSchema",
    "DeviceSummarySchema",
    "DeviceUpdateSchema",
    "ProvisioningPackageSchema",
    # Device model schemas
    "DeviceModelCreateSchema",
    "DeviceModelFirmwareResponseSchema",
    "DeviceModelListResponseSchema",
    "DeviceModelResponseSchema",
    "DeviceModelSummarySchema",
    "DeviceModelUpdateSchema",
    # Error schemas
    "ErrorResponseSchema",
    # Rotation schemas
    "RotationJobResultSchema",
    "RotationStatusSchema",
    "RotationTriggerResponseSchema",
]
