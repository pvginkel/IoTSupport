"""Dependency injection container for services."""

from dependency_injector import containers, providers

from app.config import Settings
from app.services.asset_upload_service import AssetUploadService
from app.services.config_service import ConfigService
from app.services.image_proxy_service import ImageProxyService
from app.services.metrics_service import MetricsService
from app.services.mqtt_service import MqttService


class ServiceContainer(containers.DeclarativeContainer):
    """Container for service dependency injection."""

    # Configuration provider - Singleton for app settings
    config = providers.Dependency(instance_of=Settings)

    # MetricsService - Singleton for app lifetime
    metrics_service = providers.Singleton(MetricsService)

    # MqttService - Singleton to maintain persistent MQTT connection
    mqtt_service = providers.Singleton(
        MqttService,
        mqtt_url=config.provided.MQTT_URL,
        mqtt_username=config.provided.MQTT_USERNAME,
        mqtt_password=config.provided.MQTT_PASSWORD,
    )

    # AssetUploadService - Singleton to cache RSA key for performance
    asset_upload_service = providers.Singleton(
        AssetUploadService,
        assets_dir=config.provided.ASSETS_DIR,
        signing_key_path=config.provided.SIGNING_KEY_PATH,
        timestamp_tolerance_seconds=config.provided.TIMESTAMP_TOLERANCE_SECONDS,
    )

    # ConfigService - Factory creates new instance per request for thread safety
    config_service = providers.Factory(
        ConfigService,
        config_dir=config.provided.ESP32_CONFIGS_DIR,
    )

    # ImageProxyService - Factory creates new instance per request for thread safety
    image_proxy_service = providers.Factory(
        ImageProxyService,
        metrics_service=metrics_service,
    )
