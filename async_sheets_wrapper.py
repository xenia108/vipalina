"""
Асинхронная обертка для Google Sheets API (gspread).
Решает проблему синхронных блокирующих запросов к Google Sheets.
"""

import asyncio
import logging
from typing import Any, Callable, Optional, List, Dict
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger('vipalina_telethon')


class AsyncSheetsWrapper:
    """
    Асинхронная обертка для Google Sheets операций.
    Выполняет синхронные вызовы gspread в отдельном thread pool.
    """
    
    # Используем единый thread pool для всех операций с Sheets
    _executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='sheets_')
    
    @classmethod
    async def run_sync(cls, func: Callable, *args, **kwargs) -> Any:
        """
        Запускает синхронную функцию асинхронно в thread pool.
        
        Args:
            func: Синхронная функция для выполнения
            *args, **kwargs: Аргументы функции
            
        Returns:
            Результат выполнения функции
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(cls._executor, lambda: func(*args, **kwargs))
    
    @classmethod
    async def batch_run_sync(cls, operations: List[tuple]) -> List[Any]:
        """
        Выполняет несколько синхронных операций параллельно.
        
        Args:
            operations: List of (func, args, kwargs) tuples
            
        Returns:
            List результатов в том же порядке
        """
        tasks = []
        for operation in operations:
            if len(operation) == 1:
                func = operation[0]
                args, kwargs = (), {}
            elif len(operation) == 2:
                func, args = operation
                kwargs = {}
            else:
                func, args, kwargs = operation
            
            task = cls.run_sync(func, *args, **kwargs)
            tasks.append(task)
        
        return await asyncio.gather(*tasks)


def async_sheets_method(method: Callable) -> Callable:
    """
    Декоратор для автоматического преобразования синхронных методов
    Google Sheets в асинхронные.
    
    Usage:
        @async_sheets_method
        def get_all_values(self):
            return self.worksheet.get_all_values()
    """
    @wraps(method)
    async def wrapper(self, *args, **kwargs):
        return await AsyncSheetsWrapper.run_sync(
            lambda: method(self, *args, **kwargs)
        )
    return wrapper
