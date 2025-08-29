import logging
from typing import Optional, List
from datetime import datetime, timedelta, UTC
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from functools import lru_cache

from app.models.news import NewsCollection, NewsItem
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

    async def get_news_by_source(
        self,
        source: str,
        limit: int = 50,
        offset: int = 0
    ) -> NewsCollection:
        """
        Получает новости по источнику
        
        Args:
            source: URL источника
            limit: Максимальное количество статей
            offset: Смещение для пагинации
            
        Returns:
            NewsCollection: Коллекция новостей
        """
        try:
            collection = await self._get_collection()

            # Получаем последнюю коллекцию для данного источника
            document = await collection.find_one(
                {"source": source},
                sort=[("parsed_at", -1)]
            )

            if document:
                document.pop('_id', None)
                news_collection = NewsCollection.model_validate(document)
                
                # Применяем пагинацию
                if offset > 0 or limit < len(news_collection.items):
                    news_collection.items = news_collection.items[offset:offset + limit]
                    news_collection.total_items = len(news_collection.items)
                
                return news_collection

            # Если ничего не найдено, возвращаем пустую коллекцию
            return NewsCollection(
                source=source,
                items=[],
                total_items=0,
                parse_status="not_found"
            )

        except Exception as e:
            self.logger.error(f"Ошибка получения новостей для источника {source}: {str(e)}")
            return NewsCollection(
                source=source,
                items=[],
                total_items=0,
                parse_status="error",
                error_message=str(e)
            )

    async def get_news_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> NewsCollection:
        """
        Получает новости за период времени
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            source: Опциональный фильтр по источнику
            limit: Максимальное количество статей
            offset: Смещение для пагинации
            
        Returns:
            NewsCollection: Коллекция новостей за период
        """
        try:
            collection = await self._get_collection()

            # Формируем фильтр
            filter_query = {
                "parsed_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            
            if source:
                filter_query["source"] = source

            cursor = collection.find(filter_query).sort("parsed_at", -1)

            all_items = []
            combined_source = source or "multiple_sources"

            async for document in cursor:
                document.pop('_id', None)
                try:
                    news_collection = NewsCollection.model_validate(document)
                    all_items.extend(news_collection.items)
                except Exception as e:
                    self.logger.warning(f"Ошибка валидации коллекции новостей: {str(e)}")
                    continue

            # Применяем пагинацию
            total_items = len(all_items)
            paginated_items = all_items[offset:offset + limit]

            return NewsCollection(
                source=combined_source,
                items=paginated_items,
                total_items=total_items,
                parse_status="success" if total_items > 0 else "no_data"
            )

        except Exception as e:
            self.logger.error(f"Ошибка получения новостей по дате: {str(e)}")
            return NewsCollection(
                source=source or "multiple_sources",
                items=[],
                total_items=0,
                parse_status="error",
                error_message=str(e)
            )

    async def search_news(
        self,
        query: str,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> NewsCollection:
        """
        Поиск новостей по тексту
        
        Args:
            query: Поисковый запрос
            source: Опциональный фильтр по источнику
            limit: Максимальное количество статей
            offset: Смещение для пагинации
            
        Returns:
            NewsCollection: Результаты поиска
        """
        try:
            collection = await self._get_collection()

            # Формируем фильтр для поиска
            search_filter = {
                "$or": [
                    {"items.article_data.title": {"$regex": query, "$options": "i"}},
                    {"items.article_data.content_body": {"$regex": query, "$options": "i"}},
                    {"items.article_data.author": {"$regex": query, "$options": "i"}}
                ]
            }
            
            if source:
                search_filter["source"] = source

            cursor = collection.find(search_filter).sort("parsed_at", -1)

            all_items = []
            combined_source = source or "search_results"

            async for document in cursor:
                document.pop('_id', None)
                try:
                    news_collection = NewsCollection.model_validate(document)
                    # Фильтруем элементы внутри коллекции по поисковому запросу
                    filtered_items = [
                        item for item in news_collection.items
                        if query.lower() in item.article_data.title.lower() or
                           query.lower() in item.article_data.content_body.lower() or
                           (item.article_data.author and query.lower() in item.article_data.author.lower())
                    ]
                    all_items.extend(filtered_items)
                except Exception as e:
                    self.logger.warning(f"Ошибка валидации при поиске: {str(e)}")
                    continue

            # Применяем пагинацию
            total_items = len(all_items)
            paginated_items = all_items[offset:offset + limit]

            return NewsCollection(
                source=combined_source,
                items=paginated_items,
                total_items=total_items,
                parse_status="success" if total_items > 0 else "no_results"
            )

        except Exception as e:
            self.logger.error(f"Ошибка поиска новостей: {str(e)}")
            return NewsCollection(
                source=source or "search_results",
                items=[],
                total_items=0,
                parse_status="error",
                error_message=str(e)
            )

    async def get_statistics(self) -> dict:
        """
        Получает статистику по новостям
        
        Returns:
            dict: Статистика по новостям
        """
        try:
            collection = await self._get_collection()

            total_collections = await collection.count_documents({})

            last_24h = datetime.now(UTC) - timedelta(hours=24)
            recent_collections = await collection.count_documents({
                "parsed_at": {"$gte": last_24h}
            })

            # Агрегация для подсчета общего количества статей
            pipeline = [
                {"$project": {
                    "source": 1,
                    "total_items": 1,
                    "parsed_at": 1,
                    "items_count": {"$size": "$items"}
                }},
                {"$group": {
                    "_id": None,
                    "total_articles": {"$sum": "$items_count"},
                    "avg_articles_per_collection": {"$avg": "$items_count"},
                    "max_articles_per_collection": {"$max": "$items_count"},
                    "sources": {"$addToSet": "$source"}
                }}
            ]

            agg_result = await collection.aggregate(pipeline).to_list(1)
            stats = agg_result[0] if agg_result else {}

            return {
                "total_collections": total_collections,
                "recent_collections_24h": recent_collections,
                "total_articles": stats.get("total_articles", 0),
                "avg_articles_per_collection": round(stats.get("avg_articles_per_collection", 0), 2),
                "max_articles_per_collection": stats.get("max_articles_per_collection", 0),
                "unique_sources": len(stats.get("sources", [])),
                "sources": stats.get("sources", [])
            }

        except Exception as e:
            self.logger.error(f"Ошибка получения статистики новостей: {str(e)}")
            return {}

    async def cleanup_old_news(self, days: int = 30) -> int:
        """
        Удаляет старые новости (старше указанного количества дней)
        
        Args:
            days: Количество дней для хранения
            
        Returns:
            int: Количество удаленных коллекций
        """
        try:
            collection = await self._get_collection()

            cutoff_date = datetime.now(UTC) - timedelta(days=days)

            result = await collection.delete_many({
                "parsed_at": {"$lt": cutoff_date}
            })

            deleted_count = result.deleted_count
            if deleted_count > 0:
                self.logger.info(f"Удалено {deleted_count} старых коллекций новостей (старше {days} дней)")

            return deleted_count

        except Exception as e:
            self.logger.error(f"Ошибка очистки старых новостей: {str(e)}")
            return 0

    async def get_recent_news(self, hours: int = 24, limit: int = 50) -> List[NewsCollection]:
        """
        Получает недавно спарсенные новости
        
        Args:
            hours: Количество часов назад
            limit: Максимальное количество коллекций
            
        Returns:
            List[NewsCollection]: Список недавних коллекций новостей
        """
        try:
            collection = await self._get_collection()

            start_date = datetime.now(UTC) - timedelta(hours=hours)

            cursor = collection.find({
                "parsed_at": {"$gte": start_date}
            }).sort("parsed_at", -1).limit(limit)

            news_collections = []
            async for document in cursor:
                document.pop('_id', None)
                try:
                    news_collection = NewsCollection.model_validate(document)
                    news_collections.append(news_collection)
                except Exception as e:
                    self.logger.warning(f"Ошибка валидации новостей: {str(e)}")
                    continue

            return news_collections

        except Exception as e:
            self.logger.error(f"Ошибка получения недавних новостей: {str(e)}")
            return []


@lru_cache()
def get_news_repository() -> NewsRepository:
    """
    Фабрика для создания экземпляра NewsRepository
    """
    return NewsRepository()
