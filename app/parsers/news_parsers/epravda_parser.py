from typing import List, Optional
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import re
import logging

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
            
            # Определяем диапазон дат для парсинга
            start_date = datetime.now(timezone.utc).date()
            end_date = until_date.date() if until_date else start_date
            
            self.logger.info(f"Парсим от {start_date} до {end_date}")
            
            # Получаем URL-ы для всех дат в диапазоне
            date_urls = self._generate_date_urls(start_date, end_date)
            self.logger.info(f"Сгенерировано {date_urls}")
            
            all_articles = []
            processed_dates = 0
            
            # Парсим каждую дату отдельно
            for date_url in date_urls:
                processed_dates += 1
                self.logger.info(f"Обрабатываем {processed_dates}/{len(date_urls)} - {date_url}")
                
                try:
                    # Получаем контент страницы с датой
                    content = await self._get_content(date_url, client)
                    if not content:
                        self.logger.warning(f"ПАГИНАЦИЯ: Не удалось получить контент для {date_url}")
                        continue
                    
                    # Извлекаем дату из URL для текущей страницы
                    page_date = self._extract_date_from_date_url(date_url)
                    self.logger.info(f"ПАГИНАЦИЯ: Обрабатываем дату {page_date}")
                    
                    # Извлекаем статьи с заголовками
                    page_articles = self._extract_articles_with_titles(content, self.base_url, page_date)
                    self.logger.info(f"ПАГИНАЦИЯ: Найдено {len(page_articles)} статей на странице {date_url}")
                    
                    if page_articles:
                        all_articles.extend(page_articles)
                        self.logger.info(f"ПАГИНАЦИЯ: Добавлено {len(page_articles)} статей, всего: {len(all_articles)}")
                    else:
                        self.logger.warning(f"ПАГИНАЦИЯ: На странице {date_url} статьи не найдены")
                        
                except Exception as e:
                    self.logger.error(f"ПАГИНАЦИЯ: Ошибка обработки страницы {date_url}: {str(e)}")
                    continue
            
            self.logger.info(f"ПАГИНАЦИЯ: Завершено. Обработано {processed_dates} страниц, найдено {len(all_articles)} статей")
            
            # Убираем дубликаты по URL
            unique_articles = []
            seen_urls = set()
            for article in all_articles:
                if article['url'] not in seen_urls:
                    unique_articles.append(article)
                    seen_urls.add(article['url'])
            
            self.logger.info(f"ДЕДУПЛИКАЦИЯ: После удаления дубликатов осталось {len(unique_articles)} уникальных статей")
            
            # Создаем объекты новостей
            news_items = []
            for article in unique_articles:
                article_data = ArticleData(
                    title=article.get('title', 'Новость без заголовка'),
                    content_body="",  # Только заголовки и ссылки
                    published_at=article.get('datetime')
                )
                
                news_item = NewsItem(
                    source=url,
                    url=article['url'],
                    article_data=article_data
                )
                
                # Дополнительная фильтрация по дате
                if until_date is None or self._is_date_valid(article.get('datetime'), until_date):
                    news_items.append(news_item)
            
            self.logger.info(f"ИТОГО: Создано {len(news_items)} объектов новостей")
            
            return NewsCollection(
                source=url,
                items=news_items,
                total_items=len(news_items),
                parse_status="success"
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
            
            # Переходим к предыдущему дню
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
            # Паттерн для date_DDMMYYYY
            date_pattern = r'date_(\d{2})(\d{2})(\d{4})'
            match = re.search(date_pattern, url)
            if match:
                day, month, year = match.groups()
                return datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
                
        except Exception as e:
            self.logger.error(f"Ошибка извлечения даты из URL {url}: {str(e)}")
            
        return None

    def _extract_articles_with_titles(self, content: str, base_url: str, page_date: Optional[datetime] = None) -> List[dict]:
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
            
            # Ищем основной контейнер с новостями
            news_container = soup.find('div', class_='section_articles_grid_wrapper')
            if not news_container:
                self.logger.warning("ИЗВЛЕЧЕНИЕ: Не найден контейнер section_articles_grid_wrapper")
                return []
            
            # Ищем все статьи в контейнере
            news_articles = news_container.find_all('div', class_='article_news')
            self.logger.info(f"ИЗВЛЕЧЕНИЕ: Найдено {len(news_articles)} статей в контейнере")
            
            for article_div in news_articles:
                try:
                    # Извлекаем время публикации
                    time_element = article_div.find('div', class_='article_date')
                    time_str = None
                    if time_element:
                        time_str = self._clean_text(time_element.get_text())
                        self.logger.info(f"ИЗВЛЕЧЕНИЕ: Найдено время {time_str}")
                    else:
                        self.logger.warning(f"ИЗВЛЕЧЕНИЕ: Время не найдено в article_date")
                    
                    # Извлекаем заголовок и ссылку
                    title_element = article_div.find('div', class_='article_title')
                    if title_element:
                        link_element = title_element.find('a')
                        if link_element and link_element.get('href'):
                            url = self._normalize_url(link_element.get('href'), base_url)
                            title = self._clean_text(link_element.get_text())
                            
                            if title and url and len(title) > 10:
                                # Создаем datetime с датой страницы и временем из элемента
                                article_datetime = self._combine_date_and_time(page_date, time_str)
                                
                                article = {
                                    'title': title,
                                    'url': url,
                                    'time': time_str,
                                    'datetime': article_datetime
                                }
                                articles.append(article)
                                
                                self.logger.info(f"ИЗВЛЕЧЕНИЕ: Найдена статья - {time_str} -> {article_datetime}: {title[:50]}...")
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
            


    def _find_news_link_near_time(self, element) -> Optional:
        """
        Ищет ссылку на новость рядом с элементом времени
        """
        # Ищем в том же элементе (только если это BeautifulSoup элемент)
        if hasattr(element, 'find'):
            link = element.find('a', href=re.compile(r'/[a-z]+/.*-\d{6}/?$'))
            if link:
                return link
        
        # Ищем в следующих элементах того же уровня
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
        
        # Ищем в родительском элементе
        if hasattr(element, 'parent') and element.parent and hasattr(element.parent, 'find'):
            link = element.parent.find('a', href=re.compile(r'/[a-z]+/.*-\d{6}/?$'))
            if link:
                return link
        
        return None

    def _find_time_near_link(self, link) -> Optional[str]:
        """
        Ищет время рядом со ссылкой
        """
        # Ищем в том же элементе
        if link.parent and hasattr(link.parent, 'find'):
            time_element = link.parent.find(string=re.compile(r'\d{1,2}:\d{2}'))
            if time_element:
                return time_element.strip()
        
        # Ищем в предыдущих элементах
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

    async def _parse_article(self, url: str, client: str = "http") -> Optional[ArticleData]:
        """
        Парсит отдельную статью (базовая реализация для совместимости)
        """
        return ArticleData(
            title="Статья",
            content_body="",
            published_at=datetime.now(timezone.utc)
        )