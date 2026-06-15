"""
State Manager для VipAlina.
Сохраняет состояние операций в Google Sheets для обработки offline/restart сценариев.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
from async_sheets_wrapper import AsyncSheetsWrapper

from config import (
    GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE as GOOGLE_SHEETS_CREDENTIALS_FILE,
    GOOGLE_SHEETS_ID
)

logger = logging.getLogger(__name__)

# Название вкладки для состояний в Google Sheets
STATE_SHEET_TAB = "System State"


class StateManager:
    """
    Управляет состоянием системы с сохранением в Google Sheets.
    Позволяет восстанавливать состояние после рестартов.
    """
    
    def __init__(self):
        """Инициализация State Manager."""
        self.worksheet = None
        self.pending_operations: Dict[str, Dict[str, Any]] = {}
        logger.info("State Manager создан")
    
    async def initialize(self):
        """Инициализирует подключение к Google Sheets."""
        try:
            scopes = ['https://www.googleapis.com/auth/spreadsheets']
            credentials = await AsyncSheetsWrapper.run_sync(
                Credentials.from_service_account_file,
                GOOGLE_SHEETS_CREDENTIALS_FILE,
                scopes=scopes
            )
            
            gc = await AsyncSheetsWrapper.run_sync(
                gspread.authorize,
                credentials
            )
            
            spreadsheet = await AsyncSheetsWrapper.run_sync(
                gc.open_by_key,
                GOOGLE_SHEETS_ID
            )
            
            # Пытаемся открыть существующий лист или создаем новый
            try:
                self.worksheet = await AsyncSheetsWrapper.run_sync(
                    spreadsheet.worksheet,
                    STATE_SHEET_TAB
                )
                logger.info(f"Подключен к существующему листу '{STATE_SHEET_TAB}'")
            except gspread.exceptions.WorksheetNotFound:
                self.worksheet = await AsyncSheetsWrapper.run_sync(
                    spreadsheet.add_worksheet,
                    title=STATE_SHEET_TAB,
                    rows=1000,
                    cols=10
                )
                logger.info(f"Создан новый лист '{STATE_SHEET_TAB}'")
                await self._init_headers()
            
            logger.info("✅ State Manager инициализирован")
            
        except Exception as e:
            logger.error(f"Ошибка инициализации State Manager: {e}", exc_info=True)
            raise
    
    async def _init_headers(self):
        """Инициализирует заголовки таблицы состояний."""
        try:
            headers = [
                'Operation ID',
                'Type',
                'Status',
                'Data (JSON)',
                'Created At',
                'Updated At',
                'Retry Count',
                'Last Error',
                'Completed At',
                'Notes'
            ]
            
            await AsyncSheetsWrapper.run_sync(
                self.worksheet.update,
                'A1:J1',
                [headers]
            )
            
            await AsyncSheetsWrapper.run_sync(
                self.worksheet.format,
                'A1:J1',
                {
                    'textFormat': {'bold': True},
                    'backgroundColor': {'red': 0.2, 'green': 0.6, 'blue': 0.2}
                }
            )
            
            logger.info("Инициализированы заголовки таблицы состояний")
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации заголовков состояний: {e}")
    
    async def save_operation(
        self,
        operation_id: str,
        operation_type: str,
        data: Dict[str, Any],
        status: str = "pending"
    ) -> bool:
        """
        Сохраняет операцию в Google Sheets.
        
        Args:
            operation_id: Уникальный ID операции
            operation_type: Тип операции (onboarding, message_send, etc.)
            data: Данные операции
            status: Статус (pending, in_progress, completed, failed)
            
        Returns:
            True если сохранено успешно
        """
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            row_data = [
                operation_id,
                operation_type,
                status,
                json.dumps(data, ensure_ascii=False),
                current_time,
                current_time,
                '0',  # retry count
                '',   # last error
                '',   # completed at
                ''    # notes
            ]
            
            # Проверяем, существует ли операция
            existing_row = await self._find_operation_row(operation_id)
            
            if existing_row:
                # Обновляем существующую
                await AsyncSheetsWrapper.run_sync(
                    self.worksheet.update,
                    f'A{existing_row}:J{existing_row}',
                    [row_data]
                )
                logger.debug(f"Обновлена операция {operation_id}")
            else:
                # Добавляем новую
                await AsyncSheetsWrapper.run_sync(
                    self.worksheet.append_row,
                    row_data
                )
                logger.info(f"Сохранена операция {operation_id}: {operation_type}")
            
            # Сохраняем в локальный кеш
            self.pending_operations[operation_id] = {
                'type': operation_type,
                'data': data,
                'status': status,
                'created_at': current_time
            }
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении операции {operation_id}: {e}", exc_info=True)
            return False
    
    async def update_operation_status(
        self,
        operation_id: str,
        status: str,
        error: Optional[str] = None,
        increment_retry: bool = False
    ) -> bool:
        """
        Обновляет статус операции.
        
        Args:
            operation_id: ID операции
            status: Новый статус
            error: Текст ошибки (если есть)
            increment_retry: Увеличить счетчик попыток
            
        Returns:
            True если обновлено успешно
        """
        try:
            row_number = await self._find_operation_row(operation_id)
            
            if not row_number:
                logger.warning(f"Операция {operation_id} не найдена для обновления")
                return False
            
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Получаем текущие данные
            row_data = await AsyncSheetsWrapper.run_sync(
                self.worksheet.row_values,
                row_number
            )
            
            # Обновляем поля
            row_data[2] = status  # Status
            row_data[5] = current_time  # Updated At
            
            if increment_retry and len(row_data) > 6:
                try:
                    retry_count = int(row_data[6]) + 1
                    row_data[6] = str(retry_count)
                except (ValueError, IndexError):
                    row_data[6] = '1'
            
            if error and len(row_data) > 7:
                row_data[7] = error  # Last Error
            
            if status == 'completed' and len(row_data) > 8:
                row_data[8] = current_time  # Completed At
            
            # Сохраняем
            await AsyncSheetsWrapper.run_sync(
                self.worksheet.update,
                f'A{row_number}:J{row_number}',
                [row_data]
            )
            
            # Обновляем локальный кеш
            if operation_id in self.pending_operations:
                self.pending_operations[operation_id]['status'] = status
                if status == 'completed':
                    del self.pending_operations[operation_id]
            
            logger.debug(f"Обновлен статус операции {operation_id}: {status}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса операции {operation_id}: {e}", exc_info=True)
            return False
    
    async def _find_operation_row(self, operation_id: str) -> Optional[int]:
        """Находит строку операции по ID."""
        try:
            all_values = await AsyncSheetsWrapper.run_sync(
                self.worksheet.col_values,
                1  # Column A (Operation ID)
            )
            
            for i, value in enumerate(all_values[1:], start=2):
                if value == operation_id:
                    return i
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при поиске операции {operation_id}: {e}")
            return None
    
    async def restore_pending_operations(self) -> List[Dict[str, Any]]:
        """
        Восстанавливает незавершенные операции после рестарта.
        
        Returns:
            Список незавершенных операций
        """
        try:
            logger.info("Восстановление незавершенных операций...")
            
            all_data = await AsyncSheetsWrapper.run_sync(
                self.worksheet.get_all_values
            )
            
            if len(all_data) <= 1:
                logger.info("Нет незавершенных операций")
                return []
            
            pending_ops = []
            
            for row in all_data[1:]:  # Пропускаем заголовки
                if len(row) < 4:
                    continue
                
                operation_id = row[0]
                operation_type = row[1]
                status = row[2]
                data_json = row[3]
                
                # Восстанавливаем только pending и in_progress операции
                if status in ['pending', 'in_progress']:
                    try:
                        data = json.loads(data_json)
                        operation = {
                            'id': operation_id,
                            'type': operation_type,
                            'data': data,
                            'status': status
                        }
                        pending_ops.append(operation)
                        self.pending_operations[operation_id] = operation
                    except json.JSONDecodeError:
                        logger.error(f"Не удалось декодировать данные операции {operation_id}")
            
            logger.info(f"Восстановлено {len(pending_ops)} незавершенных операций")
            return pending_ops
            
        except Exception as e:
            logger.error(f"Ошибка при восстановлении операций: {e}", exc_info=True)
            return []
    
    async def save_state(self):
        """Сохраняет текущее состояние всех операций."""
        try:
            logger.info(f"Сохранение состояния ({len(self.pending_operations)} операций)...")
            
            for operation_id, operation in self.pending_operations.items():
                await self.save_operation(
                    operation_id,
                    operation['type'],
                    operation['data'],
                    operation['status']
                )
            
            logger.info("✅ Состояние сохранено")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении состояния: {e}", exc_info=True)
    
    async def cleanup_completed_operations(self, days_old: int = 7):
        """
        Очищает завершенные операции старше указанного количества дней.
        
        Args:
            days_old: Количество дней
        """
        try:
            logger.info(f"Очистка завершенных операций старше {days_old} дней...")
            
            # TODO: Реализовать логику очистки
            # Для этого нужно:
            # 1. Получить все операции
            # 2. Отфильтровать completed операции старше days_old
            # 3. Удалить их из таблицы
            
            logger.info("Очистка завершена")
            
        except Exception as e:
            logger.error(f"Ошибка при очистке операций: {e}", exc_info=True)
