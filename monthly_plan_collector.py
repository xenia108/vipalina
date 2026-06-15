"""
Модуль сбора месячных планов студентов.
Рассылает запросы на планы 1-3 числа каждого месяца и собирает ответы.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import re
from shared_gspread_client import get_shared_gspread_client
from config import GOOGLE_SHEETS_ID, VIPALINA_LOGS_SPREADSHEET_ID
from async_sheets_wrapper import AsyncSheetsWrapper

logger = logging.getLogger(__name__)


class MonthlyPlanCollector:
    """Сборщик месячных планов студентов"""
    
    # Маппинг месяцев для колонок планов.
    # Блок каждого месяца = 7 колонок: [Дата посл. ДЗ, Посл. ДЗ, Статус, Кол-во ДЗ, KPI, Комментарий, План]
    # Февраль26: AU:BA → план = BA
    # Март 26:   BB:BH → план = BH
    PLAN_COLUMNS = {
        'февраль26': 'BA',   # колонка 53
        'март26':    'BH',   # колонка 60
        'апрель26':  'BO',   # колонка 67
        'май26':     'BV',   # колонка 74
        'июнь26':    'CC',   # колонка 81
        'июль26':    'CJ',   # колонка 88
        'август26':  'CQ',   # колонка 95
        'сентябрь26':'CX',   # колонка 102
        'октябрь26': 'DE',   # колонка 109
        'ноябрь26':  'DL',   # колонка 116
        'декабрь26': 'DS',   # колонка 123
        'январь27':  'DZ',   # колонка 130
        'февраль27': 'EG',   # колонка 137
        'март27':    'EN',   # колонка 144
        'апрель27':  'EU',   # колонка 151
        'май27':     'FB',   # колонка 158
        'июнь27':    'FI',   # колонка 165
        'июль27':    'FP',   # колонка 172
        'август27':  'FW',   # колонка 179
        'сентябрь27':'GD',   # колонка 186
        'октябрь27': 'GK',   # колонка 193
        'ноябрь27':  'GR',   # колонка 200
        'декабрь27': 'GY',   # колонка 207
    }
    
    # Названия месяцев на русском (нижний регистр)
    MONTH_NAMES = [
        'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
        'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
    ]
    
    PENDING_PLANS_TAB = 'Pending_Plans'
    
    def __init__(self):
        """Инициализация сборщика планов"""
        self.gc = get_shared_gspread_client()
        self.kpi_spreadsheet = None
        self.logs_spreadsheet = None
        self.pending_plans = {}  # {user_id: {'getcourse_id': ..., 'message_id': ...}}
        
        # Восстанавливаем pending_plans из таблицы при старте
        self._load_pending_from_sheet_sync()
        
        logger.info("✅ MonthlyPlanCollector инициализирован")
    
    def _get_logs_spreadsheet(self):
        """Получает Логи Випалина spreadsheet"""
        if not self.logs_spreadsheet:
            self.logs_spreadsheet = self.gc.open_by_key(VIPALINA_LOGS_SPREADSHEET_ID)
        return self.logs_spreadsheet
    
    def _load_pending_from_sheet_sync(self):
        """Загружает pending_plans из таблицы при инициализации (синхронно)"""
        try:
            sp = self._get_logs_spreadsheet()
            ws = sp.worksheet(self.PENDING_PLANS_TAB)
            rows = ws.get_all_values()
            count = 0
            for row in rows[1:]:  # пропускаем заголовок
                if len(row) < 6 or not row[0]:
                    continue
                try:
                    user_id = int(row[0])
                    self.pending_plans[user_id] = {
                        'getcourse_id': row[1],
                        'message_id': int(row[2]) if row[2] else None,
                        'tracker_url': row[3],
                        'start_date': row[4],
                        'timestamp': datetime.fromisoformat(row[5]) if row[5] else datetime.now(),
                        'student_name': row[6] if len(row) > 6 else '',
                    }
                    count += 1
                except Exception:
                    continue
            if count:
                logger.info(f"♻️ Восстановлено {count} pending_plans из Логи Випалина")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить pending_plans из таблицы: {e}")
    
    def _get_kpi_spreadsheet(self):
        """Получает KPI Ultra spreadsheet"""
        if not self.kpi_spreadsheet:
            self.kpi_spreadsheet = self.gc.open_by_key(GOOGLE_SHEETS_ID)
        return self.kpi_spreadsheet
    
    def _get_current_month_key(self) -> str:
        """
        Получает ключ текущего месяца для колонок планов.
        Например: 'февраль26'
        """
        now = datetime.now()
        month_name = self.MONTH_NAMES[now.month - 1]  # Месяцы с 0
        year_suffix = str(now.year)[-2:]  # Последние 2 цифры года
        return f"{month_name}{year_suffix}"
    
    def _get_plan_column_for_month(self, month_key: str) -> Optional[str]:
        """
        Получает букву колонки для плана заданного месяца.
        
        Args:
            month_key: Ключ месяца (например, 'февраль26')
            
        Returns:
            Буква колонки (например, 'BA') или None
        """
        return self.PLAN_COLUMNS.get(month_key)
    
    async def get_students_for_monthly_plan(self) -> List[Dict[str, Any]]:
        """
        Получает список студентов в статусах "Учится" и "Новый" 
        из текущего месяца KPI Ultra.
        
        Returns:
            Список словарей с данными студентов
        """
        try:
            spreadsheet = await AsyncSheetsWrapper.run_sync(self._get_kpi_spreadsheet)
            ws = await AsyncSheetsWrapper.run_sync(spreadsheet.worksheet, 'Общий список new')
            all_data = await AsyncSheetsWrapper.run_sync(ws.get_all_values)
            
            # Определяем текущий месяц
            now = datetime.now()
            current_month_name = self.MONTH_NAMES[now.month - 1]
            current_year = str(now.year)[-2:]
            
            # Ищем колонку статуса текущего месяца (например, "Статус Февраль26")
            header_row = all_data[19]  # Строка 20 (индекс 19)
            status_col_idx = None
            
            for idx, header in enumerate(header_row):
                if f"Статус {current_month_name.capitalize()}{current_year}" in header:
                    status_col_idx = idx
                    logger.info(f"✅ Найдена колонка статуса: {header} (индекс {idx})")
                    break
            
            if status_col_idx is None:
                logger.error(f"❌ Не найдена колонка статуса для {current_month_name}{current_year}")
                return []
            
            students = []
            
            # Данные студентов начинаются со строки 21 (индекс 20)
            for row_idx, row in enumerate(all_data[20:], start=21):
                if len(row) < 8 or not row[0]:
                    continue
                
                # Проверяем статус
                status = row[status_col_idx] if len(row) > status_col_idx else ''
                
                if status in ['Учится', 'Новый']:
                    student = {
                        'row_idx': row_idx,
                        'getcourse_id': row[0],  # A
                        'name': row[2] if len(row) > 2 else '',  # C
                        'course': row[3] if len(row) > 3 else '',  # D
                        'tracker_url': row[5] if len(row) > 5 else '',  # F
                        'chat_link': row[6] if len(row) > 6 else '',  # G
                        'manager_name': row[10] if len(row) > 10 else '',  # K
                        'status': status
                    }
                    students.append(student)
            
            logger.info(f"✅ Найдено {len(students)} студентов со статусами 'Учится' и 'Новый'")
            return students
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения студентов для месячного плана: {e}", exc_info=True)
            return []
    
    def split_students_into_groups(self, students: List[Dict], days: int = 3) -> Dict[int, List[Dict]]:
        """
        Разбивает студентов на равные группы для дней 1-3 числа.
        
        Args:
            students: Список студентов
            days: Количество дней (по умолчанию 3)
            
        Returns:
            Словарь {день: [студенты]}
        """
        total = len(students)
        per_day = total // days
        remainder = total % days
        
        groups = {}
        start_idx = 0
        
        for day in range(1, days + 1):
            # Первые remainder дней получают на 1 студента больше
            count = per_day + (1 if day <= remainder else 0)
            groups[day] = students[start_idx:start_idx + count]
            start_idx += count
        
        logger.info(f"📊 Разбиение студентов: {[len(groups[d]) for d in range(1, days + 1)]}")
        return groups
    
    def get_message_text(self, student_username: Optional[str], student_name: str) -> str:
        """
        Формирует текст сообщения-запроса плана на месяц.
        
        Args:
            student_username: Telegram username студента (может быть None)
            student_name: Имя студента
            
        Returns:
            Текст сообщения
        """
        # Формируем обращение
        if student_username:
            greeting = f"@{student_username.lstrip('@')}"
        else:
            greeting = student_name
        
        message = f"""Здравствуйте, {greeting}!

