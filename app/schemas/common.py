from pydantic import BaseModel, Field
from datetime import datetime, UTC


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
