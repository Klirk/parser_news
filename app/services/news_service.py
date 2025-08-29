from typing import Optional
from datetime import datetime
import logging
from functools import lru_cache

from app.models.news import NewsCollection
from app.repositories.news_repository import NewsRepository
from app.parsers.news_parsers.base_news_parser import BaseNewsParser
from app.parsers.news_parsers.pravda_parser import PravdaNewsParser
from app.parsers.news_parsers.epravda_parser import EpravdaNewsParser
from app.parsers.news_parsers.politeka_parser import PolitekaNewsParser


class NewsService:
    """
    Сервис для работы с новостями
    Реализует бизнес-логику парсинга и сохранения новостей
    """

    def __init__(self, news_repository: NewsRepository):
        self.news_repository = news_repository
        self.logger = logging.getLogger(self.__class__.__name__)

        self.parsers: dict[str, BaseNewsParser] = {
            'epravda.com.ua': EpravdaNewsParser(),
            'pravda.com.ua': PravdaNewsParser(),
            'politeka.net': PolitekaNewsParser()
        }

    async def parse_news(
            self,
            url: str,
            until_date: Optional[datetime] = None,
            client: str = "http"
    ) -> NewsCollection:
        """
        Парсит новости с указанного источника
        
        Args:
            url: URL источника новостей
            until_date: Самая старая дата для парсинга - парсинг идет от сегодня назад до этой даты включительно
            client: Тип клиента (http или browser)
            
        Returns:
            NewsCollection: Коллекция новостей
        """
        try:
            self.logger.info(f"Начинаем парсинг новостей: {url}")

            # Определяем парсер по URL
            parser = self._get_parser_for_url(url)
            if not parser:
                raise ValueError(f"Парсер для URL {url} не найден")

            # Парсим новости
            news_collection = await parser.parse_news(url, until_date, client)

            # Сохраняем в базу данных
            await self.news_repository.save_news_collection(news_collection)

            self.logger.info(f"Парсинг завершен. Найдено {news_collection.total_items} статей")
            return news_collection

        except Exception as e:
            self.logger.error(f"Ошибка парсинга новостей {url}: {str(e)}")
            raise

    def _get_parser_for_url(self, url: str) -> Optional[BaseNewsParser]:
        """
        Возвращает подходящий парсер для указанного URL
        
        Args:
            url: URL источника
            
        Returns:
            BaseNewsParser: Парсер для источника или None
        """
        url_lower = url.lower()

        # Сортируем домены по длине в убывающем порядке для более точного совпадения
        sorted_domains = sorted(self.parsers.items(), key=lambda x: len(x[0]), reverse=True)

        for domain, parser in sorted_domains:
            if domain in url_lower:
                self.logger.info(f"Выбран парсер {parser.__class__.__name__} для домена {domain}")
                return parser

        return None


@lru_cache()
def get_news_service() -> NewsService:
    """
    Фабрика для создания экземпляра NewsService
    """
    from app.repositories.news_repository import get_news_repository
    return NewsService(get_news_repository())
