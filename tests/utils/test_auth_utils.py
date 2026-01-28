"""Tests for authentication utilities including token refresh functionality."""

import time

import jwt
import pytest

from app.exceptions import AuthorizationException
from app.services.auth_service import AuthContext
from app.utils.auth import (
    PendingTokenRefresh,
    allow_roles,
    check_authorization,
    get_token_expiry_seconds,
    public,
)


class TestGetTokenExpirySeconds:
    """Test suite for get_token_expiry_seconds utility function."""

    def test_valid_jwt_returns_remaining_seconds(self):
        """Test that a valid JWT returns correct remaining seconds."""
        # Create a token expiring in 1 hour
        exp_time = int(time.time()) + 3600
        payload = {"sub": "test-user", "exp": exp_time}
        token = jwt.encode(payload, "secret", algorithm="HS256")

        remaining = get_token_expiry_seconds(token)

        # Should be close to 3600 (within a few seconds of test execution)
        assert remaining is not None
        assert 3590 <= remaining <= 3600

    def test_expired_jwt_returns_zero(self):
        """Test that an expired JWT returns 0 (not negative)."""
        # Create a token that expired 1 hour ago
        exp_time = int(time.time()) - 3600
        payload = {"sub": "test-user", "exp": exp_time}
        token = jwt.encode(payload, "secret", algorithm="HS256")

        remaining = get_token_expiry_seconds(token)

        assert remaining == 0

    def test_jwt_without_exp_returns_none(self):
        """Test that a JWT without exp claim returns None."""
        payload = {"sub": "test-user"}
        token = jwt.encode(payload, "secret", algorithm="HS256")

        remaining = get_token_expiry_seconds(token)

        assert remaining is None

    def test_invalid_jwt_returns_none(self):
        """Test that an invalid JWT string returns None."""
        remaining = get_token_expiry_seconds("not-a-valid-jwt")

        assert remaining is None

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        remaining = get_token_expiry_seconds("")

        assert remaining is None

    def test_opaque_token_returns_none(self):
        """Test that an opaque (non-JWT) token returns None."""
        # Opaque tokens are typically random strings, not JWTs
        remaining = get_token_expiry_seconds("some-opaque-refresh-token-abc123")

        assert remaining is None


class TestPendingTokenRefresh:
    """Test suite for PendingTokenRefresh dataclass."""

    def test_create_with_refresh_token(self):
        """Test creating PendingTokenRefresh with all fields."""
        pending = PendingTokenRefresh(
            access_token="new-access-token",
            refresh_token="new-refresh-token",
            access_token_expires_in=300,
        )

        assert pending.access_token == "new-access-token"
        assert pending.refresh_token == "new-refresh-token"
        assert pending.access_token_expires_in == 300

    def test_create_without_refresh_token(self):
        """Test creating PendingTokenRefresh without refresh token."""
        pending = PendingTokenRefresh(
            access_token="new-access-token",
            refresh_token=None,
            access_token_expires_in=300,
        )

        assert pending.access_token == "new-access-token"
        assert pending.refresh_token is None
        assert pending.access_token_expires_in == 300


class TestPublicDecorator:
    """Test suite for @public decorator."""

    def test_public_sets_is_public_attribute(self):
        """Test that @public sets is_public=True on the function."""
        @public
        def my_endpoint():
            return "public data"

        assert hasattr(my_endpoint, "is_public")
        assert my_endpoint.is_public is True

    def test_public_preserves_function_behavior(self):
        """Test that @public doesn't change function behavior."""
        @public
        def my_endpoint(x, y):
            return x + y

        assert my_endpoint(2, 3) == 5

    def test_function_without_public_has_no_is_public(self):
        """Test that functions without @public don't have is_public attribute."""
        def my_endpoint():
            return "private data"

        assert not getattr(my_endpoint, "is_public", False)


class TestAllowRolesDecorator:
    """Test suite for @allow_roles decorator."""

    def test_allow_roles_sets_allowed_roles_attribute(self):
        """Test that @allow_roles sets allowed_roles as a set."""
        @allow_roles("pipeline")
        def my_endpoint():
            return "data"

        assert hasattr(my_endpoint, "allowed_roles")
        assert my_endpoint.allowed_roles == {"pipeline"}

    def test_allow_roles_multiple_roles(self):
        """Test that @allow_roles handles multiple roles."""
        @allow_roles("pipeline", "reader", "writer")
        def my_endpoint():
            return "data"

        assert my_endpoint.allowed_roles == {"pipeline", "reader", "writer"}

    def test_allow_roles_preserves_function_behavior(self):
        """Test that @allow_roles doesn't change function behavior."""
        @allow_roles("pipeline")
        def my_endpoint(x):
            return x * 2

        assert my_endpoint(5) == 10

    def test_function_without_allow_roles_has_no_allowed_roles(self):
        """Test that functions without @allow_roles don't have allowed_roles."""
        def my_endpoint():
            return "data"

        assert not hasattr(my_endpoint, "allowed_roles")


