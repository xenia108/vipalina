"""
Планировщик рассылки запросов месячных планов студентам.
Запускается 1, 2, 3 числа каждого месяца.
"""

import logging
import asyncio
from datetime import datetime, time
from typing import Optional
import pytz

logger = logging.getLogger(__name__)


class MonthlyPlanScheduler:
    """Планировщик рассылки запросов месячных планов"""
    
    def __init__(self, client, monthly_plan_collector, chat_to_student: dict, students_data: dict):
        """
        Инициализация планировщика.
        
        Args:
            client: Telethon client
            monthly_plan_collector: Экземпляр MonthlyPlanCollector
            chat_to_student: Словарь chat_id -> getcourse_id
            students_data: Словарь getcourse_id -> student_data
        """
        self.client = client
        self.collector = monthly_plan_collector
        self.chat_to_student = chat_to_student
        self.students_data = students_data
        self.task = None
        self.moscow_tz = pytz.timezone('Europe/Moscow')
        self.sent_today = {}  # {day: True} - флаг отправки за день
        
        logger.info("✅ MonthlyPlanScheduler инициализирован")
    
    def start(self):
        """Запускает планировщик"""
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._schedule_loop())
            logger.info("🔄 Планировщик месячных планов запущен")
    
    def stop(self):
        """Останавливает планировщик"""
        if self.task and not self.task.done():
            self.task.cancel()
            logger.info("⏸ Планировщик месячных планов остановлен")
    
    async def _schedule_loop(self):
        """Основной цикл планировщика"""
        while True:
            try:
                # Проверяем каждый час, нужно ли запускать рассылку
                now = datetime.now(self.moscow_tz)
                
                # Сбрасываем флаг в начале нового месяца
                if now.day == 1 and now.hour < 10:
                    self.sent_today = {}
                
                # Проверяем, что сегодня 1, 2 или 3 число
                if now.day in [1, 2, 3]:
                    # Проверяем время (после 16:00 МСК) и что ещё не отправляли сегодня
                    if now.hour >= 16 and not self.sent_today.get(now.day):
                        logger.info(f"📅 Запуск рассылки месячных планов (день {now.day})")
                        await self.send_monthly_plan_requests(now.day)
                        self.sent_today[now.day] = True
                        logger.info(f"✅ Рассылка за день {now.day} завершена, флаг установлен")
                
                # Проверяем каждый час
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                logger.info("📭 Планировщик месячных планов остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в планировщике месячных планов: {e}", exc_info=True)
                await asyncio.sleep(3600)
    
    async def send_monthly_plan_requests(self, day: int):
        """
        Отправляет запросы планов студентам за конкретный день.
        
        Args:
            day: День месяца (1, 2 или 3)
        """
        try:
            logger.info(f"📊 Начало рассылки планов для дня {day}")
            
            # Получаем студентов со статусами "Учится" и "Новый"
            students = await self.collector.get_students_for_monthly_plan()
            
            if not students:
                logger.warning("⚠️ Нет студентов для рассылки планов")
                return
            
            # Разбиваем на 3 группы
            groups = self.collector.split_students_into_groups(students, days=3)
            
            # Получаем группу для текущего дня
            students_for_day = groups.get(day, [])
            
            logger.info(f"📤 Отправка планов {len(students_for_day)} студентам (день {day}/{len(groups)})")
            
            sent_count = 0
            error_count = 0
            
            for student in students_for_day:
                try:
                    success = await self._send_plan_request_to_student(student)
                    if success:
                        sent_count += 1
                    else:
                        error_count += 1
                    
                    # Задержка между отправками (чтобы не флудить)
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки плана студенту {student['name']}: {e}")
                    error_count += 1
            
            logger.info(
                f"✅ Рассылка завершена (день {day}): "
                f"отправлено {sent_count}, ошибок {error_count}"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка при рассылке месячных планов: {e}", exc_info=True)
    
    async def _send_plan_request_to_student(self, student: dict) -> bool:
        """
        Отправляет запрос плана конкретному студенту.
        
        Args:
            student: Данные студента из KPI Ultra
            
        Returns:
            True если успешно отправлено
        """
        try:
            getcourse_id = student['getcourse_id']
            student_name = student['name']
            tracker_url = student.get('tracker_url', '')
            
            # Находим chat_id для этого студента
            chat_id = None
            for cid, gid in self.chat_to_student.items():
                if gid == getcourse_id:
                    chat_id = cid
                    break
            
            if not chat_id:
                logger.warning(f"⚠️ Не найден chat_id для студента {student_name} ({getcourse_id})")
                return False
            
            # Получаем данные студента для username
            student_data = self.students_data.get(getcourse_id, {})
            student_username = student_data.get('telegram_username', '')
            student_telegram_id = student_data.get('telegram_id')
            
            if not student_telegram_id:
                logger.warning(f"⚠️ Нет telegram_id для студента {student_name}")
                return False
            
            # Проверяем, не был ли запрос уже отправлен (защита от дублей при перезапуске)
            existing_plan = self.collector.get_pending_plan(student_telegram_id)
            if existing_plan:
                logger.info(f"⏭ Пропуск {student_name} — запрос плана уже отправлен ранее (pending)")
                return True
            
            # Формируем текст сообщения
            message_text = self.collector.get_message_text(student_username, student_name)
            
            # Отправляем сообщение
            sent_message = await self.client.send_message(chat_id, message_text, parse_mode='Markdown')
            
            # Получаем дату начала обучения из трекера (если есть)
            start_date = ''
            if tracker_url:
                try:
                    import re
                    from shared_gspread_client import get_shared_gspread_client
                    
                    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', tracker_url)
                    if match:
                        tracker_id = match.group(1)
                        gc = get_shared_gspread_client()
                        tracker_sheet = gc.open_by_key(tracker_id)
                        ws = tracker_sheet.sheet1
                        start_date = ws.acell('C4').value or ''
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить дату начала из трекера: {e}")
            
            # Регистрируем ожидание ответа
            self.collector.register_pending_plan(
                user_id=student_telegram_id,
                getcourse_id=getcourse_id,
                message_id=sent_message.id,
                tracker_url=tracker_url,
                start_date=start_date,
                student_name=student_name,
            )
            
            logger.info(f"✅ Запрос плана отправлен студенту {student_name} (chat_id={chat_id})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки запроса плана: {e}", exc_info=True)
            return False
    
    async def manual_send_all_plans(self):
        """
        Ручной запуск рассылки всем студентам (для тестирования).
        Отправляет сразу всем, не разделяя на дни.
        """
        try:
            logger.info("🔧 Ручной запуск рассылки месячных планов")
            
            # Получаем всех студентов
            students = await self.collector.get_students_for_monthly_plan()
            
            if not students:
                logger.warning("⚠️ Нет студентов для рассылки")
                return 0
            
            sent_count = 0
            
            for student in students:
                try:
                    success = await self._send_plan_request_to_student(student)
                    if success:
                        sent_count += 1
                    
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка: {e}")
            
            logger.info(f"✅ Ручная рассылка завершена: отправлено {sent_count}")
            return sent_count
            
        except Exception as e:
            logger.error(f"❌ Ошибка ручной рассылки: {e}", exc_info=True)
            return 0
