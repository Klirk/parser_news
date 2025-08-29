# app/middleware/auth.py

import logging
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import get_settings

logger = logging.getLogger(__name__)

# Инициализируем схему Bearer токена
security = HTTPBearer(auto_error=False)


class APIKeyAuth:
    """
    Класс для аутентификации через API ключ
    Поддерживает Bearer токены в заголовке Authorization
    """
    
    def __init__(self):
        self.settings = get_settings()
        # В продакшене ключи должны храниться в переменных окружения или внешней системе
        self.valid_api_keys = {
            "demo_key_123": {
                "name": "Demo User",
                "permissions": ["read", "write"],
                "rate_limit": 1000  # запросов в час
            },
            "admin_key_456": {
                "name": "Admin User", 
                "permissions": ["read", "write", "admin"],
                "rate_limit": 10000
            },
            "readonly_key_789": {
                "name": "ReadOnly User",
                "permissions": ["read"],
                "rate_limit": 500
            }
        }
    
    async def verify_api_key(
        self, 
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
    ) -> dict:
        """
        Проверяет API ключ и возвращает информацию о пользователе
        
        Args:
            credentials: HTTP Bearer токен
            
        Returns:
            dict: Информация о пользователе
            
        Raises:
            HTTPException: При недействительном или отсутствующем токене
        """
        # Если аутентификация отключена в настройках
        if getattr(self.settings, 'disable_auth', False):
            return {
                "name": "Anonymous",
                "permissions": ["read", "write"],
                "rate_limit": 100
            }
        
        if not credentials or not hasattr(credentials, 'credentials'):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API ключ отсутствует. Передайте в заголовке: Authorization: Bearer YOUR_API_KEY",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        api_key = credentials.credentials
        
        if api_key not in self.valid_api_keys:
            logger.warning(f"Попытка использования недействительного API ключа: {api_key[:10]}...")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Недействительный API ключ",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_info = self.valid_api_keys[api_key]
        logger.info(f"Успешная аутентификация пользователя: {user_info['name']}")
        
        return {
            "api_key": api_key,
            **user_info
        }
    
    async def verify_permission(
        self,
        required_permission: str,
        user_info: dict
    ) -> bool:
        """
        Проверяет, есть ли у пользователя необходимое разрешение
        
        Args:
            required_permission: Требуемое разрешение
            user_info: Информация о пользователе
            
        Returns:
            bool: True если разрешение есть
        """
        user_permissions = user_info.get("permissions", [])
        return required_permission in user_permissions or "admin" in user_permissions


# Глобальный экземпляр аутентификации
api_key_auth = APIKeyAuth()


# Dependency для обязательной аутентификации
async def require_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> dict:
    """
    Dependency для эндпоинтов, требующих аутентификации
    
    Returns:
        dict: Информация о пользователе
    """
    return await api_key_auth.verify_api_key(credentials)


# Dependency для аутентификации с правом на чтение
async def require_read_permission(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> dict:
    """
    Dependency для эндпоинтов, требующих право на чтение
    
    Returns:
        dict: Информация о пользователе
    """
    user_info = await api_key_auth.verify_api_key(credentials)
    
    if not await api_key_auth.verify_permission("read", user_info):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав доступа. Требуется разрешение 'read'"
        )
    
    return user_info


# Dependency для аутентификации с правом на запись
async def require_write_permission(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> dict:
    """
    Dependency для эндпоинтов, требующих право на запись
    
    Returns:
        dict: Информация о пользователе
    """
    user_info = await api_key_auth.verify_api_key(credentials)
    
    if not await api_key_auth.verify_permission("write", user_info):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав доступа. Требуется разрешение 'write'"
        )
    
    return user_info


# Dependency для администраторских операций
async def require_admin_permission(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> dict:
    """
    Dependency для эндпоинтов, требующих административные права
    
    Returns:
        dict: Информация о пользователе
    """
    user_info = await api_key_auth.verify_api_key(credentials)
    
    if not await api_key_auth.verify_permission("admin", user_info):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав доступа. Требуются административные права"
        )
    
    return user_info


# Опциональная аутентификация (для публичных эндпоинтов с ограничениями)
async def optional_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[dict]:
    """
    Опциональная аутентификация для публичных эндпоинтов
    
    Returns:
        dict или None: Информация о пользователе или None для анонимного доступа
    """
    try:
        return await api_key_auth.verify_api_key(credentials)
    except HTTPException:
        # Возвращаем None для анонимного доступа
        return None
