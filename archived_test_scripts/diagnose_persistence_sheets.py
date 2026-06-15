#!/usr/bin/env python3
"""
Диагностический скрипт для проверки работы листов Active_SLA_Requests, 
Onboarding_Progress и Student_Messages в таблице "Логи Випалина".

Проверяет:
1. Структуру листов (заголовки)
2. Наличие данных
3. Типы данных и форматирование
4. Потенциальные проблемы (дубликаты, пустые значения, неверный формат)
"""

import logging
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('diagnostics')

# Конфигурация
CREDENTIALS_FILE = "vipalina_google_service_account.json"
SPREADSHEET_ID = "1wWbgAq92qehpTO0lm4AQJzTQ8RvpA9fX_vORYBqkHCE"

# Названия листов для проверки
SHEETS_TO_CHECK = {
    "Active_SLA_Requests": {
        "expected_headers": ["chat_id", "student_id", "student_name", "request_text", 
                           "request_time", "is_working_hours", "created_at"],
        "key_columns": [0, 1]  # chat_id, student_id
    },
    "Onboarding_Progress": {
        "expected_headers": ["getcourse_id", "student_name", "manager_name", "telegram_id",
                           "telegram_username", "start_time", "message_id", "steps_json",
                           "overall_status", "errors_json", "updated_at"],
        "key_columns": [0]  # getcourse_id
    },
    "Student_Messages": {
        "expected_headers": ["timestamp", "date", "time", "chat_id", "student_id",
                           "getcourse_id", "student_name", "manager_name",
                           "message_type", "message_text", "course"],
        "key_columns": [3, 4, 0]  # chat_id, student_id, timestamp
    }
}


