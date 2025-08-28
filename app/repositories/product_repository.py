import logging
from typing import Optional, List
from datetime import datetime, timedelta, UTC
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection

from app.models.product import Product
from app.database import get_database


class ProductRepository:
    """
    Репозиторий для работы с продуктами в MongoDB
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._collection: Optional[AsyncIOMotorCollection] = None

    async def _get_collection(self) -> AsyncIOMotorCollection:
        """Получает коллекцию продуктов, инициализируя подключение при необходимости"""
        if self._collection is None:
            self._db = await get_database()
            self._collection = self._db.products
        return self._collection

    async def save_product(self, product: Product) -> Optional[str]:
        """
        Сохраняет продукт в базе данных
        
        Args:
            product: Объект продукта для сохранения
            
        Returns:
            str: ID сохраненного документа или None при ошибке
            
        Raises:
            Exception: При ошибках сохранения
        """
        try:
            collection = await self._get_collection()

            product_dict = product.model_dump()

            product_dict['parsed_at'] = datetime.now(UTC)
            product_dict['total_offers'] = len(product.offers)

            result = await collection.replace_one(
                {"url": product.url},
                product_dict,
                upsert=True
            )
            
            if result.upserted_id:
                self.logger.info(f"Создан новый продукт: {product.url}")
                return str(result.upserted_id)
            elif result.modified_count > 0:
                self.logger.info(f"Обновлен существующий продукт: {product.url}")
                existing = await collection.find_one({"url": product.url}, {"_id": 1})
                return str(existing["_id"]) if existing else None
            else:
                self.logger.warning(f"Продукт не был изменен: {product.url}")
                return None
                
        except Exception as e:
            self.logger.error(f"Ошибка сохранения продукта {product.url}: {str(e)}")
            raise

    async def get_product_by_url(self, url: str) -> Optional[Product]:
        """
        Получает продукт по URL
        
        Args:
            url: URL продукта
            
        Returns:
            Product: Объект продукта или None если не найден
        """
        try:
            collection = await self._get_collection()
            
            document = await collection.find_one({"url": url})
            
            if document:
                document.pop('_id', None)
                return Product.model_validate(document)
                
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка получения продукта {url}: {str(e)}")
            return None

    async def get_products_by_date_range(
        self, 
        start_date: datetime, 
        end_date: datetime,
        limit: int = 100
    ) -> List[Product]:
        """
        Получает продукты в заданном диапазоне дат
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            limit: Максимальное количество продуктов
            
        Returns:
            List[Product]: Список продуктов
        """
        try:
            collection = await self._get_collection()
            
            cursor = collection.find({
                "parsed_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }).sort("parsed_at", -1).limit(limit)
            
            products = []
            async for document in cursor:
                document.pop('_id', None)
                try:
                    product = Product.model_validate(document)
                    products.append(product)
                except Exception as e:
                    self.logger.warning(f"Ошибка валидации продукта: {str(e)}")
                    continue
                    
            return products
            
        except Exception as e:
            self.logger.error(f"Ошибка получения продуктов по датам: {str(e)}")
            return []

    async def get_recent_products(self, hours: int = 24, limit: int = 50) -> List[Product]:
        """
        Получает недавно спарсенные продукты
        
        Args:
            hours: Количество часов назад
            limit: Максимальное количество продуктов
            
        Returns:
            List[Product]: Список недавних продуктов
        """
        start_date = datetime.now(UTC) - timedelta(hours=hours)
        end_date = datetime.now(UTC)
        
        return await self.get_products_by_date_range(start_date, end_date, limit)

    async def delete_product_by_url(self, url: str) -> bool:
        """
        Удаляет продукт по URL
        
        Args:
            url: URL продукта
            
        Returns:
            bool: True если продукт был удален
        """
        try:
            collection = await self._get_collection()
            
            result = await collection.delete_one({"url": url})
            
            if result.deleted_count > 0:
                self.logger.info(f"Удален продукт: {url}")
                return True
            else:
                self.logger.warning(f"Продукт не найден для удаления: {url}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка удаления продукта {url}: {str(e)}")
            return False

    async def get_product_stats(self) -> dict:
        """
        Получает статистику по продуктам
        
        Returns:
            dict: Статистика по продуктам
        """
        try:
            collection = await self._get_collection()

            total_count = await collection.count_documents({})

            last_24h = datetime.now(UTC) - timedelta(hours=24)
            recent_count = await collection.count_documents({
                "parsed_at": {"$gte": last_24h}
            })
            
            # Среднее количество офферов
            pipeline = [
                {"$group": {
                    "_id": None,
                    "avg_offers": {"$avg": "$total_offers"},
                    "max_offers": {"$max": "$total_offers"},
                    "min_offers": {"$min": "$total_offers"}
                }}
            ]
            
            agg_result = await collection.aggregate(pipeline).to_list(1)
            stats = agg_result[0] if agg_result else {}
            
            return {
                "total_products": total_count,
                "recent_products_24h": recent_count,
                "avg_offers_per_product": round(stats.get("avg_offers", 0), 2),
                "max_offers_per_product": stats.get("max_offers", 0),
                "min_offers_per_product": stats.get("min_offers", 0)
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики: {str(e)}")
            return {}

    async def cleanup_old_products(self, days: int = 7) -> int:
        """
        Удаляет старые продукты (старше указанного количества дней)
        
        Args:
            days: Количество дней для хранения
            
        Returns:
            int: Количество удаленных продуктов
        """
        try:
            collection = await self._get_collection()
            
            cutoff_date = datetime.now(UTC) - timedelta(days=days)
            
            result = await collection.delete_many({
                "parsed_at": {"$lt": cutoff_date}
            })
            
            deleted_count = result.deleted_count
            if deleted_count > 0:
                self.logger.info(f"Удалено {deleted_count} старых продуктов (старше {days} дней)")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Ошибка очистки старых продуктов: {str(e)}")
            return 0
