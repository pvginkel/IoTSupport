"""Dependency injection container for services."""

from dependency_injector import containers, providers
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.services.auth_service import AuthService
from app.services.coredump_service import CoredumpService
from app.services.device_model_service import DeviceModelService
from app.services.device_service import DeviceService
from app.services.elasticsearch_service import ElasticsearchService
from app.services.firmware_service import FirmwareService
from app.services.image_proxy_service import ImageProxyService
from app.services.keycloak_admin_service import KeycloakAdminService
from app.services.logsink_service import LogSinkService
from app.services.metrics_service import MetricsService
from app.services.mqtt_service import MqttService
from app.services.oidc_client_service import OidcClientService
from app.services.rotation_service import RotationService
from app.services.settings_service import SettingsService
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
        config=config,
    )

    # TestDataService - Factory creates new instance per request with database session
    test_data_service = providers.Factory(
        TestDataService,
        db=db_session,
    )

    # SettingsService - Factory creates new instance per request with database session
    settings_service = providers.Factory(
        SettingsService,
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

    # KeycloakAdminService - Singleton for admin API access
    keycloak_admin_service = providers.Singleton(
        KeycloakAdminService,
        config=config,
        metrics_service=metrics_service,
    )

    # ElasticsearchService - Singleton for device log queries
    elasticsearch_service = providers.Singleton(
        ElasticsearchService,
        config=config,
        metrics_service=metrics_service,
    )

    # LogSinkService - Singleton for MQTT log ingestion to Elasticsearch
    logsink_service = providers.Singleton(
        LogSinkService,
        config=config,
        mqtt_service=mqtt_service,
    )

    # CoredumpService - Singleton for coredump file management
    coredump_service = providers.Singleton(
        CoredumpService,
        coredumps_dir=config.provided.coredumps_dir,
    )

    # FirmwareService - Singleton for firmware file management
    firmware_service = providers.Singleton(
        FirmwareService,
        assets_dir=config.provided.assets_dir,
    )

    # DeviceModelService - Factory creates new instance per request with database session
    device_model_service = providers.Factory(
        DeviceModelService,
        db=db_session,
        firmware_service=firmware_service,
        mqtt_service=mqtt_service,
    )

    # DeviceService - Factory creates new instance per request with database session
    device_service = providers.Factory(
        DeviceService,
        db=db_session,
        config=config,
        device_model_service=device_model_service,
        keycloak_admin_service=keycloak_admin_service,
        mqtt_service=mqtt_service,
    )

    # RotationService - Factory creates new instance per request with database session
    rotation_service = providers.Factory(
        RotationService,
        db=db_session,
        config=config,
        device_service=device_service,
        keycloak_admin_service=keycloak_admin_service,
        mqtt_service=mqtt_service,
        metrics_service=metrics_service,
    )