class SheetDiagnostics:
    """Класс для диагностики листов Google Sheets"""
    
    def __init__(self):
        """Инициализация подключения к Google Sheets"""
        logger.info("🔌 Подключение к Google Sheets...")
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            credentials = Credentials.from_service_account_file(
                CREDENTIALS_FILE,
                scopes=scopes
            )
            self.gc = gspread.authorize(credentials)
            self.spreadsheet = self.gc.open_by_key(SPREADSHEET_ID)
            logger.info(f"✅ Подключено к таблице: {self.spreadsheet.title}")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            raise
    
    def check_all_sheets(self):
        """Проверяет все листы"""
        logger.info("\n" + "="*80)
        logger.info("🔍 ДИАГНОСТИКА ЛИСТОВ В ТАБЛИЦЕ 'Логи Випалина'")
        logger.info("="*80)
        
        # Получаем список всех листов
        all_worksheets = self.spreadsheet.worksheets()
        all_sheet_names = [ws.title for ws in all_worksheets]
        
        logger.info(f"\n📋 Всего листов в таблице: {len(all_sheet_names)}")
        logger.info(f"Листы: {', '.join(all_sheet_names)}")
        
        # Проверяем каждый лист
        for sheet_name, config in SHEETS_TO_CHECK.items():
            logger.info("\n" + "-"*80)
            self.check_sheet(sheet_name, config, all_sheet_names)
    
    def check_sheet(self, sheet_name: str, config: dict, all_sheet_names: list):
        """
        Проверяет конкретный лист
        
        Args:
            sheet_name: Название листа
            config: Конфигурация с ожидаемыми заголовками
            all_sheet_names: Список всех листов в таблице
        """
        logger.info(f"\n📄 ПРОВЕРКА ЛИСТА: {sheet_name}")
        logger.info("─"*80)
        
        # Проверка 1: Существует ли лист
        if sheet_name not in all_sheet_names:
            logger.error(f"❌ ПРОБЛЕМА: Лист '{sheet_name}' НЕ НАЙДЕН в таблице!")
            logger.info(f"   Возможные причины:")
            logger.info(f"   - Лист был удален")
            logger.info(f"   - Лист имеет другое название (проверьте регистр букв)")
            logger.info(f"   - Лист еще не был создан при инициализации")
            return
        
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            logger.info(f"✅ Лист найден")
            
            # Получаем все данные
            all_values = worksheet.get_all_values()
            
            if not all_values:
                logger.warning(f"⚠️  Лист пустой (нет данных)")
                return
            
            # Проверка 2: Заголовки
            actual_headers = all_values[0] if all_values else []
            expected_headers = config['expected_headers']
            
            logger.info(f"\n🏷️  ЗАГОЛОВКИ:")
            logger.info(f"   Ожидается: {len(expected_headers)} столбцов")
            logger.info(f"   Фактически: {len(actual_headers)} столбцов")
            
            # Сравниваем заголовки
            if actual_headers == expected_headers:
                logger.info(f"   ✅ Заголовки совпадают полностью")
            else:
                logger.warning(f"   ⚠️  НЕСООТВЕТСТВИЕ ЗАГОЛОВКОВ!")
                logger.info(f"\n   Ожидаемые заголовки:")
                for i, h in enumerate(expected_headers):
                    logger.info(f"      {i+1}. {h}")
                logger.info(f"\n   Фактические заголовки:")
                for i, h in enumerate(actual_headers):
                    match = "✅" if i < len(expected_headers) and h == expected_headers[i] else "❌"
                    logger.info(f"      {i+1}. {h} {match}")
                
                # Показываем отличия
                missing = set(expected_headers) - set(actual_headers)
                extra = set(actual_headers) - set(expected_headers)
                if missing:
                    logger.warning(f"   ❌ Отсутствуют столбцы: {', '.join(missing)}")
                if extra:
                    logger.warning(f"   ⚠️  Лишние столбцы: {', '.join(extra)}")
            
            # Проверка 3: Количество данных
            data_rows = all_values[1:] if len(all_values) > 1 else []
            logger.info(f"\n📊 ДАННЫЕ:")
            logger.info(f"   Строк с данными: {len(data_rows)}")
            
            if len(data_rows) == 0:
                logger.warning(f"   ⚠️  Нет данных (только заголовки)")
                return
            
            # Проверка 4: Анализ данных
            self.analyze_data(sheet_name, data_rows, actual_headers, config)
            
        except gspread.WorksheetNotFound:
            logger.error(f"❌ ОШИБКА: Лист '{sheet_name}' не найден (исключение)")
        except Exception as e:
            logger.error(f"❌ ОШИБКА при проверке листа: {e}", exc_info=True)
    
    def analyze_data(self, sheet_name: str, data_rows: list, headers: list, config: dict):
        """
        Анализирует данные в листе на наличие проблем
        
        Args:
            sheet_name: Название листа
            data_rows: Строки с данными
            headers: Заголовки столбцов
            config: Конфигурация листа
        """
        logger.info(f"\n🔬 АНАЛИЗ ДАННЫХ:")
        
        # Статистика по заполненности столбцов
        empty_counts = defaultdict(int)
        total_rows = len(data_rows)
        
        for row in data_rows:
            for i, value in enumerate(row):
                if not value or value.strip() == '':
                    col_name = headers[i] if i < len(headers) else f"Column_{i+1}"
                    empty_counts[col_name] += 1
        
        # Показываем статистику пустых значений
        if empty_counts:
            logger.info(f"\n   📉 Пустые значения по столбцам:")
            for col_name, count in sorted(empty_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_rows) * 100
                status = "⚠️ " if percentage > 50 else ""
                logger.info(f"      {status}{col_name}: {count}/{total_rows} ({percentage:.1f}%)")
        
        # Проверка дубликатов по ключевым столбцам
        key_columns = config.get('key_columns', [])
        if key_columns:
            logger.info(f"\n   🔑 Проверка дубликатов по ключевым столбцам:")
            seen_keys = defaultdict(list)
            
            for row_idx, row in enumerate(data_rows, start=2):  # +2 для учета заголовка
                key_values = []
                for col_idx in key_columns:
                    if col_idx < len(row):
                        key_values.append(row[col_idx])
                    else:
                        key_values.append('')
                
                key = tuple(key_values)
                seen_keys[key].append(row_idx)
            
            # Находим дубликаты
            duplicates = {k: v for k, v in seen_keys.items() if len(v) > 1}
            
            if duplicates:
                logger.warning(f"      ⚠️  Найдено {len(duplicates)} групп дубликатов:")
                for key, rows in list(duplicates.items())[:5]:  # Показываем первые 5
                    logger.warning(f"         Ключ {key}: строки {rows}")
                if len(duplicates) > 5:
                    logger.warning(f"         ... и еще {len(duplicates) - 5} групп")
            else:
                logger.info(f"      ✅ Дубликатов не найдено")
        
        # Специальные проверки для каждого листа
        if sheet_name == "Active_SLA_Requests":
            self.analyze_sla_requests(data_rows, headers)
        elif sheet_name == "Onboarding_Progress":
            self.analyze_onboarding_progress(data_rows, headers)
        elif sheet_name == "Student_Messages":
            self.analyze_student_messages(data_rows, headers)
        
        # Показываем примеры последних записей
        logger.info(f"\n   📝 Примеры последних 3 записей:")
        for i, row in enumerate(data_rows[-3:], start=1):
            logger.info(f"      Запись {len(data_rows) - 3 + i}:")
            for col_idx, value in enumerate(row[:min(5, len(row))]):  # Первые 5 столбцов
                col_name = headers[col_idx] if col_idx < len(headers) else f"Col{col_idx+1}"
                display_value = value[:50] + "..." if len(str(value)) > 50 else value
                logger.info(f"         {col_name}: {display_value}")
    
    def analyze_sla_requests(self, data_rows: list, headers: list):
        """Специальная проверка для Active_SLA_Requests"""
        logger.info(f"\n   🎯 Специфичные проверки для SLA-запросов:")
        
        # Проверяем активные запросы (не должно быть слишком много старых)
        try:
            request_time_idx = headers.index('request_time') if 'request_time' in headers else -1
            
            if request_time_idx >= 0:
                old_requests = 0
                now = datetime.now()
                
                for row in data_rows:
                    if request_time_idx < len(row) and row[request_time_idx]:
                        try:
                            req_time = datetime.strptime(row[request_time_idx], '%Y-%m-%d %H:%M:%S')
                            age_hours = (now - req_time).total_seconds() / 3600
                            if age_hours > 24:  # Старше 24 часов
                                old_requests += 1
                        except:
                            pass
                
                if old_requests > 0:
                    logger.warning(f"      ⚠️  Найдено {old_requests} запросов старше 24 часов")
                    logger.warning(f"         (они должны быть удалены после ответа менеджера)")
                else:
                    logger.info(f"      ✅ Нет старых запросов (все свежие)")
        except Exception as e:
            logger.warning(f"      ⚠️  Не удалось проверить возраст запросов: {e}")
    
    def analyze_onboarding_progress(self, data_rows: list, headers: list):
        """Специальная проверка для Onboarding_Progress"""
        logger.info(f"\n   🎯 Специфичные проверки для онбординга:")
        
        try:
            status_idx = headers.index('overall_status') if 'overall_status' in headers else -1
            
            if status_idx >= 0:
                status_counts = defaultdict(int)
                
                for row in data_rows:
                    if status_idx < len(row) and row[status_idx]:
                        status_counts[row[status_idx]] += 1
                
                logger.info(f"      Статусы онбординга:")
                for status, count in status_counts.items():
                    logger.info(f"         {status}: {count}")
                
                # Предупреждение о застрявших онбордингах
                in_progress = status_counts.get('in_progress', 0)
                if in_progress > 10:
                    logger.warning(f"      ⚠️  Много онбордингов 'in_progress' ({in_progress})")
                    logger.warning(f"         Возможно, некоторые зависли и не завершились")
        except Exception as e:
            logger.warning(f"      ⚠️  Не удалось проверить статусы: {e}")
    
    def analyze_student_messages(self, data_rows: list, headers: list):
        """Специальная проверка для Student_Messages"""
        logger.info(f"\n   🎯 Специфичные проверки для сообщений студентов:")
        
        try:
            # Статистика по типам сообщений
            msg_type_idx = headers.index('message_type') if 'message_type' in headers else -1
            
            if msg_type_idx >= 0:
                type_counts = defaultdict(int)
                
                for row in data_rows:
                    if msg_type_idx < len(row) and row[msg_type_idx]:
                        type_counts[row[msg_type_idx]] += 1
                
                logger.info(f"      Типы сообщений:")
                for msg_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                    logger.info(f"         {msg_type}: {count}")
            
            # Проверяем дату последнего сообщения
            if data_rows:
                last_row = data_rows[-1]
                timestamp_idx = headers.index('timestamp') if 'timestamp' in headers else -1
                
                if timestamp_idx >= 0 and timestamp_idx < len(last_row):
                    last_timestamp = last_row[timestamp_idx]
                    logger.info(f"      Последнее сообщение: {last_timestamp}")
        except Exception as e:
            logger.warning(f"      ⚠️  Не удалось проверить статистику сообщений: {e}")


def main():
    """Главная функция"""
    try:
        diagnostics = SheetDiagnostics()
        diagnostics.check_all_sheets()
        
        logger.info("\n" + "="*80)
        logger.info("✅ ДИАГНОСТИКА ЗАВЕРШЕНА")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
