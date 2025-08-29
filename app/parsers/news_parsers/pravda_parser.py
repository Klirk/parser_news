# app/parsers/news_parsers/pravda_parser.py

from typing import List, Optional
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import re
import logging

from app.parsers.news_parsers.base_news_parser import BaseNewsParser
from app.models.news import NewsCollection, NewsItem, ArticleData


class PravdaNewsParser(BaseNewsParser):
    """
    Парсер новостей для pravda.com.ua/news
    Поддерживает парсинг новостей с фильтрацией по дате
    """

    def __init__(self):
        super().__init__()
        self.base_url = "https://www.pravda.com.ua"
        self.news_url = "https://www.pravda.com.ua/news"
        self.logger = logging.getLogger(self.__class__.__name__)

    async def parse_news(
        self,
        url: str,
        until_date: Optional[datetime] = None,
        client: str = "http"
    ) -> NewsCollection:
        """
        Парсит новости с pravda.com.ua
        
        Args:
            url: URL категории новостей
            until_date: Граничная дата (не позднее)
            client: Тип клиента (http или browser)
            
        Returns:
            NewsCollection: Коллекция новостей
        """
        try:
            self.logger.info(f"Начинаем парсинг новостей pravda.com.ua: {url}")
            
            # Для pravda.com.ua нужно обрабатывать URL с датой
            parsed_urls = await self._get_paginated_urls(url, until_date, client)
            
            all_article_links = []
            for page_url in parsed_urls:
                content = await self._get_content(page_url, client)
                if content:
                    links = self._extract_article_links(content, self.base_url)
                    all_article_links.extend(links)
            
            # Убираем дубликаты
            unique_links = list(set(all_article_links))
            
            # Пока что возвращаем только ссылки (как просил пользователь)
            news_items = []
            for link in unique_links:
                # Создаем минимальную статью только с URL
                title = link.split('/')[-1].replace('-', ' ').replace('.html', '')
                if not title.strip():
                    title = "Новость"
                
                article_data = ArticleData(
                    title=title,
                    content_body="",  # Пока пустое содержимое
                    published_at=self._extract_date_from_url(link)
                )
                news_item = NewsItem(
                    source=url,
                    url=link,
                    article_data=article_data
                )
                
                # Фильтруем по дате
                if until_date is None or self._is_date_valid(article_data.published_at, until_date):
                    news_items.append(news_item)
            
            return NewsCollection(
                source=url,
                items=news_items,
                total_items=len(news_items),
                parse_status="success"
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка парсинга pravda.com.ua: {str(e)}")
            return NewsCollection(
                source=url,
                items=[],
                total_items=0,
                parse_status="failed",
                error_message=str(e)
            )

    async def _get_paginated_urls(
        self,
        base_url: str,
        until_date: Optional[datetime],
        client: str
    ) -> List[str]:
        """
        Формирует URL для парсинга с учетом дат
        
        Args:
            base_url: Базовый URL
            until_date: Граничная дата
            client: Тип клиента
            
        Returns:
            List[str]: Список URL для парсинга
        """
        urls = []
        
        if until_date:
            # Формируем URL с конкретной датой
            date_str = until_date.strftime("%d%m%Y")
            date_url = f"{self.news_url}/date_{date_str}/"
            urls.append(date_url)
            
            # Добавляем несколько дней назад для большего охвата
            import datetime as dt
            for days_back in range(1, 8):  # Неделя назад
                past_date = until_date - dt.timedelta(days=days_back)
                past_date_str = past_date.strftime("%d%m%Y")
                past_url = f"{self.news_url}/date_{past_date_str}/"
                urls.append(past_url)
        else:
            # Если дата не указана, парсим текущие новости
            urls.append(base_url)
            
        return urls

    def _extract_article_links(self, content: str, base_url: str) -> List[str]:
        """
        Извлекает ссылки на статьи из HTML контента pravda.com.ua
        
        Args:
            content: HTML контент страницы
            base_url: Базовый URL сайта
            
        Returns:
            List[str]: Список URL статей
        """
        soup = BeautifulSoup(content, 'html.parser')
        links = []
        
        try:
            # Ищем контейнер с новостями
            news_container = soup.find('div', class_='container_sub_news_list_wrapper mode1')
            
            if news_container:
                # Ищем все статьи
                articles = news_container.find_all('div', class_='article_news_list')
                
                for article in articles:
                    # Ищем ссылку в заголовке
                    header_link = article.find('div', class_='article_content')
                    if header_link:
                        link_element = header_link.find('a')
                        if link_element and link_element.get('href'):
                            url = link_element['href']
                            normalized_url = self._normalize_url(url, base_url)
                            links.append(normalized_url)
                            
            else:
                self.logger.warning("Не найден контейнер с новостями")
                
        except Exception as e:
            self.logger.error(f"Ошибка извлечения ссылок: {str(e)}")
            
        return links

    async def _parse_article(self, url: str, client: str = "http") -> Optional[ArticleData]:
        """
        Парсит отдельную статью с pravda.com.ua
        
        Args:
            url: URL статьи
            client: Тип клиента
            
        Returns:
            ArticleData: Данные статьи или None при ошибке
        """
        try:
            content = await self._get_content(url, client)
            if not content:
                return None
                
            soup = BeautifulSoup(content, 'html.parser')
            
            # Извлекаем заголовок
            title = ""
            title_element = soup.find('h1')
            if title_element:
                title = self._clean_text(title_element.get_text())
            
            # Извлекаем контент статьи
            content_body = ""
            content_element = soup.find('div', class_='post_text')
            if content_element:
                content_body = self._clean_text(content_element.get_text())
            
            # Извлекаем дату публикации
            published_at = self._extract_article_date(soup)
            
            # Извлекаем изображения
            image_urls = self._extract_image_urls(soup, url)
            
            # Извлекаем автора
            author = self._extract_author(soup)
            
            return ArticleData(
                title=title or "Без заголовка",
                content_body=content_body,
                image_urls=image_urls,
                published_at=published_at,
                author=author
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка парсинга статьи {url}: {str(e)}")
            return None

    def _extract_date_from_url(self, url: str) -> Optional[datetime]:
        """
        Извлекает дату из URL статьи pravda.com.ua
        
        Args:
            url: URL статьи
            
        Returns:
            datetime: Дата публикации или None
        """
        try:
            # Паттерн для pravda.com.ua: /news/2025/08/28/7458123-title/
            pattern = r'/news/(\d{4})/(\d{1,2})/(\d{1,2})/'
            match = re.search(pattern, url)
            
            if match:
                year, month, day = match.groups()
                return datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
                
        except Exception as e:
            self.logger.error(f"Ошибка извлечения даты из URL {url}: {str(e)}")
            
        return None

    def _extract_article_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """
        Извлекает дату публикации из HTML статьи
        
        Args:
            soup: BeautifulSoup объект статьи
            
        Returns:
            datetime: Дата публикации или None
        """
        try:
            # Ищем элемент с датой
            date_element = soup.find('time')
            if date_element:
                datetime_attr = date_element.get('datetime')
                if datetime_attr:
                    return datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
            
            # Альтернативный поиск даты в тексте
            date_elements = soup.find_all(['span', 'div'], class_=re.compile(r'.*date.*|.*time.*'))
            for element in date_elements:
                date_text = element.get_text()
                parsed_date = self._extract_date_from_text(date_text)
                if parsed_date:
                    return parsed_date
                    
        except Exception as e:
            self.logger.error(f"Ошибка извлечения даты статьи: {str(e)}")
            
        return None

    def _extract_image_urls(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Извлекает URL изображений из статьи
        
        Args:
            soup: BeautifulSoup объект статьи
            base_url: Базовый URL
            
        Returns:
            List[str]: Список URL изображений
        """
        image_urls = []
        
        try:
            # Ищем изображения в статье
            images = soup.find_all('img')
            for img in images:
                src = img.get('src') or img.get('data-src')
                if src:
                    normalized_url = self._normalize_url(src, base_url)
                    if normalized_url not in image_urls:
                        image_urls.append(normalized_url)
                        
        except Exception as e:
            self.logger.error(f"Ошибка извлечения изображений: {str(e)}")
            
        return image_urls

    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Извлекает автора статьи
        
        Args:
            soup: BeautifulSoup объект статьи
            
        Returns:
            str: Имя автора или None
        """
        try:
            # Ищем автора в различных местах
            author_selectors = [
                '[class*="author"]',
                '[class*="byline"]',
                '.post_author',
                '.article_author'
            ]
            
            for selector in author_selectors:
                author_element = soup.select_one(selector)
                if author_element:
                    author = self._clean_text(author_element.get_text())
                    if author and len(author) > 2:
                        return author
                        
        except Exception as e:
            self.logger.error(f"Ошибка извлечения автора: {str(e)}")
            
        return None
