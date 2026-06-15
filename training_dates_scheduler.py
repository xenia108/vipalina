"""
Планировщик периодической проверки и обновления дат обучения в листе "Випалина".
Проверяет и обновляет даты из трекеров студентов с разной периодичностью:
- Через 1 час после создания трекера
- Через 1 день после создания трекера  
- Через 1 месяц после создания трекера
"""

import logging
from datetime import datetime, timedelta
import asyncio
import pytz
from typing import List, Dict, Any
from telethon import TelegramClient

from config import MOSCOW_TZ

logger = logging.getLogger('vipalina_training_dates')


class TrainingDatesScheduler:
    """
    Планировщик обновления дат обучения из трекеров студентов.
    """
    
    def __init__(self, sheets_integration):
        """
        Args:
            sheets_integration: Интеграция с Google Sheets (для получения списка студентов и обновления дат)
        """
        self.sheets = sheets_integration
        self.moscow_tz = pytz.timezone(MOSCOW_TZ)
        self.is_running = False
        self.last_check_times = {}  # Хранит время последней проверки для каждого студента
        logger.info("Инициализирован Training Dates Scheduler")
    
    async def start(self):
        """Запускает планировщик"""
        self.is_running = True
        logger.info("Training Dates Scheduler запущен")
        
        # Запускаем фоновую задачу
        asyncio.create_task(self._schedule_loop())
    
    async def stop(self):
        """Останавливает планировщик"""
        self.is_running = False
        logger.info("Training Dates Scheduler остановлен")
    
    async def _schedule_loop(self):
        """Основной цикл планировщика
        
        Оптимизация: проверяем 1 раз в день в 10:00 МСК вместо каждых 10 минут
        Это снижает нагрузку на Google Sheets API в 144 раза (1 вместо 144 проверок в день)
        """
        last_run_date = None
        
        while self.is_running:
            try:
                now = datetime.now(self.moscow_tz)
                current_date = now.date()
                
                # Проверяем только 1 раз в день в 10:00 МСК
                if now.hour == 10 and current_date != last_run_date:
                    logger.info(f"Проверка дат обучения: {now}")
                    await self.check_and_update_training_dates()
                    last_run_date = current_date
                    logger.info(f"✅ Следующая проверка завтра в 10:00 МСК")
                
                # Проверяем каждые 30 минут (вместо 10)
                await asyncio.sleep(1800)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле Training Dates планировщика: {e}", exc_info=True)
                await asyncio.sleep(1800)
    
    async def check_and_update_training_dates(self):
        """
        Проверяет и обновляет даты обучения для всех студентов.
        Выполняет проверку с разной периодичностью:
        - Через 1 час после создания трекера
        - Через 1 день после создания трекера  
        - Через 1 месяц после создания трекера
        """
        try:
            # Получаем список всех студентов с трекерами
            students = await self.sheets.get_all_students_with_trackers()
            
            logger.info(f"Найдено {len(students)} студентов с трекерами для проверки дат обучения")
            
            updated_count = 0
            for student in students:
                try:
                    getcourse_id = student.get('getcourse_id')
                    tracker_url = student.get('tracker_url')
                    created_at = student.get('created_at')
                    
                    if not getcourse_id or not tracker_url or not created_at or tracker_url == '-':
                        continue
                    
                    # Парсим дату создания
                    try:
                        if isinstance(created_at, str):
                            # Поддерживаем различные форматы дат
                            date_str = created_at.split()[0]  # Берем только дату, игнорируем время
                            if '-' in date_str:
                                created_date = datetime.strptime(date_str, '%Y-%m-%d')
                            elif '.' in date_str:
                                created_date = datetime.strptime(date_str, '%d.%m.%Y')
                            else:
                                logger.warning(f"Неизвестный формат даты для студента {getcourse_id}: {date_str}")
                                continue
                        else:
                            created_date = created_at
                        
                        # Конвертируем в московское время если нужно
                        if created_date.tzinfo is None:
                            created_date = self.moscow_tz.localize(created_date)
                    except Exception as e:
                        logger.warning(f"Не удалось распарсить дату создания для студента {getcourse_id}: {e}")
                        continue
                    
                    # Проверяем, нужно ли обновлять даты
                    now = datetime.now(self.moscow_tz)
                    should_update = await self._should_update_dates(getcourse_id, created_date, now)
                    
                    if should_update:
                        logger.info(f"Обновляем даты обучения для студента {getcourse_id}")
                        success = await self.sheets.update_training_dates(getcourse_id, tracker_url)
                        if success:
                            updated_count += 1
                            logger.info(f"✅ Даты обучения обновлены для студента {getcourse_id}")
                        else:
                            logger.warning(f"⚠️ Не удалось обновить даты обучения для студента {getcourse_id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при проверке дат обучения для студента {student.get('getcourse_id', 'unknown')}: {e}", exc_info=True)
            
            if updated_count > 0:
                logger.info(f"Обновлены даты обучения для {updated_count} студентов")
                
        except Exception as e:
            logger.error(f"Критическая ошибка при проверке дат обучения: {e}", exc_info=True)
    
    async def _should_update_dates(self, getcourse_id: str, created_date: datetime, now: datetime) -> bool:
        """
        Определяет, нужно ли обновлять даты обучения для студента.
        
        Args:
            getcourse_id: ID студента в GetCourse
            created_date: Дата создания трекера
            now: Текущее время
            
        Returns:
            True если нужно обновить даты
        """
        try:
            # Рассчитываем интервалы
            one_hour_later = created_date + timedelta(hours=1)
            one_day_later = created_date + timedelta(days=1)
            one_month_later = created_date + timedelta(days=30)
            
            # Проверяем, прошло ли нужное время для обновления
            if now >= one_hour_later and self._was_never_checked(getcourse_id, 'hour'):
                self._mark_checked(getcourse_id, 'hour')
                logger.info(f"Обновление через 1 час для студента {getcourse_id}: {created_date} -> {one_hour_later}")
                return True
                
            if now >= one_day_later and self._was_never_checked(getcourse_id, 'day'):
                self._mark_checked(getcourse_id, 'day')
                logger.info(f"Обновление через 1 день для студента {getcourse_id}: {created_date} -> {one_day_later}")
                return True
                
            if now >= one_month_later and self._was_never_checked(getcourse_id, 'month'):
                self._mark_checked(getcourse_id, 'month')
                logger.info(f"Обновление через 1 месяц для студента {getcourse_id}: {created_date} -> {one_month_later}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Ошибка при определении необходимости обновления дат для студента {getcourse_id}: {e}")
            return False
    
    def _was_never_checked(self, getcourse_id: str, check_type: str) -> bool:
        """
        Проверяет, выполнялась ли проверка определенного типа для студента.
        
        Args:
            getcourse_id: ID студента в GetCourse
            check_type: Тип проверки ('hour', 'day', 'month')
            
        Returns:
            True если проверка еще не выполнялась
        """
        key = f"{getcourse_id}_{check_type}"
        return key not in self.last_check_times
    
    def _mark_checked(self, getcourse_id: str, check_type: str):
        """
        Отмечает, что проверка определенного типа была выполнена.
        
        Args:
            getcourse_id: ID студента в GetCourse
            check_type: Тип проверки ('hour', 'day', 'month')
        """
        key = f"{getcourse_id}_{check_type}"
        self.last_check_times[key] = datetime.now(self.moscow_tz)
        logger.debug(f"Отмечена проверка {check_type} для студента {getcourse_id}")
