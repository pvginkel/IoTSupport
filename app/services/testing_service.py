"""Testing service for Playwright test suite support."""

import logging
import secrets
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TestSession:
    """Represents a test authentication session."""

    subject: str
    name: str | None
    email: str | None
    roles: list[str]


class TestingService:
    """Service for managing test sessions and forced errors.

    This service is a singleton that stores test state in memory.
    It should only be used when the application is running in testing mode.
    """

    # In-memory storage for test sessions (token -> session data)
    _sessions: dict[str, TestSession] = {}

    # Forced error status for /api/auth/self (single-shot)
    _forced_auth_error: int | None = None

    def __init__(self) -> None:
        """Initialize the testing service."""
        # Use class-level storage so state persists across instances
        pass

    def create_session(
        self,
        subject: str,
        name: str | None = None,
        email: str | None = None,
        roles: list[str] | None = None,
    ) -> str:
        """Create a test session and return a session token.

        Args:
            subject: User subject identifier
            name: User display name
            email: User email address
            roles: User roles (defaults to empty list)

        Returns:
            Session token to be stored in cookie
        """
        token = f"test-session-{secrets.token_urlsafe(16)}"
        session = TestSession(
            subject=subject,
            name=name,
            email=email,
            roles=roles or [],
        )
        TestingService._sessions[token] = session

        logger.info(
            "Created test session: subject=%s name=%s email=%s roles=%s",
            subject,
            name,
            email,
            roles,
        )

        return token

    def get_session(self, token: str) -> TestSession | None:
        """Get a test session by token.

        Args:
            token: Session token from cookie

        Returns:
            TestSession if found, None otherwise
        """
        return TestingService._sessions.get(token)

    def clear_session(self, token: str) -> bool:
        """Clear a test session.

        Args:
            token: Session token to clear

        Returns:
            True if session was cleared, False if not found
        """
        if token in TestingService._sessions:
            del TestingService._sessions[token]
            logger.info("Cleared test session")
            return True
        return False

    def clear_all_sessions(self) -> None:
        """Clear all test sessions."""
        TestingService._sessions.clear()
        logger.info("Cleared all test sessions")

    def set_forced_auth_error(self, status_code: int) -> None:
        """Set a forced error for the next /api/auth/self request.

        Args:
            status_code: HTTP status code to return
        """
        TestingService._forced_auth_error = status_code
        logger.info("Set forced auth error: status=%d", status_code)

    def consume_forced_auth_error(self) -> int | None:
        """Consume and return the forced auth error (single-shot).

        Returns:
            HTTP status code if set, None otherwise
        """
        error = TestingService._forced_auth_error
        TestingService._forced_auth_error = None
        if error:
            logger.info("Consumed forced auth error: status=%d", error)
        return error

    def has_forced_auth_error(self) -> bool:
        """Check if a forced auth error is set.

        Returns:
            True if forced error is set, False otherwise
        """
        return TestingService._forced_auth_error is not None
