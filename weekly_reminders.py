"""
Модуль ежедневных напоминаний для VIP-менеджеров о касаниях студентов.

Проверяет студентов, для которых наступила дата "Следующее общение" из NocoDB,
и отправляет персональные уведомления менеджерам с детальной информацией:
- ДЗ за последнюю неделю (из таблицы "Доходимость по ДЗ Випалина")
- ДЗ за месяц (с 1 числа текущего месяца, норма 7 уроков)
- Ссылка на чат

Расписание: каждый будний день (Пн-Пт) в 11:30 МСК.
"""

import asyncio
import logging
import gspread
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from telethon import TelegramClient, Button, events
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)


class WeeklyRemindersManager:
    """Менеджер ежедневных напоминаний для VIP-менеджеров (Пн-Пт в 11:30 МСК)"""
    
    def __init__(self, client: TelegramClient, bot_client: TelegramClient = None, nocodb_integration=None):
        """
        Args:
            client: Telethon User Client для фоновых задач
            bot_client: Telethon Bot Client для отправки сообщений с кнопками (inline buttons)
            nocodb_integration: Интеграция с NocoDB для обновления дат
        """
        self.client = client
        self.bot_client = bot_client or client  # Fallback to user client if bot_client not provided
        self.nocodb = nocodb_integration
        self.reminder_task = None
        # Gspread client инициализируется через shared модуль
        
    def _init_gspread(self):
        """Инициализирует gspread клиент для доступа к таблицам"""
        from shared_gspread_client import get_shared_gspread_client
        return get_shared_gspread_client()
        
    async def start_weekly_reminders(self):
        """Запускает фоновую задачу ежедневных напоминаний (Пн-Пт в 11:00)"""
        if self.reminder_task and not self.reminder_task.done():
            logger.warning("Ежедневные напоминания уже запущены")
            return
        
        self.reminder_task = asyncio.create_task(self._weekly_reminder_loop())
        logger.info("✅ Запущены ежедневные напоминания VIP-менеджерам (Пн-Пт в 11:30 МСК)")
    
    async def stop_weekly_reminders(self):
        """Останавливает фоновую задачу"""
        if self.reminder_task:
            self.reminder_task.cancel()
            try:
                await self.reminder_task
            except asyncio.CancelledError:
                pass
            logger.info("🛑 Ежедневные напоминания остановлены")
    
    async def _weekly_reminder_loop(self):
        """Основной цикл ежедневных проверок (Пн-Пт)"""
        while True:
            try:
                # Ждём до следующего рабочего дня 11:30 МСК
                await self._wait_until_next_weekday()
                
                # Отправляем напоминания
                await self.send_weekly_reminders()
                
            except asyncio.CancelledError:
                logger.info("Цикл ежедневных напоминаний отменён")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле ежедневных напоминаний: {e}", exc_info=True)
                
                # Уведомляем руководителя о сбое
                try:
                    from config import VIP_HEAD
                    await self.client.send_message(
                        VIP_HEAD['telegram_id'],
                        f"❌ **Сбой напоминаний**\n\n"
                        f"Цикл ежедневных напоминаний остановлен.\n\n"
                        f"Ошибка: {str(e)[:200]}\n\n"
                        f"🔧 Проверьте логи и перезапустите бота."
                    )
                except:
                    pass
                
                # Ждём час перед повторной попыткой
                await asyncio.sleep(3600)
    
    async def _wait_until_next_weekday(self):
        """Ждёт до следующего рабочего дня (Пн-Пт) 11:30 МСК"""
        import pytz
        
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(moscow_tz)
        
        # Вычисляем следующий рабочий день (Пн-Пт) в 11:30
        next_check = now.replace(hour=11, minute=30, second=0, microsecond=0)
        
        # Если уже прошло 11:00 сегодня, переходим к следующему дню
        if now >= next_check:
            next_check += timedelta(days=1)
        
        # Пропускаем выходные (Сб=5, Вс=6)
        while next_check.weekday() >= 5:
            next_check += timedelta(days=1)
        
        wait_seconds = (next_check - now).total_seconds()
        weekday_name = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][next_check.weekday()]
        logger.info(f"⏰ Следующая проверка в {weekday_name} {next_check.strftime('%d.%m.%Y %H:%M')} (через {wait_seconds/3600:.1f} часов)")
        
        await asyncio.sleep(wait_seconds)
    
    async def send_weekly_reminders(self, filter_manager: str = None):
        """
        Отправляет ежедневные напоминания всем менеджерам (Пн-Пт) на основе NocoDB.
        
        Args:
            filter_manager: Если указано, отправляет только этому менеджеру
        """
        try:
            logger.info("📅 Начинаю ежедневную проверку касаний студентов по NocoDB...")
            
            if not self.nocodb:
                logger.error("❌ NocoDB не инициализирован")
                return
            
            from config import NOCODB_FIELD_NEXT_CONTACT
            from report_generator import get_report_generator
            
            # Группируем по менеджерам
            managers_students = {}
            today = datetime.now().date()
            
            # Предзагружаем таблицу ДЗ один раз
            homework_cache = await self._preload_homework_data()
            logger.info(f"📚 Предзагружено {len(homework_cache)} записей ДЗ")
            
            # Предзагружаем chat links из KPI Ultra один раз
            chat_links_cache = await self._preload_kpi_chat_links()
            logger.info(f"💬 Предзагружено {len(chat_links_cache)} chat links")
            
            # Получаем ВСЕ записи из NocoDB (с пагинацией)
            try:
                import httpx
                async with httpx.AsyncClient(timeout=30.0) as client:
                    url = f"{self.nocodb.api_url}/api/v2/tables/{self.nocodb.table_id}/records"
                    
                    all_records = []
                    offset = 0
                    limit = 1000
                    
                    while True:
                        params = {'limit': limit, 'offset': offset}
                        
                        response = await client.get(url, headers=self.nocodb.headers, params=params)
                        response.raise_for_status()
                        data = response.json()
                        
                        batch = data.get('list', [])
                        all_records.extend(batch)
                        
                        if len(batch) < limit:
                            break
                        
                        offset += limit
                    
                    logger.info(f"📊 Получено {len(all_records)} записей из NocoDB")
                    
                    # Обрабатываем каждую запись
                    for record in all_records:
                        # Проверяем статус
                        student_status = record.get('Статус студента', '')
                        if student_status != 'обучение':
                            continue
                        
                        # Проверяем менеджера
                        manager_name = record.get('Менеджер', '')
                        if not manager_name or manager_name in ('ДЕЖУРНЫЙ', 'Не с нами', ''):
                            continue
                        
                        # Проверяем дату следующего общения
                        next_contact_str = record.get(NOCODB_FIELD_NEXT_CONTACT, '')
                        if not next_contact_str:
                            continue
                        
                        try:
                            # Парсим дату (YYYY-MM-DD или dd/mm/yyyy)
                            try:
                                next_contact_date = datetime.strptime(next_contact_str[:10], '%Y-%m-%d').date()
                            except:
                                next_contact_date = datetime.strptime(next_contact_str, '%d/%m/%Y').date()
                            
                            # Проверяем, наступила ли дата
                            if next_contact_date > today:
                                continue
                            
                            # Собираем данные студента
                            getcourse_id = record.get('ID пользователя', '')
                            student_name = record.get('Студент', 'Без имени')
                            course_name = record.get('Курс', '')
                            
                            if not getcourse_id:
                                continue
                            
                            # Добавляем в группу менеджера
                            if manager_name not in managers_students:
                                managers_students[manager_name] = []
                            
                            # Получаем ДЗ из кэша
                            hw_week, hw_month = self._get_homework_from_cache(getcourse_id, homework_cache)
                            
                            # Получаем chat_link из кэша KPI Ultra
                            chat_link = chat_links_cache.get(getcourse_id, '')
                            
                            managers_students[manager_name].append({
                                'student': {
                                    'name': student_name,
                                    'getcourse_id': getcourse_id
                                },
                                'course': course_name,
                                'hw_week': hw_week,
                                'hw_month': hw_month,
                                'chat_link': chat_link,
                                'next_contact_date': next_contact_str,
                                'tracker_url': ''
                            })
                        
                        except Exception as e:
                            logger.warning(f"Ошибка обработки записи {record.get('ID пользователя', '?')}: {e}")
                            continue
                    
            except Exception as e:
                logger.error(f"❌ Ошибка получения данных из NocoDB: {e}", exc_info=True)
                return
            
            # Отправляем уведомления менеджерам
            total_sent = 0
            for manager_name, students_list in managers_students.items():
                # Фильтр по менеджеру (если указан)
                if filter_manager and manager_name != filter_manager:
                    continue
                
                if not students_list:
                    continue
                
                # Получаем Telegram ID менеджера
                manager_id = self._get_manager_telegram_id(manager_name)
                if not manager_id:
                    logger.warning(f"Не найден Telegram ID для менеджера {manager_name}")
                    continue
                
                # Получаем InputPeer менеджера
                try:
                    manager_entity = await self.client.get_input_entity(manager_id)
                except Exception as entity_error:
                    logger.error(f"❌ Не удалось получить InputPeer менеджера {manager_id}: {entity_error}")
                    continue
                
                # Заголовок
                if len(students_list) > 0:
                    header_msg = f"📢 Сегодня нужно сделать касания по следующим студентам:"
                    try:
                        await self.bot_client.send_message(manager_entity, header_msg)
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Ошибка отправки заголовка {manager_name}: {e}")
                
                # Отправляем сообщения по каждому студенту
                for item in students_list:
                    message = await self._format_reminder_message(item)
                    buttons = self._create_touch_buttons(item['student']['getcourse_id'])
                    try:
                        await self.bot_client.send_message(manager_entity, message, buttons=buttons, parse_mode='md')
                        total_sent += 1
                        student_name = item['student'].get('name', 'Без имени')
                        logger.info(f"✅ Отправлено напоминание для {manager_name} по студенту {student_name}")
                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Ошибка отправки напоминания {manager_name} по студенту: {e}")
            
            logger.info(f"📊 Ежедневные напоминания отправлены: {total_sent} студентам")
            
        except Exception as e:
            logger.error(f"Ошибка при отправке ежедневных напоминаний: {e}", exc_info=True)
    
    async def _preload_homework_data(self) -> Dict[str, list]:
        """
        Предзагружает все данные ДЗ из Google Sheets одним запросом.
        
        Returns:
            Dict[getcourse_id, list of rows] - словарь строк ДЗ по ID студента
        """
        try:
            from config import HOMEWORK_TRACKING_SPREADSHEET_ID, HOMEWORK_TRACKING_TAB
            
            gc = self._init_gspread()
            spreadsheet = gc.open_by_key(HOMEWORK_TRACKING_SPREADSHEET_ID)
            worksheet = spreadsheet.worksheet(HOMEWORK_TRACKING_TAB)
            all_data = worksheet.get_all_values()
            
            if len(all_data) <= 1:
                return {}
            
            # Группируем по getcourse_id
            cache = {}
            for row in all_data[1:]:  # пропускаем заголовок
                if len(row) < 8:
                    continue
                
                row_id = row[0].strip() if row[0] else ''
                if not row_id:
                    continue
                
                if row_id not in cache:
                    cache[row_id] = []
                cache[row_id].append(row)
            
            return cache
            
        except Exception as e:
            logger.error(f"❌ Ошибка предзагрузки данных ДЗ: {e}", exc_info=True)
            return {}
    
    def _get_homework_from_cache(self, getcourse_id: str, homework_cache: Dict[str, list]) -> tuple:
        """
        Получает статистику ДЗ из предзагруженного кэша.
        
        Returns:
            (hw_week, hw_month): список ДЗ за неделю, кол-во ДЗ за месяц
        """
        try:
            rows = homework_cache.get(getcourse_id, [])
            if not rows:
                return [], 0
            
            today = datetime.now().date()
            week_ago = today - timedelta(days=7)
            month_start = today.replace(day=1)
            
            hw_week = []  # [{lesson, date}, ...]
            hw_month_count = 0
            
            # Столбцы: A - ID с ГК, F - название урока, H - дата сдачи
            for row in rows:
                lesson_name = row[5].strip() if len(row) > 5 else ''  # столбец F (index 5)
                submission_date_str = row[7].strip() if len(row) > 7 else ''  # столбец H (index 7)
                
                if not submission_date_str:
                    continue
                
                try:
                    # Парсим дату (может быть dd.mm.yyyy или yyyy-mm-dd)
                    if '.' in submission_date_str:
                        submission_date = datetime.strptime(submission_date_str[:10], '%d.%m.%Y').date()
                    else:
                        submission_date = datetime.strptime(submission_date_str[:10], '%Y-%m-%d').date()
                    
                    # ДЗ за неделю
                    if submission_date >= week_ago:
                        hw_week.append({
                            'lesson': lesson_name,
                            'date': submission_date.strftime('%d.%m.%Y')
                        })
                    
                    # ДЗ за месяц
                    if submission_date >= month_start:
                        hw_month_count += 1
                except Exception as e:
                    logger.warning(f"Ошибка парсинга даты ДЗ: {submission_date_str} - {e}")
                    continue
            
            return hw_week, hw_month_count
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики ДЗ для {getcourse_id}: {e}", exc_info=True)
            return [], 0
    
    async def _get_homework_stats(self, getcourse_id: str) -> tuple:
        """
        Получает статистику ДЗ из таблицы "Доходимость по ДЗ Випалина".
        
        Returns:
            (hw_week, hw_month): список ДЗ за неделю, кол-во ДЗ за месяц
        """
        try:
            from config import HOMEWORK_TRACKING_SPREADSHEET_ID, HOMEWORK_TRACKING_TAB
            
            gc = self._init_gspread()
            spreadsheet = gc.open_by_key(HOMEWORK_TRACKING_SPREADSHEET_ID)
            worksheet = spreadsheet.worksheet(HOMEWORK_TRACKING_TAB)
            all_data = worksheet.get_all_values()
            
            if len(all_data) <= 1:
                return [], 0
            
            today = datetime.now().date()
            week_ago = today - timedelta(days=7)
            month_start = today.replace(day=1)
            
            hw_week = []  # [{lesson, date}, ...]
            hw_month_count = 0
            
            # Столбцы: A - ID с ГК, F - название урока, H - дата сдачи
            for row in all_data[1:]:  # пропускаем заголовок
                if len(row) < 8:
                    continue
                
                row_id = row[0].strip() if row[0] else ''
                lesson_name = row[5].strip() if len(row) > 5 else ''  # столбец F (index 5)
                submission_date_str = row[7].strip() if len(row) > 7 else ''  # столбец H (index 7)
                
                if row_id != getcourse_id or not submission_date_str:
                    continue
                
                try:
                    # Парсим дату (может быть dd.mm.yyyy или yyyy-mm-dd)
                    if '.' in submission_date_str:
                        submission_date = datetime.strptime(submission_date_str[:10], '%d.%m.%Y').date()
                    else:
                        submission_date = datetime.strptime(submission_date_str[:10], '%Y-%m-%d').date()
                    
                    # ДЗ за неделю
                    if submission_date >= week_ago:
                        hw_week.append({
                            'lesson': lesson_name,
                            'date': submission_date.strftime('%d.%m.%Y')
                        })
                    
                    # ДЗ за месяц
                    if submission_date >= month_start:
                        hw_month_count += 1
                except Exception as e:
                    logger.warning(f"Ошибка парсинга даты ДЗ: {submission_date_str} - {e}")
                    continue
            
            return hw_week, hw_month_count
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики ДЗ для {getcourse_id}: {e}", exc_info=True)
            return [], 0
    
    async def _get_chat_link_from_kpi(self, getcourse_id: str) -> str:
        """
        Точечный поиск chat link в KPI Ultra по getcourse_id.
        Используется только если в NocoDB нет ссылки.
        """
        try:
            from config import GOOGLE_SHEETS_ID, GOOGLE_SHEETS_KPI_TAB
            
            gc = self._init_gspread()
            spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
            worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_KPI_TAB)
            
            # Ищем строку с getcourse_id (столбец A)
            cell = worksheet.find(getcourse_id, in_column=1)
            if not cell:
                return ''
            
            # Читаем столбец G (ссылка на чат) в этой строке
            chat_link = worksheet.cell(cell.row, 7).value  # столбец G = index 7
            
            if chat_link and chat_link != '-':
                return chat_link.strip()
            return ''
            
        except Exception as e:
            logger.warning(f"Ошибка точечного поиска chat_link для {getcourse_id}: {e}")
            return ''
    
    async def _preload_kpi_chat_links(self) -> Dict[str, str]:
        """
        Предзагружает chat links из KPI Ultra одним запросом.
        
        Returns:
            Dict[getcourse_id, chat_link] - словарь ссылок на чаты
        """
        try:
            from config import GOOGLE_SHEETS_ID, GOOGLE_SHEETS_KPI_TAB
            
            gc = self._init_gspread()
            spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
            worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_KPI_TAB)
            all_data = worksheet.get_all_values()
            
            if len(all_data) <= 1:
                return {}
            
            # Столбец A - getcourse_id, столбец G (index 6) - chat_link
            cache = {}
            for row in all_data[1:]:
                if len(row) > 6:
                    getcourse_id = row[0].strip() if row[0] else ''
                    chat_link = row[6].strip() if row[6] else ''
                    
                    if getcourse_id and chat_link and chat_link != '-':
                        cache[getcourse_id] = chat_link
            
            return cache
            
        except Exception as e:
            logger.error(f"❌ Ошибка предзагрузки chat links: {e}", exc_info=True)
            return {}
    
    def _get_chat_link_from_cache(self, getcourse_id: str, vipalina_info: Dict, kpi_chat_links: Dict[str, str]) -> str:
        """
        Получает ссылку на чат из Віпалины, если нет - из предзагруженного кэша KPI Ultra.
        """
        chat_link = vipalina_info.get('chat_link', '')
        if chat_link and chat_link != '-':
            return chat_link
        
        # Fallback: ищем в KPI Ultra кэше
        return kpi_chat_links.get(getcourse_id, '')
    
    async def _get_chat_link(self, getcourse_id: str, vipalina_info: Dict) -> str:
        """
        Получает ссылку на чат из Випалины, если нет - из KPI Ultra.
        """
        chat_link = vipalina_info.get('chat_link', '')
        if chat_link and chat_link != '-':
            return chat_link
        
        # Fallback: ищем в KPI Ultra, лист "Общий список new", столбец G
        try:
            from config import GOOGLE_SHEETS_ID, GOOGLE_SHEETS_KPI_TAB
            gc = self._init_gspread()
            spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
            worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_KPI_TAB)
            all_data = worksheet.get_all_values()
            
            # Столбец A - getcourse_id, столбец G (index 6) - chat_link
            for row in all_data[1:]:
                if len(row) > 6 and row[0].strip() == getcourse_id:
                    link = row[6].strip()
                    if link and link != '-':
                        return link
                    break
        except Exception as e:
            logger.warning(f"Ошибка получения chat_link из KPI Ultra для {getcourse_id}: {e}")
        
        return ''
    
    def _create_touch_buttons(self, getcourse_id: str) -> List:
        """Создаёт inline-кнопки для касания"""
        return [
            [
                Button.inline("✅ Написала", data=f"touch_done:{getcourse_id}"),
                Button.inline("⏰ +7 дней", data=f"touch_delay_7:{getcourse_id}"),
                Button.inline("⏰ +14 дней", data=f"touch_delay_14:{getcourse_id}")
            ]
        ]
    
    async def _format_reminder_message(self, item: Dict[str, Any]) -> str:
        """
        Форматирует сообщение с напоминанием по одному студенту.
        """
        student = item['student']
        course = item.get('course', '-')
        hw_week = item.get('hw_week', [])
        hw_month = item.get('hw_month', 0)
        chat_link = item.get('chat_link', '')
        tracker_url = item.get('tracker_url', '')
        next_contact_date = item.get('next_contact_date', '')
        
        name = student.get('name', 'Без имени')
        
        message = f"**{name}**\n"
        message += f"📚 Курс: {course}\n"
        
        # Дата следующего общения
        if next_contact_date:
            try:
                # Попытка 1: формат YYYY-MM-DD
                date_obj = datetime.strptime(next_contact_date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
                message += f"⏱ Последнее общение: {formatted_date}\n"
            except:
                try:
                    # Попытка 2: формат dd/mm/yyyy
                    date_obj = datetime.strptime(next_contact_date, '%d/%m/%Y')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                    message += f"⏱ Последнее общение: {formatted_date}\n"
                except:
                    # Если ни один формат не подошёл, показываем как есть
                    message += f"⏱ Последнее общение: {next_contact_date}\n"
        else:
            message += f"⏱ Последнее общение: -\n"
        
        # ДЗ за неделю
        message += "📖 ДЗ за неделю:\n"
        if hw_week:
            for hw in hw_week:
                message += f"{hw['lesson']} - {hw['date']}\n"
        else:
            message += "Не сдавал\n"
        
        # ДЗ за месяц
        message += f"\n🗓 ДЗ за месяц: {hw_month} (норма 7 уроков)\n"
        
        # Ссылки
        getcourse_id = student.get('getcourse_id', '')
        if getcourse_id:
            getcourse_url = f"https://university.zerocoder.ru/user/control/user/update/id/{getcourse_id}"
            message += f"\n🌐 [GetCourse]({getcourse_url})"
        
        if tracker_url and tracker_url != '-':
            # Валидация URL
            if tracker_url.startswith('http://') or tracker_url.startswith('https://'):
                message += f"\n📋 [Трекер]({tracker_url})"
            else:
                logger.warning(f"Невалидный tracker_url для {getcourse_id}: {tracker_url}")
        
        if chat_link:
            message += f"\n💬 [Открыть чат]({chat_link})"
        
        return message
    
    def _get_manager_telegram_id(self, manager_name: str) -> Optional[int]:
        """Получает Telegram ID менеджера по имени"""
        from config import VIP_MANAGERS_VIP, VIP_MANAGERS_LUXURY, VIP_HEAD
        
        # Ищем в VIP
        for manager in VIP_MANAGERS_VIP:
            if manager['name'] == manager_name:
                return manager['telegram_id']
        
        # Ищем в Luxury
        for manager in VIP_MANAGERS_LUXURY:
            if manager['name'] == manager_name:
                return manager['telegram_id']
        
        # Проверяем руководителя
        if VIP_HEAD['name'] == manager_name:
            return VIP_HEAD['telegram_id']
        
        return None
    
    async def send_manual_reminder_now(self):
        """Отправляет напоминания немедленно (для тестирования)"""
        logger.info("🧪 Ручная отправка ежедневных напоминаний...")
        await self.send_weekly_reminders()
    
    async def send_manual_reminder_for_manager(self, manager_name: str):
        """
        Отправляет напоминания немедленно для одного менеджера.
        
        Args:
            manager_name: Имя менеджера
        """
        logger.info(f"🧪 Ручная отправка напоминаний для {manager_name}...")
        await self.send_weekly_reminders(filter_manager=manager_name)
    
    async def send_test_reminder_for_student(self, getcourse_id: str):
        """
        Отправляет тестовое напоминание для одного студента.
        
        Args:
            getcourse_id: ID студента в GetCourse
        """
        try:
            logger.info(f"🧪 Тестовое напоминание для студента {getcourse_id}...")
            
            # Получаем данные
            from report_generator import get_report_generator
            report_gen = get_report_generator()
            
            kpi_students = await report_gen.get_kpi_data()
            vipalina_data = await report_gen.get_vipalina_data()
            
            # Ищем студента
            student = None
            for s in kpi_students:
                if s['getcourse_id'] == getcourse_id:
                    student = s
                    break
            
            if not student:
                logger.error(f"❌ Студент {getcourse_id} не найден в KPI")
                return False
            
            manager_name = student.get('manager_name', '')
            if not manager_name:
                logger.error(f"❌ У студента {getcourse_id} нет менеджера")
                return False
            
            # Получаем Telegram ID менеджера
            manager_id = self._get_manager_telegram_id(manager_name)
            if not manager_id:
                logger.error(f"❌ Не найден Telegram ID для менеджера {manager_name}")
                return False
            
            vipalina_info = vipalina_data.get(getcourse_id, {})
            
            # Получаем данные о ДЗ
            hw_week, hw_month = await self._get_homework_stats(getcourse_id)
            
            # Получаем ссылку на чат
            chat_link = await self._get_chat_link(getcourse_id, vipalina_info)
            
            # Получаем данные из NocoDB (БЕЗ view_id - по всей таблице)
            next_contact_date_str = ''
            if self.nocodb:
                # Ищем напрямую по getcourse_id без view фильтра
                record = await self.nocodb.find_student_by_getcourse_id(getcourse_id, use_view=False)
                if record and record.get('fields'):
                    from config import NOCODB_FIELD_NEXT_CONTACT
                    next_contact_str = record['fields'].get(NOCODB_FIELD_NEXT_CONTACT, '')
                    if next_contact_str:
                        next_contact_date_str = next_contact_str  # Полный формат dd/mm/yyyy
            
            item = {
                'student': student,
                'vipalina': vipalina_info,
                'hw_week': hw_week,
                'hw_month': hw_month,
                'chat_link': chat_link,
                'next_contact_date': next_contact_date_str,
                'tracker_url': student.get('tracker_url', '')
            }
            
            # Формируем и отправляем сообщение
            message = await self._format_reminder_message(item)
            buttons = self._create_touch_buttons(getcourse_id)
            
            # Получаем InputPeer менеджера
            try:
                manager_entity = await self.client.get_input_entity(manager_id)
            except Exception as entity_error:
                logger.error(f"❌ Не удалось получить InputPeer менеджера {manager_id}: {entity_error}")
                return False
            
            # Bot Client отправляет с inline кнопками
            await self.bot_client.send_message(manager_entity, f"🧪 **ТЕСТОВОЕ НАПОМИНАНИЕ**\n\n{message}", buttons=buttons, parse_mode='md')
            
            logger.info(f"✅ Тестовое напоминание отправлено {manager_name} (ID: {manager_id})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке тестового напоминания: {e}", exc_info=True)
            return False
