"""
Планировщик ежемесячной CSI-рассылки студентам.
Отправляет ссылку на опрос 28 числа каждого месяца в 18:00 МСК.
"""

import logging
from datetime import datetime, timedelta
import asyncio
import pytz
from typing import List, Dict, Any
from telethon import TelegramClient

from config import (
    CSI_SURVEY_URL,
    CSI_SURVEY_DAY,
    CSI_SURVEY_HOUR,
    MOSCOW_TZ
)

logger = logging.getLogger('vipalina_csi')


class CSIScheduler:
    """
    Планировщик CSI-опросов для студентов.
    """
    
    def __init__(self, client: TelegramClient, sheets_integration):
        """
        Args:
            client: Telethon клиент
            sheets_integration: Интеграция с Google Sheets (для получения списка студентов)
        """
        self.client = client
        self.sheets = sheets_integration
        self.moscow_tz = pytz.timezone(MOSCOW_TZ)
        self.is_running = False
        logger.info("Инициализирован CSI Scheduler")
    
    async def start(self):
        """Запускает планировщик"""
        self.is_running = True
        logger.info("CSI Scheduler запущен")
        
        # Запускаем фоновую задачу
        asyncio.create_task(self._schedule_loop())
    
    async def stop(self):
        """Останавливает планировщик"""
        self.is_running = False
        logger.info("CSI Scheduler остановлен")
    
    async def _schedule_loop(self):
        """Основной цикл планировщика"""
        while self.is_running:
            try:
                # Проверяем, нужно ли отправлять рассылку
                now = datetime.now(self.moscow_tz)
                
                if self._is_survey_time(now):
                    logger.info(f"Время отправки CSI-опроса: {now}")
                    await self.send_csi_survey()
                    
                    # После отправки ждём до следующего дня, чтобы не отправить повторно
                    await asyncio.sleep(3600 * 2)  # 2 часа
                
                # Проверяем каждые 10 минут
                await asyncio.sleep(600)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле CSI планировщика: {e}", exc_info=True)
                await asyncio.sleep(600)
    
    def _is_survey_time(self, now: datetime) -> bool:
        """
        Проверяет, пора ли отправлять опрос.
        
        Args:
            now: Текущее время (МСК)
            
        Returns:
            True если сейчас 28 число в 18:00 (±10 минут)
        """
        if now.day != CSI_SURVEY_DAY:
            return False
        
        if now.hour != CSI_SURVEY_HOUR:
            return False
        
        # Проверяем, что минуты в диапазоне 0-10 (чтобы не пропустить)
        if now.minute > 10:
            return False
        
        return True
    
    async def send_csi_survey(self) -> Dict[str, int]:
        """
        Отправляет CSI-опрос всем студентам.
        
        Returns:
            Dict с количеством отправленных/неудачных сообщений
        """
        logger.info("Начинается рассылка CSI-опроса")
        
        stats = {
            'sent': 0,
            'failed': 0,
            'not_in_chat': 0
        }
        
        try:
            # Получаем список всех активных студентов
            students = self.sheets.get_all_active_students()
            
            logger.info(f"Найдено {len(students)} студентов для рассылки")
            
            for student in students:
                try:
                    chat_id = student.get('chat_id')
                    student_name = student.get('name', 'студент')
                    
                    if not chat_id:
                        logger.warning(f"У студента {student_name} нет chat_id")
                        stats['failed'] += 1
                        continue
                    
                    # Проверяем, есть ли бот в чате
                    try:
                        chat = await self.client.get_entity(chat_id)
                    except Exception as e:
                        logger.warning(f"Не удалось получить чат {chat_id} для студента {student_name}: {e}")
                        stats['not_in_chat'] += 1
                        continue
                    
                    # Формируем сообщение
                    message = self._format_survey_message(student_name)
                    
                    # Отправляем сообщение
                    await self.client.send_message(chat_id, message)
                    stats['sent'] += 1
                    
                    logger.info(f"CSI-опрос отправлен студенту {student_name} (chat_id: {chat_id})")
                    
                    # Небольшая задержка, чтобы не попасть под ограничения
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Ошибка при отправке опроса студенту {student.get('name', 'unknown')}: {e}")
                    stats['failed'] += 1
            
            logger.info(
                f"Рассылка CSI завершена. Отправлено: {stats['sent']}, "
                f"Не отправлено (нет в чате): {stats['not_in_chat']}, "
                f"Ошибки: {stats['failed']}"
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Критическая ошибка при рассылке CSI: {e}", exc_info=True)
            return stats
    
    def _format_survey_message(self, student_name: str = "студент") -> str:
        """
        Форматирует сообщение с опросом.
        
        Args:
            student_name: Имя студента
            
        Returns:
            Отформатированное сообщение
        """
        first_name = student_name.split()[0] if student_name else "студент"
        
        message = f"""Здравствуйте!

Оцените, пожалуйста, работу вашего персонального менеджера за прошедший месяц:

{CSI_SURVEY_URL}

Ваше мнение очень важно для нас! 💜

Спасибо за обратную связь!
"""
        
        return message
    
    async def send_manual_survey(self, chat_ids: List[int] = None) -> Dict[str, int]:
        """
        Отправляет опрос вручную (для тестирования или внеплановой рассылки).
        
        Args:
            chat_ids: Список chat_id для отправки (если None - всем студентам)
            
        Returns:
            Dict с количеством отправленных/неудачных сообщений
        """
        logger.info("Начинается ручная рассылка CSI-опроса")
        
        if chat_ids:
            # Отправляем только указанным чатам
            stats = {'sent': 0, 'failed': 0, 'not_in_chat': 0}
            
            for chat_id in chat_ids:
                try:
                    message = self._format_survey_message()
                    await self.client.send_message(chat_id, message)
                    stats['sent'] += 1
                    logger.info(f"CSI-опрос отправлен в чат {chat_id}")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Ошибка при отправке в чат {chat_id}: {e}")
                    stats['failed'] += 1
            
            return stats
        else:
            # Отправляем всем студентам
            return await self.send_csi_survey()
