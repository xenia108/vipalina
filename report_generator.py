"""
Модуль генерации отчётов для VIP-менеджеров.
Читает данные из нескольких источников:
- "Общий список new" — KPI, ДЗ, статусы по месяцам
- "Випалина" — активность в чате, последний контакт
- "SLA_Data" — время ответа менеджеров

Команды:
- /bigreport — большой сводный отчёт
- /reportmonth — месячный отчёт
- /reportweek — недельный отчёт
- /report <id> — отчёт по конкретному студенту
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter
import gspread
from google.oauth2.service_account import Credentials

from config import (
    GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE,
    GOOGLE_SHEETS_ID,
    SLA_GOOGLE_SHEETS_ID,
    VIP_MANAGERS_VIP,
    VIP_MANAGERS_LUXURY,
    VIP_HEAD,
    ON_DUTY_ACCOUNTS
)

logger = logging.getLogger('vipalina_telethon')


class ReportGenerator:
    """
    Генератор отчётов для VIP-менеджеров.
    Объединяет данные из нескольких источников.
    """
    
    # Индексы колонок статуса для каждого месяца в "Общий список new"
    # Формат: {key: {'name': str, 'year': int, 'month': int, 'date': int, 'hw': int, 'status': int, 'count': int, 'kpi': int}}
    # Заполняется динамически по заголовкам строки 19 листа "Общий список new"
    MONTH_COLUMNS: Dict[int, Dict[str, Any]] = {}
    
    # Статусы студентов для категоризации
    STATUS_CATEGORIES = {
        'active': ['Учится', 'Модуль ОК', 'Стажировка'],
        'new': ['Новый'],
        'frozen': ['Заморозка'],
        'missing': ['Пропал'],
        'finished': ['Закончил', 'Окупается', 'Окупился', 'Выпускной'],
        'left': ['Не с нами', 'Возврат']
    }
    
    # Маппинг имён менеджеров для согласования между таблицами
    MANAGER_NAME_MAPPING = {
        # "Общий список new" -> telegram_id
        "Марина Иванова": 5169675294,
        "Оля Антипанова": 6327692209,
        "Кристина Махмудян": 7089851957,
        "Лиза Виноградова": 6467441345,
        "Катя Чайка": 6468860203,
        "Оля Тихонова": 7814751891,
        "Ольга Тихонова": 7814751891,
        "Катя Пилипенко": 8026625530,
        "Ксюша Уланова": 268400185,
        "ДЕЖУРНЫЙ": None,
    }
    
    def __init__(self):
        self.credentials_file = GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE
        self.spreadsheet_id = GOOGLE_SHEETS_ID
        # ID таблицы для реальных дат ДЗ ("Доходимість по ДЗ Випалина")
        self.hw_dates_spreadsheet_id = '1BvRH7-KL5glYXEgRJsa2s49BiHh4m875iQ8nBJDIcu4'
        self.gc = None
        self.spreadsheet = None
        self.hw_dates_sheet = None  # Загрузим по требованию
        self._initialize_connection()
    
    def _initialize_connection(self):
        """Инициализирует подключение к Google Sheets"""
        try:
            from shared_gspread_client import get_shared_gspread_client
            self.gc = get_shared_gspread_client(self.credentials_file)
            self.spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            logger.info("ReportGenerator: подключение к KPI Ultra установлено")

            # Построение MONTH_COLUMNS по заголовкам листа "Общий список new"
            self._build_month_columns_from_header()
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка подключения: {e}", exc_info=True)
            raise
    
    def _build_month_columns_from_header(self):
        """Динамически строит MONTH_COLUMNS по заголовкам 'Общий список new'."""
        try:
            ws = self.spreadsheet.worksheet('Общий список new')
            header_row = ws.row_values(19)

            # Маппинг русских названий месяцев на номера
            month_name_map = {
                'январь': 1,
                'февраль': 2,
                'март': 3,
                'апрель': 4,
                'май': 5,
                'июнь': 6,
                'июль': 7,
                'август': 8,
                'сентябрь': 9,
                'октябрь': 10,
                'ноябрь': 11,
                'декабрь': 12,
            }

            import re

            for idx, title in enumerate(header_row):
                if not title:
                    continue
                title_strip = title.strip()
                if not title_strip.lower().startswith('статус'):
                    continue

                # Ожидаем формат типа "Статус Февраль26" или "Статус Февраль 26"
                rest = title_strip[len('Статус'):].strip()
                if not rest:
                    continue

                # Выделяем часть с буквами (название месяца) и цифры (год, например 26)
                letters = ''.join(ch for ch in rest if not ch.isdigit()).strip()
                digits = ''.join(ch for ch in rest if ch.isdigit())
                if not letters or not digits:
                    # Без года не сможем однозначно определить учебный год
                    logger.warning(f"ReportGenerator: пропускаю столбец без года: '{title_strip}'")
                    continue

                month_word = letters.split()[0].lower()
                month_num = month_name_map.get(month_word)
                if not month_num:
                    logger.warning(f"ReportGenerator: неизвестный месяц в заголовке: '{title_strip}'")
                    continue

                year_suffix = int(digits)
                year_full = 2000 + year_suffix

                key = self._get_month_key(month_num, year_full)

                # Вокруг 'Статус' по схеме: дата(−2), hw(−1), статус(0), count(+1), kpi(+2), comment(+3), plan(+4)
                self.MONTH_COLUMNS[key] = {
                    'name': letters.strip(),
                    'year': year_full,
                    'month': month_num,
                    'date': idx - 2,
                    'hw': idx - 1,
                    'status': idx,
                    'count': idx + 1,
                    'kpi': idx + 2,
                    'comment': idx + 3,
                    'plan': idx + 4,
                }

            if not self.MONTH_COLUMNS:
                logger.warning("ReportGenerator: MONTH_COLUMNS остался пустым после разбора заголовков 'Общий список new'")
            else:
                logger.info(f"ReportGenerator: построено MONTH_COLUMNS для {len(self.MONTH_COLUMNS)} месячных блоков")

        except Exception as e:
            logger.error(f"ReportGenerator: ошибка при построении MONTH_COLUMNS по заголовкам: {e}", exc_info=True)
    
    def _get_current_month_config(self) -> Dict[str, Any]:
        """Возвращает конфигурацию текущего месяца"""
        now = datetime.now()
        current_month = now.month
        current_year = now.year

        # Пытаемся найти точное совпадение по году и месяцу
        for config in self.MONTH_COLUMNS.values():
            if config.get('year') == current_year and config.get('month') == current_month:
                logger.info(f"ReportGenerator: текущий месяц {config['name']} ({current_year}/{current_month})")
                return config

        # Fallback: ищем последний месяц в текущем году, не позже текущего месяца
        candidates = [
            c for c in self.MONTH_COLUMNS.values()
            if c.get('year') == current_year and c.get('month', 0) <= current_month
        ]
        if candidates:
            best = max(candidates, key=lambda c: c['month'])
            logger.warning(
                f"ReportGenerator: прямое совпадение не найдено, использую ближайший месяц {best['name']} {current_year}"
            )
            return best

        # Fallback - последний доступный месяц вообще
        if self.MONTH_COLUMNS:
            max_key = max(self.MONTH_COLUMNS.keys())
            logger.warning(
                f"ReportGenerator: не найден месяц для {current_year}/{current_month}, использую fallback по ключу {max_key}"
            )
            return self.MONTH_COLUMNS[max_key]

        raise RuntimeError("ReportGenerator: MONTH_COLUMNS не инициализирован")
    
    def _get_manager_telegram_id(self, manager_name: str) -> Optional[int]:
        """Получает Telegram ID менеджера по имени"""
        return self.MANAGER_NAME_MAPPING.get(manager_name)
    
    def _get_manager_name_by_id(self, telegram_id: int) -> Optional[str]:
        """Получает имя менеджера по Telegram ID"""
        for name, tid in self.MANAGER_NAME_MAPPING.items():
            if tid == telegram_id:
                return name
        return None
    
    async def get_kpi_data(self) -> List[Dict[str, Any]]:
        """
        Читает данные из 'Общий список new'.
        
        Returns:
            Список словарей с данными студентов
        """
        return await self._get_kpi_data_for_month(None)  # None = текущий месяц
    
    async def _get_kpi_data_for_month(self, month_key: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Читает данные из 'Общий список new' за конкретный месяц.
        
        Args:
            month_key: Ключ месяца в MONTH_COLUMNS, None = текущий
            
        Returns:
            Список словарей с данными студентов
        """
        try:
            ws = self.spreadsheet.worksheet('Общий список new')
            # Читаем все данные начиная со строки 21 (первый студент)
            all_data = ws.get_all_values()
            
            if month_key is None:
                month_config = self._get_current_month_config()
            elif month_key in self.MONTH_COLUMNS:
                month_config = self.MONTH_COLUMNS[month_key]
            else:
                logger.warning(f"ReportGenerator: недопустимый month_key {month_key}")
                return []
            
            students = []
            
            # Данные начинаются со строки 21 (индекс 20)
            for row_idx, row in enumerate(all_data[20:], start=21):
                if len(row) < 8 or not row[0]:  # Пропускаем пустые строки
                    continue
                
                student = {
                    'row_idx': row_idx,
                    'getcourse_id': row[0],                             # A
                    'getcourse_url': row[1] if len(row) > 1 else '',    # B
                    'name': row[2] if len(row) > 2 else '',             # C
                    'course': row[3] if len(row) > 3 else '',           # D
                    'airtable_url': row[4] if len(row) > 4 else '',     # E
                    'tracker_url': row[5] if len(row) > 5 else '',      # F
                    'chat_link': row[6] if len(row) > 6 else '',        # G
                    'manager_name': row[10] if len(row) > 10 else '',   # K (индекс 10)
                }
                
                # Данные целевого месяца
                if len(row) > month_config['kpi']:
                    student['last_hw_date'] = row[month_config['date']] if len(row) > month_config['date'] else ''
                    student['last_hw'] = row[month_config['hw']] if len(row) > month_config['hw'] else ''
                    student['status'] = row[month_config['status']] if len(row) > month_config['status'] else ''
                    student['hw_count'] = row[month_config['count']] if len(row) > month_config['count'] else '0'
                    student['kpi'] = row[month_config['kpi']] if len(row) > month_config['kpi'] else ''
                else:
                    student['last_hw_date'] = ''
                    student['last_hw'] = ''
                    student['status'] = ''
                    student['hw_count'] = '0'
                    student['kpi'] = ''
                
                # Архивный студент: менеджер "Не с нами" и статус месяца "Не с нами"
                student['is_archived'] = (
                    student.get('manager_name') == 'Не с нами'
                    and student.get('status') == 'Не с нами'
                )
                
                students.append(student)
            
            logger.info(f"ReportGenerator: загружено {len(students)} студентов из 'Общий список new' (месяц {month_config.get('name', 'unknown')})")
            return students
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка чтения KPI данных: {e}", exc_info=True)
            return []
    
    async def get_vipalina_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Читает данные из 'Випалина'.
        
        Returns:
            Словарь {getcourse_id: данные студента}
        """
        try:
            ws = self.spreadsheet.worksheet('Випалина')
            all_data = ws.get_all_values()
            
            vipalina_map = {}
            
            for row in all_data[1:]:  # Пропускаем заголовки
                if len(row) < 1 or not row[0]:
                    continue
                
                getcourse_id = row[0]
                vipalina_map[getcourse_id] = {
                    'telegram_id': row[1] if len(row) > 1 else '',              # B
                    'chat_id': row[2] if len(row) > 2 else '',                  # C
                    'name': row[3] if len(row) > 3 else '',                     # D
                    'course': row[4] if len(row) > 4 else '',                   # E
                    'username': row[5] if len(row) > 5 else '',                 # F
                    'manager_id': row[6] if len(row) > 6 else '',               # G
                    'manager_name': row[7] if len(row) > 7 else '',             # H
                    'tracker_url': row[8] if len(row) > 8 else '',              # I
                    'chat_link': row[9] if len(row) > 9 else '',                # J
                    'created_at': row[10] if len(row) > 10 else '',             # K
                    'status': row[11] if len(row) > 11 else '',                 # L
                    'updated_at': row[12] if len(row) > 12 else '',             # M
                    'segment': row[13] if len(row) > 13 else '',                # N
                    'last_contact': row[14] if len(row) > 14 else '',           # O
                    'activity_status': row[15] if len(row) > 15 else '',        # P
                    'notification_date': row[16] if len(row) > 16 else '',      # Q
                    'training_start': row[17] if len(row) > 17 else '',         # R
                    'payback_start': row[18] if len(row) > 18 else '',          # S
                    'payback_due': row[19] if len(row) > 19 else '',            # T
                }
            
            logger.info(f"ReportGenerator: загружено {len(vipalina_map)} студентов из 'Випалина'")
            return vipalina_map
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка чтения Випалина: {e}", exc_info=True)
            return {}
    
    async def _get_hw_dates_sheet(self):
        """Загружает лист из таблицы 'Доходимість по ДЗ Випалина' по требованию."""
        if self.hw_dates_sheet is None:
            try:
                hw_spreadsheet = self.gc.open_by_key(self.hw_dates_spreadsheet_id)
                self.hw_dates_sheet = hw_spreadsheet.get_worksheet(0)  # Первый лист
                logger.info("✅ ReportGenerator: подключение к таблице 'Доходимість по ДЗ' установлено")
            except Exception as e:
                logger.error(f"ReportGenerator: ошибка подключения к таблице 'Доходимість по ДЗ': {e}", exc_info=True)
                raise
        return self.hw_dates_sheet
    
    async def _get_real_last_hw_date(self, getcourse_id: str) -> Optional[str]:
        """
        Ищет реальную последнюю дату ДЗ студента в таблице 'Доходимість по ДЗ Випалина'.
        
        Возвращает дату в формате 'DD.MM.YYYY' или None, если не найдено.
        """
        try:
            sheet = await self._get_hw_dates_sheet()
            all_data = sheet.get_all_values()
            
            # Ищем строку с указанным getcourse_id в столбце A (индекс 0)
            for row in all_data[1:]:  # Пропускаем заголовок
                if len(row) < 9:  # Минимум 9 столбцов (до столбца I)
                    continue
                
                if row[0] == getcourse_id:
                    # Столбец I (индекс 8) - дата последнего ДЗ
                    last_hw_date = row[8].strip()
                    if last_hw_date and last_hw_date.lower() not in ('', 'не сдавал', '-'):
                        return last_hw_date
                    else:
                        return None
            
            # Студент не найден в таблице
            return None
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка получения даты ДЗ для {getcourse_id}: {e}", exc_info=True)
            return None
    
    async def generate_manager_report(self, manager_telegram_id: int) -> str:
        """
        Генерирует отчёт для конкретного менеджера.
        
        Args:
            manager_telegram_id: Telegram ID менеджера
            
        Returns:
            Отформатированный текст отчёта
        """
        try:
            # Получаем имя менеджера
            manager_name = self._get_manager_name_by_id(manager_telegram_id)
            if not manager_name:
                return "❌ Менеджер не найден в системе"
            
            # Загружаем данные из обоих источников
            kpi_students = await self.get_kpi_data()
            vipalina_data = await self.get_vipalina_data()
            
            # Фильтруем студентов по менеджеру
            my_students = [s for s in kpi_students if s['manager_name'] == manager_name]
            
            if not my_students:
                return f"📊 У вас пока нет студентов в системе"
            
            # Объединяем данные
            enriched_students = []
            for student in my_students:
                gid = student['getcourse_id']
                vipalina_info = vipalina_data.get(gid, {})
                
                enriched = {**student}
                enriched['last_contact'] = vipalina_info.get('last_contact', '')
                enriched['activity_status'] = vipalina_info.get('activity_status', '')
                enriched['chat_id'] = vipalina_info.get('chat_id', '')
                enriched_students.append(enriched)
            
            # Категоризация студентов
            month_name = self._get_current_month_config()['name']
            
            # Отличники (KPI=TRUE, ДЗ >= 6)
            excellent = [s for s in enriched_students 
                        if self._parse_hw_count(s['hw_count']) >= 6]
            
            # Нужна мотивация (ДЗ 1-5)
            need_motivation = [s for s in enriched_students 
                              if 1 <= self._parse_hw_count(s['hw_count']) <= 5]
            
            # Не начал / без ДЗ
            no_activity = [s for s in enriched_students 
                          if self._parse_hw_count(s['hw_count']) == 0 
                          and s['status'] not in ('Заморозка', 'Пропал', 'Не с нами', 'Закончил')]
            
            # Пропавшие (по чату)
            missing = [s for s in enriched_students 
                      if '🔴' in s.get('activity_status', '') or s['status'] == 'Пропал']
            
            # Формируем отчёт
            report = f"""📊 **Сводка по вашим студентам**
