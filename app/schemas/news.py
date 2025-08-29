from pydantic import BaseModel, Field, field_validator, field_serializer
from typing import List, Optional
from datetime import datetime, UTC

from app.models.news import NewsCollection, NewsItem, ArticleData


class NewsParseRequest(BaseModel):
    """Схема запроса для парсинга новостей"""
    url: str = Field(..., description="URL категории новостей")
    until_date: Optional[datetime] = Field(None, description="Самая старая дата для парсинга - от сегодня назад до этой даты включительно")
    client: str = Field(default="http", description="Тип клиента: http или browser")


    @field_validator('url')
    def validate_url(cls, v: str) -> str:
        if not v.startswith('https://'):
            raise ValueError('URL должен начинаться с https://')
        
        # Проверяем, что URL относится к одному из поддерживаемых источников
        supported_domains = [
            'epravda.com.ua',
            'politeka.net',
            'pravda.com.ua'
        ]
        
        if not any(domain in v.lower() for domain in supported_domains):
            raise ValueError(f'URL должен быть с одного из поддерживаемых сайтов: {supported_domains}')
        
        return v

    @field_validator('client')
    def validate_client(cls, v: str) -> str:
        allowed_clients = ['http', 'browser']
        if v not in allowed_clients:
            raise ValueError(f'client должен быть одним из: {allowed_clients}')
        return v

    @field_validator('until_date')
    def validate_until_date(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None and v > datetime.now(UTC):
            raise ValueError('until_date не может быть в будущем')
        return v


class ArticleDataResponse(BaseModel):
    """Схема ответа для данных статьи"""
    title: str = Field(..., description="Заголовок статьи")
    content_body: str = Field(..., description="Полный текст статьи без HTML")
    image_urls: List[str] = Field(default_factory=list, description="Список URL изображений")
    published_at: Optional[datetime] = Field(None, description="Дата публикации")
    author: Optional[str] = Field(None, description="Автор статьи")
    views: Optional[int] = Field(None, description="Количество просмотров")
    comments: List[str] = Field(default_factory=list, description="Комментарии к статье")
    likes: Optional[int] = Field(None, description="Количество лайков")
    dislikes: Optional[int] = Field(None, description="Количество дизлайков")
    video_url: Optional[str] = Field(None, description="URL видео")

    @field_serializer('published_at')
    def serialize_published_at(self, value: Optional[datetime]) -> Optional[str]:
        """Сериализует дату и время в формат ISO для JSON"""
        if value is None:
            return None
        return value.isoformat()

    @classmethod
    def from_article_data(cls, article_data: ArticleData) -> "ArticleDataResponse":
        """Преобразует модель ArticleData в схему ответа"""
        return cls(
            title=article_data.title,
            content_body=article_data.content_body,
            image_urls=article_data.image_urls,
            published_at=article_data.published_at,
            author=article_data.author,
            views=article_data.views,
            comments=article_data.comments,
            likes=article_data.likes,
            dislikes=article_data.dislikes,
            video_url=article_data.video_url
        )


class NewsItemResponse(BaseModel):
    """Схема ответа для новостной статьи"""
    source: str = Field(..., description="URL источника новостей")
    url: str = Field(..., description="URL конкретной статьи")
    article_data: ArticleDataResponse = Field(..., description="Данные статьи")

    @classmethod
    def from_news_item(cls, news_item: NewsItem) -> "NewsItemResponse":
        """Преобразует модель NewsItem в схему ответа"""
        return cls(
            source=news_item.source,
            url=news_item.url,
            article_data=ArticleDataResponse.from_article_data(news_item.article_data)
        )


class NewsCollectionResponse(BaseModel):
    """Схема ответа для коллекции новостей"""
    source: str = Field(..., description="URL источника новостей")
    items: List[NewsItemResponse] = Field(default_factory=list, description="Список новостных статей")
    parsed_at: datetime = Field(..., description="Время парсинга")
    total_items: int = Field(..., description="Общее количество найденных статей")
    parse_status: str = Field(..., description="Статус парсинга")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке если есть")

    @classmethod
    def from_news_collection(cls, news_collection: NewsCollection) -> "NewsCollectionResponse":
        """Преобразует модель NewsCollection в схему ответа"""
        return cls(
            source=news_collection.source,
            items=[NewsItemResponse.from_news_item(item) for item in news_collection.items],
            parsed_at=news_collection.parsed_at,
            total_items=news_collection.total_items,
            parse_status=news_collection.parse_status,
            error_message=news_collection.error_message
        )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }



