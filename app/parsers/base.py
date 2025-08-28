from abc import ABC, abstractmethod
from typing import Optional
import logging

from app.models.product import Product


class BaseParser(ABC):
    """
    Базовый абстрактный класс для всех парсеров
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def parse_product(
        self,
        url: str,
        timeout_limit: int = 30,
        count_limit: Optional[int] = None,
        sort_by: str = "price"
    ) -> Product:
        """

        Args:
            url: URL страницы товара
            timeout_limit: Таймаут запроса в секундах
            count_limit: Максимальное количество офферов
            sort_by: Критерий сортировки офферов
            
        Returns:
            Product: Объект товара с офферами
            
        Raises:
            ValueError: При некорректных входных данных
            Exception: При ошибках парсинга
        """
        pass

    @staticmethod
    def _validate_url(url: str, domain: str) -> bool:
        """
        Валидирует URL для соответствующего домена

        Args:
            url: URL для валидации
            domain: Ожидаемый домен

        Returns:
            bool: True если URL валидный
        """
        if not url or not isinstance(url, str):
            return False

        if domain.lower() not in url.lower():
            return False

        return url.startswith('https://')

    @staticmethod
    def _validate_parameters(
            timeout_limit: int,
        count_limit: Optional[int],
        sort_by: str
    ) -> None:
        """
        Валидирует входные параметры
        
        Args:
            timeout_limit: Таймаут запроса
            count_limit: Лимит количества офферов  
            sort_by: Критерий сортировки
            
        Raises:
            ValueError: При некорректных параметрах
        """
        if not isinstance(timeout_limit, int) or timeout_limit < 5 or timeout_limit > 300:
            raise ValueError("timeout_limit должен быть между 5 и 300 секундами")

        if count_limit is not None:
            if not isinstance(count_limit, int) or count_limit < 1 or count_limit > 100:
                raise ValueError("count_limit должен быть между 1 и 100")

        valid_sorts = ["price", "price_desc", "shop", "shop_desc"]
        if sort_by not in valid_sorts:
            raise ValueError(f"sort_by должен быть одним из: {valid_sorts}")


class IProductParser(ABC):
    """
    Интерфейс для парсеров продуктов
    """

    @abstractmethod
    async def parse_product(
        self,
        url: str,
        timeout_limit: int = 30,
        count_limit: Optional[int] = None,
        sort_by: str = "price"
    ) -> Product:
        """Парсит продукт по URL"""
        pass


class INewsParser(ABC):
    """
    Интерфейс для парсеров новостей
    """

    @abstractmethod
    async def parse_news(self, url: str) -> dict:
        """Парсит новость по URL"""
        pass