from typing import List, Optional
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import re
import logging
import asyncio
from urllib.parse import urlparse

from app.parsers.news_parsers.base_news_parser import BaseNewsParser
from app.models.news import NewsCollection, NewsItem, ArticleData


class PravdaNewsParser(BaseNewsParser):
    """
    Парсер новостей для pravda.com.ua/news
    Поддерживает парсинг новостей с единой страницы
    """

    def __init__(self):
        super().__init__()
        self.base_url = "https://www.pravda.com.ua"
        self.news_url = "https://www.pravda.com.ua/news"
        self.logger = logging.getLogger(self.__class__.__name__)

        # Семафоры для ограничения одновременных запросов
        self.article_semaphore = asyncio.Semaphore(10)

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
            self.logger.info(f"Клиент: {client}, граничная дата: {until_date}")

            # Получаем контент главной страницы новостей
            content = await self._get_content(url, client)
            if not content:
                self.logger.warning(f"Не удалось получить контент для {url}")
                return NewsCollection(
                    source=url,
                    items=[],
                    total_items=0,
                    parse_status="failed",
                    error_message="Не удалось получить контент страницы"
                )

            # Извлекаем статьи с заголовками
            all_articles = self._extract_articles_with_titles(content, self.base_url)
            self.logger.info(f"Найдено {len(all_articles)} статей на странице")

            if not all_articles:
                return NewsCollection(
                    source=url,
                    items=[],
                    total_items=0,
                    parse_status="success",
                    error_message=None
                )

            # Фильтруем по дате если нужно
            filtered_articles = []
            for article in all_articles:
                if until_date is None or self._is_date_valid(article.get('datetime'), until_date):
                    filtered_articles.append(article)

            self.logger.info(f"После фильтрации по дате осталось {len(filtered_articles)} статей")

            # Асинхронно обрабатываем статьи
            news_items = await self._process_articles_async(filtered_articles, url, client, until_date)

            self.logger.info(f"ИТОГО: Создано {len(news_items)} объектов новостей")

            return NewsCollection(
                source=url,
                items=news_items,
                total_items=len(news_items),
                parse_status="success",
                error_message=None
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

    async def _process_articles_async(self, articles: List[dict], source_url: str, client: str, until_date: Optional[datetime]) -> List[NewsItem]:
        """
        Асинхронно обрабатывает статьи (парсит полный контент для подходящих)
        
        Args:
            articles: Список словарей статей
            source_url: URL источника
            client: Тип клиента
            until_date: Граничная дата
            
        Returns:
            List[NewsItem]: Список обработанных новостных объектов
        """
        if not articles:
            return []
        
        self.logger.info(f"ASYNC ARTICLES: Начинаем обработку {len(articles)} статей")

        full_parse_articles = []
        simple_articles = []
        
        for article in articles:
            if self._should_parse_full_content(source_url, article['url']):
                full_parse_articles.append(article)
            else:
                simple_articles.append(article)
        
        self.logger.info(f"ASYNC ARTICLES: Полный парсинг для {len(full_parse_articles)} статей, простой для {len(simple_articles)}")

        # Обрабатываем простые статьи
        simple_news_items = []
        for article in simple_articles:
            article_data = self._create_simple_article_data(article)
            news_item = NewsItem(
                source=source_url,
                url=article['url'],
                article_data=article_data
            )
            simple_news_items.append(news_item)

        # Обрабатываем статьи с полным парсингом
        full_news_items = []
        if full_parse_articles:
            batch_size = 20
            for i in range(0, len(full_parse_articles), batch_size):
                batch = full_parse_articles[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(full_parse_articles) + batch_size - 1) // batch_size
                
                self.logger.info(f"ASYNC ARTICLES: Обрабатываем батч {batch_num}/{total_batches} ({len(batch)} статей)")
                
                batch_results = await self._process_articles_batch(batch, source_url, client, until_date)
                full_news_items.extend(batch_results)
        
        all_news_items = simple_news_items + full_news_items
        self.logger.info(f"ASYNC ARTICLES: Завершено. Создано {len(all_news_items)} объектов новостей")
        
        return all_news_items

    async def _process_articles_batch(self, articles_batch: List[dict], source_url: str, client: str, until_date: Optional[datetime]) -> List[NewsItem]:
        """
        Асинхронно обрабатывает батч статей
        
        Args:
            articles_batch: Батч статей для обработки
            source_url: URL источника
            client: Тип клиента
            until_date: Граничная дата
            
        Returns:
            List[NewsItem]: Обработанные NewsItem объекты
        """
        tasks = [self._process_single_article(article, source_url, client) for article in articles_batch]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        news_items = []
        successful = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"ASYNC ARTICLES: Ошибка парсинга статьи {articles_batch[i]['url']}: {str(result)}")
                # Создаем простую статью в случае ошибки
                article_data = self._create_simple_article_data(articles_batch[i])
                news_item = NewsItem(
                    source=source_url,
                    url=articles_batch[i]['url'],
                    article_data=article_data
                )
                news_items.append(news_item)
            elif result:
                news_items.append(result)
                successful += 1
        
        self.logger.info(f"ASYNC ARTICLES: Батч завершен. Успешно: {successful}/{len(articles_batch)}")
        return news_items

    async def _process_single_article(self, article: dict, source_url: str, client: str) -> Optional[NewsItem]:
        """
        Асинхронно обрабатывает одну статью с полным парсингом
        
        Args:
            article: Словарь с данными статьи
            source_url: URL источника
            client: Тип клиента
            
        Returns:
            Optional[NewsItem]: NewsItem объект или None при ошибке
        """
        async with self.article_semaphore:
            try:
                self.logger.debug(f"ASYNC ARTICLES: Парсим {article['url']}")
                
                full_article_data = await self._parse_full_article(article['url'], client)
                if full_article_data:
                    # Сохраняем время из списка новостей
                    if article.get('datetime'):
                        full_article_data.published_at = article['datetime']
                    
                    news_item = NewsItem(
                        source=source_url,
                        url=article['url'],
                        article_data=full_article_data
                    )
                    return news_item
                else:
                    self.logger.warning(f"ASYNC ARTICLES: Не удалось спарсить {article['url']}, используем базовые данные")
                    return None
                    
            except Exception as e:
                self.logger.error(f"ASYNC ARTICLES: Ошибка обработки статьи {article['url']}: {str(e)}")
                return None

    def _create_simple_article_data(self, article: dict) -> ArticleData:
        """
        Создает простые данные статьи без полного контента
        
        Args:
            article: Словарь с данными статьи
            
        Returns:
            ArticleData: Базовые данные статьи
        """
        return ArticleData(
            title=article.get('title', 'Новость без заголовка'),
            content_body=article.get('subheader', ''),  # Используем подзаголовок как краткое содержание
            published_at=article.get('datetime'),
            author=None,
            views=None,
            comments=[],
            likes=None,
            dislikes=None,
            video_url=None,
            image_urls=[]
        )

    def _extract_articles_with_titles(self, content: str, base_url: str) -> List[dict]:
        """
        Извлекает статьи с заголовками из HTML контента страницы pravda.com.ua
        
        Args:
            content: HTML контент страницы
            base_url: Базовый URL сайта
            
        Returns:
            List[dict]: Список словарей с ключами 'title', 'url', 'time', 'datetime', 'subheader'
        """
        soup = BeautifulSoup(content, 'html.parser')
        articles = []

        try:
            self.logger.info(f"ИЗВЛЕЧЕНИЕ: Начинаем извлечение статей из HTML контента")

            # Ищем контейнер со всеми новостями
            news_container = soup.find('div', class_='container_sub_news_list_wrapper mode1')
            if not news_container:
                self.logger.warning("ИЗВЛЕЧЕНИЕ: Не найден контейнер container_sub_news_list_wrapper mode1")
                return []

            # Ищем все статьи в контейнере
            news_articles = news_container.find_all('div', class_='article_news_list')
            self.logger.info(f"ИЗВЛЕЧЕНИЕ: Найдено {len(news_articles)} статей в контейнере")

            for article_div in news_articles:
                try:
                    # Извлекаем время
                    time_element = article_div.find('div', class_='article_time')
                    time_str = None
                    if time_element:
                        time_str = self._clean_text(time_element.get_text())
                        self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Найдено время {time_str}")

                    # Извлекаем заголовок и ссылку
                    content_div = article_div.find('div', class_='article_content')
                    if not content_div:
                        self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Не найден article_content")
                        continue

                    header_div = content_div.find('div', class_='article_header')
                    if not header_div:
                        self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Не найден article_header")
                        continue

                    link_element = header_div.find('a')
                    if not link_element or not link_element.get('href'):
                        self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Не найдена ссылка в заголовке")
                        continue

                    url = self._normalize_pravda_url(link_element.get('href'), base_url)
                    title = self._clean_text(link_element.get_text())

                    # Извлекаем подзаголовок
                    subheader_div = content_div.find('div', class_='article_subheader')
                    subheader = ""
                    if subheader_div:
                        subheader = self._clean_text(subheader_div.get_text())

                    if title and url and len(title) > 5:
                        # Создаем datetime из времени (используем сегодняшнюю дату)
                        article_datetime = self._combine_time_with_today(time_str)

                        article = {
                            'title': title,
                            'url': url,
                            'time': time_str,
                            'datetime': article_datetime,
                            'subheader': subheader
                        }
                        articles.append(article)

                        self.logger.debug(
                            f"ИЗВЛЕЧЕНИЕ: Найдена статья - {time_str} -> {article_datetime}: {title[:50]}...")
                    else:
                        self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Пропущена статья - некорректные данные")

                except Exception as e:
                    self.logger.warning(f"ИЗВЛЕЧЕНИЕ: Ошибка обработки статьи: {str(e)}")
                    continue

            self.logger.info(f"ИЗВЛЕЧЕНИЕ: Всего извлечено {len(articles)} статей")
            return articles

        except Exception as e:
            self.logger.error(f"ИЗВЛЕЧЕНИЕ: Критическая ошибка извлечения статей: {str(e)}")
            return []

    def _normalize_pravda_url(self, url: str, base_url: str) -> str:
        """
        Нормализует URL для pravda.com.ua
        Если ссылка относительная (начинается с /), добавляет домен
        Если ссылка полная, возвращает как есть
        
        Args:
            url: URL для нормализации
            base_url: Базовый URL
            
        Returns:
            str: Нормализованный URL
        """
        if url.startswith('http'):
            # Полная ссылка, возвращаем как есть
            return url
        elif url.startswith('/'):
            # Относительная ссылка, добавляем домен
            # Удаляем path из base_url если есть
            base_parts = base_url.split('/')
            if len(base_parts) > 3:
                base_url = '/'.join(base_parts[:3])
            return base_url + url
        else:
            # Просто добавляем к base_url
            return base_url + '/' + url

    def _combine_time_with_today(self, time_str: Optional[str]) -> Optional[datetime]:
        """
        Комбинирует сегодняшнюю дату со временем из строки
        
        Args:
            time_str: Строка времени в формате "HH:MM"
            
        Returns:
            datetime: Дата и время или None
        """
        try:
            today = datetime.now(timezone.utc).date()
            
            if time_str and time_str.strip():
                time_match = re.search(r'(\d{1,2}):(\d{2})', time_str.strip())
                if time_match:
                    hour, minute = time_match.groups()
                    combined_dt = datetime.combine(today, datetime.min.time().replace(
                        hour=int(hour), minute=int(minute)
                    )).replace(tzinfo=timezone.utc)
                    self.logger.debug(f"ВРЕМЯ: Скомбинировано: {combined_dt}")
                    return combined_dt
                else:
                    self.logger.warning(f"ВРЕМЯ: Не удалось распарсить время '{time_str}'")
            
            # Возвращаем полночь сегодняшнего дня
            fallback_dt = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
            self.logger.debug(f"ВРЕМЯ: Используем полночь: {fallback_dt}")
            return fallback_dt

        except Exception as e:
            self.logger.error(f"ВРЕМЯ: Ошибка комбинирования времени '{time_str}': {str(e)}")
            return datetime.now(timezone.utc)

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

            # Убираем www. для сравнения
            source_domain = source_domain.replace('www.', '')
            article_domain = article_domain.replace('www.', '')

            should_parse = source_domain == article_domain
            self.logger.debug(f"ПРОВЕРКА ДОМЕНА: {source_domain} == {article_domain} -> {should_parse}")

            return should_parse

        except Exception as e:
            self.logger.error(f"Ошибка проверки доменов {source_url} vs {article_url}: {str(e)}")
            return False

    async def _parse_full_article(self, url: str, client: str = "http") -> Optional[ArticleData]:
        """
        Парсит полный контент статьи с pravda.com.ua
        
        Args:
            url: URL статьи
            client: Тип клиента
            
        Returns:
            ArticleData: Полные данные статьи или None при ошибке
        """
        try:
            self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Начинаем парсинг статьи {url}")

            content = await self._get_content(url, client)
            if not content:
                self.logger.warning(f"ПОЛНЫЙ ПАРСИНГ: Не удалось получить контент для {url}")
                return None

            soup = BeautifulSoup(content, 'html.parser')

            # Ищем основной контейнер статьи
            container_element = soup.find('div', class_='container_sub_post_news')
            if not container_element:
                self.logger.warning(f"ПОЛНЫЙ ПАРСИНГ: Не найден контейнер container_sub_post_news в {url}")
                return None

            article_element = container_element.find('article', class_='post')
            if not article_element:
                self.logger.warning(f"ПОЛНЫЙ ПАРСИНГ: Не найден элемент article.post в {url}")
                return None

            # Извлекаем заголовок
            title = ""
            title_element = article_element.find('h1', class_='post_title')
            if title_element:
                title = self._clean_text(title_element.get_text())
                self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Найден заголовок: {title[:50]}...")
            
            if not title:
                self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Заголовок не найден, используем title страницы")
                title_tag = soup.find('title')
                if title_tag:
                    title = self._clean_text(title_tag.get_text())

            # Извлекаем автора
            author = None
            author_element = article_element.find('span', class_='post_author')
            if author_element:
                author_link = author_element.find('a')
                if author_link:
                    author = self._clean_text(author_link.get_text())
                    self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Найден автор: {author}")

            # Извлекаем дату и время из post_time
            published_at = None
            time_element = article_element.find('div', class_='post_time')
            if time_element:
                time_text = self._clean_text(time_element.get_text())
                # Извлекаем дату в формате "П'ятниця, 29 серпня 2025, 13:04"
                published_at = self._parse_pravda_datetime(time_text)
                self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Найдена дата: {published_at}")

            # Извлекаем просмотры
            views = None
            views_element = article_element.find('div', class_='post_views')
            if views_element:
                views_text = views_element.get_text()
                views_match = re.search(r'(\d+)', views_text)
                if views_match:
                    views = int(views_match.group(1))
                    self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Найдено просмотров: {views}")

            # Извлекаем изображения
            image_urls = []
            photo_element = article_element.find('div', class_='post_photo_news')
            if photo_element:
                img_element = photo_element.find('img', class_='post_photo_news_img')
                if img_element and img_element.get('src'):
                    img_url = img_element.get('src')
                    normalized_url = self._normalize_pravda_url(img_url, self.base_url)
                    image_urls.append(normalized_url)
                    self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Найдено изображение: {normalized_url}")

            # Извлекаем основной текст
            content_body = ""
            text_element = article_element.find('div', class_='post_text')
            if text_element:
                # Убираем рекламные блоки
                for ad_block in text_element.find_all('div', class_=['advtext_mob', 'nts-ad']):
                    ad_block.decompose()
                
                paragraphs = text_element.find_all(['p', 'li'])
                content_parts = []
                for p in paragraphs:
                    text = self._clean_text(p.get_text())
                    if text and len(text) > 10:  # Игнорируем очень короткие строки
                        content_parts.append(text)
                content_body = '\n\n'.join(content_parts)
                self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Извлечен контент ({len(content_body)} символов)")

            # Извлекаем теги как комментарии
            tags = []
            tags_element = article_element.find('div', class_='post_tags')
            if tags_element:
                tag_links = tags_element.find_all('a')
                for tag_link in tag_links:
                    tag = self._clean_text(tag_link.get_text())
                    if tag:
                        tags.append(tag)
                if tags:
                    self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Найдены теги: {', '.join(tags)}")

            self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Успешно спарсена статья {url}")

            return ArticleData(
                title=title or "Статья без заголовка",
                content_body=content_body,
                image_urls=image_urls,
                published_at=published_at or datetime.now(timezone.utc),
                author=author,
                views=views,
                comments=tags,  # Используем теги как комментарии
                likes=None,
                dislikes=None,
                video_url=None
            )

        except Exception as e:
            self.logger.error(f"ПОЛНЫЙ ПАРСИНГ: Ошибка парсинга статьи {url}: {str(e)}")
            return None

    def _parse_pravda_datetime(self, time_text: str) -> Optional[datetime]:
        """
        Парсит дату и время в формате pravda: "П'ятниця, 29 серпня 2025, 13:04"
        
        Args:
            time_text: Строка с датой и временем
            
        Returns:
            datetime: Распарсенная дата или None
        """
        try:
            if not time_text:
                return None

            # Убираем автора из строки (до " — ")
            if " — " in time_text:
                time_text = time_text.split(" — ", 1)[1]

            # Словарь украинских месяцев
            months_uk = {
                'січня': 1, 'лютого': 2, 'березня': 3, 'квітня': 4,
                'травня': 5, 'червня': 6, 'липня': 7, 'серпня': 8,
                'вересня': 9, 'жовтня': 10, 'листопада': 11, 'грудня': 12
            }

            # Паттерн: "П'ятниця, 29 серпня 2025, 13:04"
            pattern = r'(\d{1,2})\s+([а-яёє]+)\s+(\d{4}),\s*(\d{1,2}):(\d{2})'
            match = re.search(pattern, time_text.lower())
            
            if match:
                day, month_name, year, hour, minute = match.groups()
                month = months_uk.get(month_name.lower())
                
                if month:
                    combined_dt = datetime(
                        year=int(year),
                        month=month,
                        day=int(day),
                        hour=int(hour),
                        minute=int(minute),
                        tzinfo=timezone.utc
                    )
                    
                    self.logger.debug(f"ВРЕМЯ: Распарсено {time_text} -> {combined_dt}")
                    return combined_dt

            self.logger.warning(f"ВРЕМЯ: Не удалось распарсить дату '{time_text}'")
            return None

        except Exception as e:
            self.logger.error(f"ВРЕМЯ: Ошибка парсинга даты '{time_text}': {str(e)}")
            return None

    async def _parse_article(self, url: str, client: str = "http") -> Optional[ArticleData]:
        """
        Парсит отдельную статью (использует полный парсинг)
        """
        return await self._parse_full_article(url, client)
