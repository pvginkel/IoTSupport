"""Device log stream subscribe/unsubscribe API endpoints.

These endpoints allow frontend clients to manage SSE subscriptions for
real-time device log streaming. The subscribe endpoint resolves device_id
to device_entity_id using the request-scoped DeviceService, then delegates
to the singleton DeviceLogStreamService.
"""

import logging
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, g, request
from spectree import Response as SpectreeResponse

from app.exceptions import RecordNotFoundException
from app.schemas.device_log_stream import (
    DeviceLogSubscribeRequest,
    DeviceLogSubscribeResponse,
    DeviceLogUnsubscribeRequest,
    DeviceLogUnsubscribeResponse,
)
from app.services.container import ServiceContainer
from app.services.device_log_stream_service import DeviceLogStreamService
from app.services.device_service import DeviceService
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

logger = logging.getLogger(__name__)

device_log_stream_bp = Blueprint(
    "device_log_stream", __name__, url_prefix="/device-logs"
)


def _get_caller_subject() -> str | None:
    """Extract the caller's OIDC subject from the request context.

    Returns None when OIDC is disabled (no auth context on g).
    """
    auth_context = getattr(g, "auth_context", None)
    if auth_context is not None:
        subject: str = auth_context.subject
        return subject
    return None


@device_log_stream_bp.route("/subscribe", methods=["POST"])
@api.validate(
    json=DeviceLogSubscribeRequest,
    resp=SpectreeResponse(HTTP_200=DeviceLogSubscribeResponse),
)
@handle_api_errors
@inject
def subscribe(
    device_log_stream_service: DeviceLogStreamService = Provide[
        ServiceContainer.device_log_stream_service
    ],
    device_service: DeviceService = Provide[ServiceContainer.device_service],
) -> Any:
    """Subscribe an SSE connection to a device's log stream.

    Resolves device_id to device_entity_id, verifies identity, then
    registers the subscription. Idempotent for the same (request_id, device_id) pair.
    """
    data = DeviceLogSubscribeRequest.model_validate(request.get_json())

    # Resolve device_id -> device_entity_id using request-scoped DeviceService
    # get_device raises RecordNotFoundException if device doesn't exist
    device = device_service.get_device(data.device_id)

    # Device must have an entity_id for log matching to work
    if not device.device_entity_id:
        raise RecordNotFoundException("Device entity ID", data.device_id)

    # Delegate to singleton service with identity verification.
    # AuthorizationException (403) propagates to handle_api_errors if
    # the caller's identity does not match the SSE connection's binding.
    caller_subject = _get_caller_subject()
    device_log_stream_service.subscribe(
        data.request_id, device.device_entity_id, caller_subject
    )

    return DeviceLogSubscribeResponse(
        device_entity_id=device.device_entity_id,
    ).model_dump()


@device_log_stream_bp.route("/unsubscribe", methods=["POST"])
@api.validate(
    json=DeviceLogUnsubscribeRequest,
    resp=SpectreeResponse(HTTP_200=DeviceLogUnsubscribeResponse),
)
@handle_api_errors
@inject
def unsubscribe(
    device_log_stream_service: DeviceLogStreamService = Provide[
        ServiceContainer.device_log_stream_service
    ],
    device_service: DeviceService = Provide[ServiceContainer.device_service],
) -> Any:
    """Unsubscribe an SSE connection from a device's log stream.

    Verifies identity before removing the subscription.
    """
    data = DeviceLogUnsubscribeRequest.model_validate(request.get_json())

    # Resolve device_id -> device_entity_id
    # get_device raises RecordNotFoundException if device doesn't exist
    device = device_service.get_device(data.device_id)

    # Device must have an entity_id for subscription matching to work
    if not device.device_entity_id:
        raise RecordNotFoundException("Device entity ID", data.device_id)

    # Delegate to singleton service with identity verification.
    # AuthorizationException (403) propagates to handle_api_errors if
    # the caller's identity does not match. RecordNotFoundException (404)
    # propagates if no active subscription exists.
    caller_subject = _get_caller_subject()
    device_log_stream_service.unsubscribe(
        data.request_id, device.device_entity_id, caller_subject
    )

    return DeviceLogUnsubscribeResponse().model_dump()
