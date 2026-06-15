"""
Централизованная система логирования для VipAlina.
Логи сохраняются в Google Sheets и файлы с ротацией.
"""

import logging
import sys
from datetime import datetime
from typing import Optional
import gspread
from google.oauth2.service_account import Credentials
from logging.handlers import RotatingFileHandler
import asyncio
from async_sheets_wrapper import AsyncSheetsWrapper

from config import (
    GOOGLE_SHEETS_CREDENTIALS_FILE,
    GOOGLE_SHEETS_ID,
    LOG_LEVEL
)

# Для логирования используем сервисный аккаунт
LOGGING_CREDENTIALS_FILE = "vipalina_google_service_account.json"

# Название вкладки для логов в Google Sheets
LOGS_SHEET_TAB = "System Logs"


class GoogleSheetsHandler(logging.Handler):
    """
    Handler для отправки логов в Google Sheets.
    Использует асинхронную запись для не блокирования.
    """
    
    def __init__(self, spreadsheet_id: str, credentials_file: str = None):
        super().__init__()
        self.spreadsheet_id = spreadsheet_id
        # Используем правильный файл учетных данных для логирования
        self.credentials_file = credentials_file or LOGGING_CREDENTIALS_FILE
        self.worksheet = None
        self._init_worksheet()
    
    def _init_worksheet(self):
        """Инициализирует подключение к Google Sheets."""
        try:
            from shared_gspread_client import get_shared_gspread_client
            
            gc = get_shared_gspread_client(self.credentials_file)
            spreadsheet = gc.open_by_key(self.spreadsheet_id)
            
            # Пытаемся открыть существующий лист или создаем новый
            try:
                self.worksheet = spreadsheet.worksheet(LOGS_SHEET_TAB)
            except gspread.exceptions.WorksheetNotFound:
                self.worksheet = spreadsheet.add_worksheet(
                    title=LOGS_SHEET_TAB,
                    rows=10000,
                    cols=10
                )
                self._init_headers()
            
        except Exception as e:
            print(f"Ошибка инициализации Google Sheets для логов: {e}")
    
    def _init_headers(self):
        """Инициализирует заголовки таблицы логов."""
        try:
            headers = [
                'Timestamp',
                'Level',
                'Logger',
                'Message',
                'Module',
                'Function',
                'Line',
                'Thread',
                'Process',
                'Extra Info'
            ]
            
            self.worksheet.update('A1:J1', [headers])
            self.worksheet.format('A1:J1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.2, 'green': 0.2, 'blue': 0.8}
            })
            
        except Exception as e:
            print(f"Ошибка при инициализации заголовков логов: {e}")
    
    def emit(self, record: logging.LogRecord):
        """
        Отправляет запись лога в Google Sheets асинхронно.
        
        Args:
            record: Запись лога
        """
        try:
            # Форматируем запись
            log_entry = [
                datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
                record.levelname,
                record.name,
                self.format(record),
                record.module,
                record.funcName,
                str(record.lineno),
                str(record.thread),
                str(record.process),
                getattr(record, 'extra_info', '')
            ]
            
            # Асинхронно добавляем в Google Sheets (не блокируем)
            if self.worksheet:
                try:
                    # Создаем task для асинхронной записи
                    loop = asyncio.get_event_loop()
                    loop.create_task(self._async_append(log_entry))
                except RuntimeError:
                    # Если нет event loop, записываем синхронно (только для критических логов)
                    if record.levelno >= logging.ERROR:
                        self.worksheet.append_row(log_entry)
                        
        except Exception as e:
            # Не падаем при ошибке логирования
            print(f"Ошибка при записи лога в Google Sheets: {e}")
    
    async def _async_append(self, log_entry: list):
        """Асинхронно добавляет запись в Google Sheets."""
        try:
            await AsyncSheetsWrapper.run_sync(
                self.worksheet.append_row,
                log_entry
            )
        except Exception as e:
            print(f"Ошибка async записи лога: {e}")


def setup_centralized_logging(log_level: Optional[str] = None):
    """
    Настраивает централизованную систему логирования.
    
    Логи записываются в:
    1. Консоль (stdout)
    2. Файл с ротацией (vipalina.log)
    3. Google Sheets (для важных событий) - опционально
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    import os
    
    # Создаем директорию для логов, если ее нет
    os.makedirs('vipalina_logs', exist_ok=True)
    
    # Определяем уровень логирования
    level = getattr(logging, (log_level or LOG_LEVEL).upper(), logging.INFO)
    
    # Создаем корневой logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Удаляем существующие handlers
    root_logger.handlers.clear()
    
    # Формат логов
    detailed_format = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_format = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_format)
    root_logger.addHandler(console_handler)
    
    # 2. File Handler с ротацией (максимум 10 MB, 5 файлов)
    try:
        file_handler = RotatingFileHandler(
            'vipalina_logs/vipalina.log',
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_format)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Не удалось создать file handler: {e}")
    
    # 3. Google Sheets Handler - ОТКЛЮЧЕН
    # Причина: запись логов в ту же таблицу KPI Ultra перегружает Google Sheets
    # и вызывает timeout при чтении данных студентов (48000+ строк логов + 85 листов с формулами)
    # Файловый лог достаточен для диагностики.
    print("ℹ️ Google Sheets logging отключен (файловый лог активен)")
    
    # Логируем успешную настройку
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info("ЦЕНТРАЛИЗОВАННОЕ ЛОГИРОВАНИЕ НАСТРОЕНО")
    logger.info(f"Уровень логирования: {logging.getLevelName(level)}")
    logger.info(f"Handlers: Console, File (vipalina_logs/vipalina.log)")
    logger.info("=" * 80)


def get_logger(name: str) -> logging.Logger:
    """
    Получает logger с заданным именем.
    
    Args:
        name: Имя logger'а (обычно __name__)
        
    Returns:
        Настроенный logger
    """
    return logging.getLogger(name)
