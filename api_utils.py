"""
Утилиты для работы с внешними API.
Включает retry-механизм и обработку ошибок.
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, Any, Optional, Type, Tuple
import time

logger = logging.getLogger('api_utils')


def retry_async(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Декоратор для повторных попыток выполнения асинхронной функции при ошибках.
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Начальная задержка между попытками (в секундах)
        backoff: Множитель для увеличения задержки (exponential backoff)
        exceptions: Tuple типов исключений для обработки
        on_retry: Callback функция, вызываемая при повторной попытке
    
    Example:
        @retry_async(max_attempts=3, delay=1.0, backoff=2.0)
        async def fetch_data():
            # Your async code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.error(
                            f"Функция {func.__name__} не выполнена после {max_attempts} попыток. "
                            f"Последняя ошибка: {e}",
                            exc_info=True
                        )
                        raise
                    
                    logger.warning(
                        f"Попытка {attempt}/{max_attempts} для {func.__name__} не удалась: {e}. "
                        f"Повтор через {current_delay:.1f}с..."
                    )
                    
                    if on_retry:
                        try:
                            if asyncio.iscoroutinefunction(on_retry):
                                await on_retry(attempt, e, *args, **kwargs)
                            else:
                                on_retry(attempt, e, *args, **kwargs)
                        except Exception as callback_error:
                            logger.error(f"Ошибка в on_retry callback: {callback_error}")
                    
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


def retry_sync(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Декоратор для повторных попыток выполнения синхронной функции при ошибках.
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Начальная задержка между попытками (в секундах)
        backoff: Множитель для увеличения задержки
        exceptions: Tuple типов исключений для обработки
        on_retry: Callback функция, вызываемая при повторной попытке
    
    Example:
        @retry_sync(max_attempts=3, delay=1.0)
        def fetch_data():
            # Your sync code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.error(
                            f"Функция {func.__name__} не выполнена после {max_attempts} попыток. "
                            f"Последняя ошибка: {e}",
                            exc_info=True
                        )
                        raise
                    
                    logger.warning(
                        f"Попытка {attempt}/{max_attempts} для {func.__name__} не удалась: {e}. "
                        f"Повтор через {current_delay:.1f}с..."
                    )
                    
                    if on_retry:
                        try:
                            on_retry(attempt, e, *args, **kwargs)
                        except Exception as callback_error:
                            logger.error(f"Ошибка в on_retry callback: {callback_error}")
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


class APIError(Exception):
    """Базовый класс для ошибок API"""
    pass


class TelegramAPIError(APIError):
    """Ошибка Telegram API"""
    pass


class GoogleSheetsAPIError(APIError):
    """Ошибка Google Sheets API"""
    pass


class AirtableAPIError(APIError):
    """Ошибка Airtable API"""
    pass


class OpenAIAPIError(APIError):
    """Ошибка OpenAI API"""
    pass


def safe_api_call(func: Callable, *args, **kwargs) -> Optional[Any]:
    """
    Безопасно вызывает функцию API с обработкой ошибок.
    
    Args:
        func: Функция для вызова
        *args: Позиционные аргументы
        **kwargs: Именованные аргументы
    
    Returns:
        Результат вызова функции или None при ошибке
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Ошибка при вызове {func.__name__}: {e}", exc_info=True)
        return None


async def safe_api_call_async(func: Callable, *args, **kwargs) -> Optional[Any]:
    """
    Безопасно вызывает асинхронную функцию API с обработкой ошибок.
    
    Args:
        func: Асинхронная функция для вызова
        *args: Позиционные аргументы
        **kwargs: Именованные аргументы
    
    Returns:
        Результат вызова функции или None при ошибке
    """
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Ошибка при вызове {func.__name__}: {e}", exc_info=True)
        return None
