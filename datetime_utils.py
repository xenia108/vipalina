"""
Утилита для работы с датами и временем в московском часовом поясе.

Все операции с датами и временем в системе должны использовать московское время (Europe/Moscow).
"""

import pytz
from datetime import datetime
from typing import Optional

# Московский часовой пояс
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


def get_moscow_now() -> datetime:
    """
    Получает текущее время в московском часовом поясе.
    
    Returns:
        datetime с московским часовым поясом
    """
    return datetime.now(MOSCOW_TZ)


def to_moscow_time(dt: datetime) -> datetime:
    """
    Конвертирует datetime в московский часовой пояс.
    
    Args:
        dt: datetime объект (может быть naive или aware)
        
    Returns:
        datetime с московским часовым поясом
    """
    if dt.tzinfo is None:
        # Если datetime без timezone, считаем что это UTC
        dt = pytz.utc.localize(dt)
    
    return dt.astimezone(MOSCOW_TZ)


def format_moscow_time(dt: Optional[datetime] = None, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Форматирует datetime в строку с московским временем.
    
    Args:
        dt: datetime объект для форматирования (если None, используется текущее время)
        format_str: Формат строки (по умолчанию '%Y-%m-%d %H:%M:%S')
        
    Returns:
        Отформатированная строка с московским временем
    """
    if dt is None:
        dt = get_moscow_now()
    else:
        dt = to_moscow_time(dt)
    
    return dt.strftime(format_str)


def get_moscow_date_str(dt: Optional[datetime] = None) -> str:
    """
    Получает дату в московском времени в формате YYYY-MM-DD.
    
    Args:
        dt: datetime объект (если None, используется текущее время)
        
    Returns:
        Строка даты в формате YYYY-MM-DD
    """
    return format_moscow_time(dt, '%Y-%m-%d')


def get_moscow_datetime_str(dt: Optional[datetime] = None) -> str:
    """
    Получает дату и время в московском времени в формате DD.MM.YYYY HH:MM.
    
    Args:
        dt: datetime объект (если None, используется текущее время)
        
    Returns:
        Строка даты и времени в формате DD.MM.YYYY HH:MM
    """
    return format_moscow_time(dt, '%d.%m.%Y %H:%M')


def get_moscow_timestamp_str(dt: Optional[datetime] = None) -> str:
    """
    Получает timestamp в московском времени в формате YYYYMMDD_HHMMSS.
    
    Args:
        dt: datetime объект (если None, используется текущее время)
        
    Returns:
        Строка timestamp в формате YYYYMMDD_HHMMSS
    """
    return format_moscow_time(dt, '%Y%m%d_%H%M%S')
