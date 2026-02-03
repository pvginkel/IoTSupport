"""MQTT utility functions."""


def parse_mqtt_url(url: str) -> tuple[str, int, bool]:
    """Parse MQTT URL to extract host, port, and TLS settings.

    Args:
        url: MQTT URL (e.g., mqtt://localhost:1883, mqtts://broker:8883)

    Returns:
        Tuple of (host, port, use_tls)

    Raises:
        ValueError: If URL format is invalid
    """
    if url.startswith("mqtts://"):
        use_tls = True
        url_without_scheme = url[8:]
        default_port = 8883
    elif url.startswith("mqtt://"):
        use_tls = False
        url_without_scheme = url[7:]
        default_port = 1883
    else:
        raise ValueError(
            f"Invalid MQTT URL scheme. Expected mqtt:// or mqtts://, got: {url}"
        )

    # Split host and port
    if ":" in url_without_scheme:
        host, port_str = url_without_scheme.split(":", 1)
        # Remove any trailing path components
        port_str = port_str.split("/")[0]
        port = int(port_str)
    else:
        # Remove any trailing path components
        host = url_without_scheme.split("/")[0]
        port = default_port

    return (host, port, use_tls)
