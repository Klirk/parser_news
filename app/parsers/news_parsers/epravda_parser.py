from typing import List, Optional
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import re
import logging
from urllib.parse import urlparse

from app.parsers.news_parsers.base_news_parser import BaseNewsParser
from app.models.news import NewsCollection, NewsItem, ArticleData


class EpravdaNewsParser(BaseNewsParser):
    """
    Парсер новостей для epravda.com.ua/news
    Поддерживает парсинг новостей с фильтрацией по дате через пагинацию
    """

    def __init__(self):
        super().__init__()
        self.base_url = "https://epravda.com.ua"
        self.news_url = "https://epravda.com.ua/news"
        self.logger = logging.getLogger(self.__class__.__name__)

    async def parse_news(
            self,
            url: str,
            until_date: Optional[datetime] = None,
            client: str = "http"
    ) -> NewsCollection:
        """
        Парсит новости с epravda.com.ua по страницам с датами
        
        Args:
            url: URL категории новостей
            until_date: Граничная дата (не позднее)
            client: Тип клиента (http или browser)
            
        Returns:
            NewsCollection: Коллекция новостей
        """
        try:
            self.logger.info(f"Начинаем парсинг новостей epravda.com.ua: {url}")
            self.logger.info(f"Клиент: {client}, граничная дата: {until_date}")

            start_date = datetime.now(timezone.utc).date()
            end_date = until_date.date() if until_date else start_date

            self.logger.info(f"Парсим от {start_date} до {end_date}")

            date_urls = self._generate_date_urls(start_date, end_date)
            self.logger.info(f"Сгенерировано {date_urls}")

            all_articles = []
            processed_dates = 0

            for date_url in date_urls:
                processed_dates += 1
                self.logger.info(f"Обрабатываем {processed_dates}/{len(date_urls)} - {date_url}")

                try:
                    content = await self._get_content(date_url, client)
                    if not content:
                        self.logger.warning(f"ПАГИНАЦИЯ: Не удалось получить контент для {date_url}")
                        continue

                    page_date = self._extract_date_from_date_url(date_url)
                    self.logger.info(f"ПАГИНАЦИЯ: Обрабатываем дату {page_date}")

                    page_articles = self._extract_articles_with_titles(content, self.base_url, page_date)
                    self.logger.info(f"ПАГИНАЦИЯ: Найдено {len(page_articles)} статей на странице {date_url}")

                    if page_articles:
                        all_articles.extend(page_articles)
                        self.logger.info(
                            f"ПАГИНАЦИЯ: Добавлено {len(page_articles)} статей, всего: {len(all_articles)}")
                    else:
                        self.logger.warning(f"ПАГИНАЦИЯ: На странице {date_url} статьи не найдены")

                except Exception as e:
                    self.logger.error(f"ПАГИНАЦИЯ: Ошибка обработки страницы {date_url}: {str(e)}")
                    continue

            self.logger.info(
                f"ПАГИНАЦИЯ: Завершено. Обработано {processed_dates} страниц, найдено {len(all_articles)} статей")

            unique_articles = []
            seen_urls = set()
            for article in all_articles:
                if article['url'] not in seen_urls:
                    unique_articles.append(article)
                    seen_urls.add(article['url'])

            self.logger.info(
                f"ДЕДУПЛИКАЦИЯ: После удаления дубликатов осталось {len(unique_articles)} уникальных статей")

            news_items = []
            for article in unique_articles:
                should_parse_full = self._should_parse_full_content(url, article['url'])

                if should_parse_full:
                    self.logger.info(f"ПОЛНЫЙ ПАРСИНГ: Парсим полный контент для {article['url']}")
                    full_article_data = await self._parse_full_article(article['url'], client)
                    if full_article_data:
                        full_article_data.published_at = article.get('datetime')
                        article_data = full_article_data
                    else:
                        # Fallback на базовые данные
                        article_data = ArticleData(
                            title=article.get('title', 'Новость без заголовка'),
                            content_body="",
                            published_at=article.get('datetime'),
                            author=None,
                            views=None,
                            comments=[],
                            likes=None,
                            dislikes=None,
                            video_url=None,
                            image_urls=[]
                        )
                else:
                    article_data = ArticleData(
                        title=article.get('title', 'Новость без заголовка'),
                        content_body="",
                        published_at=article.get('datetime'),
                        author=None,
                        views=None,
                        comments=[],
                        likes=None,
                        dislikes=None,
                        video_url=None,
                        image_urls=[]
                    )

                news_item = NewsItem(
                    source=url,
                    url=article['url'],
                    article_data=article_data
                )

                if until_date is None or self._is_date_valid(article.get('datetime'), until_date):
                    news_items.append(news_item)

            self.logger.info(f"ИТОГО: Создано {len(news_items)} объектов новостей")

            return NewsCollection(
                source=url,
                items=news_items,
                total_items=len(news_items),
                parse_status="success",
                error_message=None
            )

        except Exception as e:
            self.logger.error(f"Ошибка парсинга epravda.com.ua: {str(e)}")
            return NewsCollection(
                source=url,
                items=[],
                total_items=0,
                parse_status="failed",
                error_message=str(e)
            )

    def _generate_date_urls(self, start_date, end_date) -> List[str]:
        """
        Генерирует URL-ы для парсинга по датам от start_date до end_date
        
        Args:
            start_date: Начальная дата (сегодня)
            end_date: Конечная дата (указанная пользователем)
            
        Returns:
            List[str]: Список URL-ов для дат
        """
        urls = []
        current_date = start_date

        self.logger.info(f"ГЕНЕРАЦИЯ URL: Создаем URL-ы от {start_date} до {end_date}")

        while current_date >= end_date:
            # Формат даты: DDMMYYYY
            date_str = current_date.strftime("%d%m%Y")
            date_url = f"{self.news_url}/date_{date_str}/"
            urls.append(date_url)

            self.logger.debug(f"ГЕНЕРАЦИЯ URL: Добавлен URL {date_url} для даты {current_date}")

            current_date -= timedelta(days=1)

        self.logger.info(f"ГЕНЕРАЦИЯ URL: Сгенерировано {len(urls)} URL-ов")
        return urls

    def _extract_date_from_date_url(self, url: str) -> Optional[datetime]:
        """
        Извлекает дату из URL вида /date_29082025/
        
        Args:
            url: URL с датой
            
        Returns:
            datetime: Дата из URL
        """
        try:
            date_pattern = r'date_(\d{2})(\d{2})(\d{4})'
            match = re.search(date_pattern, url)
            if match:
                day, month, year = match.groups()
                return datetime(int(year), int(month), int(day), tzinfo=timezone.utc)

        except Exception as e:
            self.logger.error(f"Ошибка извлечения даты из URL {url}: {str(e)}")

        return None

    def _extract_articles_with_titles(self, content: str, base_url: str, page_date: Optional[datetime] = None) -> List[
        dict]:
        """
        Извлекает статьи с заголовками из HTML контента страницы с датой epravda.com.ua
        
        Args:
            content: HTML контент страницы
            base_url: Базовый URL сайта
            page_date: Дата страницы для установки времени
            
        Returns:
            List[dict]: Список словарей с ключами 'title', 'url', 'time', 'datetime'
        """
        soup = BeautifulSoup(content, 'html.parser')
        articles = []

        try:
            self.logger.info(f"ИЗВЛЕЧЕНИЕ: Начинаем извлечение статей из HTML контента")

            news_container = soup.find('div', class_='section_articles_grid_wrapper')
            if not news_container:
                self.logger.warning("ИЗВЛЕЧЕНИЕ: Не найден контейнер section_articles_grid_wrapper")
                return []

            news_articles = news_container.find_all('div', class_='article_news')
            self.logger.info(f"ИЗВЛЕЧЕНИЕ: Найдено {len(news_articles)} статей в контейнере")

            for article_div in news_articles:
                try:
                    time_element = article_div.find('div', class_='article_date')
                    time_str = None
                    if time_element:
                        time_str = self._clean_text(time_element.get_text())
                        self.logger.info(f"ИЗВЛЕЧЕНИЕ: Найдено время {time_str}")
                    else:
                        self.logger.warning(f"ИЗВЛЕЧЕНИЕ: Время не найдено в article_date")

                    title_element = article_div.find('div', class_='article_title')
                    if title_element:
                        link_element = title_element.find('a')
                        if link_element and link_element.get('href'):
                            url = self._normalize_url(link_element.get('href'), base_url)
                            title = self._clean_text(link_element.get_text())

                            if title and url and len(title) > 10:
                                article_datetime = self._combine_date_and_time(page_date, time_str)

                                article = {
                                    'title': title,
                                    'url': url,
                                    'time': time_str,
                                    'datetime': article_datetime
                                }
                                articles.append(article)

                                self.logger.info(
                                    f"ИЗВЛЕЧЕНИЕ: Найдена статья - {time_str} -> {article_datetime}: {title[:50]}...")
                            else:
                                self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Пропущена статья - некорректные данные")
                        else:
                            self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Не найдена ссылка в заголовке статьи")
                    else:
                        self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Не найден заголовок статьи")

                except Exception as e:
                    self.logger.warning(f"ИЗВЛЕЧЕНИЕ: Ошибка обработки статьи: {str(e)}")
                    continue

            self.logger.info(f"ИЗВЛЕЧЕНИЕ: Всего извлечено {len(articles)} статей")
            return articles

        except Exception as e:
            self.logger.error(f"ИЗВЛЕЧЕНИЕ: Критическая ошибка извлечения статей: {str(e)}")
            return []

    @staticmethod
    def _find_news_link_near_time(element) -> Optional:
        """
        Ищет ссылку на новость рядом с элементом времени
        """
        # Ищем в том же элементе (только если это BeautifulSoup элемент)
        if hasattr(element, 'find'):
            link = element.find('a', href=re.compile(r'/[a-z]+/.*-\d{6}/?$'))
            if link:
                return link

        if hasattr(element, 'next_sibling'):
            next_sibling = element.next_sibling
            attempts = 0
            while next_sibling and attempts < 5:
                if hasattr(next_sibling, 'find'):
                    link = next_sibling.find('a', href=re.compile(r'/[a-z]+/.*-\d{6}/?$'))
                    if link:
                        return link
                next_sibling = next_sibling.next_sibling
                attempts += 1

        if hasattr(element, 'parent') and element.parent and hasattr(element.parent, 'find'):
            link = element.parent.find('a', href=re.compile(r'/[a-z]+/.*-\d{6}/?$'))
            if link:
                return link

        return None

    @staticmethod
    def _find_time_near_link(link) -> Optional[str]:
        """
        Ищет время рядом со ссылкой
        """
        if link.parent and hasattr(link.parent, 'find'):
            time_element = link.parent.find(string=re.compile(r'\d{1,2}:\d{2}'))
            if time_element:
                return time_element.strip()

        prev_sibling = link.parent.previous_sibling if link.parent else None
        attempts = 0
        while prev_sibling and attempts < 3:
            if hasattr(prev_sibling, 'find'):
                time_element = prev_sibling.find(string=re.compile(r'\d{1,2}:\d{2}'))
                if time_element:
                    return time_element.strip()
            elif isinstance(prev_sibling, str):
                time_match = re.search(r'\d{1,2}:\d{2}', prev_sibling)
                if time_match:
                    return time_match.group()
            prev_sibling = prev_sibling.previous_sibling
            attempts += 1

        return None

    def _combine_date_and_time(self, page_date: Optional[datetime], time_str: Optional[str]) -> Optional[datetime]:
        """
        Комбинирует дату страницы и время статьи
        
        Args:
            page_date: Дата страницы
            time_str: Строка времени в формате "HH:MM"
            
        Returns:
            datetime: Дата и время статьи
        """
        try:
            self.logger.info(f"ВРЕМЯ: Комбинируем дату {page_date} с временем '{time_str}'")

            if not page_date:
                fallback_dt = datetime.now(timezone.utc)
                self.logger.warning(f"ВРЕМЯ: Дата страницы отсутствует, используем {fallback_dt}")
                return fallback_dt

            if time_str and time_str.strip():
                time_match = re.search(r'(\d{1,2}):(\d{2})', time_str.strip())
                if time_match:
                    hour, minute = time_match.groups()
                    combined_dt = page_date.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
                    self.logger.info(f"ВРЕМЯ: Успешно скомбинировано: {combined_dt}")
                    return combined_dt
                else:
                    self.logger.warning(f"ВРЕМЯ: Не удалось распарсить время '{time_str}', используем дату страницы")
            else:
                self.logger.warning(f"ВРЕМЯ: Время пустое или None, используем дату страницы")

            # Если время не найдено, используем дату страницы с полуночью
            fallback_dt = page_date.replace(hour=0, minute=0, second=0, microsecond=0)
            self.logger.info(f"ВРЕМЯ: Используем дату страницы: {fallback_dt}")
            return fallback_dt

        except Exception as e:
            self.logger.error(f"ВРЕМЯ: Ошибка комбинирования даты {page_date} и времени '{time_str}': {str(e)}")
            fallback_dt = page_date or datetime.now(timezone.utc)
            return fallback_dt

    def _extract_article_links(self, content: str, base_url: str) -> List[str]:
        """
        Извлекает ссылки на статьи из HTML контента (для совместимости с базовым классом)
        """
        articles = self._extract_articles_with_titles(content, base_url)
        return [article['url'] for article in articles]

    def _should_parse_full_content(self, source_url: str, article_url: str) -> bool:
        """
        Проверяет, нужно ли парсить полный контент статьи
        Возвращает True если домены source и article совпадают
        
        Args:
            source_url: URL источника (откуда парсим)
            article_url: URL статьи
            
        Returns:
            bool: True если нужно парсить полный контент
        """
        try:
            source_domain = urlparse(source_url).netloc.lower()
            article_domain = urlparse(article_url).netloc.lower()

            source_domain = source_domain.replace('www.', '')
            article_domain = article_domain.replace('www.', '')

            should_parse = source_domain == article_domain
            self.logger.info(f"ПРОВЕРКА ДОМЕНА: {source_domain} == {article_domain} -> {should_parse}")

            return should_parse

        except Exception as e:
            self.logger.error(f"Ошибка проверки доменов {source_url} vs {article_url}: {str(e)}")
            return False

    async def _parse_full_article(self, url: str, client: str = "http") -> Optional[ArticleData]:
        """
        Парсит полный контент статьи с epravda.com.ua
        
        Args:
            url: URL статьи
            client: Тип клиента
            
        Returns:
            ArticleData: Полные данные статьи или None при ошибке
        """
        try:
            self.logger.info(f"ПОЛНЫЙ ПАРСИНГ: Начинаем парсинг статьи {url}")

            content = await self._get_content(url, client)
            if not content:
                self.logger.warning(f"ПОЛНЫЙ ПАРСИНГ: Не удалось получить контент для {url}")
                return None

            soup = BeautifulSoup(content, 'html.parser')

            article_element = soup.find('article', class_='post_news')
            if not article_element:
                self.logger.warning(f"ПОЛНЫЙ ПАРСИНГ: Не найден элемент article.post_news в {url}")
                return None

            title = ""
            title_element = article_element.find('h1', class_='post_news_title')
            if title_element:
                title = self._clean_text(title_element.get_text())
                self.logger.info(f"ПОЛНЫЙ ПАРСИНГ: Найден заголовок: {title[:50]}...")

            author = None
            author_element = article_element.find('span', class_='post_news_author')
            if author_element:
                author_link = author_element.find('a')
                if author_link:
                    author = self._clean_text(author_link.get_text())
                    self.logger.info(f"ПОЛНЫЙ ПАРСИНГ: Найден автор: {author}")

            content_body = ""
            text_element = article_element.find('div', class_='post_news_text')
            if text_element:
                paragraphs = text_element.find_all(['p', 'li'])
                content_parts = []
                for p in paragraphs:
                    text = self._clean_text(p.get_text())
                    if text:
                        content_parts.append(text)
                content_body = '\n\n'.join(content_parts)
                self.logger.info(f"ПОЛНЫЙ ПАРСИНГ: Извлечен контент ({len(content_body)} символов)")

            image_urls = []
            photo_element = article_element.find('div', class_='post_news_photo')
            if photo_element:
                img_element = photo_element.find('img')
                if img_element and img_element.get('src'):
                    img_url = img_element.get('src')
                    normalized_url = self._normalize_url(img_url, self.base_url)
                    image_urls.append(normalized_url)
                    self.logger.info(f"ПОЛНЫЙ ПАРСИНГ: Найдено изображение: {normalized_url}")

            views = None
            views_element = article_element.find('div', class_='post_views')
            if views_element:
                views_text = views_element.get_text()
                views_match = re.search(r'(\d+)', views_text)
                if views_match:
                    views = int(views_match.group(1))
                    self.logger.info(f"ПОЛНЫЙ ПАРСИНГ: Найдено просмотров: {views}")

            tags = []
            tags_element = article_element.find('div', class_='post_news_tags')
            if tags_element:
                tag_links = tags_element.find_all('a')
                for tag_link in tag_links:
                    tag = self._clean_text(tag_link.get_text())
                    if tag:
                        tags.append(tag)
                if tags:
                    self.logger.info(f"ПОЛНЫЙ ПАРСИНГ: Найдены теги: {', '.join(tags)}")

            self.logger.info(f"ПОЛНЫЙ ПАРСИНГ: Успешно спарсена статья {url}")

            return ArticleData(
                title=title or "Статья без заголовка",
                content_body=content_body,
                image_urls=image_urls,
                published_at=datetime.now(timezone.utc),
                author=author,
                views=views,
                comments=tags,
                likes=None,
                dislikes=None,
                video_url=None
            )

        except Exception as e:
            self.logger.error(f"ПОЛНЫЙ ПАРСИНГ: Ошибка парсинга статьи {url}: {str(e)}")
            return None

    async def _parse_article(self, url: str, client: str = "http") -> Optional[ArticleData]:
        """
        Парсит отдельную статью (использует полный парсинг)
        """
        return await self._parse_full_article(url, client)
