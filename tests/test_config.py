"""Tests for the configuration module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import ConfigurationError, Environment, Settings, _derive_fernet_key


class TestDerivesFernetKey:
    """Tests for Fernet key derivation."""

    def test_derives_consistent_key(self):
        """Same input produces same output."""
        key1 = _derive_fernet_key("test-secret")
        key2 = _derive_fernet_key("test-secret")
        assert key1 == key2

    def test_different_inputs_produce_different_keys(self):
        """Different inputs produce different keys."""
        key1 = _derive_fernet_key("secret-1")
        key2 = _derive_fernet_key("secret-2")
        assert key1 != key2

    def test_produces_valid_base64(self):
        """Key is valid URL-safe base64."""
        import base64
        key = _derive_fernet_key("test-secret")
        # Should not raise
        decoded = base64.urlsafe_b64decode(key)
        assert len(decoded) == 32  # SHA256 produces 32 bytes


class TestEnvironment:
    """Tests for Environment class."""

    def test_loads_from_environment(self, tmp_path: Path):
        """Environment loads values from environment variables."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        with patch.dict(os.environ, {
            "SECRET_KEY": "env-secret",
            "FLASK_ENV": "production",
            "DEBUG": "False",
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://test:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
        }, clear=False):
            env = Environment(_env_file=None)  # type: ignore[call-arg]

            assert env.SECRET_KEY == "env-secret"
            assert env.FLASK_ENV == "production"
            assert env.DEBUG is False
            assert env.MQTT_URL == "mqtt://test:1883"
            assert env.WIFI_SSID == "TestNet"

    def test_uses_defaults(self, tmp_path: Path):
        """Environment uses default values when not set."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        # Only set required fields
        with patch.dict(os.environ, {
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://test:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
        }, clear=False):
            env = Environment(_env_file=None)  # type: ignore[call-arg]

            # Check defaults
            assert env.FLASK_ENV == "development"
            assert env.DEBUG is True
            assert env.CORS_ORIGINS == ["http://localhost:3000"]
            assert env.OIDC_ENABLED is False


class TestSettingsLoad:
    """Tests for Settings.load() method."""

    def test_load_creates_settings_from_environment(self, tmp_path: Path):
        """Settings.load() creates Settings from Environment."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        with patch.dict(os.environ, {
            "SECRET_KEY": "test-secret",
            "FLASK_ENV": "development",
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://test:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
            "BASEURL": "https://iot.example.com/",  # With trailing slash
        }, clear=False):
            settings = Settings.load()

            assert settings.secret_key == "test-secret"
            assert settings.flask_env == "development"
            assert settings.mqtt_url == "mqtt://test:1883"
            # Trailing slash should be stripped
            assert settings.baseurl == "https://iot.example.com"

    def test_device_baseurl_fallback(self, tmp_path: Path):
        """DEVICE_BASEURL falls back to BASEURL if not set."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        with patch.dict(os.environ, {
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://test:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
            "BASEURL": "https://iot.example.com",
        }, clear=False):
            # Ensure DEVICE_BASEURL is not set
            os.environ.pop("DEVICE_BASEURL", None)
            settings = Settings.load()

            assert settings.device_baseurl == "https://iot.example.com"

    def test_device_baseurl_explicit(self, tmp_path: Path):
        """DEVICE_BASEURL can be set explicitly."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        with patch.dict(os.environ, {
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://test:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
            "BASEURL": "https://iot.example.com",
            "DEVICE_BASEURL": "https://devices.example.com",
        }, clear=False):
            settings = Settings.load()

            assert settings.device_baseurl == "https://devices.example.com"

    def test_device_mqtt_url_fallback(self, tmp_path: Path):
        """DEVICE_MQTT_URL falls back to MQTT_URL if not set."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        with patch.dict(os.environ, {
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://broker.example.com:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
            "BASEURL": "https://iot.example.com",
        }, clear=False):
            # Ensure DEVICE_MQTT_URL is not set
            os.environ.pop("DEVICE_MQTT_URL", None)
            settings = Settings.load()

            assert settings.device_mqtt_url == "mqtt://broker.example.com:1883"

    def test_device_mqtt_url_explicit(self, tmp_path: Path):
        """DEVICE_MQTT_URL can be set explicitly."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        with patch.dict(os.environ, {
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://internal-broker:1883",
            "DEVICE_MQTT_URL": "mqtt://device-broker.example.com:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
            "BASEURL": "https://iot.example.com",
        }, clear=False):
            settings = Settings.load()

            assert settings.device_mqtt_url == "mqtt://device-broker.example.com:1883"
            # Original mqtt_url should still be the internal one
            assert settings.mqtt_url == "mqtt://internal-broker:1883"

    def test_fernet_key_derived_from_secret(self, tmp_path: Path):
        """Fernet key is derived from SECRET_KEY if not explicit."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        with patch.dict(os.environ, {
            "SECRET_KEY": "my-secret-key",
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://test:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
        }, clear=False):
            # Ensure FERNET_KEY is not set
            os.environ.pop("FERNET_KEY", None)
            settings = Settings.load()

            expected_key = _derive_fernet_key("my-secret-key")
            assert settings.fernet_key == expected_key

    def test_oidc_audience_fallback(self, tmp_path: Path):
        """OIDC_AUDIENCE falls back to OIDC_CLIENT_ID."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        with patch.dict(os.environ, {
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://test:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
            "OIDC_CLIENT_ID": "my-client-id",
        }, clear=False):
            # Ensure OIDC_AUDIENCE is not set
            os.environ.pop("OIDC_AUDIENCE", None)
            settings = Settings.load()

            assert settings.oidc_audience == "my-client-id"

    def test_cookie_secure_inferred_from_https(self, tmp_path: Path):
        """Cookie secure flag is inferred from BASEURL scheme."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        # HTTPS baseurl -> secure=True
        with patch.dict(os.environ, {
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://test:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
            "BASEURL": "https://iot.example.com",
        }, clear=False):
            os.environ.pop("OIDC_COOKIE_SECURE", None)
            settings = Settings.load()
            assert settings.oidc_cookie_secure is True

        # HTTP baseurl -> secure=False
        with patch.dict(os.environ, {
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://test:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
            "BASEURL": "http://localhost:3200",
        }, clear=False):
            os.environ.pop("OIDC_COOKIE_SECURE", None)
            settings = Settings.load()
            assert settings.oidc_cookie_secure is False

    def test_keycloak_urls_computed(self, tmp_path: Path):
        """Keycloak admin and console URLs are computed from base URL and realm."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        with patch.dict(os.environ, {
            "ASSETS_DIR": str(assets_dir),
            "MQTT_URL": "mqtt://test:1883",
            "WIFI_SSID": "TestNet",
            "WIFI_PASSWORD": "TestPass",
            "KEYCLOAK_BASE_URL": "https://auth.example.com",
            "KEYCLOAK_REALM": "iot",
        }, clear=False):
            settings = Settings.load()

            assert settings.keycloak_admin_url == "https://auth.example.com/admin/realms/iot"
            assert settings.keycloak_console_base_url == "https://auth.example.com/admin/master/console/#/iot/clients"

    def test_keycloak_urls_none_when_missing(self, tmp_path: Path):
        """Keycloak URLs are None when base URL or realm is missing."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        # Create a minimal environment that doesn't have keycloak settings
        env = Environment(
            _env_file=None,  # type: ignore[call-arg]
            ASSETS_DIR=assets_dir,
            MQTT_URL="mqtt://test:1883",
            WIFI_SSID="TestNet",
            WIFI_PASSWORD="TestPass",
            KEYCLOAK_BASE_URL=None,
            KEYCLOAK_REALM=None,
        )
        settings = Settings.load(env)

        assert settings.keycloak_admin_url is None
        assert settings.keycloak_console_base_url is None


class TestSettingsDirectConstruction:
    """Tests for constructing Settings directly (for tests)."""

    def test_construct_minimal_settings(self, tmp_path: Path):
        """Can construct Settings with all required fields."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        settings = Settings(
            secret_key="test-secret",
            flask_env="testing",
            debug=True,
            database_url="sqlite:///:memory:",
            assets_dir=assets_dir,
            cors_origins=["http://localhost:3000"],
            mqtt_url="mqtt://test:1883",
            device_mqtt_url="mqtt://test:1883",
            mqtt_username=None,
            mqtt_password=None,
            baseurl="http://localhost:3200",
            device_baseurl="http://localhost:3200",
            oidc_enabled=False,
            oidc_issuer_url=None,
            oidc_client_id=None,
            oidc_client_secret=None,
            oidc_scopes="openid profile email",
            oidc_audience=None,
            oidc_clock_skew_seconds=30,
            oidc_cookie_name="access_token",
            oidc_cookie_secure=False,
            oidc_cookie_samesite="Lax",
            oidc_refresh_cookie_name="refresh_token",
            oidc_token_url=None,
            keycloak_base_url=None,
            keycloak_realm=None,
            keycloak_admin_client_id=None,
            keycloak_admin_client_secret=None,
            keycloak_device_scope_name="iot-device-audience",
            keycloak_admin_url=None,
            keycloak_console_base_url=None,
            wifi_ssid="TestNet",
            wifi_password="TestPass",
            rotation_cron=None,
            rotation_timeout_seconds=300,
            rotation_critical_threshold_days=None,
            elasticsearch_url=None,
            elasticsearch_username=None,
            elasticsearch_password=None,
            elasticsearch_index_pattern="logstash-http-*",
            mqtt_client_id="iotsupport-backend",
            fernet_key="test-fernet-key-base64-encoded-32-bytes-here==",
        )

        assert settings.flask_env == "testing"
        assert settings.is_testing is True
        assert settings.is_production is False

    def test_is_production_property(self, tmp_path: Path):
        """is_production returns True for production or non-debug mode."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        base_kwargs = {
            "secret_key": "test-secret",
            "database_url": "sqlite:///:memory:",
            "assets_dir": assets_dir,
            "cors_origins": [],
            "mqtt_url": "mqtt://test:1883",
            "device_mqtt_url": "mqtt://test:1883",
            "mqtt_username": None,
            "mqtt_password": None,
            "baseurl": "http://localhost",
            "device_baseurl": "http://localhost",
            "oidc_enabled": False,
            "oidc_issuer_url": None,
            "oidc_client_id": None,
            "oidc_client_secret": None,
            "oidc_scopes": "openid",
            "oidc_audience": None,
            "oidc_clock_skew_seconds": 30,
            "oidc_cookie_name": "access_token",
            "oidc_cookie_secure": False,
            "oidc_cookie_samesite": "Lax",
            "oidc_refresh_cookie_name": "refresh_token",
            "oidc_token_url": None,
            "keycloak_base_url": None,
            "keycloak_realm": None,
            "keycloak_admin_client_id": None,
            "keycloak_admin_client_secret": None,
            "keycloak_device_scope_name": "iot-device-audience",
            "keycloak_admin_url": None,
            "keycloak_console_base_url": None,
            "wifi_ssid": "Test",
            "wifi_password": "Test",
            "rotation_cron": None,
            "rotation_timeout_seconds": 300,
            "rotation_critical_threshold_days": None,
            "elasticsearch_url": None,
            "elasticsearch_username": None,
            "elasticsearch_password": None,
            "elasticsearch_index_pattern": "logstash-http-*",
            "mqtt_client_id": "iotsupport-backend",
            "fernet_key": "test-fernet-key-base64-encoded-32-bytes-here==",
        }

        # Development + debug=True -> not production
        settings = Settings(flask_env="development", debug=True, **base_kwargs)
        assert settings.is_production is False

        # Production + debug=True -> is production (flask_env takes precedence)
        settings = Settings(flask_env="production", debug=True, **base_kwargs)
        assert settings.is_production is True

        # Development + debug=False -> is production (debug=False means production)
        settings = Settings(flask_env="development", debug=False, **base_kwargs)
        assert settings.is_production is True


class TestSettingsValidation:
    """Tests for Settings.validate_production_config()."""

    def test_validation_skipped_for_development(self, tmp_path: Path):
        """Validation passes in development mode even with missing config."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        settings = Settings(
            secret_key="dev-secret-key-change-in-production",  # Default
            flask_env="development",
            debug=True,
            database_url="sqlite:///:memory:",
            assets_dir=assets_dir,
            cors_origins=[],
            mqtt_url="mqtt://test:1883",
            device_mqtt_url="mqtt://test:1883",
            mqtt_username=None,
            mqtt_password=None,
            baseurl="http://localhost",
            device_baseurl="http://localhost",
            oidc_enabled=False,
            oidc_issuer_url=None,
            oidc_client_id=None,
            oidc_client_secret=None,
            oidc_scopes="openid",
            oidc_audience=None,
            oidc_clock_skew_seconds=30,
            oidc_cookie_name="access_token",
            oidc_cookie_secure=False,
            oidc_cookie_samesite="Lax",
            oidc_refresh_cookie_name="refresh_token",
            oidc_token_url=None,
            keycloak_base_url=None,
            keycloak_realm=None,
            keycloak_admin_client_id=None,
            keycloak_admin_client_secret=None,
            keycloak_device_scope_name="iot-device-audience",
            keycloak_admin_url=None,
            keycloak_console_base_url=None,
            wifi_ssid="Test",
            wifi_password="Test",
            rotation_cron=None,
            rotation_timeout_seconds=300,
            rotation_critical_threshold_days=None,
            elasticsearch_url=None,
            elasticsearch_username=None,
            elasticsearch_password=None,
            elasticsearch_index_pattern="logstash-http-*",
            mqtt_client_id="iotsupport-backend",
            fernet_key="test-key",
        )

        # Should not raise - development mode
        settings.validate_production_config()

    def test_validation_fails_for_default_secret_in_production(self, tmp_path: Path):
        """Validation fails if SECRET_KEY is the default in production."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        settings = Settings(
            secret_key="dev-secret-key-change-in-production",  # Default!
            flask_env="production",
            debug=False,
            database_url="postgresql://localhost/db",
            assets_dir=assets_dir,
            cors_origins=[],
            mqtt_url="mqtt://test:1883",
            device_mqtt_url="mqtt://test:1883",
            mqtt_username=None,
            mqtt_password=None,
            baseurl="https://iot.example.com",
            device_baseurl="https://iot.example.com",
            oidc_enabled=False,
            oidc_issuer_url=None,
            oidc_client_id=None,
            oidc_client_secret=None,
            oidc_scopes="openid",
            oidc_audience=None,
            oidc_clock_skew_seconds=30,
            oidc_cookie_name="access_token",
            oidc_cookie_secure=True,
            oidc_cookie_samesite="Lax",
            oidc_refresh_cookie_name="refresh_token",
            oidc_token_url="https://auth.example.com/token",
            keycloak_base_url="https://auth.example.com",
            keycloak_realm="iot",
            keycloak_admin_client_id="admin",
            keycloak_admin_client_secret="secret",
            keycloak_device_scope_name="iot-device-audience",
            keycloak_admin_url="https://auth.example.com/admin/realms/iot",
            keycloak_console_base_url="https://auth.example.com/console",
            wifi_ssid="TestNet",
            wifi_password="TestPass",
            rotation_cron="0 8 * * *",
            rotation_timeout_seconds=300,
            rotation_critical_threshold_days=7,
            elasticsearch_url=None,
            elasticsearch_username=None,
            elasticsearch_password=None,
            elasticsearch_index_pattern="logstash-http-*",
            mqtt_client_id="iotsupport-backend",
            fernet_key="explicit-fernet-key",
        )

        with pytest.raises(ConfigurationError) as exc_info:
            settings.validate_production_config()

        assert "SECRET_KEY must be set to a secure value" in str(exc_info.value)


class TestSettingsProperties:
    """Tests for Settings computed properties."""

    def test_sqlalchemy_properties(self, tmp_path: Path):
        """SQLAlchemy compatibility properties work correctly."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        settings = Settings(
            secret_key="test-secret",
            flask_env="testing",
            debug=True,
            database_url="postgresql://localhost/testdb",
            assets_dir=assets_dir,
            cors_origins=[],
            mqtt_url="mqtt://test:1883",
            device_mqtt_url="mqtt://test:1883",
            mqtt_username=None,
            mqtt_password=None,
            baseurl="http://localhost",
            device_baseurl="http://localhost",
            oidc_enabled=False,
            oidc_issuer_url=None,
            oidc_client_id=None,
            oidc_client_secret=None,
            oidc_scopes="openid",
            oidc_audience=None,
            oidc_clock_skew_seconds=30,
            oidc_cookie_name="access_token",
            oidc_cookie_secure=False,
            oidc_cookie_samesite="Lax",
            oidc_refresh_cookie_name="refresh_token",
            oidc_token_url=None,
            keycloak_base_url=None,
            keycloak_realm=None,
            keycloak_admin_client_id=None,
            keycloak_admin_client_secret=None,
            keycloak_device_scope_name="iot-device-audience",
            keycloak_admin_url=None,
            keycloak_console_base_url=None,
            wifi_ssid="Test",
            wifi_password="Test",
            rotation_cron=None,
            rotation_timeout_seconds=300,
            rotation_critical_threshold_days=None,
            elasticsearch_url=None,
            elasticsearch_username=None,
            elasticsearch_password=None,
            elasticsearch_index_pattern="logstash-http-*",
            mqtt_client_id="iotsupport-backend",
            fernet_key="test-fernet-key",
            sqlalchemy_engine_options={"pool_size": 10},
        )

        # Flask config DTO
        flask_config = settings.to_flask_config()
        assert flask_config.SQLALCHEMY_DATABASE_URI == "postgresql://localhost/testdb"
        assert flask_config.SQLALCHEMY_TRACK_MODIFICATIONS is False
        assert flask_config.SQLALCHEMY_ENGINE_OPTIONS == {"pool_size": 10}
