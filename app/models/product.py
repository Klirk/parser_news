from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List
from datetime import datetime, UTC
import re


class ProductOffer(BaseModel):
    """Модель оффера товара"""
    url: str = Field(..., description="URL перехода к офферу")
    original_url: str = Field(..., description="Оригинальный URL в магазине")
    title: str = Field(..., min_length=1, description="Название товара")
    shop: str = Field(..., min_length=1, description="Название магазина")
    price: float = Field(..., ge=0, description="Цена товара в гривнах")
    is_used: bool = Field(default=False, description="Товар б/у")

    @field_validator('price')
    def validate_price(cls, v):
        if v < 0:
            raise ValueError('Цена не может быть отрицательной')
        return round(v, 2)

    @field_validator('title', 'shop')
    def clean_text(cls, v):
        if isinstance(v, str):
            v = re.sub(r'\s+', ' ', v).strip()
        return v


class Product(BaseModel):
    """Модель товара"""
    url: str = Field(..., description="URL страницы товара")
    offers: List[ProductOffer] = Field(default_factory=list, description="Список офферов")
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Время парсинга")
    total_offers: int = Field(default=0, description="Общее количество офферов")

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )

    @field_validator('url')
    def validate_url(cls, v):
        if "hotline.ua" not in v.lower():
            raise ValueError('URL должен быть с сайта hotline.ua')
        return v

    @field_validator('total_offers', mode='before')
    def calculate_total_offers(cls, v, info):
        if info.data and 'offers' in info.data:
            return len(info.data['offers'])
        return v or 0
