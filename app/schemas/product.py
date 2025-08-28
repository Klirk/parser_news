from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime, UTC

from app.models.product import Product, ProductOffer


class ProductOfferResponse(BaseModel):
    """Схема ответа для оффера товара"""
    url: str = Field(..., description="URL перехода к офферу")
    original_url: str = Field(..., description="Оригинальный URL в магазине")
    title: str = Field(..., description="Название товара")
    shop: str = Field(..., description="Название магазина")
    price: float = Field(..., description="Цена товара в гривнах")
    is_used: bool = Field(..., description="Товар б/у")

    @classmethod
    def from_offer(cls, offer: ProductOffer) -> "ProductOfferResponse":
        """Преобразует модель ProductOffer в схему ответа"""
        return cls(
            url=offer.url,
            original_url=offer.original_url,
            title=offer.title,
            shop=offer.shop,
            price=offer.price,
            is_used=offer.is_used
        )


class ProductResponse(BaseModel):
    """Схема ответа для товара с офферами"""
    url: str = Field(..., description="URL страницы товара")
    offers: List[ProductOfferResponse] = Field(default_factory=list, description="Список офферов")

    @classmethod
    def from_product(cls, product: Product) -> "ProductResponse":
        """Преобразует модель Product в схему ответа"""
        return cls(
            url=product.url,
            offers=[ProductOfferResponse.from_offer(offer) for offer in product.offers]
        )


class ProductParseRequest(BaseModel):
    """Схема запроса для парсинга товара (для валидации query параметров)"""
    url: str = Field(..., description="URL страницы товара на hotline.ua")
    timeout_limit: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Таймаут запроса в секундах"
    )
    count_limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Максимальное количество офферов"
    )

    @field_validator('url')
    def validate_url(cls, v: str) -> str:
        if not v.startswith('https://'):
            raise ValueError('URL должен начинаться с https://')
        if "hotline.ua" not in v.lower():
            raise ValueError('URL должен быть с сайта hotline.ua')
        return v

class ErrorResponse(BaseModel):
    """Универсальная схема ответа для ошибок"""
    detail: str = Field(..., description="Описание ошибки")
    error_type: str = Field(..., description="Тип ошибки")
    status_code: int = Field(..., description="HTTP статус код")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Время ошибки")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
