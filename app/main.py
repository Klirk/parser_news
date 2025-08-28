import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings, setup_logging
from app.database import init_db, close_db
from app.api.v1.endpoints import products, news
from app.middleware import setup_error_handlers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Обработка жизненного цикла приложения
    """
    settings = get_settings()

    # Настройка логирования
    setup_logging(settings)
    logger = logging.getLogger(__name__)

    try:
        # Инициализация базы данных
        logger.info("Инициализация подключения к базе данных...")
        await init_db()
        logger.info("База данных инициализирована успешно")

        yield

    except Exception as e:
        logger.error(f"Ошибка инициализации приложения: {str(e)}")
        raise
    finally:
        logger.info("Закрытие подключений...")
        await close_db()
        logger.info("Приложение завершено")


def create_app() -> FastAPI:
    """
    Фабрика для создания экземпляра FastAPI приложения
    """
    settings = get_settings()

    fastapi_app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Асинхронный сервис для парсинга продуктов и новостей",
        lifespan=lifespan,
        debug=settings.debug,
        docs_url="/docs" if not settings.environment == "production" else None,
        redoc_url="/redoc" if not settings.environment == "production" else None,
    )

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=settings.cors_methods,
        allow_headers=["*"],
    )

    fastapi_app.include_router(
        products.router,
        prefix=f"{settings.api_prefix}/product",
        tags=["products"]
    )

    fastapi_app.include_router(
        news.router,
        prefix=f"{settings.api_prefix}/news",
        tags=["news"]
    )

    setup_error_handlers(fastapi_app)

    @fastapi_app.get("/")
    async def root():
        """Корневой эндпоинт"""
        return {
            "message": "News Scraper API",
            "version": settings.app_version,
            "environment": settings.environment
        }

    @fastapi_app.get("/health")
    async def health_check():
        """Проверка здоровья приложения"""
        from app.database import db_manager

        db_status = await db_manager.health_check()

        return {
            "status": "ok",
            "version": settings.app_version,
            "environment": settings.environment,
            "database": db_status
        }

    return fastapi_app


# Создание экземпляра приложения
app = create_app()

if __name__ == "__main__":
    import uvicorn

    app_settings = get_settings()

    uvicorn.run(
        "app.main:app",
        host=app_settings.api_host,
        port=app_settings.api_port,
        reload=app_settings.debug,
        log_level=app_settings.log_level.lower(),
        access_log=True,
    )
