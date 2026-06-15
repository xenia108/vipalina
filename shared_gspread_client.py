"""
Централизованный gspread клиент для всех модулей системы.

Использует паттерн Singleton для предотвращения дублирования клиентов Google Sheets API.
Каждый модуль должен использовать get_shared_gspread_client() вместо создания своего клиента.
"""

import gspread
import logging
from typing import Optional
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)


class SharedGspreadClient:
    """
    Singleton класс для управления единым gspread клиентом.
    
    Преимущества:
    - Одна авторизация вместо множественных
    - Экономия памяти (один кэш вместо нескольких)
    - Снижение нагрузки на Google API
    """
    
    _instance: Optional[gspread.Client] = None
    _credentials_file: Optional[str] = None
    
    @classmethod
    def get_client(cls, credentials_file: str = None) -> gspread.Client:
        """
        Возвращает единый экземпляр gspread клиента.
        
        Args:
            credentials_file: Путь к JSON файлу с credentials (только при первом вызове)
            
        Returns:
            gspread.Client: Авторизованный клиент
            
        Raises:
            ValueError: Если credentials_file не указан при первом вызове
        """
        if cls._instance is None:
            if credentials_file is None:
                # Пытаемся использовать значение по умолчанию из config
                try:
                    from config import GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE
                    credentials_file = GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE
                except ImportError:
                    raise ValueError(
                        "credentials_file must be provided on first call to get_client() "
                        "or GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE must be defined in config.py"
                    )
            
            cls._credentials_file = credentials_file
            cls._instance = cls._authorize(credentials_file)
            logger.info(f"✅ Создан единый gspread клиент (credentials: {credentials_file})")
        
        return cls._instance
    
    @classmethod
    def _authorize(cls, credentials_file: str) -> gspread.Client:
        """
        Авторизует gspread клиент через service account.
        Устанавливает timeout для HTTP-запросов.
        
        Args:
            credentials_file: Путь к JSON файлу с credentials
            
        Returns:
            Авторизованный gspread.Client
        """
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        credentials = Credentials.from_service_account_file(
            credentials_file,
            scopes=scopes
        )
        client = gspread.authorize(credentials)
        # Устанавливаем timeout: 10с на connect, 30с на read
        # Без этого при 503/500 Google запросы висят 3+ минут
        client.http_client.timeout = (10, 30)
        return client
    
    @classmethod
    def reset(cls):
        """
        Сбрасывает клиент (для тестирования или переинициализации).
        """
        cls._instance = None
        cls._credentials_file = None
        logger.info("🔄 Gspread клиент сброшен")


def get_shared_gspread_client(credentials_file: str = None) -> gspread.Client:
    """
    Удобная функция для получения единого gspread клиента.
    
    Args:
        credentials_file: Путь к JSON файлу (опционально, используется из config)
        
    Returns:
        gspread.Client: Авторизованный клиент
        
    Example:
        from shared_gspread_client import get_shared_gspread_client
        
        gc = get_shared_gspread_client()
        spreadsheet = gc.open_by_key('your-spreadsheet-id')
    """
    return SharedGspreadClient.get_client(credentials_file)