class TestCheckAuthorization:
    """Test suite for check_authorization function."""

    def test_admin_role_grants_full_access(self):
        """Test that admin role grants access to any endpoint."""
        auth_context = AuthContext(
            subject="admin-user",
            email="admin@example.com",
            name="Admin User",
            roles={"admin"},
        )

        # Should not raise - admin has full access
        check_authorization(auth_context, view_func=None)

    def test_admin_role_grants_access_even_with_allow_roles(self):
        """Test that admin role grants access even when @allow_roles is present."""
        @allow_roles("pipeline")
        def pipeline_endpoint():
            pass

        auth_context = AuthContext(
            subject="admin-user",
            email="admin@example.com",
            name="Admin User",
            roles={"admin"},
        )

        # Should not raise - admin bypasses @allow_roles check
        check_authorization(auth_context, view_func=pipeline_endpoint)

    def test_allowed_role_grants_access(self):
        """Test that a role listed in @allow_roles grants access."""
        @allow_roles("pipeline")
        def pipeline_endpoint():
            pass

        auth_context = AuthContext(
            subject="pipeline-user",
            email="ci@example.com",
            name="Pipeline User",
            roles={"pipeline"},
        )

        # Should not raise - pipeline role is allowed
        check_authorization(auth_context, view_func=pipeline_endpoint)

    def test_one_of_multiple_allowed_roles_grants_access(self):
        """Test that having one of multiple allowed roles grants access."""
        @allow_roles("pipeline", "reader", "writer")
        def multi_role_endpoint():
            pass

        auth_context = AuthContext(
            subject="reader-user",
            email="reader@example.com",
            name="Reader User",
            roles={"reader"},
        )

        # Should not raise - reader is one of the allowed roles
        check_authorization(auth_context, view_func=multi_role_endpoint)

    def test_unrecognized_role_denied_without_allow_roles(self):
        """Test that unrecognized role is denied when no @allow_roles present."""
        def regular_endpoint():
            pass

        auth_context = AuthContext(
            subject="other-user",
            email="other@example.com",
            name="Other User",
            roles={"some-other-role"},
        )

        with pytest.raises(AuthorizationException) as exc_info:
            check_authorization(auth_context, view_func=regular_endpoint)

        assert "admin" in str(exc_info.value)

    def test_unrecognized_role_denied_with_allow_roles(self):
        """Test that unrecognized role is denied even when @allow_roles present."""
        @allow_roles("pipeline")
        def pipeline_endpoint():
            pass

        auth_context = AuthContext(
            subject="other-user",
            email="other@example.com",
            name="Other User",
            roles={"some-other-role"},
        )

        with pytest.raises(AuthorizationException) as exc_info:
            check_authorization(auth_context, view_func=pipeline_endpoint)

        # Error message should mention both admin and the allowed role
        error_msg = str(exc_info.value)
        assert "admin" in error_msg
        assert "pipeline" in error_msg

    def test_error_message_format_without_allow_roles(self):
        """Test error message format when endpoint has no @allow_roles."""
        def regular_endpoint():
            pass

        auth_context = AuthContext(
            subject="user",
            email="user@example.com",
            name="User",
            roles={"viewer"},
        )

        with pytest.raises(AuthorizationException) as exc_info:
            check_authorization(auth_context, view_func=regular_endpoint)

        assert "'admin' role required" in str(exc_info.value)

    def test_error_message_format_with_allow_roles(self):
        """Test error message format when endpoint has @allow_roles."""
        @allow_roles("pipeline", "operator")
        def restricted_endpoint():
            pass

        auth_context = AuthContext(
            subject="user",
            email="user@example.com",
            name="User",
            roles={"viewer"},
        )

        with pytest.raises(AuthorizationException) as exc_info:
            check_authorization(auth_context, view_func=restricted_endpoint)

        error_msg = str(exc_info.value)
        assert "admin" in error_msg
        assert "operator" in error_msg
        assert "pipeline" in error_msg

    def test_no_view_func_requires_admin(self):
        """Test that when view_func is None, only admin role is accepted."""
        auth_context = AuthContext(
            subject="pipeline-user",
            email="ci@example.com",
            name="Pipeline User",
            roles={"pipeline"},
        )

        # Without view_func, we can't check @allow_roles, so only admin works
        with pytest.raises(AuthorizationException) as exc_info:
            check_authorization(auth_context, view_func=None)

        assert "'admin' role required" in str(exc_info.value)

    def test_empty_roles_denied(self):
        """Test that user with no roles is denied."""
        auth_context = AuthContext(
            subject="no-role-user",
            email="norole@example.com",
            name="No Role User",
            roles=set(),
        )

        with pytest.raises(AuthorizationException):
            check_authorization(auth_context, view_func=None)
