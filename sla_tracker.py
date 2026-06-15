"""
Модуль трекинга SLA (время ответа менеджеров на запросы студентов).
Отслеживает первое сообщение студента за сутки и время ответа менеджера.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pytz

from config import (
    SLA_WORKING_HOURS,
    SLA_RESPONSE_TIME_LIMIT,
    MOSCOW_TZ,
    VIP_MANAGERS_VIP,
    VIP_MANAGERS_LUXURY,
    VIP_HEAD,
    ON_DUTY_ACCOUNTS
)

# Модуль персистенции
try:
    from vipalina_persistence import get_persistence
except ImportError:
    get_persistence = None

logger = logging.getLogger('vipalina_sla')


class SLATracker:
    """
    Трекер SLA для мониторинга времени ответа менеджеров.
    """
    
    def __init__(self):
        self.moscow_tz = pytz.timezone(MOSCOW_TZ)
        # Хранилище активных запросов: {chat_id: {student_id: {'request_time': datetime, 'request_text': str}}}
        self.active_requests: Dict[int, Dict[int, Dict[str, Any]]] = {}
        # Хранилище студентов, которые уже обращались за сутки: {chat_id: {student_id: request_time}}
        self.responded_today: Dict[int, Dict[int, datetime]] = {}
        logger.info("Инициализирован SLA Tracker")
    
    def is_working_hours(self, dt: datetime) -> bool:
        """
        Проверяет, находится ли время в рабочих часах.
        
        Args:
            dt: Время для проверки (должно быть в МСК)
            
        Returns:
            True если рабочее время
        """
        # Получаем день недели
        weekday = dt.strftime('%A').lower()
        
        # Маппинг дней недели
        day_mapping = {
            'monday': 'monday',
            'tuesday': 'tuesday',
            'wednesday': 'wednesday',
            'thursday': 'thursday',
            'friday': 'friday',
            'saturday': 'saturday',
            'sunday': 'sunday'
        }
        
        working_hours = SLA_WORKING_HOURS.get(weekday)
        
        if working_hours is None:
            return False  # Выходной
        
        start_hour, end_hour = working_hours
        current_hour = dt.hour
        
        return start_hour <= current_hour < end_hour
    
    def get_current_day_start(self, now: datetime) -> datetime:
        """
        Возвращает начало текущих "суток" (10:00 текущего дня).
        Если сейчас до 10:00, то начало - это 10:00 вчерашнего дня.
        
        Args:
            now: Текущее время (МСК)
            
        Returns:
            Время начала текущих суток
        """
        if now.hour < 10:
            # Если до 10 утра - сутки начались вчера в 10:00
            day_start = now.replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=1)
        else:
            # Если после 10 утра - сутки начались сегодня в 10:00
            day_start = now.replace(hour=10, minute=0, second=0, microsecond=0)
        
        return day_start
    
    def is_first_request_today(self, chat_id: int, student_id: int, now: datetime) -> bool:
        """
        Проверяет, является ли это первым запросом студента за текущие сутки.
        
        Args:
            chat_id: ID чата
            student_id: ID студента
            now: Текущее время (МСК)
            
        Returns:
            True если это первый запрос за сутки
        """
        day_start = self.get_current_day_start(now)
        
        # Проверяем, есть ли активный запрос от этого студента в этом чате
        if chat_id in self.active_requests:
            if student_id in self.active_requests[chat_id]:
                last_request_time = self.active_requests[chat_id][student_id]['request_time']
                
                # Если последний запрос был после начала текущих суток - это не первый запрос
                if last_request_time >= day_start:
                    return False
        
        # Проверяем, не обращался ли студент уже сегодня (даже если ему уже ответили)
        if chat_id in self.responded_today:
            if student_id in self.responded_today[chat_id]:
                last_responded_time = self.responded_today[chat_id][student_id]
                if last_responded_time >= day_start:
                    return False
        
        return True
    
    def register_student_request(
        self,
        chat_id: int,
        student_id: int,
        student_name: str,
        message_text: str,
        timestamp: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Регистрирует запрос студента.
        
        Args:
            chat_id: ID чата
            student_id: ID студента
            student_name: Имя студента
            message_text: Текст сообщения
            timestamp: Время сообщения (должно быть в МСК)
            
        Returns:
            Dict с данными запроса если это первый запрос за сутки, иначе None
        """
        # Проверяем, первый ли это запрос за сутки
        if not self.is_first_request_today(chat_id, student_id, timestamp):
            logger.debug(f"Не первый запрос от студента {student_name} (ID: {student_id}) в чате {chat_id} за сутки")
            return None
        
        # Регистрируем новый запрос
        if chat_id not in self.active_requests:
            self.active_requests[chat_id] = {}
        
        request_data = {
            'request_time': timestamp,
            'request_text': message_text,
            'student_id': student_id,
            'student_name': student_name,
            'chat_id': chat_id,
            'is_working_hours': self.is_working_hours(timestamp)
        }
        
        self.active_requests[chat_id][student_id] = request_data
        
        # Сохраняем в персистенцию
        try:
            if get_persistence:
                persistence = get_persistence()
                if persistence and persistence.is_initialized():
                    persistence.save_sla_request(chat_id, student_id, request_data)
        except Exception as e:
            logger.error(f"Ошибка сохранения SLA-запроса в персистенцию: {e}")
        
        logger.info(
            f"Зарегистрирован запрос от студента {student_name} в чате {chat_id} "
            f"в {'рабочее' if request_data['is_working_hours'] else 'нерабочее'} время"
        )
        
        return request_data
    
    def register_manager_response(
        self,
        chat_id: int,
        student_id: int,
        manager_id: int,
        manager_name: str,
        response_time: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Регистрирует ответ менеджера на запрос студента.
        
        Args:
            chat_id: ID чата
            student_id: ID студента
            manager_id: ID менеджера
            manager_name: Имя менеджера
            response_time: Время ответа (МСК)
            
        Returns:
            Dict с результатами SLA-трекинга или None если нет активного запроса
        """
        # Проверяем, есть ли активный запрос
        if chat_id not in self.active_requests:
            return None
        
        if student_id not in self.active_requests[chat_id]:
            return None
        
        request_data = self.active_requests[chat_id][student_id]
        request_time = request_data['request_time']
        
        # Рассчитываем время ответа
        response_delta = response_time - request_time
        response_minutes = response_delta.total_seconds() / 60
        
        # Проверяем соблюдение SLA
        sla_met = response_minutes <= SLA_RESPONSE_TIME_LIMIT
        
        result = {
            'chat_id': chat_id,
            'student_id': student_id,
            'student_name': request_data['student_name'],
            'manager_id': manager_id,
            'manager_name': manager_name,
            'request_time': request_time,
            'response_time': response_time,
            'response_minutes': round(response_minutes, 2),
            'sla_met': sla_met,
            'is_working_hours': request_data['is_working_hours'],
            'request_text': request_data['request_text'][:100]  # Первые 100 символов
        }
        
        # Запоминаем, что студент уже обращался сегодня
        if chat_id not in self.responded_today:
            self.responded_today[chat_id] = {}
        self.responded_today[chat_id][student_id] = request_time
        
        # Удаляем запрос из активных
        del self.active_requests[chat_id][student_id]
        if not self.active_requests[chat_id]:
            del self.active_requests[chat_id]
        
        # Удаляем из персистенции
        try:
            if get_persistence:
                persistence = get_persistence()
                if persistence and persistence.is_initialized():
                    persistence.delete_sla_request(chat_id, student_id)
        except Exception as e:
            logger.error(f"Ошибка удаления SLA-запроса из персистенции: {e}")
        
        logger.info(
            f"Ответ менеджера {manager_name} на запрос студента {result['student_name']} "
            f"за {response_minutes:.1f} мин. SLA {'соблюдён' if sla_met else 'НЕ соблюдён'}"
        )
        
        return result
    
    def is_manager(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь менеджером"""
        # Проверяем в VIP очереди
        for manager in VIP_MANAGERS_VIP:
            if manager['telegram_id'] == user_id:
                return True
        
        # Проверяем в Luxury очереди
        for manager in VIP_MANAGERS_LUXURY:
            if manager['telegram_id'] == user_id:
                return True
        
        if VIP_HEAD['telegram_id'] == user_id:
            return True
        
        for on_duty in ON_DUTY_ACCOUNTS:
            if on_duty['telegram_id'] == user_id:
                return True
        
        return False
    
    def get_manager_name(self, user_id: int) -> Optional[str]:
        """Получает имя менеджера по ID"""
        # Проверяем в VIP очереди
        for manager in VIP_MANAGERS_VIP:
            if manager['telegram_id'] == user_id:
                return manager['name']
        
        # Проверяем в Luxury очереди
        for manager in VIP_MANAGERS_LUXURY:
            if manager['telegram_id'] == user_id:
                return manager['name']
        
        if VIP_HEAD['telegram_id'] == user_id:
            return VIP_HEAD['name']
        
        for on_duty in ON_DUTY_ACCOUNTS:
            if on_duty['telegram_id'] == user_id:
                return on_duty['name']
        
        return None
