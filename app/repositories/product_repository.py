import logging
from typing import Optional
from datetime import datetime, UTC
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