#!/usr/bin/env python3
"""
Модуль агрегации прогресса студентов из трекеров.
Создает сводную таблицу "Прогресс менеджеров" в KPI Ultra.
"""

import logging
import asyncio
import calendar
from typing import Dict, Any, List, Optional
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

from config import (
    GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE,
    GOOGLE_SHEETS_ID
)
from shared_gspread_client import get_shared_gspread_client
from report_generator import get_report_generator

logger = logging.getLogger('vipalina_telethon')


class ProgressAggregator:
    """
    Агрегатор прогресса студентов.
    Собирает данные из трекеров в сводную таблицу.
    """
    
    SHEET_NAME = "Прогресс менеджеров"
    
    def __init__(self):
        self.gc = get_shared_gspread_client(GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE)
        self.spreadsheet = self.gc.open_by_key(GOOGLE_SHEETS_ID)
        self.progress_sheet = None
        logger.info("ProgressAggregator инициализирован")
    
    def _get_or_create_sheet(self) -> gspread.Worksheet:
        """
        Получает или создает лист "Прогресс менеджеров".
        """
        try:
            # Пытаемся найти существующий лист
            self.progress_sheet = self.spreadsheet.worksheet(self.SHEET_NAME)
            logger.info(f"Найден существующий лист '{self.SHEET_NAME}'")

            # Гарантируем наличие колонки "Месяц" в заголовке (M)
            try:
                header_row = self.progress_sheet.row_values(1)
                # Если меньше 13 колонок или нет нужного заголовка — обновляем
                if len(header_row) < 13 or header_row[12] != 'Месяц':
                    # Делаем длину заголовка ровно 12 колонок (A-L)
                    header_row = list(header_row)
                    while len(header_row) < 12:
                        header_row.append('')
                    if len(header_row) > 12:
                        header_row = header_row[:12]
                    header_row.append('Месяц')  # M
                    self.progress_sheet.update('A1:M1', [header_row], value_input_option='RAW')
                    logger.info("Обновлены заголовки листа 'Прогресс менеджеров' — добавлена колонка 'Месяц'")
            except Exception as e:
                logger.warning(f"Не удалось убедиться в наличии колонки 'Месяц' в заголовке: {e}")

            return self.progress_sheet
        except gspread.exceptions.WorksheetNotFound:
            # Создаем новый лист
            logger.info(f"Создаю новый лист '{self.SHEET_NAME}'")
            self.progress_sheet = self.spreadsheet.add_worksheet(
                title=self.SHEET_NAME,
                rows=1000,
                cols=15
            )
            self._initialize_headers()
            return self.progress_sheet
    
    def _initialize_headers(self):
        """
        Инициализирует заголовки таблицы.
        """
        headers = [
            [
                'ID студента',                    # A
                'Имя студента',                   # B
                'Менеджер',                       # C
                'Статус',                         # D
                'Ссылка на трекер',              # E
                'Дата начала обучения',          # F
                'Текущий месяц обучения',        # G
                'Цель текущего месяца',          # H
                'Факт текущего месяца',          # I
                'Выполнил норму?',               # J
                'Процент выполнения',            # K
                'Дата последнего обновления',    # L
                'Месяц'                          # M
            ]
        ]
        
        self.progress_sheet.update('A1:M1', headers, value_input_option='RAW')
        
        # Форматируем заголовки
        self.progress_sheet.format('A1:M1', {
            'textFormat': {'bold': True},
            'backgroundColor': {'red': 0.2, 'green': 0.5, 'blue': 0.8},
            'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}}
        })
        
        # Замораживаем первую строку
        self.progress_sheet.freeze(rows=1)
        
        logger.info("Заголовки инициализированы")
    
    async def _run_sync_with_retries(self, func, *args, attempts: int = 3, delay: int = 3, **kwargs):
        """Выполняет синхронный Google Sheets вызов с повторами при временных сбоях API."""
        from vipalina_sheets import AsyncSheetsWrapper
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                return await AsyncSheetsWrapper.run_sync(func, *args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt >= attempts:
                    break
                wait_seconds = delay * attempt
                logger.warning(f"⚠️ Google Sheets API временно недоступен ({e}), повтор {attempt}/{attempts} через {wait_seconds} сек")
                await asyncio.sleep(wait_seconds)
        raise last_error
    
    async def sync_students_from_vipalina(self, month_label: str = None):
        """
        Синхронизирует список студентов из листа "Общий список new".
        Добавляет новые строки в лист "Прогресс менеджеров" для указанного (или текущего) месяца.
        
        Args:
            month_label: Метка месяца, например "Март26". Если None — текущий месяц.
        """
        try:
            # Получаем или создаём лист прогресса
            progress_sheet = self._get_or_create_sheet()
            
            # Загружаем KPI-данные из "Общий список new" через ReportGenerator
            report_gen = get_report_generator()
            # Перечитываем заголовки, чтобы подхватить новые месячные колонки
            report_gen._build_month_columns_from_header()

            # Определяем month_label и находим соответствующий month_key и count_col_letter
            count_col_letter = None
            target_month_key = None

            if month_label is None:
                raise ValueError("Для /syncprogress нужно явно указать месяц, например: /syncprogress апрель26")

            # Ищем month_key и колонку count для данного month_label
            for key, config in report_gen.MONTH_COLUMNS.items():
                label = f"{config.get('name', '')}{str(config.get('year', ''))[-2:]}"
                if label.lower() == month_label.lower():
                    month_label = label
                    target_month_key = key
                    count_idx_0based = config.get('count')
                    if count_idx_0based is not None:
                        count_col_letter = self._col_idx_to_letter(count_idx_0based + 1)
                    break

            # Если месяц не найден в заголовках листа — колонок ещё нет, прерываем с ясной ошибкой
            if target_month_key is None:
                raise ValueError(
                    f"Месяц '{month_label}' не найден в колонках листа 'Общий список new'.\n"
                    f"Возможно, колонки для этого месяца ещё не созданы в таблице KPI Ultra."
                )

            if count_col_letter:
                logger.info(f"📊 Колонка Количество ДЗ для {month_label}: {count_col_letter}")
            else:
                logger.warning(f"⚠️ Не найдена колонка count для {month_label} в MONTH_COLUMNS")

            # Читаем данные строго за запрошенный месяц
            kpi_students = await report_gen._get_kpi_data_for_month(target_month_key)
            
            # Создаём словарь актуальных студентов со статусом "Учится"
            current_students_with_study = {}  # {getcourse_id: student_data}
            for student in kpi_students:
                status = student.get('status')
                getcourse_id = student.get('getcourse_id')
                tracker_url = student.get('tracker_url')
                
                if status == 'Учится' and getcourse_id and tracker_url and tracker_url != '-':
                    current_students_with_study[getcourse_id] = student
            
            # Читаем существующие строки
            existing_data = await self._run_sync_with_retries(progress_sheet.get_all_values)
            existing_keys: set[tuple[str, str]] = set()  # (ИД, Месяц) для избежания дублей
            rows_to_delete = []  # Индексы строк для удаления
            existing_month_rows = []  # Индексы строк уже существующего month_label

            for idx, row in enumerate(existing_data[1:], start=2):  # пропускаем заголовок
                if len(row) < 13:
                    continue
                    
                sid = row[0]  # A: ID студента
                m = row[12]   # M: Месяц
                
                if not sid or not m:
                    continue
                
                existing_keys.add((sid, m))
                
                # Если это строка текущего месяца, проверяем актуальность
                if m == month_label:
                    if sid not in current_students_with_study:
                        rows_to_delete.append(idx)
                    else:
                        existing_month_rows.append(idx)
            
            # Не удаляем строки физически: это опасно при сбоях Google API.
            # Неактуальные строки ниже будут помечены как "Неактуально" и не попадут в KPI-формулы.
            if rows_to_delete:
                logger.info(f"ℹ️ Найдено {len(rows_to_delete)} неактуальных строк для месяца {month_label}; строки будут помечены, а не удалены")

            # Обновляем все формулы F-K и дату обновления L для уже существующих строк этого месяца
            if existing_month_rows and month_label:
                ref_date = self._month_label_to_ref_date(month_label)
                ref_date_expr = ref_date if ref_date else 'СЕГОДНЯ()'
                now_str = datetime.now().strftime('%d-%m-%Y %H:%M')
                formula_requests = []
                for row_idx in existing_month_rows:
                    formula_requests.extend([
                        {
                            'range': f'D{row_idx}',
                            'values': [['Учится']]
                        },
                        {
                            'range': f'F{row_idx}',
                            'values': [[f'=IMPORTRANGE(E{row_idx};"📈 Статистика!C4")']]
                        },
                        {
                            'range': f'G{row_idx}',
                            'values': [[f'=ЕСЛИ(ЕПУСТО(F{row_idx});"";РАЗНДАТ(F{row_idx};{ref_date_expr};"M")+1)']]
                        },
                        {
                            'range': f'H{row_idx}',
                            'values': [[f'=ЕСЛИ(ЕПУСТО(G{row_idx});"";ЕСЛИОШИБКА(IMPORTRANGE(E{row_idx};"📈 Статистика!C"&(20+G{row_idx}));"-"))']]
                        },
                        {
                            'range': f'J{row_idx}',
                            'values': [[f'=ЕСЛИ(И(НЕ(ЕПУСТО(H{row_idx}));НЕ(ЕПУСТО(I{row_idx})));ЕСЛИ(I{row_idx}>=H{row_idx};"✅";"❌");"")']]
                        },
                        {
                            'range': f'K{row_idx}',
                            'values': [[f'=ЕСЛИ(И(НЕ(ЕПУСТО(H{row_idx}));H{row_idx}<>0);ОКРУГЛ(I{row_idx}/H{row_idx}*100;0)&"%";"")']]
                        },
                        {
                            'range': f'L{row_idx}',
                            'values': [[now_str]]
                        }
                    ])
                    if count_col_letter:
                        formula_requests.append({
                            'range': f'I{row_idx}',
                            'values': [[f'=ЕСЛИОШИБКА(ИНДЕКС(\'Общий список new\'!{count_col_letter}:{count_col_letter};ПОИСКПОЗ(A{row_idx};\'Общий список new\'!A:A;0));0)']]
                        })
                    else:
                        formula_requests.append({
                            'range': f'I{row_idx}',
                            'values': [[f'=ЕСЛИ(ЕПУСТО(G{row_idx});"";ЕСЛИОШИБКА(IMPORTRANGE(E{row_idx};"📈 Статистика!D"&(20+G{row_idx}));0))']]
                        })
                # Помечаем неактуальные строки так, чтобы они не попадали в отчёты по D="Учится"
                for row_idx in rows_to_delete:
                    formula_requests.extend([
                        {
                            'range': f'D{row_idx}',
                            'values': [['Неактуально']]
                        },
                        {
                            'range': f'L{row_idx}',
                            'values': [[now_str]]
                        }
                    ])
                if formula_requests:
                    from vipalina_sheets import AsyncSheetsWrapper
                    for start in range(0, len(formula_requests), 500):
                        await self._run_sync_with_retries(
                            progress_sheet.batch_update,
                            formula_requests[start:start + 500],
                            value_input_option='USER_ENTERED'
                        )
                    logger.info(f"🔁 Обновлены F-K/L для {len(existing_month_rows)} актуальных строк и помечено {len(rows_to_delete)} неактуальных строк ({month_label})")
            
            # Теперь добавляем новых студентов
            current_rows = len(await self._run_sync_with_retries(progress_sheet.get_all_values))
            
            rows_to_add: List[List[Any]] = []
            
            for getcourse_id, student in current_students_with_study.items():
                # Пропускаем, если такая пара (ИД, месяц) уже есть
                if (getcourse_id, month_label) in existing_keys:
                    continue
                
                new_row = [
                    getcourse_id,                               # A: ID студента
                    student.get('name', ''),                    # B: Имя студента
                    student.get('manager_name', ''),            # C: Менеджер
                    'Учится',                               # D: Статус
                    student.get('tracker_url', ''),             # E: Ссылка на трекер
                    '',  # F: Дата начала обучения (формула)
                    '',  # G: Текущий месяц обучения (формула)
                    '',  # H: Цель текущего месяца (формула)
                    '',  # I: Факт текущего месяца (формула)
                    '',  # J: Выполнил норму? (формула)
                    '',  # K: Процент выполнения (формула)
                    datetime.now().strftime('%d-%m-%Y %H:%M'),  # L: Дата последнего обновления
                    month_label                                # M: Календарный месяц
                ]
                rows_to_add.append(new_row)
            
            if rows_to_add:
                start_row = current_rows + 1
                await self._run_sync_with_retries(progress_sheet.append_rows, rows_to_add, value_input_option='RAW')
                logger.info(f"✅ Добавлено {len(rows_to_add)} студентов в лист '{self.SHEET_NAME}' для месяца {month_label}")
                
                # Добавляем формулы для всех новых строк
                end_row = start_row + len(rows_to_add) - 1
                await self._fill_formulas_for_rows(progress_sheet, start_row, end_row,
                                                   month_label=month_label, count_col_letter=count_col_letter)
            else:
                logger.info("Нет новых студентов для добавления")
        
        except Exception as e:
            logger.error(f"❌ Ошибка синхронизации студентов: {e}", exc_info=True)
            raise
    
    @staticmethod
    def _col_idx_to_letter(col_idx_1based: int) -> str:
        """1-based column index → буква столбца (57 → 'BE')"""
        result = ""
        while col_idx_1based > 0:
            col_idx_1based, rem = divmod(col_idx_1based - 1, 26)
            result = chr(65 + rem) + result
        return result

    @staticmethod
    def _month_label_to_ref_date(month_label: str) -> Optional[str]:
        """
        Парсит метку месяца (напр. "Март26") и возвращает последний день месяца
        в формате DATE(год;месяц;день) для Google Sheets.
        Если не удалось — возвращает None (используется TODAY()).
        """
        import re
        _MONTH_MAP = {
            'январь': 1, 'февраль': 2, 'март': 3, 'апрель': 4,
            'май': 5, 'июнь': 6, 'июль': 7, 'август': 8,
            'сентябрь': 9, 'октябрь': 10, 'ноябрь': 11, 'декабрь': 12,
        }
        m = re.match(r'([а-яё]+)(\d{2})$', month_label.lower())
        if not m:
            return None
        name, yr = m.group(1), int(m.group(2))
        month_num = _MONTH_MAP.get(name)
        if not month_num:
            return None
        year = 2000 + yr
        last_day = calendar.monthrange(year, month_num)[1]
        return f'ДАТА({year};{month_num};{last_day})'

    async def _fill_formulas_for_rows(self, sheet: gspread.Worksheet, start_row: int, end_row: int,
                                      month_label: str = None, count_col_letter: str = None):
        """
        Заполняет формулы для указанного диапазона строк.

        Args:
            sheet: Лист Google Sheets
            start_row: Начальная строка (включительно)
            end_row: Конечная строка (включительно)
            month_label: Метка отчётного месяца (напр. "Март26"). Если None — TODAY().
        """
        try:
            logger.info(f"📝 Заполняю формулы для строк {start_row}-{end_row}...")
            
            # Определяем дату отсчёта для колонки G
            ref_date = None
            if month_label:
                ref_date = self._month_label_to_ref_date(month_label)
            ref_date_expr = ref_date if ref_date else 'TODAY()'

            # Готовим batch update для всех формул
            requests = []
            
            for row in range(start_row, end_row + 1):
                # F: Дата начала (IMPORTRANGE)
                requests.append({
                    'range': f'F{row}',
                    'values': [[f'=IMPORTRANGE(E{row};"📈 Статистика!C4")']]
                })
                
                # G: Текущий месяц обучения (считаем от последнего дня отчётного месяца)
                requests.append({
                    'range': f'G{row}',
                    'values': [[f'=ЕСЛИ(ЕПУСТО(F{row});"";РАЗНДАТ(F{row};{ref_date_expr};"M")+1)']]
                })
                
                # H: Цель текущего месяца
                requests.append({
                    'range': f'H{row}',
                    'values': [[f'=ЕСЛИ(ЕПУСТО(G{row});"";ЕСЛИОШИБКА(IMPORTRANGE(E{row};"📈 Статистика!C"&(20+G{row}));"-"))']]
                })
                
                # I: Факт текущего месяца — из Общий список new (count колонка) или IMPORTRANGE из трекера
                if count_col_letter:
                    requests.append({
                        'range': f'I{row}',
                        'values': [[f'=ЕСЛИОШИБКА(ИНДЕКС(\'Общий список new\'!{count_col_letter}:{count_col_letter};ПОИСКПОЗ(A{row};\'Общий список new\'!A:A;0));0)']]
                    })
                else:
                    requests.append({
                        'range': f'I{row}',
                        'values': [[f'=ЕСЛИ(ЕПУСТО(G{row});"";ЕСЛИОШИБКА(IMPORTRANGE(E{row};"📈 Статистика!D"&(20+G{row}));0))']]
                    })
                
                # J: Выполнил норму?
                requests.append({
                    'range': f'J{row}',
                    'values': [[f'=ЕСЛИ(И(НЕ(ЕПУСТО(H{row}));НЕ(ЕПУСТО(I{row})));ЕСЛИ(I{row}>=H{row};"✅";"❌");"")']]  
                })
                
                # K: Процент выполнения
                requests.append({
                    'range': f'K{row}',
                    'values': [[f'=ЕСЛИ(И(НЕ(ЕПУСТО(H{row}));H{row}<>0);ОКРУГЛ(I{row}/H{row}*100;0)&"%";"")']]  
                })
            
            # Применяем все формулы одним batch-запросом
            for start in range(0, len(requests), 500):
                await self._run_sync_with_retries(
                    sheet.batch_update,
                    requests[start:start + 500],
                    value_input_option='USER_ENTERED'
                )
            
            logger.info(f"✅ Формулы заполнены для строк {start_row}-{end_row}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при заполнении формул: {e}", exc_info=True)
    
    async def update_student_status(self, getcourse_id: str):
        """
        Обновляет статус конкретного студента.
        """
        try:
            progress_sheet = self._get_or_create_sheet()
            
            # Находим строку студента
            ids_column = progress_sheet.col_values(1)
            
            try:
                row_index = ids_column.index(getcourse_id) + 1
            except ValueError:
                logger.warning(f"Студент {getcourse_id} не найден в листе прогресса")
                return
            
            # Обновляем дату последнего обновления
            progress_sheet.update(
                f'L{row_index}',
                [[datetime.now().strftime('%d-%m-%Y %H:%M')]],
                value_input_option='RAW'
            )
            
            logger.info(f"✅ Обновлен статус студента {getcourse_id} в строке {row_index}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса студента: {e}", exc_info=True)
    
    async def get_manager_stats(self, manager_name: str, month_label: str = None) -> Dict[str, Any]:
        """
        Получает статистику по менеджеру за указанный месяц (на основе листа "Прогресс менеджеров").
        
        Args:
            manager_name: имя менеджера
            month_label: метка месяца (например, "Февраль26"). Если None — текущий месяц.
        """
        try:
            progress_sheet = self._get_or_create_sheet()

            # Определяем месяц
            report_gen = get_report_generator()
            if month_label is None:
                month_config = report_gen._get_current_month_config()
                month_label = f"{month_config.get('name', '')}{str(month_config.get('year', ''))[-2:]}"

            # Читаем все данные
            all_data = progress_sheet.get_all_values()

            # Пропускаем заголовок
            students_data = all_data[1:]

            total_students = 0
            completed_norm = 0
            not_completed = 0
            students = []

            for row in students_data:
                # Нужны хотя бы колонки до M (месяц)
                if len(row) < 13:
                    continue

                row_manager = row[2]  # C: Менеджер
                row_status = row[3]   # D: Статус (месяца в KPI)
                row_month = row[12]   # M: Месяц (например, Январь26)

                # Фильтруем по менеджеру и месяцу
                if row_manager != manager_name:
                    continue
                if row_month != month_label:
                    continue

                # Нужны только студенты в статусе "Учится"
                if row_status != 'Учится':
                    continue

                total_students += 1

                student_info = {
                    'id': row[0],
                    'name': row[1],
                    'current_month': row[6],
                    'goal': row[7],
                    'fact': row[8],
                    'completed': row[9],
                    'percentage': row[10],
                    'month': row_month,
                }

                if row[9] == '✅':
                    completed_norm += 1
                else:
                    not_completed += 1

                students.append(student_info)

            completion_rate = (completed_norm / total_students * 100) if total_students > 0 else 0

            return {
                'manager_name': manager_name,
                'month_label': month_label,
                'total_students': total_students,
                'completed_norm': completed_norm,
                'not_completed': not_completed,
                'completion_rate': round(completion_rate, 1),
                'students': students,
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики менеджера: {e}", exc_info=True)
            return {
                'manager_name': manager_name,
                'month_label': month_label or '',
                'total_students': 0,
                'completed_norm': 0,
                'not_completed': 0,
                'completion_rate': 0,
                'students': []
            }


# Глобальный экземпляр
_aggregator_instance = None


def get_progress_aggregator() -> ProgressAggregator:
    """Возвращает глобальный экземпляр ProgressAggregator."""
    global _aggregator_instance
    if _aggregator_instance is None:
        _aggregator_instance = ProgressAggregator()
    return _aggregator_instance
