import logging
from typing import Optional, List
from datetime import datetime, UTC

from app.models.product import Product
from app.repositories.product_repository import ProductRepository
from app.parsers.product_parsers.hotline_parser import HotlineParser
from app.config import get_settings


class ProductService:
    """
    Сервисный слой для работы с продуктами
    Координирует взаимодействие между парсерами и репозиторием
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.settings = get_settings()
        self.repository = ProductRepository()
        self.hotline_parser = HotlineParser()

    async def parse_and_save_product(
        self,
        url: str,
        timeout_limit: int = 30,
        count_limit: Optional[int] = None,
        sort_by: str = "price"
    ) -> Product:
        """
        Парсит продукт и сохраняет его в базе данных
        
        Args:
            url: URL страницы товара
            timeout_limit: Таймаут запроса в секундах
            count_limit: Максимальное количество офферов
            sort_by: Критерий сортировки офферов
            
        Returns:
            Product: Спарсенный и сохраненный продукт
            
        Raises:
            ValueError: При некорректных входных данных
            Exception: При ошибках парсинга или сохранения
        """
        try:
            self.logger.info(f"Начинаем парсинг продукта: {url}")

            if not self._is_allowed_domain(url):
                raise ValueError(f"Домен не разрешен для парсинга: {url}")

            if timeout_limit is None:
                timeout_limit = self.settings.default_timeout
            if count_limit is None:
                count_limit = self.settings.default_count_limit
            if sort_by is None:
                sort_by = self.settings.default_sort

            if "hotline.ua" in url.lower():
                product = await self.hotline_parser.parse_product(
                    url=url,
                    timeout_limit=timeout_limit,
                    count_limit=count_limit,
                    sort_by=sort_by
                )
            else:
                raise ValueError(f"Парсер для данного URL не найден: {url}")

            await self.repository.save_product(product)
            
            self.logger.info(
                f"Продукт успешно спарсен и сохранен: {url}, "
                f"найдено {len(product.offers)} офферов"
            )
            
            return product
            
        except Exception as e:
            self.logger.error(f"Ошибка обработки продукта {url}: {str(e)}")
            raise

    async def get_product(self, url: str) -> Optional[Product]:
        """
        Получает продукт из базы данных по URL
        
        Args:
            url: URL продукта
            
        Returns:
            Product: Продукт или None если не найден
        """
        try:
            return await self.repository.get_product_by_url(url)
        except Exception as e:
            self.logger.error(f"Ошибка получения продукта {url}: {str(e)}")
            return None

    async def get_or_parse_product(
        self,
        url: str,
        timeout_limit: int = 30,
        count_limit: Optional[int] = None,
        sort_by: str = "price",
        force_refresh: bool = False
    ) -> Product:
        """
        Получает продукт из кэша или парсит заново
        
        Args:
            url: URL страницы товара
            timeout_limit: Таймаут запроса в секундах
            count_limit: Максимальное количество офферов
            sort_by: Критерий сортировки офферов
            force_refresh: Принудительно перепарсить (игнорировать кэш)
            
        Returns:
            Product: Продукт из кэша или свежеспарсенный
        """
        try:
            if not force_refresh:
                cached_product = await self.get_product(url)
                if cached_product and self._is_cache_valid(cached_product):
                    self.logger.info(f"Возвращаем продукт из кэша: {url}")
                    return cached_product

            self.logger.info(f"Парсим продукт заново: {url}")
            return await self.parse_and_save_product(
                url=url,
                timeout_limit=timeout_limit,
                count_limit=count_limit,
                sort_by=sort_by
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка получения/парсинга продукта {url}: {str(e)}")
            raise

    async def get_recent_products(self, hours: int = 24, limit: int = 50) -> List[Product]:
        """
        Получает недавно спарсенные продукты
        
        Args:
            hours: Количество часов назад
            limit: Максимальное количество продуктов
            
        Returns:
            List[Product]: Список недавних продуктов
        """
        try:
            return await self.repository.get_recent_products(hours, limit)
        except Exception as e:
            self.logger.error(f"Ошибка получения недавних продуктов: {str(e)}")
            return []

    async def get_product_statistics(self) -> dict:
        """
        Получает статистику по продуктам
        
        Returns:
            dict: Статистика по продуктам
        """
        try:
            return await self.repository.get_product_stats()
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики: {str(e)}")
            return {}

    async def cleanup_old_products(self, days: int = 7) -> int:
        """
        Удаляет старые продукты
        
        Args:
            days: Количество дней для хранения
            
        Returns:
            int: Количество удаленных продуктов
        """
        try:
            return await self.repository.cleanup_old_products(days)
        except Exception as e:
            self.logger.error(f"Ошибка очистки старых продуктов: {str(e)}")
            return 0

    def _is_allowed_domain(self, url: str) -> bool:
        """
        Проверяет, разрешен ли домен для парсинга
        
        Args:
            url: URL для проверки
            
        Returns:
            bool: True если домен разрешен
        """
        url_lower = url.lower()
        return any(domain in url_lower for domain in self.settings.allowed_domains)

    def _is_cache_valid(self, product: Product) -> bool:
        """
        Проверяет, валиден ли кэш продукта
        
        Args:
            product: Продукт для проверки
            
        Returns:
            bool: True если кэш валиден
        """
        if not self.settings.enable_cache:
            return False

        cache_age = datetime.now(UTC) - product.parsed_at
        max_age_minutes = self.settings.cache_ttl_minutes
        
        return cache_age.total_seconds() < (max_age_minutes * 60)

    async def refresh_product_cache(self, url: str) -> Optional[Product]:
        """
        Принудительно обновляет кэш продукта
        
        Args:
            url: URL продукта
            
        Returns:
            Product: Обновленный продукт или None при ошибке
        """
        try:
            return await self.get_or_parse_product(url, force_refresh=True)
        except Exception as e:
            self.logger.error(f"Ошибка обновления кэша продукта {url}: {str(e)}")
            return None

    async def delete_product(self, url: str) -> bool:
        """
        Удаляет продукт из базы данных
        
        Args:
            url: URL продукта
            
        Returns:
            bool: True если продукт был удален
        """
        try:
            return await self.repository.delete_product_by_url(url)
        except Exception as e:
            self.logger.error(f"Ошибка удаления продукта {url}: {str(e)}")
            return False


# Dependency injection для FastAPI
async def get_product_service() -> ProductService:
    """
    Dependency injection функция для получения сервиса продуктов
    
    Returns:
        ProductService: Экземпляр сервиса продуктов
    """
    return ProductService()
