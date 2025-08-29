from pydantic import BaseModel, Field, field_validator, ConfigDict, field_serializer
from typing import List, Optional
from datetime import datetime, UTC
import re


class ArticleData(BaseModel):
    """Модель данных статьи"""
    title: str = Field(..., description="Заголовок статьи")
    content_body: str = Field(..., description="Полный текст статьи без HTML")
    image_urls: List[str] = Field(default_factory=list, description="Список URL изображений")
    published_at: Optional[datetime] = Field(None, description="Дата публикации")
    author: Optional[str] = Field(None, description="Автор статьи")
    views: Optional[int] = Field(None, ge=0, description="Количество просмотров")
    comments: List[str] = Field(default_factory=list, description="Комментарии к статье")
    likes: Optional[int] = Field(None, ge=0, description="Количество лайков")
    dislikes: Optional[int] = Field(None, ge=0, description="Количество дизлайков")
    video_url: Optional[str] = Field(None, description="URL видео")

    @field_serializer('published_at')
    def serialize_published_at(self, value: Optional[datetime]) -> Optional[str]:
        """Сериализует дату и время в формат ISO для JSON"""
        if value is None:
            return None
        return value.isoformat()

    @field_validator('image_urls', mode='before')
    def validate_image_urls(cls, v):
        if not isinstance(v, list):
            return []
        
        valid_urls = []
        for url in v:
            if isinstance(url, str) and url.strip():
                # Нормализуем URL
                url = url.strip()
                if url.startswith('//'):
                    url = 'https:' + url
                elif url.startswith('/'):
                    continue
                elif not url.startswith('https://'):
                    url = 'https://' + url
                valid_urls.append(url)
        return valid_urls

    @field_validator('video_url')
    def validate_video_url(cls, v):
        if v is None:
            return v
        if not isinstance(v, str):
            return None
        v = v.strip()
        if not v:
            return None
        if v.startswith('//'):
            v = 'https:' + v
        elif not v.startswith('https://'):
            v = 'https://' + v
        return v

    @field_validator('title', 'content_body', 'author')
    def clean_text(cls, v):
        if isinstance(v, str):
            # Очищаем от лишних пробелов и HTML тегов
            v = re.sub(r'<[^>]+>', '', v)  # Удаляем HTML теги
            v = re.sub(r'\s+', ' ', v).strip()  # Нормализуем пробелы
        return v

    @field_validator('comments', mode='before')
    def validate_comments(cls, v):
        if not isinstance(v, list):
            return []
        
        clean_comments = []
        for comment in v:
            if isinstance(comment, str) and comment.strip():
                # Очищаем комментарий от HTML и лишних пробелов
                clean_comment = re.sub(r'<[^>]+>', '', comment)
                clean_comment = re.sub(r'\s+', ' ', clean_comment).strip()
                if clean_comment:
                    clean_comments.append(clean_comment)
        return clean_comments


class NewsItem(BaseModel):
    """Модель новостной статьи"""
    source: str = Field(..., description="URL источника новостей")
    url: str = Field(..., description="URL конкретной статьи")
    article_data: ArticleData = Field(..., description="Данные статьи")

    @field_validator('source', 'url')
    def validate_urls(cls, v):
        if not v.startswith('https://'):
            if v.startswith('//'):
                v = 'https:' + v
            elif v.startswith('/'):
                raise ValueError('Относительные URL не поддерживаются для source и url')
            else:
                v = 'https://' + v
        return v


class NewsCollection(BaseModel):
    """Модель коллекции новостей с одного источника"""
    source: str = Field(..., description="URL источника новостей")
    items: List[NewsItem] = Field(default_factory=list, description="Список новостных статей")
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Время парсинга")
    total_items: int = Field(default=0, description="Общее количество найденных статей")
    parse_status: str = Field(default="success", description="Статус парсинга")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке если есть")

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )

    @field_validator('source')
    def validate_source_url(cls, v):
        if not v.startswith('https://'):
            raise ValueError('source должен быть полным URL')
        return v

    @field_validator('total_items', mode='before')
    def calculate_total_items(cls, v, info):
        if info.data and 'items' in info.data:
            return len(info.data['items'])
        return v or 0

    @field_validator('parse_status')
    def validate_parse_status(cls, v):
        allowed_statuses = ['success', 'partial', 'failed']
        if v not in allowed_statuses:
            raise ValueError(f'parse_status должен быть одним из: {allowed_statuses}')
        return v


class NewsFilter(BaseModel):
    """Модель фильтра для парсинга новостей"""
    url: str = Field(..., description="URL категории новостей")
    until_date: Optional[datetime] = Field(None, description="Граничная дата (не позднее)")
    client: str = Field(default="http", description="Тип клиента: http или browser")
    limit: Optional[int] = Field(None, ge=1, le=100, description="Максимальное количество статей")

    @field_validator('url')
    def validate_url(cls, v):
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
    def validate_client(cls, v):
        allowed_clients = ['http', 'browser']
        if v not in allowed_clients:
            raise ValueError(f'client должен быть одним из: {allowed_clients}')
        return v

    @field_validator('until_date')
    def validate_until_date(cls, v):
        if v is not None and v > datetime.now(UTC):
            raise ValueError('until_date не может быть в будущем')
        return v