📅 {month_name} | {datetime.now().strftime('%d.%m.%Y')}
👥 Всего студентов: {len(my_students)}

"""
            
            if excellent:
                report += f"✅ **Молодцы ({len(excellent)})** — похвалить!\n"
                for s in excellent[:5]:  # Показываем первых 5
                    hw = self._parse_hw_count(s['hw_count'])
                    report += f"  • {s['name']}: {hw} ДЗ\n"
                if len(excellent) > 5:
                    report += f"  ... и ещё {len(excellent) - 5}\n"
                report += "\n"
            
            if need_motivation:
                report += f"⚠️ **Нужна мотивация ({len(need_motivation)})**\n"
                for s in need_motivation[:5]:
                    hw = self._parse_hw_count(s['hw_count'])
                    last_hw = s.get('last_hw_date', '-')
                    report += f"  • {s['name']}: {hw} ДЗ (посл: {last_hw})\n"
                if len(need_motivation) > 5:
                    report += f"  ... и ещё {len(need_motivation) - 5}\n"
                report += "\n"
            
            if no_activity:
                report += f"🆕 **Не начали обучение ({len(no_activity)})**\n"
                for s in no_activity[:5]:
                    contact = s.get('last_contact', '-')[:10] if s.get('last_contact') else '-'
                    report += f"  • {s['name']} (контакт: {contact})\n"
                if len(no_activity) > 5:
                    report += f"  ... и ещё {len(no_activity) - 5}\n"
                report += "\n"
            
            if missing:
                report += f"🔴 **Пропавшие ({len(missing)})** — срочно связаться!\n"
                for s in missing[:5]:
                    contact = s.get('last_contact', '-')[:10] if s.get('last_contact') else '-'
                    report += f"  • {s['name']} (посл. контакт: {contact})\n"
                if len(missing) > 5:
                    report += f"  ... и ещё {len(missing) - 5}\n"
            
            return report
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка генерации отчёта: {e}", exc_info=True)
            return f"❌ Ошибка генерации отчёта: {e}"
    
    async def generate_leadership_report(self) -> str:
        """
        Генерирует сводный отчёт для руководства.
        
        Returns:
            Отформатированный текст отчёта
        """
        try:
            kpi_students = await self.get_kpi_data()
            vipalina_data = await self.get_vipalina_data()
            
            month_name = self._get_current_month_config()['name']
            
            # Группируем по менеджерам
            by_manager = {}
            for student in kpi_students:
                mgr = student['manager_name']
                if mgr not in by_manager:
                    by_manager[mgr] = []
                by_manager[mgr].append(student)
            
            report = f"""📊 **СВОДНЫЙ ОТЧЁТ VIP-ОТДЕЛА**
📅 {month_name} | {datetime.now().strftime('%d.%m.%Y')}
👥 Всего студентов: {len(kpi_students)}

━━━━━━━━━━━━━━━━━━━━━━━

