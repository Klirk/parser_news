import logging
from typing import Optional
from datetime import datetime, timedelta, UTC
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from functools import lru_cache

from app.models.news import NewsCollection
from app.database import get_database


class NewsRepository:
    """
    Репозиторий для работы с новостями в MongoDB
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._collection: Optional[AsyncIOMotorCollection] = None

    async def _get_collection(self) -> AsyncIOMotorCollection:
        """Получает коллекцию новостей, инициализируя подключение при необходимости"""
        if self._collection is None:
            self._db = await get_database()
            self._collection = self._db.news
        return self._collection

    async def save_news_collection(self, news_collection: NewsCollection) -> Optional[str]:
        """
        Сохраняет коллекцию новостей в базе данных
        
        Args:
            news_collection: Коллекция новостей для сохранения
            
        Returns:
            str: ID сохраненного документа или None при ошибке
        """
        try:
            collection = await self._get_collection()

            collection_dict = news_collection.model_dump()
            collection_dict['parsed_at'] = datetime.now(UTC)

            # Сохраняем коллекцию как один документ
            result = await collection.replace_one(
                {
                    "source": news_collection.source,
                    "parsed_at": {
                        "$gte": datetime.now(UTC) - timedelta(hours=1)  # За последний час
                    }
                },
                collection_dict,
                upsert=True
            )

            if result.upserted_id:
                self.logger.info(f"Создана новая коллекция новостей: {news_collection.source}")
                return str(result.upserted_id)
            elif result.modified_count > 0:
                self.logger.info(f"Обновлена коллекция новостей: {news_collection.source}")
                existing = await collection.find_one({"source": news_collection.source}, {"_id": 1})
                return str(existing["_id"]) if existing else None
            else:
                # Если нет изменений, сохраняем как новую запись
                result = await collection.insert_one(collection_dict)
                self.logger.info(f"Добавлена новая коллекция новостей: {news_collection.source}")
                return str(result.inserted_id)

        except Exception as e:
            self.logger.error(f"Ошибка сохранения коллекции новостей {news_collection.source}: {str(e)}")
            raise

@lru_cache()
def get_news_repository() -> NewsRepository:
    """
    Фабрика для создания экземпляра NewsRepository
    """
    return NewsRepository()
