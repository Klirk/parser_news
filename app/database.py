import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure

from app.config import get_settings


class DatabaseManager:
    """
    Менеджер подключения к MongoDB
    Следует принципу Singleton для управления подключением к БД
    """

    _instance: Optional['DatabaseManager'] = None
    _client: Optional[AsyncIOMotorClient] = None
    _database: Optional[AsyncIOMotorDatabase] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.logger = logging.getLogger(__name__)
            self.settings = get_settings()
            self._initialized = True

    async def connect(self) -> None:
        """
        Устанавливает подключение к MongoDB
        """
        try:
            if self._client is None:
                self.logger.info("Подключение к MongoDB...")

                # Если в URL есть аутентификация, используем authSource
                auth_params = {}
                if "@" in self.settings.mongodb_url:
                    auth_params["authSource"] = "admin"

                self._client = AsyncIOMotorClient(
                    self.settings.mongodb_url,
                    serverSelectionTimeoutMS=5000,  # 5 секунд таймаут
                    connectTimeoutMS=10000,  # 10 секунд таймаут подключения
                    socketTimeoutMS=20000,   # 20 секунд таймаут сокета
                    maxPoolSize=100,         # Максимум 100 подключений в пуле
                    minPoolSize=10,          # Минимум 10 подключений в пуле
                    maxIdleTimeMS=30000,     # 30 секунд перед закрытием неактивного соединения
                    **auth_params
                )

                # Проверяем подключение
                await self._client.admin.command('ping')

                self._database = self._client[self.settings.database_name]

                # Создаем индексы
                await self._create_indexes()

                self.logger.info(f"Успешно подключились к MongoDB: {self.settings.database_name}")

        except ConnectionFailure as e:
            self.logger.error(f"Ошибка подключения к MongoDB: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при подключении к MongoDB: {str(e)}")
            raise

    async def disconnect(self) -> None:
        """
        Закрывает подключение к MongoDB
        """
        if self._client:
            self.logger.info("Закрытие подключения к MongoDB...")
            self._client.close()
            self._client = None
            self._database = None
            self.logger.info("Подключение к MongoDB закрыто")

    async def get_database(self) -> AsyncIOMotorDatabase:
        """
        Возвращает объект базы данных

        Returns:
            AsyncIOMotorDatabase: Объект базы данных

        Raises:
            RuntimeError: Если подключение не установлено
        """
        if self._database is None:
            await self.connect()

        if self._database is None:
            raise RuntimeError("Не удалось установить подключение к базе данных")

        return self._database

    async def _create_indexes(self) -> None:
        """
        Создает необходимые индексы для коллекций
        """
        try:
            products_collection = self._database.products

            # Индекс для поиска по URL (уникальный)
            await products_collection.create_index("url", unique=True)

            # Индекс для поиска по времени парсинга
            await products_collection.create_index("parsed_at")

            # Индекс для поиска по количеству офферов
            await products_collection.create_index("total_offers")

            # Составной индекс для эффективного поиска
            await products_collection.create_index([
                ("parsed_at", -1),
                ("total_offers", -1)
            ])

            self.logger.info("Индексы MongoDB созданы успешно")

        except Exception as e:
            self.logger.warning(f"Ошибка создания индексов: {str(e)}")

    async def health_check(self) -> dict:
        """
        Проверяет состояние подключения к БД

        Returns:
            dict: Статус подключения
        """
        try:
            if self._database is None:
                return {"status": "disconnected", "details": "No database connection"}

            # Простая команда для проверки подключения
            result = await self._client.admin.command('ping')

            # Получаем статистику БД
            stats = await self._database.command("dbStats")

            return {
                "status": "connected",
                "database": self.settings.database_name,
                "ping": result.get("ok", 0) == 1,
                "collections": stats.get("collections", 0),
                "data_size": stats.get("dataSize", 0),
                "storage_size": stats.get("storageSize", 0)
            }

        except Exception as e:
            return {
                "status": "error",
                "details": str(e)
            }


# Глобальный экземпляр менеджера БД
db_manager = DatabaseManager()


async def get_database() -> AsyncIOMotorDatabase:
    """
    Фабричная функция для получения подключения к БД

    Returns:
        AsyncIOMotorDatabase: Объект базы данных
    """
    return await db_manager.get_database()


async def init_db() -> None:
    """
    Инициализирует подключение к базе данных
    Используется при старте приложения
    """
    await db_manager.connect()


async def close_db() -> None:
    """
    Закрывает подключение к базе данных
    Используется при завершении приложения
    """
    await db_manager.disconnect()
