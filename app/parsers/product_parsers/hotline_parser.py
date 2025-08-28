import httpx
import re
import asyncio
from typing import List, Optional, Dict, Any

from app.parsers.base import BaseParser, IProductParser
from app.models.product import ProductOffer, Product


class HotlineParser(BaseParser, IProductParser):
    """
    Парсер для hotline.ua использующий официальный GraphQL API
    Извлекает данные о товарах и офферах через /svc/frontend-api/graphql
    """

    def __init__(self):
        super().__init__()
        self.base_url = "https://hotline.ua"
        self.graphql_url = "https://hotline.ua/svc/frontend-api/graphql"
        self.session_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Referer': 'https://hotline.ua/',
            'Origin': 'https://hotline.ua',
            'Accept-Language': 'uk-UA,uk;q=0.9,en;q=0.8,ru;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'X-Requested-With': 'XMLHttpRequest'
        }

    async def parse_product(
            self,
            url: str,
            timeout_limit: int = 30,
            count_limit: Optional[int] = None,
            sort_by: str = "price"
    ) -> Product:
        """
        Парсит продукт по URL используя GraphQL API
        Args:
            url: URL страницы товара на hotline.ua
            timeout_limit: Таймаут запроса в секундах
            count_limit: Максимальное количество офферов
            sort_by: Критерий сортировки офферов (price, price_desc, shop, shop_desc)
        Returns:
            Product: Объект товара с офферами
        Raises:
            ValueError: При некорректных входных данных
            Exception: При ошибках парсинга
        """
        try:
            self._validate_parameters(timeout_limit, count_limit, sort_by)

            if not self._validate_url(url, "hotline.ua"):
                raise ValueError(f"Неподдерживаемый URL: {url}")

            path = await self._extract_path_from_url(url)
            if not path:
                raise ValueError(f"Не удается извлечь path товара из URL: {url}")

            self.logger.info(f"Извлечен path: {path} из URL: {url}")

            async with httpx.AsyncClient(
                    timeout=timeout_limit,
                    headers=self.session_headers,
                    follow_redirects=True
            ) as client:
                x_token = await self._initialize_session(client, url)

                offers_data = await self._get_offers_via_graphql(client, path, x_token, url)

                if not offers_data:
                    self.logger.warning(f"Не найдены офферы для path: {path}")
                    return Product(url=url, offers=[])

                offers = await self._parse_offers(offers_data, sort_by, count_limit, client)

                self.logger.info(f"Найдено {len(offers)} офферов для товара: {url}")

                return Product(
                    url=url,
                    offers=offers
                )

        except Exception as e:
            self.logger.error(f"Ошибка парсинга продукта {url}: {str(e)}")
            raise

    async def _extract_path_from_url(self, url: str) -> Optional[str]:
        """
        Извлекает path товара из URL hotline.ua
        """
        try:
            clean_url = url.split('?')[0].split('#')[0]
            patterns = [
                r'/([^/]+)/?$',  # Последний сегмент URL
                r'/([^/]+)/$',  # Последний сегмент с обязательным слешем
                r'/([a-zA-Z0-9-_]+)/?$',  # Альфанумерический последний сегмент
            ]

            for pattern in patterns:
                match = re.search(pattern, clean_url)
                if match:
                    path = match.group(1)
                    if path not in ['ua', 'uk', 'ru', 'en']:
                        return path

            segments = [s for s in clean_url.split('/') if s]
            if len(segments) >= 2:
                potential_path = segments[-1]
                if potential_path and potential_path not in ['ua', 'uk', 'ru', 'en']:
                    return potential_path
                elif len(segments) >= 2:
                    potential_path = segments[-2]
                    if potential_path and potential_path not in ['ua', 'uk', 'ru', 'en']:
                        return potential_path

            return None

        except Exception as e:
            self.logger.error(f"Ошибка извлечения path из URL {url}: {str(e)}")
            return None

    async def _get_offers_via_graphql(self, client: httpx.AsyncClient, path: str, x_token: str, referer_url: str) -> \
            List[Dict[str, Any]]:
        """
        Получает офферы через GraphQL API hotline.ua
        """

        query = """
        query getOffers($path: String!, $cityId: Int!) {
          byPathQueryProduct(path: $path, cityId: $cityId) {
            id
            offers(first: 1000) {
              totalCount
              edges {
                node {
                  _id
                  condition
                  conditionId
                  conversionUrl
                  descriptionFull
                  descriptionShort
                  firmId
                  firmLogo
                  firmTitle
                  firmExtraInfo
                  guaranteeTerm
                  guaranteeTermName
                  guaranteeType
                  hasBid
                  historyId
                  payment
                  price
                  reviewsNegativeNumber
                  reviewsPositiveNumber
                  bid
                  shipping
                  delivery {
                    deliveryMethods
                    hasFreeDelivery
                    isSameCity
                    name
                    countryCodeFirm
                    __typename
                  }
                  sortPlace
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
        }
        """

        variables = {
            "path": path,
            "cityId": 370
        }

        payload = {
            "operationName": "getOffers",
            "variables": variables,
            "query": query
        }

        try:
            self.logger.info(f"Выполняется GraphQL запрос для path: {path}")
            self.logger.debug(f"GraphQL payload: {payload}")

            graphql_headers = {
                **self.session_headers,
                'x-token': x_token,
                'x-language': 'uk',
                'x-referer': referer_url,
                'x-request-id': self._generate_request_id()
            }

            response = await client.post(
                self.graphql_url,
                json=payload,
                headers=graphql_headers
            )

            if response.status_code != 200:
                self.logger.error(f"GraphQL запрос вернул статус {response.status_code}: {response.text}")
                return []

            data = response.json()

            if "errors" in data:
                self.logger.error(f"GraphQL ошибки: {data['errors']}")
                return []

            try:
                self.logger.info(f"Полный ответ GraphQL {data}")
                product_data = data["data"]["byPathQueryProduct"]
                if not product_data:
                    self.logger.warning(f"Товар не найден для path: {path}")
                    return []

                offers_data = product_data["offers"]["edges"]
                self.logger.info(f"Получено {len(offers_data)} офферов через GraphQL")

                return [edge["node"] for edge in offers_data]

            except (KeyError, TypeError) as e:
                self.logger.error(f"Ошибка парсинга ответа GraphQL: {str(e)}")
                self.logger.debug(f"Ответ GraphQL: {data}")
                return []

        except Exception as e:
            self.logger.error(f"Ошибка выполнения GraphQL запроса: {str(e)}")
            return []

    async def _parse_offers(
            self,
            offers_data: List[Dict[str, Any]],
            sort_by: str,
            count_limit: Optional[int] = None,
            client: httpx.AsyncClient = None
    ) -> List[ProductOffer]:
        """
        Преобразует сырые данные офферов из GraphQL в модели Pydantic
        Использует параллельную обработку для получения original_url
        """
        self.logger.info(f"Начинаем обработку {len(offers_data)} офферов")

        raw_offers = []
        hotline_urls = []

        for i, offer_data in enumerate(offers_data):
            try:
                self.logger.debug(f"Обрабатываем оффер {i + 1}/{len(offers_data)}")

                price = self._extract_price(offer_data.get("price", 0))

                if price <= 0:
                    self.logger.debug(f"Пропускаем оффер {i + 1} без цены")
                    continue

                condition_id = offer_data.get("conditionId", 1)
                condition = offer_data.get("condition", "").lower()

                is_used = not (condition_id == 0 or condition == "новый")

                self.logger.debug(
                    f"Состояние товара: conditionId={condition_id}, condition='{condition}' -> is_used={is_used}")

                conversion_url = offer_data.get("conversionUrl", "")
                if conversion_url:
                    offer_url = f"https://hotline.ua{conversion_url}"
                else:
                    offer_url = ""

                shop_name = offer_data.get("firmTitle", "Unknown Shop")

                title = offer_data.get("descriptionShort") or offer_data.get("descriptionFull", "")
                if not title:
                    title = f"Товар от {shop_name}"

                raw_offer = {
                    'url': offer_url,
                    'title': title,
                    'shop': shop_name,
                    'price': price,
                    'is_used': is_used,
                    'index': len(raw_offers)  # Для сопоставления с результатами редиректов
                }
                raw_offers.append(raw_offer)
                hotline_urls.append(offer_url)

                self.logger.debug(f"Оффер {i + 1}: {shop_name} - {price} грн - {title[:50]}...")

            except Exception as e:
                self.logger.warning(f"Ошибка парсинга оффера {i + 1}: {str(e)}")
                continue

        self.logger.info(f"Подготовлено {len(raw_offers)} офферов для обработки редиректов")

        if client and hotline_urls:
            self.logger.info("Начинаем параллельное получение original_url...")
            original_urls = await self._get_original_urls_batch(client, hotline_urls)
        else:
            self.logger.warning("Нет клиента для получения original_url, используем hotline URLs")
            original_urls = hotline_urls

        offers = []
        for i, raw_offer in enumerate(raw_offers):
            try:
                original_url = original_urls[i] if i < len(original_urls) else raw_offer['url']

                offer = ProductOffer(
                    url=raw_offer['url'],
                    original_url=original_url,
                    title=raw_offer['title'],
                    shop=raw_offer['shop'],
                    price=raw_offer['price'],
                    is_used=raw_offer['is_used']
                )
                offers.append(offer)

                self.logger.debug(f"Создан оффер: {raw_offer['shop']} -> {original_url}")

            except Exception as e:
                self.logger.warning(f"Ошибка создания оффера {i + 1}: {str(e)}")
                continue

        self.logger.info(f"Успешно создано {len(offers)} офферов")

        offers = self._sort_offers(offers, sort_by)
        self.logger.debug(f"Офферы отсортированы по: {sort_by}")

        if count_limit and count_limit > 0:
            original_count = len(offers)
            offers = offers[:count_limit]
            self.logger.info(f"Применен лимит: {original_count} -> {len(offers)} офферов")

        self.logger.info(f"Финальный результат: {len(offers)} офферов готово к возврату")
        return offers

    async def _get_original_urls_batch(self, client: httpx.AsyncClient, hotline_urls: List[str]) -> List[str]:
        """
        Параллельно получает original_url для списка URLs
        
        Args:
            client: HTTP клиент
            hotline_urls: Список URL hotline.ua для редиректов
            
        Returns:
            List[str]: Список финальных URLs в том же порядке
        """
        self.logger.info(f"Получаем original_url для {len(hotline_urls)} офферов параллельно")

        tasks = [
            self._get_original_url(client, url)
            for url in hotline_urls
        ]

        try:
            original_urls = await asyncio.gather(*tasks, return_exceptions=True)

            results = []
            for i, result in enumerate(original_urls):
                if isinstance(result, Exception):
                    self.logger.warning(f"Ошибка получения original_url для оффера {i + 1}: {str(result)}")
                    results.append(hotline_urls[i])  # Fallback к исходному URL
                else:
                    results.append(result)

            success_count = sum(1 for r in original_urls if not isinstance(r, Exception))
            self.logger.info(f"Успешно получено {success_count}/{len(hotline_urls)} original_url")

            return results

        except Exception as e:
            self.logger.error(f"Критическая ошибка при параллельном получении original_url: {str(e)}")
            return hotline_urls

    async def _get_original_url(self, client: httpx.AsyncClient, hotline_url: str) -> str:
        """
        Получает финальный URL магазина после редиректа с hotline.ua
        
        Args:
            client: HTTP клиент
            hotline_url: URL hotline.ua для редиректа (например, /go/price/13798593681/)
            
        Returns:
            str: Финальный URL магазина или исходный URL при ошибке
        """
        if not hotline_url or not hotline_url.startswith('https://hotline.ua/go/'):
            self.logger.debug(f"Пропускаем редирект для {hotline_url} (не hotline URL)")
            return hotline_url

        try:
            self.logger.debug(f"Получаем original_url для: {hotline_url}")

            response = await client.head(
                hotline_url,
                follow_redirects=True,
                timeout=10
            )

            final_url = str(response.url)

            if final_url != hotline_url and not final_url.startswith('https://hotline.ua/go/'):
                clean_url = self._clean_url_parameters(final_url)
                self.logger.debug(f"Успешный HEAD редирект: {hotline_url} -> {clean_url}")
                return clean_url
            else:
                self.logger.debug(f"HEAD редирект не сработал, пробуем GET для: {hotline_url}")
                get_response = await client.get(
                    hotline_url,
                    follow_redirects=True,
                    timeout=10
                )
                final_url = str(get_response.url)
                if final_url != hotline_url:
                    clean_url = self._clean_url_parameters(final_url)
                    self.logger.debug(f"Успешный GET редирект: {hotline_url} -> {clean_url}")
                    return clean_url
                else:
                    self.logger.warning(f"Редирект не сработал для: {hotline_url}")

        except asyncio.TimeoutError:
            self.logger.warning(f"Таймаут при получении original_url для {hotline_url}")
        except httpx.HTTPStatusError as e:
            self.logger.warning(f"HTTP ошибка {e.response.status_code} для {hotline_url}")
        except Exception as e:
            self.logger.warning(f"Ошибка получения original_url для {hotline_url}: {type(e).__name__}: {str(e)}")

        return hotline_url

    def _clean_url_parameters(self, url: str) -> str:
        """
        Очищает URL от query параметров (UTM, affiliate и др.)
        
        Args:
            url: Исходный URL с параметрами
            
        Returns:
            str: Чистый URL без параметров
        """
        try:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(url)
            clean_url = urlunparse((
                parsed.scheme,  # схема (https)
                parsed.netloc,  # домен (f.ua)
                parsed.path,  # путь (/ua/arena/fast-urban-3-0-all-black-002492-500.html)
                '',  # params (пустые)
                '',  # query (убираем все параметры)
                ''  # fragment (убираем якорь)
            ))

            return clean_url

        except Exception as e:
            self.logger.warning(f"Ошибка очистки URL {url}: {str(e)}")
            return url.split('?')[0].split('#')[0]

    async def _initialize_session(self, client: httpx.AsyncClient, product_url: str) -> str:
        """
        Инициализирует сессию и извлекает x-token для GraphQL запросов
        
        Returns:
            str: x-token для авторизации GraphQL запросов
        """
        try:
            self.logger.info(f"Инициализируем сессию для {product_url}")

            response = await client.get(product_url)
            if response.status_code == 200:
                self.logger.info("Сессия инициализирована успешно")

                x_token = self._extract_x_token(response.text)
                if x_token:
                    self.logger.info(f"Получен x-token: {x_token[:20]}... (длина: {len(x_token)})")
                    return x_token
                else:
                    self.logger.warning("Не удалось извлечь x-token из страницы")
                    self.logger.debug(f"HTML содержимое (первые 500 символов): {response.text[:500]}")
                    return ""
            else:
                self.logger.warning(f"Не удалось инициализировать сессию: {response.status_code}")
                return ""

        except Exception as e:
            self.logger.warning(f"Ошибка инициализации сессии: {str(e)}")
            return ""

    @staticmethod
    def _extract_x_token(html_content: str) -> str:
        """
        Извлекает x-token из HTML страницы
        """
        import re

        # Паттерны для поиска токена в JavaScript
        patterns = [
            r'"x-token":\s*"([^"]+)"',
            r'x-token["\']:\s*["\']([^"\']+)["\']',
            r'X_TOKEN["\']?\s*=\s*["\']([^"\']+)["\']',
            r'requestId["\']?\s*=\s*["\']([^"\']+)["\']',
            r'window\.requestId\s*=\s*["\']([^"\']+)["\']',
            r'data-token="([^"]+)"',
            r'token:\s*["\']([^"\']+)["\']'
        ]

        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                token = match.group(1)
                if len(token) > 10:
                    return token

        return ""

    @staticmethod
    def _generate_request_id() -> str:
        """
        Генерирует случайный request ID в формате как у hotline.ua
        """
        import uuid
        return str(uuid.uuid4()).replace('-', '')[:32]

    @staticmethod
    def _extract_price(price_data: Any) -> float:
        """
        Извлекает цену из данных оффера
        """
        if isinstance(price_data, (int, float)):
            return float(price_data)
        elif isinstance(price_data, str):
            # Удаляем все нечисловые символы кроме точки и запятой
            price_clean = re.sub(r'[^\d.,]', '', price_data)
            price_clean = price_clean.replace(',', '.')
            try:
                return float(price_clean)
            except ValueError:
                return 0.0
        return 0.0

    @staticmethod
    def _sort_offers(offers: List[ProductOffer], sort_by: str) -> List[ProductOffer]:
        """
        Сортирует офферы по указанному критерию
        """
        if sort_by == "price":
            offers.sort(key=lambda x: x.price)
        elif sort_by == "price_desc":
            offers.sort(key=lambda x: x.price, reverse=True)
        elif sort_by == "shop":
            offers.sort(key=lambda x: x.shop.lower())
        elif sort_by == "shop_desc":
            offers.sort(key=lambda x: x.shop.lower(), reverse=True)

        return offers