"""
            
            for manager_name, students in sorted(by_manager.items()):
                if not manager_name or manager_name in ('ДЕЖУРНЫЙ', ''):
                    continue
                
                # Статистика по менеджеру
                excellent = sum(1 for s in students if self._parse_hw_count(s['hw_count']) >= 6)
                medium = sum(1 for s in students if 1 <= self._parse_hw_count(s['hw_count']) <= 5)
                
                # Не учатся: статус Учится, но 0 ДЗ
                not_learning = sum(1 for s in students if s['status'] == 'Учится' and self._parse_hw_count(s['hw_count']) == 0)
                
                # Не начали: статус Новый и 0 ДЗ
                not_started = sum(1 for s in students if s['status'] == 'Новый' and self._parse_hw_count(s['hw_count']) == 0)
                
                # Пропавшие
                missing = sum(1 for s in students if s['status'] == 'Пропал')
                
                # Окупается и Стажировка
                payback = sum(1 for s in students if s['status'] == 'Окупается')
                internship = sum(1 for s in students if s['status'] == 'Стажировка')
                
                total = len(students)
                active_pct = round((excellent + medium) / (excellent + medium + not_learning) * 100) if (excellent + medium + not_learning) > 0 else 0
                
                report += f"**{manager_name}** ({total} студ.)\n"
                report += f"  ✅ Отличники (6+ ДЗ): {excellent}\n"
                report += f"  ⚠️ Средние (1-5 ДЗ): {medium}\n"
                report += f"  ❌ Не учатся (Учится, 0 ДЗ): {not_learning}\n"
                report += f"  🆕 Не начали (Новый, 0 ДЗ): {not_started}\n"
                report += f"  🔴 Пропавшие: {missing}\n"
                if payback > 0:
                    report += f"  💰 Окупается: {payback}\n"
                if internship > 0:
                    report += f"  💼 Стажировка: {internship}\n"
                report += f"  📈 Активность: {active_pct}%\n\n"
            
            # Общие проблемы
            all_missing = [s for s in kpi_students if s['status'] == 'Пропал']
            if all_missing:
                report += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                report += f"⚠️ **Требуют внимания:** {len(all_missing)} пропавших\n"
            
            return report
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка генерации сводного отчёта: {e}", exc_info=True)
            return f"❌ Ошибка: {e}"
    
    def _parse_hw_count(self, value: str) -> int:
        """Парсит количество ДЗ из строки"""
        try:
            return int(value) if value and value.isdigit() else 0
        except:
            return 0
    
    async def _get_real_hw_count_for_week(self, getcourse_id: str) -> int:
        """
        Получает реальное количество ДЗ за последнюю неделю из таблицы "ВСЕ ДЗ".
        
        Args:
            getcourse_id: ID студента в GetCourse
            
        Returns:
            Количество ДЗ за неделю
        """
        try:
            from config import HOMEWORK_TRACKING_SPREADSHEET_ID, HOMEWORK_TRACKING_TAB
            import asyncio
            
            spreadsheet = self.gc.open_by_key(HOMEWORK_TRACKING_SPREADSHEET_ID)
            worksheet = spreadsheet.worksheet(HOMEWORK_TRACKING_TAB)
            all_data = await asyncio.to_thread(worksheet.get_all_values)
            
            if len(all_data) <= 1:
                return 0
            
            now = datetime.now()
            week_ago = now - timedelta(days=7)
            hw_count = 0
            
            # Столбцы: A - ID с ГК, H - дата сдачи
            for row in all_data[1:]:
                if len(row) < 8:
                    continue
                
                row_id = row[0].strip() if row[0] else ''
                submission_date_str = row[7].strip() if len(row) > 7 else ''
                
                if row_id != getcourse_id or not submission_date_str:
                    continue
                
                try:
                    if '.' in submission_date_str:
                        submission_date = datetime.strptime(submission_date_str[:10], '%d.%m.%Y')
                    else:
                        submission_date = datetime.strptime(submission_date_str[:10], '%Y-%m-%d')
                    
                    if submission_date >= week_ago:
                        hw_count += 1
                except:
                    continue
            
            return hw_count
            
        except Exception as e:
            logger.warning(f"ReportGenerator: ошибка получения ДЗ за неделю для {getcourse_id}: {e}")
            return 0
    
    def _get_month_key(self, month: int, year: int) -> int:
        """Получает ключ месяца для MONTH_COLUMNS (универсально по годам)."""
        # Используем формат YYYYMM, чтобы ключи всегда росли с годами
        return year * 100 + month
    
    async def get_sla_data(self, year: int = None, month: int = None) -> Dict[str, Any]:
        """
        Читает SLA данные.
        
        Returns:
            Статистика SLA по менеджерам
        """
        try:
            if year is None:
                year = datetime.now().year
            if month is None:
                month = datetime.now().month
            
            sla_spreadsheet = self.gc.open_by_key(SLA_GOOGLE_SHEETS_ID)
            ws = sla_spreadsheet.worksheet('SLA_Data')
            all_data = ws.get_all_values()
            
            if len(all_data) <= 1:
                return {'total': 0, 'by_manager': {}}
            
            month_name = datetime(year, month, 1).strftime('%B')
            year_str = str(year)
            
            # Фильтруем по месяцу (колонка 13) и году (колонка 14)
            stats = {'total': 0, 'sla_met': 0, 'avg_time': 0, 'by_manager': {}}
            total_time = 0
            
            for row in all_data[1:]:
                if len(row) < 15:
                    continue
                if row[13] != month_name or row[14] != year_str:
                    continue
                
                stats['total'] += 1
                # Handle both comma and period as decimal separators
                response_time_str = row[6] if row[6] else '0'
                response_time = float(response_time_str.replace(',', '.')) if response_time_str else 0
                sla_met = row[8] == 'Да'
                manager_name = row[4]
                
                if sla_met:
                    stats['sla_met'] += 1
                total_time += response_time
                
                if manager_name not in stats['by_manager']:
                    stats['by_manager'][manager_name] = {'requests': 0, 'sla_met': 0, 'total_time': 0}
                
                stats['by_manager'][manager_name]['requests'] += 1
                stats['by_manager'][manager_name]['total_time'] += response_time
                if sla_met:
                    stats['by_manager'][manager_name]['sla_met'] += 1
            
            if stats['total'] > 0:
                stats['avg_time'] = round(total_time / stats['total'], 1)
                stats['sla_pct'] = round(stats['sla_met'] / stats['total'] * 100, 1)
            
            for mgr in stats['by_manager']:
                m = stats['by_manager'][mgr]
                if m['requests'] > 0:
                    m['avg_time'] = round(m['total_time'] / m['requests'], 1)
                    m['sla_pct'] = round(m['sla_met'] / m['requests'] * 100, 1)
            
            return stats
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка чтения SLA: {e}", exc_info=True)
            return {'total': 0, 'by_manager': {}}
    
    async def get_student_by_id(self, getcourse_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает полные данные о студенте.
        """
        try:
            kpi_students = await self.get_kpi_data()
            vipalina_data = await self.get_vipalina_data()
            
            student = None
            for s in kpi_students:
                if s['getcourse_id'] == getcourse_id:
                    student = s
                    break
            
            if not student:
                return None
            
            # Добавляем данные из Випалины
            vipalina_info = vipalina_data.get(getcourse_id, {})
            student['last_contact'] = vipalina_info.get('last_contact', '')
            student['activity_status'] = vipalina_info.get('activity_status', '')
            student['chat_id'] = vipalina_info.get('chat_id', '')
            student['created_at'] = vipalina_info.get('created_at', '')
            
            return student
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка получения студента: {e}", exc_info=True)
            return None
    
    async def generate_student_report(self, getcourse_id: str) -> str:
        """
        Генерирует детальный отчёт по конкретному студенту.
        
        Команда: /report <getcourse_id>
        """
        try:
            student = await self.get_student_by_id(getcourse_id)
            
            if not student:
                return f"❌ Студент с ID {getcourse_id} не найден"
            
            vipalina_data = await self.get_vipalina_data()
            vipalina_info = vipalina_data.get(getcourse_id, {})
            
            now = datetime.now()
            month_config = self._get_current_month_config()
            hw_count = self._parse_hw_count(student.get('hw_count', '0'))
            
            # === 1. БАЗОВАЯ ИНФОРМАЦИЯ ===
            # Сколько дней в системе
            created_at = student.get('created_at', '')
            days_in_system = '-'
            created_date_str = '-'
            if created_at:
                try:
                    created_date = datetime.strptime(created_at[:10], '%Y-%m-%d')
                    days_in_system = (now - created_date).days
                    created_date_str = created_date.strftime('%d.%m.%Y')
                except:
                    pass
            
            report = f"""📊 **ОТЧЁТ ПО СТУДЕНТУ**

👤 **{student['name']}**
ID: `{getcourse_id}`
📚 Курс: {student.get('course', '-')}
👩‍💼 Менеджер: {student.get('manager_name', '-')}
📅 В системе: {f"{days_in_system} дней (с {created_date_str})" if days_in_system != '-' else '-'}

"""
            
            # === 2. УСПЕВАЕМОСТЬ ===
            report += "━━━━━ УСПЕВАЕМОСТЬ ━━━━━\n\n"
            
            # Общая статистика за всё время
            last_hw_date = student.get('last_hw_date', '')
            days_since_hw = '-'
            hw_date_str = '-'
            if last_hw_date and last_hw_date != 'не сдавал':
                try:
                    hw_date = datetime.strptime(last_hw_date[:10], '%d.%m.%Y')
                    days_since_hw = (now - hw_date).days
                    hw_date_str = hw_date.strftime('%d.%m')
                except:
                    pass
            
            report += f"📊 **Всего за время обучения:**\n"
            report += f"• ДЗ сдано: {hw_count}\n"
            if days_since_hw != '-':
                days_word = "день" if days_since_hw == 1 else "дня" if 2 <= days_since_hw <= 4 else "дней"
                report += f"• Последнее ДЗ: {days_since_hw} {days_word} назад ({hw_date_str})\n"
            else:
                report += f"• Последнее ДЗ: {last_hw_date if last_hw_date else 'не сдавал'}\n"
            
            kpi_status = "✅ Выполняет" if student.get('kpi') == 'TRUE' else "⚠️ Не выполняет"
            report += f"• KPI: {kpi_status}\n\n"
            
            # Текущий месяц
            report += f"🗓 **За текущий месяц ({month_config['name']}):**\n"
            report += f"• Статус: {student.get('status', '-')}\n"
            report += f"• ДЗ в месяц: {hw_count}\n"
            
            # Оценка прогресса
            progress_status = "На уровне нормы" if hw_count >= 6 else "Требует внимания" if hw_count >= 3 else "Низкая активность"
            report += f"• Прогресс: {progress_status}\n\n"
            
            # За неделю - считаем реальное количество из таблицы "ВСЕ ДЗ"
            hw_this_week = await self._get_real_hw_count_for_week(getcourse_id)
            
            report += f"📅 **За последнюю неделю:**\n"
            report += f"• ДЗ: {hw_this_week}\n"
            week_activity = "Высокая" if hw_this_week > 0 else "Низкая"
            report += f"• Активность: {week_activity}\n\n"
            
            # === 3. АКТИВНОСТЬ В ЧАТЕ ===
            report += "━━━━━ АКТИВНОСТЬ В ЧАТЕ ━━━━━\n\n"
            
            last_contact = vipalina_info.get('last_contact', '')
            if last_contact:
                try:
                    contact_date = datetime.strptime(last_contact[:10], '%Y-%m-%d')
                    days_since_contact = (now - contact_date).days
                    contact_str = f"{days_since_contact} дней назад ({contact_date.strftime('%d.%m')})"
                except:
                    contact_str = last_contact[:10]
            else:
                contact_str = '-'
            
            activity_status = vipalina_info.get('activity_status', '-')
            report += f"💬 Последний контакт: {contact_str}\n"
            report += f"📊 Статус: {activity_status}\n\n"
            
            # === 4. SLA & ПОДДЕРЖКА ===
            # Получаем SLA для конкретного студента
            try:
                sla_spreadsheet = self.gc.open_by_key(SLA_GOOGLE_SHEETS_ID)
                ws = sla_spreadsheet.worksheet('SLA_Data')
                all_data = ws.get_all_values()
                
                student_sla = {'total': 0, 'sla_met': 0, 'total_time': 0}
                
                for row in all_data[1:]:
                    if len(row) < 10:
                        continue
                    # GetCourse ID в колонке 2 (индекс 2)
                    if row[2] == getcourse_id:
                        student_sla['total'] += 1
                        # Handle both comma and period as decimal separators
                        response_time_str = row[6] if row[6] else '0'
                        response_time = float(response_time_str.replace(',', '.')) if response_time_str else 0
                        sla_met = row[8] == 'Да'
                        
                        if sla_met:
                            student_sla['sla_met'] += 1
                        student_sla['total_time'] += response_time
                
                if student_sla['total'] > 0:
                    report += "━━━━━ SLA & ПОДДЕРЖКА ━━━━━\n\n"
                    avg_time = round(student_sla['total_time'] / student_sla['total'], 1)
                    sla_pct = round(student_sla['sla_met'] / student_sla['total'] * 100, 1)
                    
                    report += f"⏱ Ср. время ответа менеджера: {avg_time} мин\n"
                    report += f"✅ SLA выполнен: {sla_pct}% ({student_sla['sla_met']} из {student_sla['total']} запросов)\n"
                    
                    quality = "Отличное" if sla_pct >= 90 else "Хорошее" if sla_pct >= 70 else "Требует улучшения"
                    report += f"🎯 Качество поддержки: {quality}\n\n"
            except Exception as e:
                logger.warning(f"ReportGenerator: не удалось получить SLA студента: {e}")
            
            # === 5. ДАТЫ & СРОКИ (из Випалины колонки R, S, T) ===
            training_start = vipalina_info.get('training_start', '')
            payback_start = vipalina_info.get('payback_start', '')
            payback_due = vipalina_info.get('payback_due', '')
            
            if training_start or payback_start or payback_due:
                report += "━━━━━ ДАТЫ & СРОКИ ━━━━━\n\n"
                
                if training_start and training_start != '-':
                    report += f"📅 Дата начала обучения: {training_start}\n"
                
                if payback_start and payback_start != '-':
                    report += f"💰 Начало окупаемости: {payback_start}\n"
                
                if payback_due and payback_due != '-':
                    report += f"🎯 Окупить до: {payback_due}\n"
                    
                    # Считаем дни до окупаемости
                    try:
                        due_date = datetime.strptime(payback_due, '%d.%m.%Y')
                        days_to_payback = (due_date - now).days
                        if days_to_payback > 0:
                            report += f"⏳ До окупаемости: {days_to_payback} дней\n"
                        elif days_to_payback == 0:
                            report += "⏳ До окупаемости: Сегодня!\n"
                        else:
                            report += f"⚠️ Просрочено на {abs(days_to_payback)} дней\n"
                    except:
                        pass
                
                report += "\n"
            
            # === 6. СРАВНЕНИЕ СО СРЕДНИМ ===
            # Получаем статистику по курсу
            try:
                all_students = await self.get_kpi_data()
                course_students = [s for s in all_students if s['course'] == student['course']]
                
                if len(course_students) > 1:
                    report += "━━━━━ СРАВНЕНИЕ СО СРЕДНИМ ━━━━━\n\n"
                    
                    # Средний счёт ДЗ
                    avg_hw = sum(self._parse_hw_count(s['hw_count']) for s in course_students) / len(course_students)
                    hw_diff_pct = round((hw_count - avg_hw) / avg_hw * 100) if avg_hw > 0 else 0
                    
                    hw_comparison = "Выше среднего" if hw_diff_pct > 10 else "Ниже среднего" if hw_diff_pct < -10 else "На уровне"
                    report += f"📖 ДЗ в месяц: {hw_comparison} (средний: {round(avg_hw, 1)})\n"
                    
                    # Активность в чате
                    if last_contact:
                        active_students = 0
                        for s in course_students:
                            v = vipalina_data.get(s['getcourse_id'], {})
                            if v.get('last_contact'):
                                try:
                                    contact_date = datetime.strptime(v['last_contact'][:10], '%Y-%m-%d')
                                    if (now - contact_date).days <= 7:
                                        active_students += 1
                                except:
                                    pass
                        
                        activity_pct = round(active_students / len(course_students) * 100) if course_students else 0
                        is_active = last_contact and (now - datetime.strptime(last_contact[:10], '%Y-%m-%d')).days <= 7
                        
                        if is_active:
                            report += f"💬 Активность в чате: Выше среднего (топ {activity_pct}%)\n"
                        else:
                            report += f"💬 Активность в чате: Ниже среднего\n"
                    
                    report += "\n"
            except Exception as e:
                logger.warning(f"ReportGenerator: не удалось получить сравнение: {e}")
            
            # === 7. РЕКОМЕНДАЦИИ ===
            report += "━━━━━ РЕКОМЕНДАЦИИ ━━━━━\n\n"
            
            # Автоматические рекомендации на основе данных
            recommendations = []
            
            if hw_count >= 6 and (days_since_hw == '-' or days_since_hw <= 7):
                recommendations.append("✅ Студент активен и мотивирован")
                recommendations.append("✅ Регулярно сдаёт ДЗ")
                recommendations.append("💡 Рекомендация: Продолжать в том же темпе")
            elif hw_count >= 3:
                recommendations.append("⚠️ Умеренная активность")
                recommendations.append("💡 Рекомендация: Усилить мотивацию, проверить сложности")
            else:
                recommendations.append("🔴 Низкая активность")
                recommendations.append("💡 Рекомендация: Срочно связаться, выяснить причины")
            
            if days_since_hw != '-' and days_since_hw > 14:
                recommendations.append("⚠️ Давно не сдавал ДЗ — требует внимания")
            
            if last_contact:
                try:
                    contact_date = datetime.strptime(last_contact[:10], '%Y-%m-%d')
                    days_no_contact = (now - contact_date).days
                    if days_no_contact > 7:
                        recommendations.append(f"⚠️ Не выходит на связь {days_no_contact} дней")
                except:
                    pass
            
            for rec in recommendations:
                report += f"{rec}\n"
            
            # === 8. ССЫЛКИ ===
            report += "\n📎 **ССЫЛКИ**\n"
            
            if student.get('tracker_url') and student['tracker_url'] != '-':
                report += f"• [📊 Трекер]({student['tracker_url']})\n"
            if student.get('chat_link') and student['chat_link'] != '-':
                report += f"• [💬 Чат]({student['chat_link']})\n"
            if student.get('getcourse_url'):
                report += f"• [🎓 GetCourse]({student['getcourse_url']})\n"
            
            return report
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка отчёта по студенту: {e}", exc_info=True)
            return f"❌ Ошибка: {e}"
    
    async def generate_big_report(self, manager_name: Optional[str] = None, is_head: bool = False) -> str:
        """
        Генерирует большой сводный отчёт.
        
        Команда: /bigreport
        
        Args:
            manager_name: Имя менеджера или None для всех
            is_head: True если отчёт для руководителя (показывать сравнение)
        """
        try:
            kpi_students = await self.get_kpi_data()
            vipalina_data = await self.get_vipalina_data()
            sla_data = await self.get_sla_data()
            
            # Получаем данные предыдущего месяца для динамики
            prev_month_data = await self._get_previous_month_data()
            
            month_config = self._get_current_month_config()
            now = datetime.now()
            
            # Фильтруем по менеджеру если указан
            if manager_name and manager_name.lower() != 'все':
                students = [s for s in kpi_students if s['manager_name'] == manager_name]
                title = f"📊 **БОЛЬШОЙ ОТЧЁТ: {manager_name}**"
                show_all_managers = False
            else:
                students = kpi_students
                title = "📊 **БОЛЬШОЙ ОТЧЁТ VIP-ОТДЕЛА**"
                show_all_managers = True
            
            if not students:
                return "❌ Нет данных для отчёта"
            
            # Разделяем активных и архивных студентов
            archived_students = [
                s for s in students
                if s.get('manager_name') == 'Не с нами' and s.get('status') == 'Не с нами'
            ]
            active_students = [s for s in students if s not in archived_students]
            
            if not active_students:
                return "❌ Нет активных студентов для отчёта"
            
            total = len(active_students)
            
            # Динамика: прирост/отток
            new_this_month = sum(1 for s in active_students if s.get('status') == 'Новый')
            left_this_month = sum(1 for s in active_students if s.get('status') in ('Не с нами', 'Возврат'))
            
            growth_str = ""
            if new_this_month > 0:
                growth_str += f" | 🆕 Новых сейчас: {new_this_month}"
            if left_this_month > 0:
                growth_str += f" | ❌ Не с нами сейчас: {left_this_month}"
            
            # 1. Статистика по статусам
            status_counts = Counter(s.get('status', '') for s in active_students)
            
            report = f"""{title}
📅 {month_config['name']} | {now.strftime('%d.%m.%Y')}
👥 Всего: {total}{growth_str}

━━━━━ СТАТУСЫ СТУДЕНТОВ ━━━━━

"""
            
            status_emoji = {
                'Учится': '🟢', 'Новый': '🆕', 'Заморозка': '❄️',
                'Пропал': '🔴', 'Закончил': '🎓', 'Окупается': '💰',
                'Окупился': '✅', 'Выпускной': '🎉', 'Модуль ОК': '📝',
                'Стажировка': '💼', 'Не с нами': '❌', 'Возврат': '↩️'
            }
            
            for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
                if not status:
                    continue
                emoji = status_emoji.get(status, '▪️')
                pct = round(count / total * 100, 1)
                report += f"{emoji} {status}: {count} ({pct}%)\n"
            
            # 2. Доходимость по курсам
            course_stats = await self._calculate_course_completion(active_students)
            if course_stats:
                report += "\n━━━━━ ДОХОДИМОСТЬ ПО КУРСАМ ━━━━━\n\n"
                for course, stats in sorted(course_stats.items(), key=lambda x: -x[1]['pct'])[:5]:
                    report += f"📚 {course}: {stats['pct']}% ({stats['active']}/{stats['total']})\n"
            
            # 3. Статистика по менеджерам
            if show_all_managers:
                report += "\n━━━━━ МЕНЕДЖЕРЫ ━━━━━\n\n"
                
                by_manager = {}
                for s in active_students:
                    mgr = s['manager_name']
                    if not mgr or mgr in ('ДЕЖУРНЫЙ', ''):
                        continue
                    if mgr not in by_manager:
                        by_manager[mgr] = []
                    by_manager[mgr].append(s)
                
                # Сначала считаем статистику по всем менеджерам
                manager_stats = []
                for mgr, mgr_students in sorted(by_manager.items()):
                    total_mgr = len(mgr_students)
                    hw_6plus = sum(1 for s in mgr_students if self._parse_hw_count(s['hw_count']) >= 6)
                    hw_1_5 = sum(1 for s in mgr_students if 1 <= self._parse_hw_count(s['hw_count']) <= 5)
                    hw_0 = sum(
                        1
                        for s in mgr_students
                        if self._parse_hw_count(s['hw_count']) == 0
                        and s['status'] not in ('Заморозка', 'Пропал', 'Не с нами')
                    )
                    missing = sum(1 for s in mgr_students if s['status'] == 'Пропал')
                    new_count = sum(1 for s in mgr_students if s['status'] == 'Новый')
                    
                    active_pct = round((hw_6plus + hw_1_5) / total_mgr * 100) if total_mgr > 0 else 0
                    
                    # SLA менеджера
                    sla_mgr = sla_data.get('by_manager', {}).get(mgr, {})
                    sla_pct = sla_mgr.get('sla_pct', '-')
                    avg_time = sla_mgr.get('avg_time', '-')
                    
                    manager_stats.append({
                        'name': mgr,
                        'total': total_mgr,
                        'hw_6plus': hw_6plus,
                        'hw_1_5': hw_1_5,
                        'hw_0': hw_0,
                        'missing': missing,
                        'new': new_count,
                        'active_pct': active_pct,
                        'sla_pct': sla_pct,
                        'avg_time': avg_time,
                    })
                
                # Средняя активность по отделу (по всем реальным менеджерам, кроме служебных групп "Не с нами" и "ДЕЖУРНЫЙ")
                filtered_for_avg = [
                    m for m in manager_stats
                    if m['name'] not in ('Не с нами', 'ДЕЖУРНЫЙ')
                ]
                dept_avg_activity = (
                    round(sum(m['active_pct'] for m in filtered_for_avg) / len(filtered_for_avg))
                    if filtered_for_avg
                    else None
                )
                
                # Печатаем блок по каждому менеджеру с интерпретацией
                for mgr_entry in sorted(manager_stats, key=lambda x: x['name']):
                    mgr = mgr_entry['name']
                    total_mgr = mgr_entry['total']
                    hw_6plus = mgr_entry['hw_6plus']
                    hw_1_5 = mgr_entry['hw_1_5']
                    hw_0 = mgr_entry['hw_0']
                    missing = mgr_entry['missing']
                    new_count = mgr_entry['new']
                    active_pct = mgr_entry['active_pct']
                    sla_pct = mgr_entry['sla_pct']
                    avg_time = mgr_entry['avg_time']
                    
                    report += f"**{mgr}** ({total_mgr}"
                    if new_count > 0:
                        report += f" | +{new_count} нов"
                    report += ")\n"
                    report += f"  ✅{hw_6plus} ⚠️{hw_1_5} 🆕{hw_0} 🔴{missing}\n"
                    report += f"  📈 Активность: {active_pct}%"
                    if sla_pct != '-':
                        report += f" | ⏱ SLA: {sla_pct}%"
                    report += "\n"
                    
                    # Короткая интерпретация для руководителя
                    diagnostics = []
                    if total_mgr > 0:
                        # Высокая доля пропавших (порог 30%)
                        if missing >= 2 and missing / total_mgr >= 0.30:
                            diagnostics.append(
                                f"⚠️ Высокая доля пропавших: {missing}/{total_mgr} — проверь воронку сопровождения"
                            )
                        
                        # Много активных без ДЗ среди студентов со статусом "Учится" (порог 30%)
                        learning_students = [
                            s for s in mgr_students
                            if s.get('status') == 'Учится'
                        ]
                        total_learning = len(learning_students)
                        learning_zero_hw = sum(
                            1 for s in learning_students
                            if self._parse_hw_count(s.get('hw_count', '0')) == 0
                        )
                        if total_learning > 0 and learning_zero_hw / total_learning >= 0.30:
                            diagnostics.append(
                                f"⚠️ Много активных без ДЗ среди 'Учится': {learning_zero_hw}/{total_learning} ({round(learning_zero_hw/total_learning*100)}%) — нужны касания"
                            )
                        
                        # Активность ниже среднего по отделу
                        if (
                            dept_avg_activity is not None
                            and mgr not in ('Не с нами', 'ДЕЖУРНЫЙ')
                            and active_pct < dept_avg_activity - 5
                        ):
                            diagnostics.append(
                                f"⚠️ Активность ниже среднего по отделу: {active_pct}% (среднее {dept_avg_activity}%)"
                            )
                    
                    for line in diagnostics:
                        report += f"  {line}\n"
                    
                    report += "\n"
                
                # 4. Сравнение менеджеров (только для руководителя)
                # В сравнении менеджеров не учитываем служебную группу "Не с нами"
                comparison_stats = [m for m in manager_stats if m['name'] != 'Не с нами']
                if is_head and comparison_stats:
                    report += "━━━━━ СРАВНЕНИЕ МЕНЕДЖЕРОВ ━━━━━\n\n"
                    
                    # Лучший SLA
                    best_sla = max(
                        (m for m in comparison_stats if m['sla_pct'] != '-'),
                        key=lambda x: x['sla_pct'],
                        default=None,
                    )
                    if best_sla:
                        report += f"🏆 Лучший SLA: {best_sla['name']} ({best_sla['sla_pct']}%)\n"
                    
                    # Лучшая активность
                    best_activity = max(comparison_stats, key=lambda x: x['active_pct'])
                    report += f"📈 Лучшая активность: {best_activity['name']} ({best_activity['active_pct']}%)\n"
                    
                    # Больше всего пропавших
                    most_missing = max(comparison_stats, key=lambda x: x['missing'])
                    if most_missing['missing'] > 0:
                        report += f"⚠️ Больше всего 🔴: {most_missing['name']} ({most_missing['missing']})\n"
                    
                    # Меньше всего отличников
                    least_excellent = min(comparison_stats, key=lambda x: x['hw_6plus'])
                    report += f"📝 Меньше всего ✅: {least_excellent['name']} ({least_excellent['hw_6plus']})\n"
                    report += "\n"
            
            # 5. Топ проблемных студентов (разбивка на группы)
            problematic = await self._get_problematic_students(active_students, vipalina_data)
            if problematic:
                report += "━━━━━ ТРЕБУЮТ ВНИМАНИЯ ━━━━━\n\n"
                
                # Карта getcourse_id -> данные студента для определения статуса и количества ДЗ
                students_by_gc = {s.get('getcourse_id'): s for s in active_students if s.get('getcourse_id')}
                
                new_students = []
                learning_zero_hw = []
                stuck_in_progress = []
                
                for p in problematic:
                    gid = p.get('getcourse_id')
                    s = students_by_gc.get(gid)
                    if not s:
                        continue
                    status = s.get('status', '')
                    hw_count = self._parse_hw_count(s.get('hw_count', '0'))
                    
                    if status == 'Новый':
                        new_students.append(p)
                    elif status == 'Учится' and hw_count == 0:
                        learning_zero_hw.append(p)
                    else:
                        stuck_in_progress.append(p)
                
                def print_group(title: str, group: List[Dict]) -> None:
                    nonlocal report
                    if not group:
                        return
                    report += f"{title}\n"
                    for student in group[:5]:
                        report += (
                            f"⚠️ {student['name']} ({student['manager']}) — "
                            f"{student['days']} дней без ДЗ\n"
                        )
                    if len(group) > 5:
                        report += f"... и ещё {len(group) - 5}\n"
                    report += "\n"
                
                print_group("Новые без старта (статус 'Новый')", new_students)
                print_group("Учится, но 0 ДЗ", learning_zero_hw)
                print_group("Провисшие в процессе", stuck_in_progress)
                
                # Итоги по менеджерам среди всех проблемных
                manager_counter = Counter(p['manager'] for p in problematic if p.get('manager'))
                if manager_counter:
                    report += "Итого по менеджерам среди проблемных:\n"
                    for mgr, cnt in manager_counter.most_common():
                        report += f"- {mgr}: {cnt} студент(ов)\n"
                    report += "\n"
            
            # 6. Прогноз доходимости вынесен в отдельную команду /forecast
            
            # 7. Общий SLA
            if sla_data.get('total', 0) > 0:
                report += "━━━━━ SLA ОТДЕЛА ━━━━━\n\n"
                report += f"📍 Всего запросов: {sla_data['total']}\n"
                report += f"✅ SLA выполнен: {sla_data.get('sla_pct', 0)}%\n"
                report += f"⏱ Ср. время ответа: {sla_data.get('avg_time', 0)} мин\n"
            
            # 8. Архивные студенты (не учитываются в статистике)
            if archived_students:
                report += "\n━━━━━ АРХИВНЫЕ СТУДЕНТЫ ━━━━━\n\n"
                report += (
                    "Не учитываются в статистике (менеджер и статус месяца = \"Не с нами\"). "
                    f"Всего: {len(archived_students)}\n"
                )
                for s in archived_students[:5]:
                    report += f"- {s.get('name', '-')}\n"
                if len(archived_students) > 5:
                    report += f"... и ещё {len(archived_students) - 5}\n"
            
            return report
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка big report: {e}", exc_info=True)
            return f"❌ Ошибка: {e}"
    
    async def _calculate_course_completion(self, students: List[Dict]) -> Dict[str, Dict]:
        """Рассчитывает доходимость по курсам"""
        try:
            course_stats = {}
            for s in students:
                course = s.get('course', '')
                if not course:
                    continue
                
                if course not in course_stats:
                    course_stats[course] = {'total': 0, 'active': 0}
                
                course_stats[course]['total'] += 1
                
                # Активный = сдаёт ДЗ (хотя бы 1)
                if self._parse_hw_count(s.get('hw_count', '0')) >= 1:
                    course_stats[course]['active'] += 1
            
            # Вычисляем проценты
            for course in course_stats:
                total = course_stats[course]['total']
                active = course_stats[course]['active']
                course_stats[course]['pct'] = round(active / total * 100) if total > 0 else 0
            
            return course_stats
        except Exception as e:
            logger.error(f"Ошибка расчёта доходимости: {e}")
            return {}
    
    async def _get_problematic_students(self, students: List[Dict], vipalina_data: Dict) -> List[Dict]:
        """
        Получает список проблемных студентов (14+ дней без ДЗ), исключая 'Не с нами' и 'Пропал'.
        
        Использует таблицу 'Доходимість по ДЗ Випалина' для реального расчёта дней с последнего ДЗ.
        """
        try:
            problematic = []
            now = datetime.now()
            
            for s in students:
                # Пропускаем завершивших/замороженных/не с нами/пропавших
                if s.get('status') in ('Закончил', 'Заморозка', 'Не с нами', 'Пропал', 'Возврат', 'Окупился'):
                    continue
                # Пропускаем студентов, закреплённых за служебными "Не с нами" или "ДЕЖУРНЫЙ"
                if s.get('manager_name') in ('Не с нами', 'ДЕЖУРНЫЙ'):
                    continue
                
                getcourse_id = s.get('getcourse_id')
                if not getcourse_id:
                    continue
                
                # Ищем реальную дату последнего ДЗ
                real_last_hw_date = await self._get_real_last_hw_date(getcourse_id)
                
                if real_last_hw_date is None:
                    # Студент никогда не сдавал ДЗ (нет в таблице или пустая дата)
                    problematic.append({
                        'name': s.get('name', '-'),
                        'manager': s.get('manager_name', '-'),
                        'days': 999,  # Сентинельное значение для "никогда"
                        'getcourse_id': getcourse_id
                    })
                    continue
                
                try:
                    # Парсим дату в формате DD.MM.YYYY
                    hw_date = datetime.strptime(real_last_hw_date[:10], '%d.%m.%Y')
                    days_since = (now - hw_date).days
                    
                    if days_since >= 14:
                        problematic.append({
                            'name': s.get('name', '-'),
                            'manager': s.get('manager_name', '-'),
                            'days': days_since,
                            'getcourse_id': getcourse_id
                        })
                except Exception as parse_error:
                    logger.warning(f"ReportGenerator: не удалось распарсить дату '{real_last_hw_date}' для {getcourse_id}: {parse_error}")
                    pass
            
            # Сортируем по дням (сначала самые запущенные)
            return sorted(problematic, key=lambda x: -x['days'])
        except Exception as e:
            logger.error(f"Ошибка получения проблемных: {e}")
            return []
    
    async def _get_previous_month_data(self) -> Dict:
        """Получает данные предыдущего месяца для сравнения"""
        try:
            now = datetime.now()
            prev_month = now.month - 1 if now.month > 1 else 12
            prev_year = now.year if now.month > 1 else now.year - 1
            
            month_key = self._get_month_key(prev_month, prev_year)
            if month_key not in self.MONTH_COLUMNS:
                return {}
            
            # Читаем данные предыдущего месяца
            ws = self.spreadsheet.worksheet('Общий список new')
            all_data = ws.get_all_values()
            
            prev_config = self.MONTH_COLUMNS[month_key]
            total_active = 0
            total = 0
            
            for row in all_data[20:]:
                if len(row) < 8 or not row[0]:
                    continue
                total += 1
                
                # Проверяем кол-во ДЗ за предыдущий месяц
                if len(row) > prev_config['count']:
                    hw_count = self._parse_hw_count(row[prev_config['count']])
                    if hw_count >= 1:
                        total_active += 1
            
            return {
                'total': total,
                'active': total_active,
                'pct': round(total_active / total * 100) if total > 0 else 0
            }
        except Exception as e:
            logger.error(f"Ошибка чтения предыдущего месяца: {e}")
            return {}
    
    def _calculate_completion_forecast(self, students: List[Dict], prev_data: Dict) -> Optional[Dict]:
        """Рассчитывает прогноз доходимости"""
        try:
            total = len(students)
            if total == 0:
                return None
            
            # Текущая активность
            active_now = sum(1 for s in students if self._parse_hw_count(s.get('hw_count', '0')) >= 1)
            current_pct = round(active_now / total * 100)
            
            # В зоне риска: 0 ДЗ + не новые
            at_risk = sum(1 for s in students 
                         if self._parse_hw_count(s.get('hw_count', '0')) == 0
                         and s.get('status') not in ('Новый', 'Заморозка', 'Не с нами'))
            
            # Прогноз на основе тренда
            expected_pct = current_pct
            if prev_data.get('pct'):
                # Усредняем с предыдущим месяцем
                trend = current_pct - prev_data['pct']
                expected_pct = min(100, max(0, current_pct + trend))
            
            return {
                'expected_pct': expected_pct,
                'at_risk': at_risk,
                'current_pct': current_pct
            }
        except Exception as e:
            logger.error(f"Ошибка расчёта прогноза: {e}")
            return None
    
    async def generate_forecast_report(
        self,
        manager_name: Optional[str] = None,
        is_head: bool = False
    ) -> str:
        """Генерирует отдельный отчёт по прогнозу доходимости.

        Команда: /forecast
        """
        try:
            kpi_students = await self.get_kpi_data()
            prev_month_data = await self._get_previous_month_data()
            month_config = self._get_current_month_config()
            now = datetime.now()
            
            # Фильтруем по менеджеру
            if manager_name and manager_name.lower() != 'все':
                students = [s for s in kpi_students if s['manager_name'] == manager_name]
                title = f"📈 **ПРОГНОЗ ДОХОДИМОСТИ: {manager_name}**"
            else:
                students = kpi_students
                title = "📈 **ПРОГНОЗ ДОХОДИМОСТИ VIP-ОТДЕЛА**"
            
            if not students:
                return "❌ Нет данных для прогноза"
            
            # Исключаем архивных студентов (менеджер и статус месяца = "Не с нами")
            students = [
                s for s in students
                if not (s.get('manager_name') == 'Не с нами' and s.get('status') == 'Не с нами')
            ]
            if not students:
                return "❌ Нет активных студентов для прогноза"
            
            forecast = self._calculate_completion_forecast(students, prev_month_data)
            if not forecast:
                return "❌ Недостаточно данных для прогноза"
            
            report = f"{title}\n"
            report += f"📅 {month_config['name']} | {now.strftime('%d.%m.%Y')}\n\n"
            report += f"📊 Текущая доходимость: {forecast['current_pct']}%\n"
            report += f"📈 Ожидаемая доходимость: {forecast['expected_pct']}%\n"
            report += f"⚠️ В зоне риска (0 ДЗ, не новые): {forecast['at_risk']} студент(ов)\n\n"
            report += "ℹ️ Прогноз основан на текущей доле активных студентов и динамике предыдущего месяца.\n"
            
            return report
        
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка forecast report: {e}", exc_info=True)
            return f"❌ Ошибка: {e}"

    async def generate_month_report(
        self, 
        manager_name: Optional[str] = None,
        month: Optional[int] = None,
        year: Optional[int] = None,
        is_head: bool = False
    ) -> str:
        """
        Генерирует детальный месячный отчёт.
        
        Команда: /reportmonth
        
        Args:
            manager_name: Имя менеджера или None для всех
            month: Номер месяца (1-12), None = текущий
            year: Год, None = текущий
            is_head: True если отчёт для руководителя
        """
        try:
            now = datetime.now()
            target_month = month if month else now.month
            target_year = year if year else now.year
            
            # Получаем конфигурацию целевого месяца
            month_key = self._get_month_key(target_month, target_year)
            if month_key not in self.MONTH_COLUMNS:
                return f"❌ Данные за {target_month}/{target_year} недоступны"
            
            month_config = self.MONTH_COLUMNS[month_key]
            month_name = month_config['name']
            
            # Загружаем данные
            kpi_students = await self._get_kpi_data_for_month(month_key)
            vipalina_data = await self.get_vipalina_data()
            sla_data = await self.get_sla_data(year=target_year, month=target_month)
            
            # Данные предыдущего месяца для сравнения
            prev_month = 12 if target_month == 1 else target_month - 1
            prev_year = target_year - 1 if target_month == 1 else target_year
            prev_month_key = self._get_month_key(prev_month, prev_year)
            prev_month_students = await self._get_kpi_data_for_month(prev_month_key) if prev_month_key in self.MONTH_COLUMNS else []
            if prev_month_students:
                prev_month_students = [
                    s for s in prev_month_students
                    if not (s.get('manager_name') == 'Не с нами' and s.get('status') == 'Не с нами')
                ]
            
            # Фильтруем по менеджеру
            if manager_name and manager_name.lower() != 'все':
                students = [s for s in kpi_students if s['manager_name'] == manager_name]
                title = f"📅 **МЕСЯЧНЫЙ ОТЧЁТ: {manager_name}**"
            else:
                students = kpi_students
                title = "📅 **МЕСЯЧНЫЙ ОТЧЁТ VIP-ОТДЕЛА**"
            
            if not students:
                return f"❌ Нет данных за {month_name} {target_year}"
            
            # Исключаем архивных студентов (менеджер и статус месяца = "Не с нами")
            students = [
                s for s in students
                if not (s.get('manager_name') == 'Не с нами' and s.get('status') == 'Не с нами')
            ]
            
            if not students:
                return f"❌ Нет активных студентов за {month_name} {target_year}"
            
            total = len(students)
            
            # === 1. ЗАГОЛОВОК И ОБЩИЕ ПОКАЗАТЕЛИ ===
            report = f"""{title}
📆 {month_name} {target_year}
👥 Всего студентов: {total}

"""
            
            # Прирост/отток за месяц
            if prev_month_students:
                prev_total = len([s for s in prev_month_students if s.get('manager_name') == manager_name] if manager_name and manager_name.lower() != 'все' else prev_month_students)
                growth = total - prev_total
                growth_str = f"📈 +{growth}" if growth > 0 else f"📉 {growth}" if growth < 0 else "➡️ 0"
                report += f"Изменение: {growth_str} (было {prev_total})\n\n"
            
            report += "━━━━━ УСПЕВАЕМОСТЬ ━━━━━\n\n"
            
            # === 2. КАТЕГОРИИ СТУДЕНТОВ ===
            hw_6plus = [s for s in students if self._parse_hw_count(s['hw_count']) >= 6]
            hw_1_5 = [s for s in students if 1 <= self._parse_hw_count(s['hw_count']) <= 5]
            hw_0 = [s for s in students if self._parse_hw_count(s['hw_count']) == 0 and s['status'] not in ('Заморозка', 'Не с нами', 'Пропал', 'Закончил')]
            missing = [s for s in students if s['status'] == 'Пропал']
            left = [s for s in students if s['status'] == 'Не с нами']
            
            report += f"✅ Отличники (6+ ДЗ): {len(hw_6plus)} ({round(len(hw_6plus)/total*100, 1)}%)\n"
            report += f"⚠️ Средние (1-5 ДЗ): {len(hw_1_5)} ({round(len(hw_1_5)/total*100, 1)}%)\n"
            report += f"🆕 Не начали: {len(hw_0)} ({round(len(hw_0)/total*100, 1)}%)\n"
            report += f"🔴 Пропавшие: {len(missing)} ({round(len(missing)/total*100, 1)}%)\n"
            report += f"❌ Не с нами: {len(left)} ({round(len(left)/total*100, 1)}%)\n\n"
            
            # === 3. ИТОГИ МЕСЯЦА ===
            finished = [s for s in students if s['status'] in ('Закончил', 'Выпускной')]
            payback_started = [s for s in students if s['status'] == 'Окупается']
            payback_complete = [s for s in students if s['status'] == 'Окупился']
            
            if finished or payback_started or payback_complete:
                report += "━━━━━ ИТОГИ МЕСЯЦА ━━━━━\n\n"
                if finished:
                    report += f"🎓 Закончили обучение: {len(finished)}\n"
                if payback_started:
                    report += f"💰 Начали окупаться: {len(payback_started)}\n"
                if payback_complete:
                    report += f"✅ Окупились: {len(payback_complete)}\n"
                report += "\n"
            
            # === 4. ДИНАМИКА (сравнение с предыдущим месяцем) ===
            if prev_month_students:
                report += "━━━━━ ДИНАМИКА ━━━━━\n\n"
                
                # Активность
                prev_hw_6plus = len([s for s in prev_month_students if self._parse_hw_count(s['hw_count']) >= 6])
                prev_hw_1_5 = len([s for s in prev_month_students if 1 <= self._parse_hw_count(s['hw_count']) <= 5])
                prev_total_active = prev_hw_6plus + prev_hw_1_5
                prev_activity_pct = round(prev_total_active / len(prev_month_students) * 100, 1) if prev_month_students else 0
                
                current_activity_pct = round((len(hw_6plus) + len(hw_1_5)) / total * 100, 1)
                activity_diff = current_activity_pct - prev_activity_pct
                activity_arrow = "📈" if activity_diff > 0 else "📉" if activity_diff < 0 else "➡️"
                
                report += f"📊 Активность: {current_activity_pct}% {activity_arrow} ({activity_diff:+.1f}%)\n"
                
                # Пропавшие
                prev_missing = len([s for s in prev_month_students if s['status'] == 'Пропал'])
                missing_diff = len(missing) - prev_missing
                if missing_diff != 0:
                    missing_arrow = "⚠️" if missing_diff > 0 else "✅"
                    report += f"🔴 Пропавшие: {len(missing)} {missing_arrow} ({missing_diff:+d})\n"
                
                report += "\n"
            
            # === 5. ТОП МЕСЯЦА ===
            report += "━━━━━ ТОП МЕСЯЦА ━━━━━\n\n"
            
            # Топ студентов по ДЗ
            top_students = sorted(students, key=lambda s: self._parse_hw_count(s['hw_count']), reverse=True)[:3]
            if top_students and self._parse_hw_count(top_students[0]['hw_count']) > 0:
                report += "🏆 **Больше всего ДЗ:**\n"
                for idx, s in enumerate(top_students, 1):
                    hw_count = self._parse_hw_count(s['hw_count'])
                    if hw_count > 0:
                        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉"
                        report += f"  {medal} {s['name']}: {hw_count} ДЗ\n"
                report += "\n"
            
            # Статистика по менеджерам
            if not manager_name or manager_name.lower() == 'все':
                by_manager = {}
                for s in students:
                    mgr = s['manager_name']
                    if not mgr or mgr in ('ДЕЖУРНЫЙ', ''):
                        continue
                    if mgr not in by_manager:
                        by_manager[mgr] = []
                    by_manager[mgr].append(s)
                
                manager_stats = []
                for mgr, mgr_students in by_manager.items():
                    mgr_total = len(mgr_students)
                    mgr_hw_6plus = sum(1 for s in mgr_students if self._parse_hw_count(s['hw_count']) >= 6)
                    mgr_hw_1_5 = sum(1 for s in mgr_students if 1 <= self._parse_hw_count(s['hw_count']) <= 5)
                    mgr_activity_pct = round((mgr_hw_6plus + mgr_hw_1_5) / mgr_total * 100, 1) if mgr_total > 0 else 0
                    
                    manager_stats.append({
                        'name': mgr,
                        'total': mgr_total,
                        'activity_pct': mgr_activity_pct,
                        'hw_6plus': mgr_hw_6plus
                    })
                
                if manager_stats:
                    best_manager = max(manager_stats, key=lambda m: m['activity_pct'])
                    report += f"🏆 **Лучший менеджер:** {best_manager['name']} ({best_manager['activity_pct']}% активность)\n\n"
            
            # === 6. ПРОБЛЕМЫ ===
            # Студенты без ДЗ 30+ дней (используем колонку 'Дата последнего ДЗ' из текущего месяца)
            # Группируем по менеджерам, анализируем только статусы Учится и Новый
            long_inactive_by_manager = {}
            for s in students:
                # Фильтруем по статусам
                if s['status'] not in ('Учится', 'Новый'):
                    continue
                
                last_hw_date_str = s.get('last_hw_date', '')
                manager = s.get('manager_name', '')
                
                if not last_hw_date_str or last_hw_date_str.strip() in ('', '-', 'не сдавал'):
                    # Никогда не сдавал ДЗ
                    if manager not in long_inactive_by_manager:
                        long_inactive_by_manager[manager] = []
                    long_inactive_by_manager[manager].append({'name': s['name'], 'days': 999})
                else:
                    try:
                        # Парсим дату (формат может быть DD.MM.YYYY или DD.MM.YY)
                        date_str = last_hw_date_str.strip()[:10]
                        if '.' in date_str:
                            parts = date_str.split('.')
                            if len(parts) == 3:
                                day, month, year = parts
                                if len(year) == 2:
                                    year = '20' + year
                                hw_date = datetime(int(year), int(month), int(day))
                                days_since = (now - hw_date).days
                                if days_since >= 30:
                                    if manager not in long_inactive_by_manager:
                                        long_inactive_by_manager[manager] = []
                                    long_inactive_by_manager[manager].append({'name': s['name'], 'days': days_since})
                    except:
                        pass
            
            if long_inactive_by_manager:
                report += "━━━━━ ТРЕБУЮТ ВНИМАНИЯ ━━━━━\n\n"
                total_long_inactive = sum(len(students_list) for students_list in long_inactive_by_manager.values())
                report += f"⚠️ **Без ДЗ 30+ дней (статусы Учится/Новый):** {total_long_inactive}\n\n"
                
                # Если отчет по конкретному менеджеру - показываем имена
                if manager_name and manager_name.lower() != 'все':
                    for manager in sorted(long_inactive_by_manager.keys()):
                        students_list = long_inactive_by_manager[manager]
                        report += f"**{manager}** ({len(students_list)} студ.):\n"
                        for student in sorted(students_list, key=lambda x: x['days'] if isinstance(x['days'], int) else 999, reverse=True)[:5]:
                            report += f"  • {student['name']} — {student['days']} дней\n"
                        if len(students_list) > 5:
                            report += f"  ... и ещё {len(students_list) - 5}\n"
                        report += "\n"
                else:
                    # Для отчета "все" - только менеджеры с количеством
                    for manager in sorted(long_inactive_by_manager.keys()):
                        students_list = long_inactive_by_manager[manager]
                        report += f"  • **{manager}**: {len(students_list)}\n"
            
            # === 7. SLA ОТДЕЛА ===
            if sla_data.get('total', 0) > 0:
                report += "\n━━━━━ SLA ЗА МЕСЯЦ ━━━━━\n\n"
                sla_pct = round(sla_data.get('sla_met', 0) / sla_data['total'] * 100, 1)
                avg_time = round(sla_data.get('avg_time', 0), 1) if 'avg_time' in sla_data else '-'
                
                report += f"📍 Всего запросов: {sla_data['total']}\n"
                report += f"✅ SLA выполнен: {sla_pct}%\n"
                if avg_time != '-':
                    report += f"⏱ Ср. время ответа: {avg_time} мин\n"
            
            return report
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка month report: {e}", exc_info=True)
            return f"❌ Ошибка: {e}"
    
    async def generate_week_report(self, manager_name: Optional[str] = None, is_head: bool = False) -> str:
        """
        Генерирует детальный недельный отчёт.
        
        Команда: /reportweek
        
        Args:
            manager_name: Имя менеджера или None для всех
            is_head: True если отчёт для руководителя
        """
        try:
            kpi_students = await self.get_kpi_data()
            vipalina_data = await self.get_vipalina_data()
            
            now = datetime.now()
            week_ago = now - timedelta(days=7)
            two_weeks_ago = now - timedelta(days=14)
            
            # Фильтруем по менеджеру
            if manager_name and manager_name.lower() != 'все':
                students = [s for s in kpi_students if s['manager_name'] == manager_name]
                title = f"📅 **НЕДЕЛЬНЫЙ ОТЧЁТ: {manager_name}**"
            else:
                students = kpi_students
                title = "📅 **НЕДЕЛЬНЫЙ ОТЧЁТ VIP-ОТДЕЛА**"
            
            if not students:
                return "❌ Нет данных"
            
            # Исключаем архивных студентов (менеджер и статус месяца = "Не с нами")
            students = [
                s for s in students
                if not (s.get('manager_name') == 'Не с нами' and s.get('status') == 'Не с нами')
            ]
            
            if not students:
                return "❌ Нет активных студентов"
            
            total = len(students)
            
            # === 1. ЗАГОЛОВОК ===
            report = f"""{title}
📆 {week_ago.strftime('%d.%m')} - {now.strftime('%d.%m.%Y')}
👥 Всего студентов: {total}

"""
            
            # === 2. АКТИВНОСТЬ ЗА НЕДЕЛЮ ===
            # Студенты, сдавшие ДЗ за неделю (используем колонку 'Дата последнего ДЗ')
            active_hw_this_week = []
            for s in students:
                last_hw_date_str = s.get('last_hw_date', '')
                if last_hw_date_str and last_hw_date_str.strip() not in ('', '-', 'не сдавал'):
                    try:
                        date_str = last_hw_date_str.strip()[:10]
                        if '.' in date_str:
                            parts = date_str.split('.')
                            if len(parts) == 3:
                                day, month, year = parts
                                if len(year) == 2:
                                    year = '20' + year
                                hw_date = datetime(int(year), int(month), int(day))
                                if hw_date >= week_ago:
                                    active_hw_this_week.append(s)
                    except:
                        pass
            
            # Студенты, писавшие в чат за неделю
            active_chat_this_week = []
            for s in students:
                gid = s['getcourse_id']
                v = vipalina_data.get(gid, {})
                last_contact = v.get('last_contact', '')
                if last_contact:
                    try:
                        contact_date = datetime.strptime(last_contact[:10], '%Y-%m-%d')
                        if contact_date >= week_ago:
                            active_chat_this_week.append(s)
                    except:
                        pass
            
            # Уникальные активные (ДЗ ИЛИ чат)
            active_ids = set([s['getcourse_id'] for s in active_hw_this_week] + 
                            [s['getcourse_id'] for s in active_chat_this_week])
            active_total = len(active_ids)
            activity_pct = round(active_total / total * 100, 1) if total > 0 else 0
            
            # Новые студенты за неделю (по дате создания чата)
            new_this_week = []
            for s in students:
                gid = s['getcourse_id']
                v = vipalina_data.get(gid, {})
                created_at = v.get('created_at', '')
                if created_at:
                    try:
                        created_date = datetime.strptime(created_at[:10], '%Y-%m-%d')
                        if created_date >= week_ago:
                            new_this_week.append({'student': s, 'date': created_at[:10]})
                    except:
                        pass
            
            report += "━━━━━ АКТИВНОСТЬ ЗА НЕДЕЛЮ ━━━━━\n\n"
            report += f"📖 Сдали ДЗ: {len(active_hw_this_week)} ({round(len(active_hw_this_week)/total*100, 1)}%)\n"
            report += f"💬 Писали в чат: {len(active_chat_this_week)} ({round(len(active_chat_this_week)/total*100, 1)}%)\n"
            report += f"🎯 Активны (ДЗ+чат): {active_total} ({activity_pct}%)\n"
            
            if new_this_week:
                report += f"🆕 Новые студенты: {len(new_this_week)}\n"
            
            # === 3. ДИНАМИКА (сравнение с предыдущей неделей) ===
            # Активность за предыдущую неделю (7-14 дней назад)
            prev_week_hw = []
            prev_week_chat = []
            
            for s in students:
                getcourse_id = s.get('getcourse_id')
                if not getcourse_id:
                    continue
                
                # ДЗ за предыдущую неделю (используем колонку 'Дата последнего ДЗ')
                last_hw_date_str = s.get('last_hw_date', '')
                if last_hw_date_str and last_hw_date_str.strip() not in ('', '-', 'не сдавал'):
                    try:
                        date_str = last_hw_date_str.strip()[:10]
                        if '.' in date_str:
                            parts = date_str.split('.')
                            if len(parts) == 3:
                                day, month, year = parts
                                if len(year) == 2:
                                    year = '20' + year
                                hw_date = datetime(int(year), int(month), int(day))
                                if two_weeks_ago <= hw_date < week_ago:
                                    prev_week_hw.append(s)
                    except:
                        pass
                
                # Чат за предыдущую неделю
                gid = s['getcourse_id']
                v = vipalina_data.get(gid, {})
                last_contact = v.get('last_contact', '')
                if last_contact:
                    try:
                        contact_date = datetime.strptime(last_contact[:10], '%Y-%m-%d')
                        if two_weeks_ago <= contact_date < week_ago:
                            prev_week_chat.append(s)
                    except:
                        pass
            
            prev_active_ids = set([s['getcourse_id'] for s in prev_week_hw] + 
                                 [s['getcourse_id'] for s in prev_week_chat])
            prev_active_total = len(prev_active_ids)
            
            if prev_active_total > 0:
                report += "\n━━━━━ ДИНАМИКА ━━━━━\n\n"
                report += "📊 vs предыдущая неделя:\n"
                
                hw_diff = len(active_hw_this_week) - len(prev_week_hw)
                hw_arrow = "📈" if hw_diff > 0 else "📉" if hw_diff < 0 else "➡️"
                report += f"• ДЗ: {len(active_hw_this_week)} {hw_arrow} ({hw_diff:+d})\n"
                
                activity_diff = active_total - prev_active_total
                prev_activity_pct = round(prev_active_total / total * 100, 1) if total > 0 else 0
                activity_pct_diff = activity_pct - prev_activity_pct
                activity_arrow = "📈" if activity_pct_diff > 0 else "📉" if activity_pct_diff < 0 else "➡️"
                report += f"• Активность: {activity_pct}% {activity_arrow} ({activity_pct_diff:+.1f}%)\n"
                
                if new_this_week:
                    report += f"• Новые студенты: +{len(new_this_week)}\n"
            
            # === 4. НОВЫЕ СТУДЕНТЫ ===
            if new_this_week:
                report += "\n━━━━━ НОВЫЕ СТУДЕНТЫ ━━━━━\n\n"
                report += f"🆕 Пришли на этой неделе: {len(new_this_week)}\n"
                for new_s in sorted(new_this_week, key=lambda x: x['date'], reverse=True)[:5]:
                    s = new_s['student']
                    date_str = datetime.strptime(new_s['date'], '%Y-%m-%d').strftime('%d.%m')
                    report += f"  • {s['name']} ({date_str})\n"
                if len(new_this_week) > 5:
                    report += f"  ... и ещё {len(new_this_week) - 5}\n"
            
            # === 5. ТОП НЕДЕЛИ ===
            report += "\n━━━━━ ТОП НЕДЕЛИ ━━━━━\n\n"
            
            # Топ по ДЗ за неделю (у кого больше всего ДЗ вообще из активных)
            top_hw = sorted(active_hw_this_week, 
                          key=lambda s: self._parse_hw_count(s['hw_count']), 
                          reverse=True)[:3]
            
            if top_hw:
                report += "🏆 **Больше всего ДЗ:**\n"
                for idx, s in enumerate(top_hw, 1):
                    hw_count = self._parse_hw_count(s['hw_count'])
                    medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉"
                    last_date = s.get('last_hw_date', '')[:10] if s.get('last_hw_date') else '-'
                    report += f"  {medal} {s['name']}: {hw_count} ДЗ (посл: {last_date})\n"
                report += "\n"
            
            # === 6. ТРЕБУЮТ ВНИМАНИЯ ===
            # Студенты без связи 7+ дней
            no_contact_week = []
            for s in students:
                gid = s['getcourse_id']
                v = vipalina_data.get(gid, {})
                last_contact = v.get('last_contact', '')
                if last_contact:
                    try:
                        contact_date = datetime.strptime(last_contact[:10], '%Y-%m-%d')
                        days_since = (now - contact_date).days
                        if days_since >= 7 and s['status'] not in ('Новый', 'Заморозка', 'Не с нами', 'Пропал'):
                            no_contact_week.append({'student': s, 'days': days_since})
                    except:
                        pass
                elif s['status'] not in ('Новый', 'Заморозка', 'Не с нами', 'Пропал'):
                    # Нет данных о контакте вообще
                    no_contact_week.append({'student': s, 'days': '7+'})
            
            # Студенты без ДЗ 14+ дней (используем колонку 'Дата последнего ДЗ')
            # Группируем по менеджерам, анализируем только статусы Учится и Новый
            no_hw_2weeks_by_manager = {}
            for s in students:
                # Фильтруем по статусам
                if s['status'] not in ('Учится', 'Новый'):
                    continue
                            
                last_hw_date_str = s.get('last_hw_date', '')
                manager = s.get('manager_name', '')
                            
                if not last_hw_date_str or last_hw_date_str.strip() in ('', '-', 'не сдавал'):
                    # Никогда не сдавал ДЗ
                    if manager not in no_hw_2weeks_by_manager:
                        no_hw_2weeks_by_manager[manager] = []
                    no_hw_2weeks_by_manager[manager].append(s)
                else:
                    try:
                        date_str = last_hw_date_str.strip()[:10]
                        if '.' in date_str:
                            parts = date_str.split('.')
                            if len(parts) == 3:
                                day, month, year = parts
                                if len(year) == 2:
                                    year = '20' + year
                                hw_date = datetime(int(year), int(month), int(day))
                                days_since = (now - hw_date).days
                                if days_since >= 14:
                                    if manager not in no_hw_2weeks_by_manager:
                                        no_hw_2weeks_by_manager[manager] = []
                                    no_hw_2weeks_by_manager[manager].append(s)
                    except:
                        pass
            
            if no_contact_week or no_hw_2weeks_by_manager:
                report += "━━━━━ ТРЕБУЮТ ВНИМАНИЯ ━━━━━\n\n"
                
                if no_contact_week:
                    report += f"⚠️ **Не выходят на связь 7+ дней:** {len(no_contact_week)}\n"
                    for item in sorted(no_contact_week, 
                                     key=lambda x: x['days'] if isinstance(x['days'], int) else 999, 
                                     reverse=True)[:5]:
                        s = item['student']
                        days = item['days']
                        report += f"  • {s['name']} ({s['manager_name']}) — {days} дней\n"
                    if len(no_contact_week) > 5:
                        report += f"  ... и ещё {len(no_contact_week) - 5}\n"
                    report += "\n"
                
                if no_hw_2weeks_by_manager:
                    total_no_hw = sum(len(students_list) for students_list in no_hw_2weeks_by_manager.values())
                    report += f"🔴 **Без ДЗ 2+ недели (статусы Учится/Новый):** {total_no_hw}\n\n"
                    
                    # Если отчет по конкретному менеджеру - показываем имена
                    if manager_name and manager_name.lower() != 'все':
                        for manager in sorted(no_hw_2weeks_by_manager.keys()):
                            students_list = no_hw_2weeks_by_manager[manager]
                            report += f"**{manager}** ({len(students_list)} студ.):\n"
                            for s in students_list[:3]:
                                report += f"  • {s['name']}\n"
                            if len(students_list) > 3:
                                report += f"  ... и ещё {len(students_list) - 3}\n"
                            report += "\n"
                    else:
                        # Для отчета "все" - только менеджеры с количеством
                        for manager in sorted(no_hw_2weeks_by_manager.keys()):
                            students_list = no_hw_2weeks_by_manager[manager]
                            report += f"  • **{manager}**: {len(students_list)}\n"
            
            # === 7. SLA ЗА НЕДЕЛЮ ===
            # Получаем SLA за последние 7 дней
            try:
                sla_spreadsheet = self.gc.open_by_key(SLA_GOOGLE_SHEETS_ID)
                ws = sla_spreadsheet.worksheet('SLA_Data')
                all_data = ws.get_all_values()
                
                week_sla = {'total': 0, 'sla_met': 0, 'total_time': 0}
                
                for row in all_data[1:]:
                    if len(row) < 10:
                        continue
                    
                    # Дата в колонке 1 (индекс 1)
                    try:
                        date_str = row[1]
                        request_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                        if request_date >= week_ago:
                            week_sla['total'] += 1
                            # Handle both comma and period as decimal separators
                            response_time_str = row[6] if row[6] else '0'
                            response_time = float(response_time_str.replace(',', '.')) if response_time_str else 0
                            sla_met = row[8] == 'Да'
                            
                            if sla_met:
                                week_sla['sla_met'] += 1
                            week_sla['total_time'] += response_time
                    except:
                        continue
                
                if week_sla['total'] > 0:
                    report += "\n━━━━━ SLA ЗА НЕДЕЛЮ ━━━━━\n\n"
                    sla_pct = round(week_sla['sla_met'] / week_sla['total'] * 100, 1)
                    avg_time = round(week_sla['total_time'] / week_sla['total'], 1)
                    
                    report += f"📍 Запросов: {week_sla['total']}\n"
                    report += f"✅ SLA выполнен: {sla_pct}%\n"
                    report += f"⏱ Ср. время ответа: {avg_time} мин\n"
            except Exception as e:
                logger.warning(f"ReportGenerator: не удалось получить SLA за неделю: {e}")
            
            return report
            
        except Exception as e:
            logger.error(f"ReportGenerator: ошибка week report: {e}", exc_info=True)
            return f"❌ Ошибка: {e}"
    
    def get_manager_list(self) -> List[str]:
        """Возвращает список имён менеджеров"""
        return [name for name, tid in self.MANAGER_NAME_MAPPING.items() 
                if tid is not None and name not in ('ДЕЖУРНЫЙ',)]


# Singleton для использования в других модулях
_report_generator: Optional[ReportGenerator] = None


def get_report_generator() -> ReportGenerator:
    """Возвращает экземпляр ReportGenerator (singleton)"""
    global _report_generator
    if _report_generator is None:
        _report_generator = ReportGenerator()
    return _report_generator
