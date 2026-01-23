"""Tests for authentication utilities including token refresh functionality."""

import time

import jwt

from app.utils.auth import PendingTokenRefresh, get_token_expiry_seconds


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
