# app/middleware/error_handlers.py

import logging
import asyncio
from typing import Union
from datetime import datetime
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


async def timeout_error_handler(request: Request, exc: Union[asyncio.TimeoutError, httpx.TimeoutException, PlaywrightTimeoutError]) -> JSONResponse:
    """
    Обработчик ошибок таймаута
    Возвращает HTTP 408 Request Timeout
    """
    logger.warning(f"Timeout error на {request.url}: {str(exc)}")
    
    return JSONResponse(
        status_code=408,
        content={
            "detail": "Превышено время ожидания запроса",
            "error_type": "TimeoutError",
            "status_code": 408,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    )


async def http_status_error_handler(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    """
    Обработчик HTTP ошибок статуса
    Возвращает соответствующие коды ошибок
    """
    status_code = exc.response.status_code
    
    logger.warning(f"HTTP Status Error на {request.url}: {status_code} - {str(exc)}")
    
    # Маппинг HTTP статусов
    if status_code == 429:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Слишком много запросов. Попробуйте позже",
                "error_type": "RateLimitError", 
                "status_code": 429,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )
    elif 500 <= status_code < 600:
        return JSONResponse(
            status_code=502,
            content={
                "detail": "Ошибка внешнего сервиса",
                "error_type": "ExternalServiceError",
                "status_code": 502,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )
    elif 400 <= status_code < 500:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Ошибка запроса к внешнему сервису",
                "error_type": "BadRequestError",
                "status_code": 400,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )
    else:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Неожиданная ошибка внешнего сервиса",
                "error_type": "UnexpectedError",
                "status_code": 500,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )


async def connection_error_handler(request: Request, exc: Union[httpx.ConnectError, httpx.NetworkError]) -> JSONResponse:
    """
    Обработчик ошибок подключения
    Возвращает HTTP 503 Service Unavailable
    """
    logger.error(f"Connection error на {request.url}: {str(exc)}")
    
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Сервис временно недоступен",
            "error_type": "ConnectionError",
            "status_code": 503,
            "timestamp": "2025-01-01T00:00:00Z"
        }
    )


async def parsing_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Обработчик ошибок парсинга
    Возвращает HTTP 502 Bad Gateway
    """
    logger.error(f"Parsing error на {request.url}: {str(exc)}")
    
    return JSONResponse(
        status_code=502,
        content={
            "detail": "Ошибка обработки данных от внешнего источника",
            "error_type": "ParsingError",
            "status_code": 502,
            "timestamp": "2025-01-01T00:00:00Z"
        }
    )


async def validation_error_handler(request: Request, exc: Union[RequestValidationError, ValidationError]) -> JSONResponse:
    """
    Обработчик ошибок валидации Pydantic
    Возвращает HTTP 422 Unprocessable Entity с детальными полями
    """
    logger.warning(f"Validation error на {request.url}: {str(exc)}")
    
    errors = []
    
    if isinstance(exc, RequestValidationError):
        for error in exc.errors():
            errors.append({
                "loc": error["loc"],
                "msg": error["msg"],
                "type": error["type"],
                "input": error.get("input")
            })
    elif isinstance(exc, ValidationError):
        for error in exc.errors():
            errors.append({
                "loc": error["loc"], 
                "msg": error["msg"],
                "type": error["type"],
                "input": error.get("input")
            })
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Ошибка валидации данных",
            "error_type": "ValidationError",
            "status_code": 422,
            "errors": errors,
            "timestamp": "2025-01-01T00:00:00Z"
        }
    )


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """
    Обработчик ValueError
    Возвращает HTTP 400 Bad Request
    """
    logger.warning(f"Value error на {request.url}: {str(exc)}")
    
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "error_type": "ValueError",
            "status_code": 400,
            "timestamp": "2025-01-01T00:00:00Z"
        }
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Обработчик общих ошибок
    Возвращает HTTP 500 Internal Server Error
    """
    logger.error(f"Unexpected error на {request.url}: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Внутренняя ошибка сервера",
            "error_type": type(exc).__name__,
            "status_code": 500,
            "timestamp": "2025-01-01T00:00:00Z"
        }
    )


def setup_error_handlers(app):
    """
    Настраивает обработчики ошибок для приложения FastAPI
    
    Args:
        app: Экземпляр FastAPI приложения
    """
    # Ошибки таймаута
    app.add_exception_handler(asyncio.TimeoutError, timeout_error_handler)
    app.add_exception_handler(httpx.TimeoutException, timeout_error_handler)
    
    try:
        app.add_exception_handler(PlaywrightTimeoutError, timeout_error_handler)
    except NameError:
        # Playwright может быть не установлен
        pass
    
    # HTTP ошибки статуса
    app.add_exception_handler(httpx.HTTPStatusError, http_status_error_handler)
    
    # Ошибки подключения
    app.add_exception_handler(httpx.ConnectError, connection_error_handler)
    app.add_exception_handler(httpx.NetworkError, connection_error_handler)
    
    # Ошибки валидации
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    
    # ValueError
    app.add_exception_handler(ValueError, value_error_handler)
    
    # Общий обработчик (должен быть последним)
    app.add_exception_handler(Exception, generic_error_handler)
    
    logger.info("Обработчики ошибок настроены успешно")
