from typing import List, Optional
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import re
import logging
import asyncio
from urllib.parse import urlparse, urljoin

from app.parsers.news_parsers.base_news_parser import BaseNewsParser
from app.models.news import NewsCollection, NewsItem, ArticleData


class PolitekaNewsParser(BaseNewsParser):
    """
    Парсер новостей для politeka.net/uk/newsfeed
    Поддерживает парсинг новостей с пагинацией по страницам
    """

    def __init__(self):
        super().__init__()
        self.base_url = "https://politeka.net"
        self.news_url = "https://politeka.net/uk/newsfeed"
        self.logger = logging.getLogger(self.__class__.__name__)

        # Семафоры для ограничения одновременных запросов
        self.page_semaphore = asyncio.Semaphore(5)
        self.article_semaphore = asyncio.Semaphore(10)

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
            self.logger.info(f"Клиент: {client}, граничная дата: {until_date}")

            # Генерируем URL страниц для парсинга
            page_urls = self._generate_page_urls(url, max_pages=10)
            self.logger.info(f"Сгенерировано {len(page_urls)} URL-ов страниц")

            # Асинхронно получаем все статьи со страниц
            all_articles = await self._fetch_all_pages_async(page_urls, client, until_date)
            
            self.logger.info(f"ASYNC: Завершено. Найдено {len(all_articles)} статей со всех страниц")

            # Убираем дубликаты
            unique_articles = []
            seen_urls = set()
            for article in all_articles:
                if article['url'] not in seen_urls:
                    unique_articles.append(article)
                    seen_urls.add(article['url'])

            self.logger.info(
                f"ДЕДУПЛИКАЦИЯ: После удаления дубликатов осталось {len(unique_articles)} уникальных статей")

            # Асинхронно обрабатываем статьи
            news_items = await self._process_articles_async(unique_articles, url, client, until_date)

            self.logger.info(f"ИТОГО: Создано {len(news_items)} объектов новостей")

            return NewsCollection(
                source=url,
                items=news_items,
                total_items=len(news_items),
                parse_status="success",
                error_message=None
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

    def _generate_page_urls(self, base_url: str, max_pages: int = 10) -> List[str]:
        """
        Генерирует URL-ы страниц для парсинга
        
        Args:
            base_url: Базовый URL
            max_pages: Максимальное количество страниц
            
        Returns:
            List[str]: Список URL-ов страниц
        """
        urls = []
        
        # Первая страница - базовый URL
        urls.append(base_url)
        
        # Остальные страницы с параметром page
        for page in range(2, max_pages + 1):
            if '?' in base_url:
                page_url = f"{base_url}&page={page}"
            else:
                page_url = f"{base_url}?page={page}"
            urls.append(page_url)
        
        self.logger.info(f"ГЕНЕРАЦИЯ URL: Сгенерировано {len(urls)} URL-ов страниц")
        return urls

    async def _fetch_all_pages_async(self, page_urls: List[str], client: str, until_date: Optional[datetime]) -> List[dict]:
        """
        Асинхронно получает контент всех страниц и извлекает статьи
        
        Args:
            page_urls: Список URL страниц
            client: Тип клиента
            until_date: Граничная дата для остановки парсинга
            
        Returns:
            List[dict]: Объединенный список всех статей
        """
        self.logger.info(f"ASYNC PAGES: Начинаем параллельное получение {len(page_urls)} страниц")

        all_articles = []
        
        # Парсим страницы последовательно, чтобы контролировать until_date
        for i, page_url in enumerate(page_urls):
            page_articles = await self._fetch_single_page(page_url, client)
            
            if not page_articles:
                self.logger.info(f"ASYNC PAGES: Страница {i+1} пуста, останавливаем парсинг")
                break
            
            # Проверяем граничную дату
            if until_date:
                valid_articles = []
                should_stop = False
                
                for article in page_articles:
                    if self._is_date_valid(article.get('datetime'), until_date):
                        valid_articles.append(article)
                    else:
                        # Если нашли статью старше граничной даты, останавливаемся
                        should_stop = True
                        break
                
                all_articles.extend(valid_articles)
                
                if should_stop:
                    self.logger.info(f"ASYNC PAGES: Достигнута граничная дата на странице {i+1}, останавливаем парсинг")
                    break
            else:
                all_articles.extend(page_articles)
            
            self.logger.info(f"ASYNC PAGES: Страница {i+1} - найдено {len(page_articles)} статей")
        
        self.logger.info(f"ASYNC PAGES: Завершено. Всего статей: {len(all_articles)}")
        return all_articles

    async def _fetch_single_page(self, page_url: str, client: str) -> List[dict]:
        """
        Получает контент одной страницы и извлекает статьи
        
        Args:
            page_url: URL страницы
            client: Тип клиента
            
        Returns:
            List[dict]: Список статей со страницы
        """
        async with self.page_semaphore:
            try:
                self.logger.debug(f"ASYNC PAGES: Загружаем {page_url}")
                
                content = await self._get_content(page_url, client)
                if not content:
                    self.logger.warning(f"ASYNC PAGES: Не удалось получить контент для {page_url}")
                    return []

                page_articles = self._extract_articles_with_titles(content, self.base_url)
                
                self.logger.debug(f"ASYNC PAGES: {page_url} - извлечено {len(page_articles)} статей")
                return page_articles
                
            except Exception as e:
                self.logger.error(f"ASYNC PAGES: Ошибка обработки страницы {page_url}: {str(e)}")
                return []

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
            content_body=article.get('description', ''),
            published_at=article.get('datetime'),
            author=None,
            views=None,
            comments=[],
            likes=None,
            dislikes=None,
            video_url=None,
            image_urls=article.get('image_urls', [])
        )

    def _extract_articles_with_titles(self, content: str, base_url: str) -> List[dict]:
        """
        Извлекает статьи с заголовками из HTML контента страницы politeka.net
        
        Args:
            content: HTML контент страницы
            base_url: Базовый URL сайта
            
        Returns:
            List[dict]: Список словарей с ключами 'title', 'url', 'time', 'datetime', 'description', 'image_urls'
        """
        soup = BeautifulSoup(content, 'html.parser')
        articles = []

        try:
            self.logger.info(f"ИЗВЛЕЧЕНИЕ: Начинаем извлечение статей из HTML контента")

            # Ищем контейнер со всеми новостями
            news_container = soup.find('div', class_='col-lg-8 col-md-12')
            if not news_container:
                self.logger.warning("ИЗВЛЕЧЕНИЕ: Не найден контейнер col-lg-8 col-md-12")
                return []

            # Ищем все статьи в контейнере
            news_articles = news_container.find_all('div', class_='b_post b_post--image-sm')
            self.logger.info(f"ИЗВЛЕЧЕНИЕ: Найдено {len(news_articles)} статей в контейнере")

            for article_div in news_articles:
                try:
                    # Извлекаем ссылку и заголовок
                    title_link = article_div.find('a')
                    if not title_link or not title_link.get('href'):
                        self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Не найдена ссылка")
                        continue

                    url = title_link.get('href')
                    # URL уже полный, нормализуем если нужно
                    if not url.startswith('http'):
                        url = urljoin(base_url, url)

                    # Извлекаем заголовок из h4
                    title_element = article_div.find('h4')
                    if not title_element:
                        self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Не найден заголовок h4")
                        continue

                    title = self._clean_text(title_element.get_text())

                    # Извлекаем дату
                    date_element = article_div.find('div', class_='b_post--date')
                    time_str = None
                    if date_element:
                        time_str = self._clean_text(date_element.get_text())
                        self.logger.debug(f"ИЗВЛЕЧЕНИЕ: Найдено время {time_str}")

                    # Извлекаем описание
                    description_element = article_div.find('div', class_='b_post--description')
                    description = ""
                    if description_element:
                        description = self._clean_text(description_element.get_text())

                    # Извлекаем изображения
                    image_urls = []
                    img_element = article_div.find('img')
                    if img_element and img_element.get('src'):
                        img_url = img_element.get('src')
                        if not img_url.startswith('http'):
                            img_url = urljoin(base_url, img_url)
                        image_urls.append(img_url)

                    if title and url and len(title) > 5:
                        # Создаем datetime из времени
                        article_datetime = self._parse_politeka_date(time_str)

                        article = {
                            'title': title,
                            'url': url,
                            'time': time_str,
                            'datetime': article_datetime,
                            'description': description,
                            'image_urls': image_urls
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

    def _parse_politeka_date(self, time_str: Optional[str]) -> Optional[datetime]:
        """
        Парсит дату в формате politeka: "13:37 28.08"
        Автоматически добавляет текущий год если не указан
        
        Args:
            time_str: Строка времени в формате "ЧЧ:ММ ДД.ММ" или "ЧЧ:ММ ДД.ММ.ГГГГ"
            
        Returns:
            datetime: Дата и время или None
        """
        try:
            if not time_str or not time_str.strip():
                return datetime.now(timezone.utc)

            time_str = time_str.strip()
            
            # Паттерн: "13:37 28.08" или "13:37 28.08.2025"
            pattern = r'(\d{1,2}):(\d{2})\s+(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?'
            match = re.search(pattern, time_str)
            
            if match:
                hour, minute, day, month, year = match.groups()
                
                # Если год не указан, используем текущий
                if year is None:
                    year = datetime.now(timezone.utc).year
                else:
                    year = int(year)
                
                combined_dt = datetime(
                    year=year,
                    month=int(month),
                    day=int(day),
                    hour=int(hour),
                    minute=int(minute),
                    tzinfo=timezone.utc
                )
                
                self.logger.debug(f"ВРЕМЯ: Распарсено {time_str} -> {combined_dt}")
                return combined_dt
            else:
                self.logger.warning(f"ВРЕМЯ: Не удалось распарсить время '{time_str}'")
                return datetime.now(timezone.utc)

        except Exception as e:
            self.logger.error(f"ВРЕМЯ: Ошибка парсинга времени '{time_str}': {str(e)}")
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
        Возвращает True если домены относятся к politeka.net
        
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

            # Проверяем, что оба домена относятся к politeka.net
            # Поддерживаем поддомены: *.politeka.net
            source_is_politeka = source_domain == 'politeka.net' or source_domain.endswith('.politeka.net')
            article_is_politeka = article_domain == 'politeka.net' or article_domain.endswith('.politeka.net')

            should_parse = source_is_politeka and article_is_politeka
            self.logger.debug(f"ПРОВЕРКА ДОМЕНА: {source_domain} (politeka: {source_is_politeka}) vs {article_domain} (politeka: {article_is_politeka}) -> {should_parse}")

            return should_parse

        except Exception as e:
            self.logger.error(f"Ошибка проверки доменов {source_url} vs {article_url}: {str(e)}")
            return False

    async def _parse_full_article(self, url: str, client: str = "http") -> Optional[ArticleData]:
        """
        Парсит полный контент статьи с politeka.net
        
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
            article_element = soup.find('article', class_='getstat-article')
            if not article_element:
                self.logger.warning(f"ПОЛНЫЙ ПАРСИНГ: Не найден элемент article.getstat-article в {url}")
                return None

            # Извлекаем заголовок
            title = ""
            title_element = article_element.find('h1')
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
            author_element = article_element.find('div', class_='author')
            if author_element:
                author_link = author_element.find('a')
                if author_link:
                    author = self._clean_text(author_link.get_text())
                    self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Найден автор: {author}")

            # Извлекаем дату и время из article-date
            published_at = None
            date_element = article_element.find('div', class_='article-date')
            if date_element:
                date_text = self._clean_text(date_element.get_text())
                # Извлекаем дату в формате "вчора, 13:37" или "28.08, 13:37"
                published_at = self._parse_politeka_article_date(date_text)
                self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Найдена дата: {published_at}")

            # Извлекаем изображения
            image_urls = []
            image_element = article_element.find('div', class_='article-image main')
            if image_element:
                img_element = image_element.find('img')
                if img_element and img_element.get('src'):
                    img_url = img_element.get('src')
                    if not img_url.startswith('http'):
                        img_url = urljoin(self.base_url, img_url)
                    image_urls.append(img_url)
                    self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Найдено изображение: {img_url}")

            # Извлекаем основной текст
            content_body = ""
            body_element = article_element.find('div', class_='article-body')
            if body_element:
                # Убираем рекламные блоки
                for ad_block in body_element.find_all('div', class_='ai-placement'):
                    ad_block.decompose()
                
                paragraphs = body_element.find_all('p')
                content_parts = []
                for p in paragraphs:
                    text = self._clean_text(p.get_text())
                    if text and len(text) > 10:  # Игнорируем очень короткие строки
                        content_parts.append(text)
                content_body = '\n\n'.join(content_parts)
                self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Извлечен контент ({len(content_body)} символов)")

            self.logger.debug(f"ПОЛНЫЙ ПАРСИНГ: Успешно спарсена статья {url}")

            return ArticleData(
                title=title or "Статья без заголовка",
                content_body=content_body,
                image_urls=image_urls,
                published_at=published_at or datetime.now(timezone.utc),
                author=author,
                views=None,  # Просмотры не указаны в структуре
                comments=[],
                likes=None,
                dislikes=None,
                video_url=None
            )

        except Exception as e:
            self.logger.error(f"ПОЛНЫЙ ПАРСИНГ: Ошибка парсинга статьи {url}: {str(e)}")
            return None

    def _parse_politeka_article_date(self, date_text: str) -> Optional[datetime]:
        """
        Парсит дату в формате politeka: "вчора, 13:37" или "28.08, 13:37"
        
        Args:
            date_text: Строка с датой и временем
            
        Returns:
            datetime: Распарсенная дата или None
        """
        try:
            if not date_text:
                return None

            date_text = date_text.strip()
            
            # Словарь украинских относительных дат
            relative_dates = {
                'вчора': -1,
                'сьогодні': 0,
                'позавчора': -2
            }

            # Паттерн для относительных дат: "вчора, 13:37"
            relative_pattern = r'(вчора|сьогодні|позавчора),\s*(\d{1,2}):(\d{2})'
            relative_match = re.search(relative_pattern, date_text.lower())
            
            if relative_match:
                relative_day, hour, minute = relative_match.groups()
                days_offset = relative_dates.get(relative_day.lower(), 0)
                
                today = datetime.now(timezone.utc).date()
                target_date = today + timedelta(days=days_offset)
                
                combined_dt = datetime.combine(target_date, datetime.min.time().replace(
                    hour=int(hour), minute=int(minute)
                )).replace(tzinfo=timezone.utc)
                
                self.logger.debug(f"ВРЕМЯ: Распарсено относительную дату {date_text} -> {combined_dt}")
                return combined_dt

            # Паттерн для конкретных дат: "28.08, 13:37"
            specific_pattern = r'(\d{1,2})\.(\d{1,2}),\s*(\d{1,2}):(\d{2})'
            specific_match = re.search(specific_pattern, date_text)
            
            if specific_match:
                day, month, hour, minute = specific_match.groups()
                
                # Используем текущий год
                current_year = datetime.now(timezone.utc).year
                
                combined_dt = datetime(
                    year=current_year,
                    month=int(month),
                    day=int(day),
                    hour=int(hour),
                    minute=int(minute),
                    tzinfo=timezone.utc
                )
                
                self.logger.debug(f"ВРЕМЯ: Распарсено конкретную дату {date_text} -> {combined_dt}")
                return combined_dt

            self.logger.warning(f"ВРЕМЯ: Не удалось распарсить дату '{date_text}'")
            return None

        except Exception as e:
            self.logger.error(f"ВРЕМЯ: Ошибка парсинга даты '{date_text}': {str(e)}")
            return None

    async def _parse_article(self, url: str, client: str = "http") -> Optional[ArticleData]:
        """
        Парсит отдельную статью (использует полный парсинг)
        """
        return await self._parse_full_article(url, client)
