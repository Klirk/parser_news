from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime
import validators
import logging

from app.services.news_service import get_news_service
from app.schemas.news import NewsCollectionResponse
from app.middleware.auth import require_api_key, require_read_permission

router = APIRouter()


@router.get("/parse", response_model=NewsCollectionResponse)
async def parse_news(
        url: str = Query(..., description="URL категории новостей"),
        until_date: Optional[datetime] = Query(
            default=None,
            description="Самая старая дата для парсинга (включительно). Парсинг идет от сегодня назад до этой даты. Например: если сегодня 29.08, а until_date=2025-08-28, то будут собраны статьи за 29.08 и 28.08"
        ),
        client: str = Query(
            default="http",
            pattern="^(http|browser)$",
            description="Тип клиента: http (быстрее) или browser (для сложных сайтов)"
        ),

        news_service=Depends(get_news_service),
        user_info: dict = Depends(require_read_permission)
):
    """
    Универсальный парсер новостей для поддерживаемых источников
    
    **Требует API ключ в заголовке Authorization: Bearer YOUR_API_KEY**
    
    Поддерживаемые источники:
    - https://epravda.com.ua/news/
    - https://politeka.net/uk/newsfeed
    - https://www.pravda.com.ua/news/
    
    - **url**: URL категории новостей с одного из поддерживаемых сайтов
    - **until_date**: Самая старая дата для парсинга (включительно). Парсинг идет от сегодня назад.
      Например: если сегодня 29.08, а until_date=2025-08-28, то парсятся статьи за 29.08 и 28.08, но НЕ за 27.08
    - **client**: Тип клиента для парсинга (http быстрее, browser для сложных случаев)

    """
    if not validators.url(url):
        raise HTTPException(
            status_code=400,
            detail="Некорректный URL"
        )

    # Проверяем поддерживаемые домены
    supported_domains = [
        'epravda.com.ua',
        'politeka.net',
        'pravda.com.ua'
    ]
    
    if not any(domain in url.lower() for domain in supported_domains):
        raise HTTPException(
            status_code=400,
            detail=f"URL должен быть с одного из поддерживаемых сайтов: {supported_domains}"
        )

    try:
        # Логируем использование API
        logger = logging.getLogger(__name__)
        logger.info(f"API запрос: пользователь {user_info.get('name', 'Unknown')} парсит новости с {url}")
        
        news_collection = await news_service.parse_news(
            url=url,
            until_date=until_date,
            client=client
        )

        return NewsCollectionResponse.from_news_collection(news_collection)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка парсинга новостей: {str(e)}"
        )