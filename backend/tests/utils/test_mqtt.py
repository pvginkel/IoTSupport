"""Tests for MQTT utility functions."""

import pytest

from app.utils.mqtt import parse_mqtt_url


class TestParseMqttUrl:
    """Tests for parse_mqtt_url function."""

    def test_basic_mqtt_url(self):
        """Test parsing basic mqtt:// URL with explicit port."""
        host, port, use_tls = parse_mqtt_url("mqtt://broker.local:1883")
        assert host == "broker.local"
        assert port == 1883
        assert use_tls is False

    def test_mqtts_url(self):
        """Test parsing mqtts:// URL with explicit port."""
        host, port, use_tls = parse_mqtt_url("mqtts://broker.secure:8883")
        assert host == "broker.secure"
        assert port == 8883
        assert use_tls is True

    def test_mqtt_default_port(self):
        """Test mqtt:// URL uses default port 1883."""
        host, port, use_tls = parse_mqtt_url("mqtt://broker.local")
        assert host == "broker.local"
        assert port == 1883
        assert use_tls is False

    def test_mqtts_default_port(self):
        """Test mqtts:// URL uses default port 8883."""
        host, port, use_tls = parse_mqtt_url("mqtts://broker.secure")
        assert host == "broker.secure"
        assert port == 8883
        assert use_tls is True

    def test_url_with_path(self):
        """Test URL parsing strips trailing path components."""
        host, port, use_tls = parse_mqtt_url("mqtt://broker.local:1883/some/path")
        assert host == "broker.local"
        assert port == 1883
        assert use_tls is False

    def test_url_with_path_no_port(self):
        """Test URL parsing strips path when no port specified."""
        host, port, use_tls = parse_mqtt_url("mqtt://broker.local/some/path")
        assert host == "broker.local"
        assert port == 1883
        assert use_tls is False

    def test_invalid_scheme_raises(self):
        """Test that invalid URL scheme raises ValueError."""
        with pytest.raises(ValueError, match="Invalid MQTT URL scheme"):
            parse_mqtt_url("http://broker.local:1883")

    def test_https_scheme_raises(self):
        """Test that https:// scheme raises ValueError."""
        with pytest.raises(ValueError, match="Invalid MQTT URL scheme"):
            parse_mqtt_url("https://broker.local:8883")

    def test_custom_port(self):
        """Test parsing URL with non-standard port."""
        host, port, use_tls = parse_mqtt_url("mqtt://broker.local:9999")
        assert host == "broker.local"
        assert port == 9999
        assert use_tls is False

    def test_ip_address_host(self):
        """Test parsing URL with IP address as host."""
        host, port, use_tls = parse_mqtt_url("mqtt://192.168.1.100:1883")
        assert host == "192.168.1.100"
        assert port == 1883
        assert use_tls is False

    def test_localhost(self):
        """Test parsing URL with localhost."""
        host, port, use_tls = parse_mqtt_url("mqtt://localhost:1883")
        assert host == "localhost"
        assert port == 1883
        assert use_tls is False
