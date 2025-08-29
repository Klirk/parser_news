# News Scrapper API

Асинхронный сервис для парсинга продуктов и новостей с несколькими источниками, сохранением в MongoDB и публичным REST API.

## 🚀 Технологический стек

- **Python 3.11+** - основной язык программирования
- **FastAPI** - асинхронный веб-фреймворк
- **Pydantic v2** - валидация данных и схемы
- **MongoDB + Motor** - асинхронная база данных
- **httpx** - асинхронный HTTP-клиент
- **Playwright** - браузерная автоматизация для сложных сайтов
- **BeautifulSoup + lxml** - парсинг HTML
- **Docker + docker-compose** - контейнеризация

## 📋 Функциональность

### Продукты
- Парсинг товаров с **hotline.ua** через API
- Получение офферов с ценами, магазинами и состоянием товара
- Сортировка и ограничение количества результатов
- Кэширование результатов в MongoDB

### Новости
- Универсальный парсер для трех источников:
  - **epravda.com.ua/news/**
  - **politeka.net/uk/newsfeed**
  - **pravda.com.ua/news/**
- Фильтрация по дате публикации
- Два режима работы: HTTP (быстрый) и Browser (надежный)
- Извлечение полного контента, изображений, видео и метаданных

## 🛠 Установка и запуск

### Предварительные требования

- **Docker** и **docker-compose**
- **Git**

### Быстрый запуск

1. **Клонируйте репозиторий:**
```bash
git clone <repository-url>
cd NewsScrapper
```

2. **Запустите через Docker Compose:**
```bash
docker-compose up --build
```

3. **Проверьте работоспособность:**
```bash
curl http://localhost:8000/health
```

### API будет доступно по адресам:
- **API:** http://localhost:8000
- **Документация:** http://localhost:8000/docs
- **MongoDB Express:** http://localhost:8081 (admin/admin)

## 🔧 Конфигурация

### Переменные окружения

Создайте файл `.env` в корне проекта:

```bash
# Основные настройки
APP_NAME="News Scraper API"
APP_VERSION="1.0.0"
DEBUG=true
ENVIRONMENT=development

# API настройки
API_HOST=0.0.0.0
API_PORT=8000
API_PREFIX="/api/v1"

# MongoDB
MONGODB_URL=mongodb://admin:password123@mongo:27017/parser_db?authSource=admin
DATABASE_NAME=parser_db
MONGODB_MAX_CONNECTIONS=100
MONGODB_TIMEOUT=30

# Парсинг
DEFAULT_TIMEOUT=30
DEFAULT_COUNT_LIMIT=50
DEFAULT_SORT=price
ALLOWED_DOMAINS=["hotline.ua"]

# Кэширование
CACHE_TTL_MINUTES=60
ENABLE_CACHE=true

# Логирование
LOG_LEVEL=INFO

# CORS
CORS_ORIGINS=["*"]
CORS_METHODS=["GET", "POST", "PUT", "DELETE"]

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# HTTP клиент
USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
MAX_RETRIES=3
RETRY_DELAY=1.0

# Аутентификация
DISABLE_AUTH=false
AUTH_ENABLED=true
```

## 🔐 Аутентификация

API поддерживает аутентификацию через API ключи в заголовке Authorization.

### Типы доступа:
- **Чтение** - доступ к парсингу и получению данных
- **Запись** - обновление кэша и модификация данных  
- **Администрирование** - удаление данных и административные операции

### Тестовые API ключи:
```bash
# Демо пользователь (чтение + запись)
Authorization: Bearer demo_key_123

# Администратор (все права)
Authorization: Bearer admin_key_456

# Только чтение
Authorization: Bearer readonly_key_789
```

### Примеры использования:
```bash
# С аутентификацией
curl -H "Authorization: Bearer demo_key_123" \
  "http://localhost:8000/api/v1/news/source?url=https://epravda.com.ua/news/"

# Без аутентификации (для публичных эндпоинтов)
curl "http://localhost:8000/api/v1/product/offers?url=https://hotline.ua/mobile/apple-iphone-15/"
```

### Отключение аутентификации:
Для разработки можно отключить аутентификацию в `.env`:
```bash
DISABLE_AUTH=true
```

## 📚 API Документация

### Продукты

#### `GET /api/v1/product/offers`

Получает офферы для товара с hotline.ua

**Параметры:**
- `url` (обязательный) - URL страницы товара на hotline.ua
- `timeout_limit` (опциональный, по умолчанию: 30) - таймаут в секундах (5-300)
- `count_limit` (опциональный, по умолчанию: 1000) - максимальное количество офферов (1-1000)
- `sort` (опциональный, по умолчанию: "desc") - сортировка по цене: "desc" или "asc"

**Пример запроса:**
```bash
curl "http://localhost:8000/api/v1/product/offers?url=https://hotline.ua/mobile/apple-iphone-15-128gb-black/&timeout_limit=30&count_limit=10&sort=desc"
```

**Пример ответа:**
```json
{
  "url": "https://hotline.ua/mobile/apple-iphone-15-128gb-black/",
  "offers": [
    {
      "url": "https://hotline.ua/go/price/13841037622",
      "original_url": "https://elmir.ua/ua/travel_backpacks/backpack_arena_fast_urban_3_0_all-black_002492-500.html",
      "title": "Arena Рюкзак Arena Fast Urban 3.0 All-Black (002492-500)",
      "shop": "ELMIR.UA",
      "price": 3278.0,
      "is_used": false
    }
  ]
}
```

### Новости

#### `GET /api/v1/news/source`

Парсит новости с указанного источника

**Параметры:**
- `url` (обязательный) - URL категории новостей
- `until_date` (опциональный) - граничная дата в формате ISO (YYYY-MM-DD или YYYY-MM-DDTHH:MM:SS)
- `client` (опциональный, по умолчанию: "http") - тип клиента: "http" или "browser"

**Поддерживаемые источники:**
- https://epravda.com.ua/news/
- https://politeka.net/uk/newsfeed
- https://www.pravda.com.ua/news/

**Пример запроса:**
```bash
curl "http://localhost:8000/api/v1/news/source?url=https://epravda.com.ua/news/&until_date=2025-01-01&client=http"
```

#### `GET /api/v1/news/recent`

Получает недавние новости из базы данных

**Параметры:**
- `hours` (опциональный, по умолчанию: 24) - за сколько часов назад искать (1-168)
- `source` (опциональный) - фильтр по URL источника
- `limit` (опциональный, по умолчанию: 50) - максимальное количество статей (1-100)

#### `GET /api/v1/news/search`

Поиск статей по тексту

**Параметры:**
- `q` (обязательный) - поисковый запрос (минимум 3 символа)
- `source` (опциональный) - фильтр по источнику
- `limit` (опциональный, по умолчанию: 50) - максимальное количество результатов

#### `POST /api/v1/news/refresh`

Принудительно обновляет кэш новостей

#### `GET /api/v1/news/stats`

Получает статистику по новостям

#### `GET /api/v1/news/health`

Проверка работоспособности сервиса новостей

## 🏗 Архитектура

Проект следует принципам **SOLID** и использует **Clean Architecture**:

```
app/
├── api/v1/endpoints/     # API эндпоинты
├── models/               # Pydantic модели
├── schemas/              # Схемы запросов/ответов
├── services/             # Бизнес-логика
├── repositories/         # Слой данных
├── parsers/              # Парсеры контента
├── middleware/           # Middleware и обработчики ошибок
├── config.py             # Конфигурация
├── database.py           # Подключение к БД
└── main.py               # Точка входа
```

### Слои архитектуры:
1. **API Layer** - обработка HTTP запросов
2. **Service Layer** - бизнес-логика и координация
3. **Repository Layer** - работа с базой данных
4. **Parser Layer** - извлечение данных из внешних источников

## 🔍 Логирование и мониторинг

### Логи
Все операции логируются с соответствующими уровнями:
- `INFO` - успешные операции
- `WARNING` - предупреждения и восстановимые ошибки
- `ERROR` - критические ошибки

### Health Check эндпоинты
- `GET /health` - общее состояние системы
- `GET /api/v1/product/health` - состояние парсера продуктов
- `GET /api/v1/news/health` - состояние парсеров новостей

## 🛡 Обработка ошибок

API возвращает детальную информацию об ошибках с соответствующими HTTP кодами:

- **400** - Ошибки валидации запроса
- **408** - Таймаут запроса
- **422** - Ошибки валидации Pydantic (с детальными полями)
- **429** - Превышение лимита запросов
- **502** - Ошибки парсинга внешних источников
- **503** - Недоступность внешних сервисов
- **500** - Внутренние ошибки сервера

## 🧪 Тестирование

### Ручное тестирование

1. **Проверка продуктов:**
```bash
curl "http://localhost:8000/api/v1/product/offers?url=https://hotline.ua/mobile/apple-iphone-15/"
```

2. **Проверка новостей:**
```bash
curl "http://localhost:8000/api/v1/news/source?url=https://epravda.com.ua/news/"
```

3. **Проверка health:**
```bash
curl http://localhost:8000/health
```

### Интерактивная документация

Перейдите на http://localhost:8000/docs для тестирования API через Swagger UI.

## 🔧 Разработка

### Локальная разработка

1. **Установите зависимости:**
```bash
pip install -r requirements.txt
```

2. **Запустите MongoDB:**
```bash
docker-compose up -d mongo
```

3. **Установите переменные окружения:**
```bash
export MONGODB_URL="mongodb://admin:password123@localhost:27017/parser_db?authSource=admin"
```

4. **Запустите приложение:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Структура Docker

- **API контейнер** - основное приложение
- **MongoDB контейнер** - база данных
- **Mongo Express контейнер** - веб-интерфейс для MongoDB

## 📈 Производительность

### Оптимизации:
- **Асинхронная обработка** всех I/O операций
- **Пакетный парсинг** статей для ускорения
- **Кэширование** результатов в MongoDB
- **Пул подключений** к базе данных
- **Rate limiting** для защиты от перегрузки

### Рекомендуемые настройки:
- **timeout_limit**: 30-60 секунд для стабильности
- **count_limit**: 10-50 для оптимального времени ответа
- **client**: "http" для скорости, "browser" для надежности

## 🚨 Устранение неполадок

### Частые проблемы:

1. **Ошибка подключения к MongoDB:**
```bash
# Проверьте статус контейнера
docker-compose ps
# Пересоздайте контейнеры
docker-compose down && docker-compose up --build
```

2. **Таймауты при парсинге:**
- Увеличьте `timeout_limit`
- Используйте `client=browser` для сложных сайтов
- Проверьте подключение к интернету

3. **Ошибки парсинга:**
- Проверьте корректность URL
- Убедитесь, что сайт доступен
- Посмотрите логи: `docker-compose logs api`

4. **Проблемы с производительностью:**
- Уменьшите `count_limit`
- Включите кэширование
- Проверьте ресурсы системы

### Логи
```bash
# Просмотр логов приложения
docker-compose logs -f api

# Просмотр логов MongoDB
docker-compose logs -f mongo
```

## 📞 Поддержка

Для получения помощи:
1. Проверьте логи приложения
2. Убедитесь в корректности URL и параметров
3. Проверьте health check эндпоинты
4. Обратитесь к документации API

## 📄 Лицензия

Этот проект создан в учебных целях.

---

**Версия:** 1.0.0
