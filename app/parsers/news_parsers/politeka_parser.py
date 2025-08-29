# app/parsers/news_parsers/politeka_parser.py

from typing import List, Optional
from datetime import datetime, timezone, date
from bs4 import BeautifulSoup
import re
import logging

from app.parsers.news_parsers.base_news_parser import BaseNewsParser
from app.models.news import NewsCollection, NewsItem, ArticleData


class PolitekaNewsParser(BaseNewsParser):
    """
    Парсер новостей для politeka.net/uk/newsfeed
    Поддерживает парсинг новостей с пагинацией и фильтрацией по дате
    """

    def __init__(self):
        super().__init__()
        self.base_url = "https://politeka.net"
        self.news_url = "https://politeka.net/uk/newsfeed"
        self.logger = logging.getLogger(self.__class__.__name__)

    async def parse_news(
        self,
        url: str,
        until_date: Optional[datetime] = None,
        client: str = "http"
    ) -> NewsCollection:
        """
        Парсит новости с politeka.net
        
        Args:
            url: URL категории новостей
            until_date: Граничная дата (не позднее)
            client: Тип клиента (http или browser)
            
        Returns:
            NewsCollection: Коллекция новостей
        """
        try:
            self.logger.info(f"Начинаем парсинг новостей politeka.net: {url}")
            
            # Для politeka.net используем пагинацию
            parsed_urls = await self._get_paginated_urls(url, until_date, client)
            
            all_article_links = []
            for page_url in parsed_urls:
                content = await self._get_content(page_url, client)
                if content:
                    links = self._extract_article_links(content, self.base_url)
                    all_article_links.extend(links)
                    
                    # Проверяем, есть ли статьи старше until_date
                    if until_date and self._should_stop_pagination(content, until_date):
                        break
            
            # Убираем дубликаты
            unique_links = list(set(all_article_links))
            
            # Пока что возвращаем только ссылки (как просил пользователь)
            news_items = []
            for link in unique_links:
                # Создаем минимальную статью только с URL
                title = link.split('/')[-1].replace('-', ' ')
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
            self.logger.error(f"Ошибка парсинга politeka.net: {str(e)}")
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
        Формирует URL для парсинга с пагинацией
        
        Args:
            base_url: Базовый URL
            until_date: Граничная дата
            client: Тип клиента
            
        Returns:
            List[str]: Список URL для парсинга
        """
        urls = []
        
        # Добавляем первую страницу
        urls.append(base_url)
        
        # Добавляем страницы с пагинацией
        # politeka.net использует ?page=X для пагинации
        for page in range(2, 11):  # Парсим до 10 страниц максимум
            page_url = f"{base_url}?page={page}"
            urls.append(page_url)
            
        return urls

    def _extract_article_links(self, content: str, base_url: str) -> List[str]:
        """
        Извлекает ссылки на статьи из HTML контента politeka.net
        
        Args:
            content: HTML контент страницы
            base_url: Базовый URL сайта
            
        Returns:
            List[str]: Список URL статей
        """
        soup = BeautifulSoup(content, 'html.parser')
        links = []
        
        try:
            # Ищем контейнер с новостями для politeka
            news_container = soup.find('div', class_='col-lg-8 col-md-12')
            
            if news_container:
                # Ищем все статьи
                articles = news_container.find_all('div', class_='b_post b_post--image-sm')
                
                for article in articles:
                    # Ищем ссылку в заголовке
                    media_section = article.find('div', class_='b_post--media')
                    if media_section:
                        link_element = media_section.find('a')
                        if link_element and link_element.get('href'):
                            url = link_element['href']
                            normalized_url = self._normalize_url(url, base_url)
                            links.append(normalized_url)
                    
                    # Также проверяем ссылку на изображении
                    image_link = article.find('a', class_='b_post--image')
                    if image_link and image_link.get('href'):
                        url = image_link['href']
                        normalized_url = self._normalize_url(url, base_url)
                        if normalized_url not in links:
                            links.append(normalized_url)
                            
            if not links:
                self.logger.warning("Не найдены статьи в контейнере")
                
        except Exception as e:
            self.logger.error(f"Ошибка извлечения ссылок: {str(e)}")
            
        return links

    def _should_stop_pagination(self, content: str, until_date: datetime) -> bool:
        """
        Проверяет, нужно ли остановить пагинацию на основе дат статей
        
        Args:
            content: HTML контент страницы
            until_date: Граничная дата
            
        Returns:
            bool: True если нужно остановить пагинацию
        """
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Ищем даты на странице
            date_elements = soup.find_all('div', class_='b_post--date')
            
            for date_element in date_elements:
                date_text = date_element.get_text().strip()
                article_date = self._parse_politeka_date(date_text)
                
                if article_date and article_date < until_date:
                    return True
                    
        except Exception as e:
            self.logger.error(f"Ошибка проверки дат для пагинации: {str(e)}")
            
        return False

    def _parse_politeka_date(self, date_text: str) -> Optional[datetime]:
        """
        Парсит дату в формате politeka.net (например: "13:37 28.08")
        
        Args:
            date_text: Текст с датой
            
        Returns:
            datetime: Распарсенная дата или None
        """
        try:
            # Паттерн для politeka: "13:37 28.08"
            pattern = r'(\d{1,2}):(\d{2})\s+(\d{1,2})\.(\d{2})'
            match = re.search(pattern, date_text)
            
            if match:
                hour, minute, day, month = match.groups()
                # Предполагаем текущий год
                current_year = datetime.now().year
                
                return datetime(current_year, int(month), int(day), tzinfo=timezone.utc)
                
        except Exception as e:
            self.logger.error(f"Ошибка парсинга даты politeka '{date_text}': {str(e)}")
            
        return None

    async def _parse_article(self, url: str, client: str = "http") -> Optional[ArticleData]:
        """
        Парсит отдельную статью с politeka.net
        
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
            title_element = soup.find('h1') or soup.find('h1', class_='article_title')
            if title_element:
                title = self._clean_text(title_element.get_text())
            
            # Извлекаем контент статьи
            content_body = ""
            content_selectors = [
                '.article_text',
                '.post_content',
                '.content',
                '.article_body'
            ]
            
            for selector in content_selectors:
                content_element = soup.select_one(selector)
                if content_element:
                    content_body = self._clean_text(content_element.get_text())
                    break
            
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
        Извлекает дату из URL статьи politeka.net
        
        Args:
            url: URL статьи
            
        Returns:
            datetime: Дата публикации или None
        """
        try:
            # Паттерн для politeka.net может содержать ID
            # Попробуем извлечь из номера статьи или использовать текущую дату
            return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                
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
            
            # Ищем дату в специфических классах для politeka
            date_selectors = [
                '.article_date',
                '.post_date',
                '.b_post--date',
                '[class*="date"]'
            ]
            
            for selector in date_selectors:
                date_element = soup.select_one(selector)
                if date_element:
                    date_text = date_element.get_text()
                    parsed_date = self._parse_politeka_date(date_text)
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
                src = img.get('src') or img.get('data-src') or img.get('data-original')
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
                '.article_author',
                '.post_author',
                '.author',
                '[class*="author"]',
                '[class*="byline"]'
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
