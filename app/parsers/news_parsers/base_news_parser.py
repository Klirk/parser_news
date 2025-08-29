from abc import ABC, abstractmethod
from typing import List, Optional
import logging
import httpx
import asyncio
from datetime import datetime, timezone
from playwright.async_api import async_playwright
import re

from app.models.news import NewsCollection, ArticleData
from app.config import get_settings


class BaseNewsParser(ABC):
    """
    Базовый абстрактный класс для парсеров новостей
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.settings = get_settings()
        self.session_headers = {
            'User-Agent': self.settings.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'uk-UA,uk;q=0.9,en;q=0.8,ru;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }

    @abstractmethod
    async def parse_news(
        self,
        url: str,
        until_date: Optional[datetime] = None,
        client: str = "http"
    ) -> NewsCollection:
        """
        Абстрактный метод для парсинга новостей
        
        Args:
            url: URL категории новостей
            until_date: Граничная дата (не позднее)
            client: Тип клиента (http или browser)
            
        Returns:
            NewsCollection: Коллекция новостей
        """
        pass

    @abstractmethod
    def _extract_article_links(self, content: str, base_url: str) -> List[str]:
        """
        Извлекает ссылки на статьи из контента страницы
        
        Args:
            content: HTML контент страницы
            base_url: Базовый URL сайта
            
        Returns:
            List[str]: Список URL статей
        """
        pass

    @abstractmethod
    async def _parse_article(self, url: str, client: str = "http") -> Optional[ArticleData]:
        """
        Парсит отдельную статью
        
        Args:
            url: URL статьи
            client: Тип клиента
            
        Returns:
            ArticleData: Данные статьи или None при ошибке
        """
        pass

    async def _get_content_http(self, url: str, timeout: int = 30) -> Optional[str]:
        """
        Получает контент страницы через HTTP клиент
        
        Args:
            url: URL страницы
            timeout: Таймаут запроса
            
        Returns:
            str: HTML контент или None при ошибке
        """
        try:
            self.logger.info(f"HTTP: Получаем контент {url}")
            
            async with httpx.AsyncClient(
                timeout=timeout,
                headers=self.session_headers,
                follow_redirects=True
            ) as client:
                response = await client.get(url)
                
                self.logger.info(f"HTTP: Статус ответа {response.status_code} для {url}")
                
                if response.status_code == 403:
                    self.logger.warning(f"HTTP: Доступ запрещен (403) для {url}. Сайт может блокировать запросы")
                elif response.status_code == 429:
                    self.logger.warning(f"HTTP: Слишком много запросов (429) для {url}")
                elif response.status_code >= 400:
                    self.logger.warning(f"HTTP: Ошибка {response.status_code} для {url}")
                
                response.raise_for_status()
                content_length = len(response.text)
                self.logger.info(f"HTTP: Получен контент {content_length} символов для {url}")
                
                return response.text
                
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP: Ошибка статуса {e.response.status_code} для {url}: {str(e)}")
            return None
        except httpx.TimeoutException as e:
            self.logger.error(f"HTTP: Таймаут запроса для {url}: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"HTTP: Ошибка получения контента {url}: {str(e)}")
            return None

    async def _get_content_browser(self, url: str, timeout: int = 30) -> Optional[str]:
        """
        Получает контент страницы через браузер (Playwright)
        
        Args:
            url: URL страницы
            timeout: Таймаут загрузки
            
        Returns:
            str: HTML контент или None при ошибке
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
                
                try:
                    context = await browser.new_context(
                        user_agent=self.settings.user_agent,
                        locale='uk-UA'
                    )
                    
                    page = await context.new_page()
                    
                    # Устанавливаем таймаут
                    page.set_default_timeout(timeout * 1000)
                    
                    # Переходим на страницу
                    await page.goto(url, wait_until='domcontentloaded')
                    
                    # Ждем загрузки контента
                    await page.wait_for_timeout(2000)
                    
                    # Получаем контент
                    content = await page.content()
                    
                    return content
                    
                finally:
                    await browser.close()
                    
        except Exception as e:
            self.logger.error(f"Ошибка получения контента через браузер {url}: {str(e)}")
            return None

    async def _get_content(self, url: str, client: str = "http", timeout: int = 30) -> Optional[str]:
        """
        Получает контент страницы используя указанный клиент
        
        Args:
            url: URL страницы
            client: Тип клиента (http или browser)
            timeout: Таймаут
            
        Returns:
            str: HTML контент или None при ошибке
        """
        if client == "browser":
            return await self._get_content_browser(url, timeout)
        else:
            return await self._get_content_http(url, timeout)

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Очищает текст от HTML тегов и лишних символов
        
        Args:
            text: Исходный текст
            
        Returns:
            str: Очищенный текст
        """
        if not text:
            return ""
        
        # Удаляем HTML теги
        text = re.sub(r'<[^>]+>', '', text)
        
        # Нормализуем пробелы
        text = re.sub(r'\s+', ' ', text)
        
        # Удаляем лишние символы
        text = text.strip()
        
        return text

    @staticmethod
    def _extract_date_from_text(text: str) -> Optional[datetime]:
        """
        Извлекает дату из текста
        
        Args:
            text: Текст для поиска даты
            
        Returns:
            datetime: Найденная дата или None
        """
        if not text:
            return None
        
        # Украинские месяцы
        months_uk = {
            'січня': 1, 'січень': 1,
            'лютого': 2, 'лютий': 2,
            'березня': 3, 'березень': 3,
            'квітня': 4, 'квітень': 4,
            'травня': 5, 'травень': 5,
            'червня': 6, 'червень': 6,
            'липня': 7, 'липень': 7,
            'серпня': 8, 'серпень': 8,
            'вересня': 9, 'вересень': 9,
            'жовтня': 10, 'жовтень': 10,
            'листопада': 11, 'листопад': 11,
            'грудня': 12, 'грудень': 12
        }
        
        # Паттерны для поиска дат
        patterns = [
            # 2025-08-18T13:29:01
            r'(\d{4})-(\d{1,2})-(\d{1,2})T(\d{1,2}):(\d{1,2}):(\d{1,2})',
            # 18 серпня 2025, 13:29
            r'(\d{1,2})\s+([а-яёє]+)\s+(\d{4}),?\s*(\d{1,2}):(\d{1,2})',
            # 18.08.2025 13:29
            r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{1,2})',
            # 18/08/2025 13:29
            r'(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{1,2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()
                    
                    if len(groups) >= 6:  # ISO формат
                        year, month, day, hour, minute, second = groups[:6]
                        return datetime(
                            int(year), int(month), int(day),
                            int(hour), int(minute), int(second),
                            tzinfo=timezone.utc
                        )
                    elif len(groups) >= 5:
                        if groups[1].isdigit():  # Числовой формат
                            day, month, year, hour, minute = groups[:5]
                            return datetime(
                                int(year), int(month), int(day),
                                int(hour), int(minute),
                                tzinfo=timezone.utc
                            )
                        else:  # Украинские месяцы
                            day, month_name, year, hour, minute = groups[:5]
                            month = months_uk.get(month_name.lower())
                            if month:
                                return datetime(
                                    int(year), month, int(day),
                                    int(hour), int(minute),
                                    tzinfo=timezone.utc
                                )
                except (ValueError, TypeError):
                    continue
        
        return None

    @staticmethod
    def _normalize_url(url: str, base_url: str) -> str:
        """
        Нормализует URL
        
        Args:
            url: URL для нормализации
            base_url: Базовый URL
            
        Returns:
            str: Нормализованный URL
        """
        if url.startswith('http'):
            return url
        elif url.startswith('//'):
            return 'https:' + url
        elif url.startswith('/'):
            # Удаляем path из base_url если есть
            base_parts = base_url.split('/')
            if len(base_parts) > 3:
                base_url = '/'.join(base_parts[:3])
            return base_url + url
        else:
            return base_url + '/' + url

    @staticmethod
    def _normalize_datetime(dt: Optional[datetime]) -> Optional[datetime]:
        """
        Нормализует datetime объект для корректного сравнения
        
        Args:
            dt: datetime объект для нормализации
            
        Returns:
            datetime: нормализованный datetime с UTC timezone или None
        """
        if dt is None:
            return None
        
        # Если дата уже имеет timezone, конвертируем в UTC
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)
        
        # Если дата без timezone, предполагаем что это UTC
        return dt.replace(tzinfo=timezone.utc)

    @staticmethod
    def _is_date_valid(article_date: Optional[datetime], until_date: Optional[datetime]) -> bool:
        """
        Проверяет, соответствует ли дата статьи условиям фильтрации
        
        Args:
            article_date: Дата статьи
            until_date: Самая старая дата для парсинга (включительно) 
            
        Returns:
            bool: True если дата подходит (статья не старше until_date)
        """
        # Если until_date не указана, возвращаем True
        if until_date is None:
            return True
            
        # Если дата статьи не указана, включаем её
        if article_date is None:
            return True
        if isinstance(article_date, datetime) and isinstance(until_date, datetime):
            return article_date.date() >= until_date.date()

    def _extract_articles_with_titles(self, content: str, base_url: str) -> List[dict]:
        """
        Извлекает статьи с заголовками из HTML контента
        
        Args:
            content: HTML контент страницы
            base_url: Базовый URL сайта
            
        Returns:
            List[dict]: Список словарей с ключами 'title' и 'url'
        """
        # Этот метод должен быть переопределен в дочерних классах
        # Возвращаем пустой список как fallback
        return []

    async def _parse_articles_batch(
        self,
        article_urls: List[str],
        client: str = "http",
        max_concurrent: int = 5
    ) -> List[Optional[ArticleData]]:
        """
        Парсит статьи пакетами для ускорения
        
        Args:
            article_urls: Список URL статей
            client: Тип клиента
            max_concurrent: Максимальное количество одновременных запросов
            
        Returns:
            List[Optional[ArticleData]]: Список данных статей
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def parse_with_semaphore(url: str) -> Optional[ArticleData]:
            async with semaphore:
                return await self._parse_article(url, client)
        
        tasks = [parse_with_semaphore(url) for url in article_urls]
        return await asyncio.gather(*tasks, return_exceptions=False)
