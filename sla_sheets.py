"""
Модуль интеграции SLA-данных с Google Sheets.
Сохраняет результаты трекинга времени ответа менеджеров.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import gspread
from google.oauth2.service_account import Credentials

from config import (
    GOOGLE_SHEETS_CREDENTIALS_FILE,
    SLA_GOOGLE_SHEETS_ID,
    SLA_GOOGLE_SHEETS_TAB,
    SLA_RESPONSE_TIME_LIMIT
)
# Для SLA используем сервисный аккаунт
SLA_CREDENTIALS_FILE = "vipalina_google_service_account.json"

logger = logging.getLogger('vipalina_sla_sheets')


class SLASheetsIntegration:
    """
    Интеграция с Google Sheets для хранения SLA-данных.
    """
    
    def __init__(self):
        """Инициализация интеграции с Google Sheets"""
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            from shared_gspread_client import get_shared_gspread_client
            self.client = get_shared_gspread_client(SLA_CREDENTIALS_FILE)
            self.spreadsheet = self.client.open_by_key(SLA_GOOGLE_SHEETS_ID)
            
            # Получаем или создаём вкладку
            try:
                self.worksheet = self.spreadsheet.worksheet(SLA_GOOGLE_SHEETS_TAB)
            except gspread.WorksheetNotFound:
                self.worksheet = self.spreadsheet.add_worksheet(
                    title=SLA_GOOGLE_SHEETS_TAB,
                    rows=1000,
                    cols=15
                )
                self._setup_headers()
            
            logger.info(f"Подключение к Google Sheets SLA успешно: {SLA_GOOGLE_SHEETS_ID}")
            
        except Exception as e:
            logger.error(f"Ошибка подключения к Google Sheets SLA: {e}", exc_info=True)
            logger.error(f"Проверьте файл учетных данных: {SLA_CREDENTIALS_FILE}")
            logger.error(f"Проверьте доступ к таблице: {SLA_GOOGLE_SHEETS_ID}")
            raise    
    def _setup_headers(self):
        """Устанавливает заголовки колонок"""
        headers = [
            'Дата',
            'Время запроса',
            'Студент',
            'GetCourse ID',
            'Менеджер',
            'Время ответа',
            'Время реакции (мин)',
            'Рабочее время?',
            'SLA ≤15 мин?',
            'Chat ID',
            'Student ID',
            'Manager ID',
            'Текст запроса (фрагмент)',
            'Месяц',
            'Год',
            'Ссылка на чат'  # Колонка P
        ]
        
        try:
            self.worksheet.update('A1:P1', [headers])
            logger.info("Заголовки установлены в таблице SLA")
        except Exception as e:
            logger.error(f"Ошибка при установке заголовков: {e}")
    
    def save_sla_record(
        self,
        sla_data: Dict[str, Any],
        getcourse_id: Optional[str] = None,
        invite_link: Optional[str] = None
    ) -> bool:
        """
        Сохраняет запись о SLA в таблицу.
        
        Args:
            sla_data: Данные SLA-трекинга
            getcourse_id: GetCourse ID студента (опционально)
            invite_link: Invite-ссылка на чат (опционально)
            
        Returns:
            True если запись сохранена успешно
        """
        try:
            request_time = sla_data['request_time']
            response_time = sla_data['response_time']
            
            # Форматируем время реакции в H:MM:SS
            response_minutes = sla_data['response_minutes']
            hours = int(response_minutes // 60)
            mins = int(response_minutes % 60)
            secs = int((response_minutes % 1) * 60)
            response_duration = f"{hours}:{mins:02d}:{secs:02d}"
            
            # Форматируем данные для записи
            row_data = [
                request_time.strftime('%Y-%m-%d'),  # Дата
                request_time.strftime('%H:%M:%S'),  # Время запроса
                sla_data['student_name'],  # Студент
                getcourse_id if getcourse_id else '',  # GetCourse ID
                sla_data['manager_name'],  # Менеджер
                response_time.strftime('%H:%M:%S'),  # Время ответа
                response_duration,  # Время реакции (H:MM:SS)
                'Да' if sla_data['is_working_hours'] else 'Нет',  # Рабочее время?
                'Да' if sla_data['sla_met'] else 'Нет',  # SLA соблюдён?
                str(sla_data['chat_id']),  # Chat ID
                str(sla_data['student_id']),  # Student ID
                str(sla_data['manager_id']),  # Manager ID
                sla_data.get('request_text', '')[:100],  # Текст запроса (фрагмент)
                request_time.strftime('%B'),  # Месяц
                request_time.strftime('%Y'),  # Год
                invite_link if invite_link else ''  # Ссылка на чат
            ]
            
            # Добавляем строку в таблицу
            self.worksheet.append_row(row_data, value_input_option='USER_ENTERED')
            
            logger.info(
                f"SLA-запись сохранена: {sla_data['student_name']} -> {sla_data['manager_name']}, "
                f"{sla_data['response_minutes']:.1f} мин"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении SLA-записи: {e}", exc_info=True)
            logger.error(f"Данные SLA: {sla_data}")
            logger.error(f"GetCourse ID: {getcourse_id}")
            logger.error(f"Invite link: {invite_link}")
            return False
    
    def get_monthly_stats(self, year: int, month: int) -> Dict[str, Any]:
        """
        Получает статистику SLA за месяц.
        
        Args:
            year: Год
            month: Месяц (1-12)
            
        Returns:
            Dict со статистикой
        """
        try:
            # Получаем все данные
            all_data = self.worksheet.get_all_values()
            
            if len(all_data) <= 1:
                return self._empty_stats()
            
            # Пропускаем заголовки
            data_rows = all_data[1:]
            
            # Английские названия месяцев (как в таблице)
            english_months = {
                1: 'January', 2: 'February', 3: 'March', 4: 'April',
                5: 'May', 6: 'June', 7: 'July', 8: 'August',
                9: 'September', 10: 'October', 11: 'November', 12: 'December'
            }
            month_name = english_months.get(month, '')
            year_str = str(year)
            
            filtered_rows = [
                row for row in data_rows
                if len(row) >= 15 and row[13] == month_name and row[14] == year_str
            ]
            
            if not filtered_rows:
                return self._empty_stats()
            
            # Исключаем дежурные аккаунты из статистики
            excluded_managers = ['Черный Дежурный', 'Синий Дежурный', 'Изумрудный Дежурный']
            filtered_rows = [
                row for row in filtered_rows
                if len(row) >= 5 and row[4] not in excluded_managers
            ]
            
            if not filtered_rows:
                return self._empty_stats()
            
            # Фильтруем только рабочее время для KPI
            working_hours_rows = [row for row in filtered_rows if len(row) >= 8 and row[7] == 'Да']
            
            # Подсчитываем статистику
            stats = {
                'total_requests': len(filtered_rows),
                'working_hours_requests': len(working_hours_rows),
                'sla_met_count': 0,
                'sla_not_met_count': 0,
                'avg_response_time': 0,
                'by_manager': {}
            }
            
            total_time = 0
            
            for row in working_hours_rows:
                # Парсим время реакции (поддержка старого и нового формата)
                response_time_str = row[6] if row[6] else '0'
                
                # Новый формат H:MM:SS
                if ':' in response_time_str:
                    parts = response_time_str.split(':')
                    if len(parts) == 3:
                        hours, mins, secs = int(parts[0]), int(parts[1]), int(parts[2])
                        response_time = hours * 60 + mins + secs / 60
                    else:
                        response_time = 0
                else:
                    # Старый формат (минуты с запятой/точкой)
                    response_time = float(response_time_str.replace(',', '.')) if response_time_str else 0
                
                sla_met = row[8] == 'Да'
                manager_name = row[4]
                
                if sla_met:
                    stats['sla_met_count'] += 1
                else:
                    stats['sla_not_met_count'] += 1
                
                total_time += response_time
                
                # Статистика по менеджерам
                if manager_name not in stats['by_manager']:
                    stats['by_manager'][manager_name] = {
                        'requests': 0,
                        'sla_met': 0,
                        'total_time': 0
                    }
                
                stats['by_manager'][manager_name]['requests'] += 1
                stats['by_manager'][manager_name]['total_time'] += response_time
                if sla_met:
                    stats['by_manager'][manager_name]['sla_met'] += 1
            
            # Рассчитываем средние значения
            if working_hours_rows:
                stats['avg_response_time'] = round(total_time / len(working_hours_rows), 2)
            
            for manager_name in stats['by_manager']:
                manager_stats = stats['by_manager'][manager_name]
                if manager_stats['requests'] > 0:
                    manager_stats['avg_time'] = round(
                        manager_stats['total_time'] / manager_stats['requests'],
                        2
                    )
                    manager_stats['sla_percentage'] = round(
                        (manager_stats['sla_met'] / manager_stats['requests']) * 100,
                        1
                    )
            
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}", exc_info=True)
            return self._empty_stats()
    
    def _empty_stats(self) -> Dict[str, Any]:
        """Возвращает пустую статистику"""
        return {
            'total_requests': 0,
            'working_hours_requests': 0,
            'sla_met_count': 0,
            'sla_not_met_count': 0,
            'avg_response_time': 0,
            'by_manager': {}
        }