Начинается новый месяц нашего обучения, с чем я вас и поздравляю 😎
Напомню, что без сдачи домашних заданий мы не приближаемся к этапу окупаемости, но что еще хуже - не приобретаем новые знания!

**Давайте поставим с вами цель на этот месяц: сколько домашних заданий вы сможете сдать?**

Рекомендуемая норма для равномерного распределения нагрузки и окончания курса в заявленные сроки поддержки составляет 6 ДЗ ✔️ 
Но только вы можете оценить свои ресурсы на этот месяц, возможно, в этом месяце вы можете сдать 4 ДЗ, а в следующем аж 12 - это нормально 🤝

Пожалуйста, напишите ответом (нажмите на мое сообщение и выберите "Ответить") цифру вашего индивидуального плана на этот месяц:"""
        
        return message
    
    async def save_plan_to_tracker(self, tracker_url: str, plan_value: int, start_date: str) -> bool:
        """
        Сохраняет план в трекер студента.
        
        Args:
            tracker_url: URL трекера студента
            plan_value: Значение плана (количество ДЗ)
            start_date: Дата начала обучения (из ячейки С4)
            
        Returns:
            True если успешно сохранено
        """
        try:
            # Извлекаем ID трекера из URL
            match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', tracker_url)
            if not match:
                logger.error(f"❌ Не удалось извлечь ID трекера из URL: {tracker_url}")
                return False
            
            tracker_id = match.group(1)
            tracker_sheet = self.gc.open_by_key(tracker_id)
            ws = tracker_sheet.sheet1  # Первый лист трекера
            
            # Читаем дату начала из C4
            if not start_date:
                start_date = ws.acell('C4').value
                logger.info(f"📅 Дата начала обучения из C4: {start_date}")
            
            # Парсим дату начала (формат: dd.mm.yy или dd.mm.yyyy)
            try:
                if '.' in start_date:
                    parts = start_date.split('.')
                    day = int(parts[0])
                    month = int(parts[1])
                    year = int(parts[2])
                    if year < 100:
                        year += 2000
                    start_dt = datetime(year, month, day)
                else:
                    logger.error(f"❌ Неверный формат даты начала: {start_date}")
                    return False
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга даты начала '{start_date}': {e}")
                return False
            
            # Вычисляем текущий месяц обучения
            now = datetime.now()
            months_diff = (now.year - start_dt.year) * 12 + (now.month - start_dt.month) + 1
            
            if months_diff < 1:
                logger.warning(f"⚠️ Обучение еще не началось (месяц {months_diff})")
                months_diff = 1
            
            logger.info(f"📊 Месяц обучения: {months_diff}")
            
            # Строка плана: B21 = Месяц 1 (строка 21), B22 = Месяц 2 (строка 22), ...
            # Формула: строка = 20 + months_diff
            # Месяц 1 → строка 21 (C21)
            # Месяц 2 → строка 22 (C22)
            # Месяц 3 → строка 23 (C23)
            plan_row = 20 + months_diff
            plan_cell = f"C{plan_row}"
            
            logger.info(f"📝 Запись плана в {plan_cell} (Месяц {months_diff})")
            
            # Записываем значение
            ws.update(plan_cell, [[plan_value]])
            logger.info(f"✅ План {plan_value} сохранен в трекер ({plan_cell})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения плана в трекер: {e}", exc_info=True)
            return False
    
    async def save_plan_to_kpi(self, getcourse_id: str, plan_value: int) -> bool:
        """
        Сохраняет план в KPI Ultra (колонка плана текущего месяца).
        
        Args:
            getcourse_id: ID студента в GetCourse
            plan_value: Значение плана
            
        Returns:
            True если успешно сохранено
        """
        try:
            spreadsheet = await AsyncSheetsWrapper.run_sync(self._get_kpi_spreadsheet)
            ws = await AsyncSheetsWrapper.run_sync(spreadsheet.worksheet, 'Общий список new')
            
            # Получаем ключ текущего месяца
            month_key = self._get_current_month_key()
            plan_column = self._get_plan_column_for_month(month_key)
            
            if not plan_column:
                logger.error(f"❌ Не найдена колонка плана для месяца {month_key}")
                return False
            
            # Ищем студента по getcourse_id (колонка A)
            all_data = await AsyncSheetsWrapper.run_sync(ws.get_all_values)
            student_row = None
            
            for row_idx, row in enumerate(all_data[20:], start=21):
                if row[0] == getcourse_id:
                    student_row = row_idx
                    break
            
            if not student_row:
                logger.error(f"❌ Студент {getcourse_id} не найден в KPI Ultra")
                return False
            
            # Записываем план
            cell = f"{plan_column}{student_row}"
            await AsyncSheetsWrapper.run_sync(ws.update, cell, [[plan_value]])
            logger.info(f"✅ План {plan_value} сохранен в KPI Ultra ({cell})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения плана в KPI: {e}", exc_info=True)
            return False
    
    def parse_plan_value(self, message_text: str) -> Optional[int]:
        """
        Извлекает число плана из сообщения студента.
        
        Args:
            message_text: Текст сообщения
            
        Returns:
            Число плана или None
        """
        if not message_text:
            return None
        
        # Ищем первое число в сообщении
        match = re.search(r'\b(\d+)\b', message_text.strip())
        if match:
            value = int(match.group(1))
            # Валидация: план должен быть разумным (1-50 ДЗ)
            if 1 <= value <= 50:
                return value
        
        return None
    
    def register_pending_plan(self, user_id: int, getcourse_id: str, message_id: int, tracker_url: str = '', start_date: str = '', student_name: str = ''):
        """
        Регистрирует ожидание ответа студента на запрос плана.
        """
        entry = {
            'getcourse_id': getcourse_id,
            'message_id': message_id,
            'tracker_url': tracker_url,
            'start_date': start_date,
            'timestamp': datetime.now(),
            'student_name': student_name,
        }
        self.pending_plans[user_id] = entry
        logger.info(f"📝 Зарегистрировано ожидание плана от студента {getcourse_id} (user_id={user_id})")
        
        # Сохраняем в таблицу (синхронно — вызывается не в async-контексте)
        try:
            sp = self._get_logs_spreadsheet()
            ws = sp.worksheet(self.PENDING_PLANS_TAB)
            # Удаляем старую строку если есть
            self._delete_row_by_user_id_sync(ws, user_id)
            ws.append_row([
                str(user_id),
                getcourse_id,
                str(message_id),
                tracker_url,
                start_date,
                entry['timestamp'].isoformat(),
                student_name,
            ])
        except Exception as e:
            logger.warning(f"⚠️ Не удалось сохранить pending_plan в таблицу: {e}")
    
    def _delete_row_by_user_id_sync(self, ws, user_id: int):
        """Удаляет строку по telegram_id из листа Pending_Plans (синхронно)"""
        try:
            rows = ws.get_all_values()
            for i, row in enumerate(rows[1:], start=2):
                if row and row[0] == str(user_id):
                    ws.delete_rows(i)
                    return
        except Exception:
            pass
    
    def get_pending_plan(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает данные ожидаемого плана для студента.
        
        Args:
            user_id: Telegram ID студента
            
        Returns:
            Данные ожидаемого плана или None
        """
        return self.pending_plans.get(user_id)
    
    def clear_pending_plan(self, user_id: int):
        """
        Удаляет запись об ожидании плана (RAM + таблица).
        """
        if user_id in self.pending_plans:
            del self.pending_plans[user_id]
            logger.info(f"🗑 Очищено ожидание плана для user_id={user_id}")
        try:
            sp = self._get_logs_spreadsheet()
            ws = sp.worksheet(self.PENDING_PLANS_TAB)
            self._delete_row_by_user_id_sync(ws, user_id)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить pending_plan из таблицы: {e}")
