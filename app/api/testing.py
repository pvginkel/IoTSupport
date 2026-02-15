"""Testing API endpoints for Playwright test suite support.

Domain-specific testing endpoints (not auth — those are handled by testing_auth.py).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, current_app, request
from spectree import Response as SpectreeResponse

from app.api.testing_guard import reject_if_not_testing
from app.models.coredump import CoreDump, ParseStatus
from app.schemas.coredump import CoredumpDetailSchema
from app.schemas.testing import (
    KeycloakCleanupSchema,
    TestCoredumpCreateSchema,
)
from app.services.container import ServiceContainer
from app.services.device_service import DeviceService
from app.services.keycloak_admin_service import KeycloakAdminService
from app.utils.auth import public
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

logger = logging.getLogger(__name__)

testing_bp = Blueprint("testing", __name__, url_prefix="/testing")

testing_bp.before_request(reject_if_not_testing)


@testing_bp.route("/keycloak-cleanup", methods=["POST"])
@public
@handle_api_errors
@inject
def cleanup_keycloak_clients(
    keycloak_service: KeycloakAdminService = Provide[ServiceContainer.keycloak_admin_service],
) -> tuple[dict[str, Any], int]:
    """Delete Keycloak clients matching a regex pattern.

    This endpoint is used by Playwright tests to clean up Keycloak clients
    created during test runs. The pattern is matched against client IDs.

    Request Body:
        pattern: Regular expression to match against client IDs (required, non-empty)

    Returns:
        200: Cleanup completed with count and list of deleted client IDs
    """
    data = KeycloakCleanupSchema.model_validate(request.get_json())

    deleted_client_ids = keycloak_service.delete_clients_by_pattern(data.pattern)

    logger.info(
        "Keycloak cleanup completed: deleted %d clients matching %r",
        len(deleted_client_ids),
        data.pattern,
    )

    return {
        "deleted_count": len(deleted_client_ids),
        "deleted_client_ids": deleted_client_ids,
    }, 200


@testing_bp.route("/coredumps", methods=["POST"])
@public
@api.validate(
    json=TestCoredumpCreateSchema,
    resp=SpectreeResponse(HTTP_201=CoredumpDetailSchema),
)
@handle_api_errors
@inject
def create_test_coredump(
    device_service: DeviceService = Provide[ServiceContainer.device_service],
) -> tuple[dict[str, Any], int]:
    """Create a coredump database record for testing.

    Seeds a CoreDump row directly in the database without filesystem I/O
    or sidecar parsing. Used by Playwright tests to set up coredump UI scenarios.
    """
    data = TestCoredumpCreateSchema.model_validate(request.get_json())

    # Verify the device exists (raises RecordNotFoundException if not)
    device_service.get_device(data.device_id)

    now = datetime.now(UTC)

    # Default parsed_output for PARSED status
    parsed_output = data.parsed_output
    if data.parse_status == ParseStatus.PARSED.value and parsed_output is None:
        parsed_output = "Test coredump parsed output"

    # Set parsed_at for terminal states (PARSED or ERROR)
    parsed_at = now if data.parse_status in (ParseStatus.PARSED.value, ParseStatus.ERROR.value) else None

    # Create the coredump record (no filename -- S3 key is derived from
    # device_key + coredump id)
    coredump = CoreDump(
        device_id=data.device_id,
        chip=data.chip,
        firmware_version=data.firmware_version,
        size=data.size,
        parse_status=data.parse_status,
        parsed_output=parsed_output,
        uploaded_at=now,
        parsed_at=parsed_at,
    )

    session = current_app.container.db_session()
    session.add(coredump)
    session.flush()

    logger.info("Created test coredump: id=%d device_id=%d status=%s", coredump.id, data.device_id, data.parse_status)

    return CoredumpDetailSchema.model_validate(coredump).model_dump(), 201
