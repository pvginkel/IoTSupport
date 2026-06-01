"""Pipeline API schemas for request/response validation."""

from datetime import datetime

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


class FleetProjectionDeviceSchema(BaseModel):
    """A single registered device in the fleet projection.

    Carries only identity/firmware-binding fields needed by the architecture
    generator. No secrets, rotation state, raw config, or coredumps (identity
    fence) — see the feature plan §3.
    """

    model_config = ConfigDict(from_attributes=True)

    key: str = Field(
        description="Immutable 8-character device key (stable natural key)",
        examples=["ab12cd34"],
    )
    model_code: str = Field(
        description="Device model code (equals the firmware project() name)",
        examples=["calendar_display"],
    )
    firmware_version: str | None = Field(
        description="Current firmware version of the device's model, or null",
        examples=["1.4.2"],
    )
    device_name: str | None = Field(
        default=None,
        description="Human-readable device name, or null if not set in config",
        examples=["Hallway clock"],
    )
    created_at: datetime = Field(
        description="Immutable row creation timestamp; its date drives 'introduced'",
        examples=["2026-03-14T09:21:07Z"],
    )


class FleetConfigSchema(BaseModel):
    """Fleet-wide configuration relevant to architecture resolution.

    These URLs let the generator tiebreak capability providers (MQTT broker,
    OIDC issuer) by host. No secrets are exposed.
    """

    model_config = ConfigDict(from_attributes=True)

    mqtt_url: str | None = Field(
        default=None,
        description="Device-facing MQTT broker URL",
        examples=["mqtt://mosquitto.home:1883"],
    )
    oidc_issuer_url: str | None = Field(
        default=None,
        description="OIDC issuer/token URL used for device authentication",
        examples=["https://auth.ginbov.nl/realms/iot/protocol/openid-connect/token"],
    )


class FleetProjectionResponseSchema(BaseModel):
    """Raw fleet projection consumed by the architecture generator."""

    model_config = ConfigDict(from_attributes=True)

    devices: list[FleetProjectionDeviceSchema] = Field(
        description="Every registered device (full fleet; NOT filtered on 'active')",
    )
    fleet: FleetConfigSchema = Field(
        description="Fleet-wide configuration (MQTT/OIDC URLs)",
    )
