import logging
from functools import lru_cache
from typing import Optional, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Настройки приложения с валидацией через Pydantic
    Следует принципу Single Responsibility - только управление конфигурацией
    """

    # === Основные настройки приложения ===
    app_name: str = Field(default="News Scraper API", description="Название приложения")
    app_version: str = Field(default="1.0.0", description="Версия приложения")
    debug: bool = Field(default=False, description="Режим отладки")
    environment: str = Field(default="development", description="Окружение")

    # === Настройки API ===
    api_host: str = Field(default="0.0.0.0", description="Хост API")
    api_port: int = Field(default=8000, ge=1, le=65535, description="Порт API")
    api_prefix: str = Field(default="/api/v1", description="Префикс API")

    # === Настройки MongoDB ===
    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        description="URL подключения к MongoDB"
    )
    database_name: str = Field(
        default="news_scraper",
        description="Название базы данных"
    )
    mongodb_max_connections: int = Field(default=100, ge=1, description="Максимум подключений к MongoDB")
    mongodb_timeout: int = Field(default=30, ge=1, description="Таймаут подключения к MongoDB (сек)")

    # === Настройки парсинга ===
    default_timeout: int = Field(default=30, ge=5, le=300, description="Таймаут по умолчанию")
    default_count_limit: int = Field(default=1000, ge=1, le=1000, description="Лимит офферов по умолчанию")
    default_sort: str = Field(default="price", description="Сортировка по умолчанию")

    # Допустимые сайты для парсинга
    allowed_domains: List[str] = Field(
        default=["hotline.ua"],
        description="Разрешенные домены для парсинга"
    )

    # === Настройки кэширования ===
    cache_ttl_minutes: int = Field(default=60, ge=1, description="TTL кэша в минутах")
    enable_cache: bool = Field(default=True, description="Включить кэширование")

    # === Настройки логирования ===
    log_level: str = Field(default="INFO", description="Уровень логирования")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Формат логов"
    )

    # === Настройки безопасности ===
    cors_origins: List[str] = Field(
        default=["*"],
        description="Разрешенные CORS origins"
    )
    cors_methods: List[str] = Field(
        default=["GET", "POST", "PUT", "DELETE"],
        description="Разрешенные CORS методы"
    )

    # === Rate Limiting ===
    rate_limit_requests: int = Field(default=100, ge=1, description="Запросов в минуту")
    rate_limit_window: int = Field(default=60, ge=1, description="Окно rate limiting (сек)")
    
    # === Authentication ===
    disable_auth: bool = Field(default=False, description="Отключить аутентификацию (только для разработки)")
    auth_enabled: bool = Field(default=True, description="Включить API key аутентификацию")

    # === Настройки HTTP клиента ===
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        description="User-Agent для запросов"
    )
    max_retries: int = Field(default=3, ge=0, le=10, description="Максимум повторов запросов")
    retry_delay: float = Field(default=1.0, ge=0.1, description="Задержка между повторами (сек)")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="",
        extra="ignore"
    )

    @field_validator('environment')
    def validate_environment(cls, v):
        allowed = ['development', 'staging', 'production']
        if v not in allowed:
            raise ValueError(f'environment должен быть одним из: {allowed}')
        return v

    @field_validator('log_level')
    def validate_log_level(cls, v):
        levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in levels:
            raise ValueError(f'log_level должен быть одним из: {levels}')
        return v.upper()

    @field_validator('default_sort')
    def validate_default_sort(cls, v):
        allowed = ['price', 'price_desc', 'shop', 'shop_desc']
        if v not in allowed:
            raise ValueError(f'default_sort должен быть одним из: {allowed}')
        return v

    @field_validator('mongodb_url')
    def validate_mongodb_url(cls, v):
        if not v.startswith(('mongodb://', 'mongodb+srv://')):
            raise ValueError('mongodb_url должен начинаться с mongodb:// или mongodb+srv://')
        return v


@lru_cache()
def get_settings() -> Settings:
    """
    Возвращает кэшированный экземпляр настроек
    Использует lru_cache для производительности

    Returns:
        Settings: Экземпляр настроек приложения
    """
    return Settings()


def setup_logging(settings: Optional[Settings] = None) -> None:
    """
    Настраивает логирование приложения

    Args:
        settings: Настройки приложения (необязательно)
    """
    if settings is None:
        settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format=settings.log_format,
        handlers=[
            logging.StreamHandler(),
        ]
    )

    # Настройка уровня логирования для внешних библиотек
    logging.getLogger("motor").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    if settings.debug:
        logging.getLogger().setLevel(logging.DEBUG)


def is_production() -> bool:
    """
    Проверяет, запущено ли приложение в продакшене

    Returns:
        bool: True если production окружение
    """
    return get_settings().environment == "production"


def is_debug() -> bool:
    """
    Проверяет, включен ли режим отладки

    Returns:
        bool: True если отладка включена
    """
    settings = get_settings()
    return settings.debug or settings.environment == "development"
