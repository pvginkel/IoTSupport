"""Dependency injection container for services."""

from dependency_injector import containers, providers
from sqlalchemy.orm import sessionmaker

from app.app_config import AppSettings
from app.config import Settings
from app.services.auth_service import AuthService
from app.services.cas_image_service import CasImageService
from app.services.coredump_service import CoredumpService
from app.services.device_model_service import DeviceModelService
from app.services.device_service import DeviceService
from app.services.elasticsearch_service import ElasticsearchService
from app.services.firmware_service import FirmwareService
from app.services.frontend_version_service import FrontendVersionService
from app.services.health_service import HealthService
from app.services.image_proxy_service import ImageProxyService
from app.services.keycloak_admin_service import KeycloakAdminService
from app.services.logsink_service import LogSinkService
from app.services.metrics_service import MetricsService
from app.services.mqtt_service import MqttService
from app.services.oidc_client_service import OidcClientService
from app.services.rotation_service import RotationService
from app.services.s3_service import S3Service
from app.services.settings_service import SettingsService
from app.services.sse_connection_manager import SSEConnectionManager
from app.services.task_service import TaskService
from app.services.test_data_service import TestDataService
from app.services.testing_service import TestingService
from app.utils.lifecycle_coordinator import LifecycleCoordinator
from app.utils.temp_file_manager import TempFileManager


class ServiceContainer(containers.DeclarativeContainer):
    """Container for service dependency injection."""

    # Configuration providers
    config = providers.Dependency(instance_of=Settings)
    app_config = providers.Dependency(instance_of=AppSettings)
    session_maker = providers.Dependency(instance_of=sessionmaker)
    db_session = providers.ContextLocalSingleton(
        session_maker.provided.call()
    )

    # S3 storage services
    s3_service = providers.Factory(S3Service, settings=config)
    cas_image_service = providers.Factory(
        CasImageService,
        s3_service=s3_service,
        app_settings=app_config,
    )

    # Lifecycle coordinator - manages startup and graceful shutdown
    lifecycle_coordinator = providers.Singleton(
        LifecycleCoordinator,
        graceful_shutdown_timeout=config.provided.graceful_shutdown_timeout,
    )

    # Health service - callback registry for health checks
    health_service = providers.Singleton(
        HealthService,
        lifecycle_coordinator=lifecycle_coordinator,
        settings=config,
    )

    # Temp file manager
    temp_file_manager = providers.Singleton(
        TempFileManager,
        lifecycle_coordinator=lifecycle_coordinator,
    )

    # Metrics service - background thread for Prometheus metrics
    metrics_service = providers.Singleton(
        MetricsService,
        container=providers.Self(),
        lifecycle_coordinator=lifecycle_coordinator,
    )

    # Auth services - OIDC authentication
    auth_service = providers.Singleton(AuthService, config=config)
    oidc_client_service = providers.Singleton(OidcClientService, config=config)

    # Testing service - Singleton for test session management
    testing_service = providers.Singleton(TestingService)

    # SSE connection manager (always included - TaskService depends on it)
    sse_connection_manager = providers.Singleton(
        SSEConnectionManager,
        gateway_url=config.provided.sse_gateway_url,
        http_timeout=2.0,
    )

    # Task service - in-memory task management
    task_service = providers.Singleton(
        TaskService,
        lifecycle_coordinator=lifecycle_coordinator,
        sse_connection_manager=sse_connection_manager,
        max_workers=config.provided.task_max_workers,
        task_timeout=config.provided.task_timeout_seconds,
        cleanup_interval=config.provided.task_cleanup_interval_seconds,
    )

    # Frontend version service - SSE version notifications
    frontend_version_service = providers.Singleton(
        FrontendVersionService,
        settings=config,
        lifecycle_coordinator=lifecycle_coordinator,
        sse_connection_manager=sse_connection_manager,
    )

    # --- IoT-specific services ---

    # MqttService - Singleton to maintain persistent MQTT connection
    mqtt_service = providers.Singleton(
        MqttService,
        config=app_config,
        flask_env=config.provided.flask_env,
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

    # KeycloakAdminService - Singleton for admin API access
    keycloak_admin_service = providers.Singleton(
        KeycloakAdminService,
        config=app_config,
        metrics_service=metrics_service,
    )

    # ElasticsearchService - Singleton for device log queries
    elasticsearch_service = providers.Singleton(
        ElasticsearchService,
        config=app_config,
        metrics_service=metrics_service,
    )

    # LogSinkService - Singleton for MQTT log ingestion to Elasticsearch
    logsink_service = providers.Singleton(
        LogSinkService,
        config=app_config,
        mqtt_service=mqtt_service,
        lifecycle_coordinator=lifecycle_coordinator,
    )

    # FirmwareService - Factory for firmware management via S3 + DB
    firmware_service = providers.Factory(
        FirmwareService,
        db=db_session,
        s3_service=s3_service,
        max_firmwares=app_config.provided.max_firmwares,
    )

    # CoredumpService - Singleton for coredump S3 storage + DB tracking + parsing
    coredump_service = providers.Singleton(
        CoredumpService,
        s3_service=s3_service,
        config=app_config,
        metrics_service=metrics_service,
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
        config=app_config,
        device_model_service=device_model_service,
        keycloak_admin_service=keycloak_admin_service,
        mqtt_service=mqtt_service,
    )

    # RotationService - Factory creates new instance per request with database session
    rotation_service = providers.Factory(
        RotationService,
        db=db_session,
        config=app_config,
        device_service=device_service,
        keycloak_admin_service=keycloak_admin_service,
        mqtt_service=mqtt_service,
        metrics_service=metrics_service,
    )
