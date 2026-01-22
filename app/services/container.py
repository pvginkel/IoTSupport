"""Dependency injection container for services."""

from dependency_injector import containers, providers
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.services.asset_upload_service import AssetUploadService
from app.services.auth_service import AuthService
from app.services.config_service import ConfigService
from app.services.image_proxy_service import ImageProxyService
from app.services.metrics_service import MetricsService
from app.services.mqtt_service import MqttService
from app.services.oidc_client_service import OidcClientService
from app.services.test_data_service import TestDataService
from app.services.testing_service import TestingService


class ServiceContainer(containers.DeclarativeContainer):
    """Container for service dependency injection."""

    # Configuration provider - Singleton for app settings
    config = providers.Dependency(instance_of=Settings)

    # Database session providers
    session_maker = providers.Dependency(instance_of=sessionmaker)
    db_session = providers.ContextLocalSingleton(
        session_maker.provided.call()
    )

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

    # ConfigService - Factory creates new instance per request with database session
    config_service = providers.Factory(
        ConfigService,
        db=db_session,
    )

    # TestDataService - Factory creates new instance per request with database session
    test_data_service = providers.Factory(
        TestDataService,
        db=db_session,
    )

    # ImageProxyService - Factory creates new instance per request for thread safety
    image_proxy_service = providers.Factory(
        ImageProxyService,
        metrics_service=metrics_service,
    )

    # AuthService - Singleton to cache JWKS keys for performance
    auth_service = providers.Singleton(
        AuthService,
        config=config,
        metrics_service=metrics_service,
    )

    # OidcClientService - Singleton to cache OIDC endpoints
    oidc_client_service = providers.Singleton(
        OidcClientService,
        config=config,
        metrics_service=metrics_service,
    )

    # TestingService - Singleton for test session management
    testing_service = providers.Singleton(TestingService)
