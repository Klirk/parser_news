from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
import validators

from app.services.product_service import get_product_service
from app.schemas.product import ProductResponse
from app.middleware.auth import optional_api_key

router = APIRouter()

@router.get("/offers", response_model=ProductResponse)
async def get_product_offers(
        url: str = Query(..., description="URL страницы товара на hotline.ua"),
        timeout_limit: int = Query(
            default=5,
            ge=5,
            le=300,
            description="Таймаут запроса в секундах"
        ),
        count_limit: Optional[int] = Query(
            default=5,
            ge=1,
            le=1000,
            description="Максимальное количество офферов"
        ),
        sort: str = Query(
            default="desc",
            pattern="^(desc|asc)$",
            description="Сортировка офферов по цене: desc (по убыванию), asc (по возрастанию)"
        ),
        product_service = Depends(get_product_service),
        user_info: Optional[dict] = Depends(optional_api_key)
):
    """
    Получает офферы для товара с hotline.ua используя только API (без HTML парсинга)

    - **url**: Полный URL страницы товара на hotline.ua
    - **timeout_limit**: Таймаут для HTTP запросов (5-300 секунд)
    - **count_limit**: Лимит количества офферов (1-100)
    - **sort**: Сортировка офферов по цене: desc (по убыванию), asc (по возрастанию)
    """
    if not validators.url(url):
        raise HTTPException(
            status_code=400,
            detail="Некорректный URL"
        )

    if "hotline.ua" not in url.lower():
        raise HTTPException(
            status_code=400,
            detail="URL должен быть с сайта hotline.ua"
        )

    try:
        # Преобразуем параметр sort в формат, понятный сервису
        sort_by = "price_desc" if sort == "desc" else "price"
        
        product = await product_service.parse_and_save_product(
            url=url,
            timeout_limit=timeout_limit,
            count_limit=count_limit,
            sort_by=sort_by
        )

        return ProductResponse.from_product(product)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка парсинга товара: {str(e)}"
        )