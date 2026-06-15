"""
Интеграция с Google Sheets для таблицы KPI Ultra
"""

import gspread
from google.oauth2.service_account import Credentials
import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio
from async_sheets_wrapper import AsyncSheetsWrapper
from config import (
    GOOGLE_SHEETS_CREDENTIALS_FILE,
    GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE,
    GOOGLE_SHEETS_ID,
    GOOGLE_SHEETS_KPI_TAB
)

logger = logging.getLogger('vipalina_telethon')


class VipalinaKPISheetsIntegration:
    """
    Интеграция VipAlina с Google Sheets KPI Ultra.
    Управляет листом "Общий список new" с автоматическим созданием строк и формул.
    """
    
    # Курсы для dropdown
    COURSE_LIST = [
        "Мобилка new", "Вип навсегда", "club год", "Питон",
        "Питон (отложенный)", "Аналитик", "Промпт-инженер",
        "Лухари Карьера", "Лухари Стартап", "VIP+ мобилка",
        "VIP+ питон", "VIP+ веб", "VIP+ аналитик", "Лухари Студия",
        "Нейро маркетинг кс", "Нейроденьги", "Нейро", "Нейро корпорат",
        "Мобилка old", "веб-разраб", "FlutterFlow", "Промпт Корпоратив",
        "Web-design", "1 С разраб", "Чат бот", "VIP+prompt enginer",
        "Русские нейронки", "Рус нейр корп", "Китайские нейро кс",
        "Инвестиции", "Корп НейроБандл", "БандлНейро", "Neuro-teach",
        "Al-Консалтинг под", "neuro-law", "Al-Консалтинг \"Корп\"",
        "Китайские Нейро", "Вайб маркетинг Корп", "Вайб кодинг",
        "Аи консультант", "Вайб кодер профессия", "Автоматизация 2.0"
    ]
    
    # Менеджеры для dropdown
    MANAGER_LIST = [
        "Марина", "Катя", "Оля (Антипанова)", "Кристина",
        "Не с нами", "Дежурный", "Лиза", "Чайка", "Ольга (Тихонова)"
    ]
    
    # Статусы для dropdown
    STATUS_LIST = [
        "Новый", "Учится", "Заморозка", "Пропал", "Выпускной",
        "Стажировка", "Модуль ОК", "Окупается", "Закончил",
        "Не с нами", "Окупился", "Возврат"
    ]
    
    # Маппинг месяцев для формул
    MONTH_MAPPING = {
        10: {'name': 'октябрь', 'sheet': 'Октябрь25', 'start_col': 'T'},
        11: {'name': 'ноябрь', 'sheet': 'Ноябрь25', 'start_col': 'Y'},
        12: {'name': 'декабрь', 'sheet': 'Декабрь25', 'start_col': 'AD'},
        1: {'name': 'январь', 'sheet': 'Январь26', 'start_col': 'AI'},
        2: {'name': 'февраль', 'sheet': 'Февраль26', 'start_col': 'AN'},
        3: {'name': 'март', 'sheet': 'Март26', 'start_col': 'AS'},
        4: {'name': 'апрель', 'sheet': 'Апрель26', 'start_col': 'AX'},
        5: {'name': 'май', 'sheet': 'Май26', 'start_col': 'BC'},
        6: {'name': 'июнь', 'sheet': 'Июнь26', 'start_col': 'BH'},
        7: {'name': 'июль', 'sheet': 'Июль26', 'start_col': 'BM'},
        8: {'name': 'август', 'sheet': 'Август26', 'start_col': 'BR'},
        9: {'name': 'сентябрь', 'sheet': 'Сентябрь26', 'start_col': 'BW'}
    }
    
    def __init__(self):
        self.credentials_file = GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE
        self.spreadsheet_id = GOOGLE_SHEETS_ID
        self.tab_name = GOOGLE_SHEETS_KPI_TAB
        self.worksheet = None
        self.spreadsheet = None
        # Кеш для get_all_values и get_all_enrolled_ids
        self._all_data_cache = None
        self._all_data_cache_time = 0
        self._enrolled_ids_cache = None
        self._enrolled_ids_cache_time = 0
        self._CACHE_TTL = 120  # 2 минуты
        self._initialize_connection()
    
    def _initialize_connection(self):
        """Инициализирует подключение к Google Sheets KPI Ultra"""
        try:
            from shared_gspread_client import get_shared_gspread_client
            gc = get_shared_gspread_client(GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE)
            self.spreadsheet = gc.open_by_key(self.spreadsheet_id)
            
            # Открываем лист "Общий список new"
            try:
                self.worksheet = self.spreadsheet.worksheet(self.tab_name)
                logger.info(f"Подключен к листу '{self.tab_name}' в KPI Ultra")
            except gspread.exceptions.WorksheetNotFound:
                logger.error(f"Лист '{self.tab_name}' не найден в таблице KPI Ultra")
                raise
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации подключения к KPI Ultra: {e}", exc_info=True)
            raise
    
    async def insert_row_above_21(self) -> bool:
        """
        Вставляет новую строку над строкой 21, копируя формулы из строки 22 (бывшей 21).
        Строка 21 становится строкой 22, а новая строка - строкой 21.
        
        Returns:
            True если успешно
        """
        import asyncio as _asyncio
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Вставка новой строки над строкой 21 (попытка {attempt}/{max_retries})...")
                
                await AsyncSheetsWrapper.run_sync(
                    self.worksheet.insert_row,
                    [],
                    index=21
                )
                
                logger.info("\u2705 \u041d\u043e\u0432\u0430\u044f \u0441\u0442\u0440\u043e\u043a\u0430 \u0432\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0430 \u043d\u0430\u0434 \u0441\u0442\u0440\u043e\u043a\u043e\u0439 21")
                self.invalidate_cache()
                return True
                
            except Exception as e:
                err_str = str(e)
                if '429' in err_str or '503' in err_str or 'quota' in err_str.lower() or 'exhausted' in err_str.lower() or 'unavailable' in err_str.lower():
                    if attempt < max_retries:
                        wait_sec = 30 * attempt
                        logger.warning(f"⚠️ Квота Google API исчерпана, жду {wait_sec}с перед повторной попыткой... (попытка {attempt}/{max_retries})")
                        await _asyncio.sleep(wait_sec)
                        continue
                logger.error(f"Ошибка при вставке строки: {e}", exc_info=True)
                return False
        logger.error("Ошибка при вставке строки: превышено число попыток")
        return False
    
    def _get_current_month_config(self) -> Dict[str, str]:
        """Получает конфигурацию текущего месяца для формул"""
        current_month = datetime.now().month
        return self.MONTH_MAPPING.get(current_month, self.MONTH_MAPPING[10])
    
    def _get_kpi_manager_name(self, bot_manager_name: str) -> str:
        """
        Преобразует имя менеджера из бота в формат KPI Sheets.
        ВАЖНО: Имя должно точно совпадать со значением в выпадающем списке!
        
        Args:
            bot_manager_name: Имя менеджера в боте
            
        Returns:
            Имя менеджера для KPI таблицы (полное имя для dropdown)
        """
        mapping = {
            "Катя Пилипенко": "Катя Пилипенко",
            "Катя Чайка": "Катя Чайка",
            "Оля Антипанова": "Оля Антипанова",
            "Ольга Тихонова": "Ольга Тихонова",
            "Лиза Виноградова": "Лиза Виноградова",
            "Марина Иванова": "Марина Иванова",
            "Кристина Махмудян": "Кристина Махмудян",
            "Ксюша Уланова": "Ксюша Уланова",
            "Черный Дежурный": "ДЕЖУРНЫЙ",
            "Синий Дежурный": "ДЕЖУРНЫЙ",
            "Изумрудный Дежурный": "ДЕЖУРНЫЙ"
        }
        return mapping.get(bot_manager_name, bot_manager_name)
    
    async def add_student_to_kpi_sheet(
        self,
        student_data: Dict[str, Any],
        row_number: Optional[int] = None,
        invite_link: Optional[str] = None,
        tracker_url: Optional[str] = None,
        nocodb_url: Optional[str] = None
    ) -> bool:
        """
        Добавляет студента в лист "Общий список new" путём вставки новой строки над строкой 21.
        Заполняет только основные данные (A-H), месячные столбцы не трогает.
        
        Args:
            student_data: {
                'getcourse_id': str,
                'getcourse_url': str,
                'name': str,
                'course': str,
                'manager_name': str,
                'telegram_id': Optional[int]
            }
            row_number: Игнорируется, всегда используется строка 21
            invite_link: Invite-ссылка на чат Telegram (опционально)
            tracker_url: Ссылка на созданный трекер (опционально)
            nocodb_url: Ссылка на запись студента в NocoDB (опционально)
            
        Returns:
            True если успешно добавлено
        """
        try:
            # Всегда используем строку 21
            target_row = 21
            
            # Преобразуем имя менеджера
            kpi_manager_name = self._get_kpi_manager_name(student_data['manager_name'])
            logger.info(f"👤 Менеджер для KPI (H): '{student_data['manager_name']}' → '{kpi_manager_name}'")
            
            logger.info(f"Добавление студента {student_data['getcourse_id']} в KPI Sheets, строка {target_row}")
            
            # Шаг 1: Вставляем новую пустую строку над строкой 21
            insert_success = await self.insert_row_above_21()
            if not insert_success:
                logger.error("Не удалось вставить новую строку")
                return False
            
            # Шаг 2: Копируем формулы из строки 22 (бывшей 21) во ВСЕ месячные столбцы
            logger.info("Копирование формул из строки 22...")
            try:
                # Получаем формулы из строки 22 для ВСЕХ месячных столбцов (T-ZZ)
                source_row = 22
                
                # Диапазон месячных столбцов: T (20-я колонка) до ZZ (702-я колонка)
                # T=20, U=21, V=22, W=23, X=24, Y=25, Z=26, AA=27, ..., ZZ=702
                start_col_letter = 'T'
                end_col_letter = 'ZZ'
                
                # Читаем формулы из строки 22 для ВСЕГО диапазона T22:ZZ22
                source_formulas = await AsyncSheetsWrapper.run_sync(
                    self.worksheet.get,
                    f'{start_col_letter}{source_row}:{end_col_letter}{source_row}',
                    value_render_option='FORMULA'
                )
                source_formulas = source_formulas[0] if source_formulas else []
                
                # Заменяем номер строки 22 на 21 в формулах
                updated_formulas = []
                for formula in source_formulas:
                    if formula and str(source_row) in str(formula):
                        updated_formula = str(formula).replace(str(source_row), str(target_row))
                        updated_formulas.append(updated_formula)
                    else:
                        updated_formulas.append(formula)
                
                # Записываем формулы в строку 21 для ВСЕГО диапазона T21:ZZ21
                await AsyncSheetsWrapper.run_sync(
                    self.worksheet.update,
                    f'{start_col_letter}{target_row}:{end_col_letter}{target_row}',
                    [updated_formulas],
                    value_input_option='USER_ENTERED'
                )
                logger.info(f"✅ Формулы скопированы и обновлены для строки {target_row} (диапазон {start_col_letter}-{end_col_letter})")
            except Exception as e:
                logger.warning(f"Не удалось скопировать формулы: {e}")
            
            # Шаг 3: Заполняем только основные данные (A-K)
            # Структура колонок:
            # A: ID (формула REGEXEXTRACT)
            # B: GetCourse URL
            # C: Имя студента
            # D: Курс
            # E: Ссылка на NocoDB (запись студента)
            # F: Ссылка на трекер
            # G: Invite-ссылка на чат
            # H: Дата начала учебы (пустая, заполняется вручную)
            # I: Дата окончания поддержки (формула ВПР + ДАТАМЕС из Матрицы курсов)
            # J: Дата окончания окупаемости (формула ВПР + ДАТАМЕС из Матрицы курсов)
            # K: Менеджер
            
            # A: формула для извлечения ID из GetCourse URL
            id_formula = f'=REGEXEXTRACT(B{target_row};"id/(\\d+)")'
            
            # H: Дата начала обучения — берётся из трекера студента через IMPORTRANGE
            h_formula = f'=IMPORTRANGE(F{target_row};"📈 Статистика!C4")'
            
             # I: формула для расчета даты окончания поддержки
            # ВПР ищет курс из D в Матрице курсов (колонка B) и берет значение из F (5-я колонка)
            # ДАТАМЕС прибавляет месяцы к дате начала учебы
            support_end_formula = f'=ЕСЛИ(ИЛИ(H{target_row}="";H{target_row}="");"";ДАТАМЕС(H{target_row};ЕСЛИОШИБКА(ВПР(D{target_row};\'Матрица курсов\'!B:F;5;0);0)))'
            
            # J: формула для расчета даты окончания окупаемости
            # ВПР ищет курс из D в Матрице курсов (колонка B) и берет значение из G (6-я колонка)
            # ДАТАМЕС прибавляет месяцы к дате начала учебы
            profitability_end_formula = f'=ЕСЛИ(ИЛИ(H{target_row}="";H{target_row}="");"";ДАТАМЕС(H{target_row};ЕСЛИОШИБКА(ВПР(D{target_row};\'Матрица курсов\'!B:G;6;0);0)))'
            
            # Обновляем колонки по отдельности с правильными опциями
            # C: Имя (только первое слово, без фамилии)
            full_name = student_data.get('name', '')
            first_name = full_name.split()[0] if full_name else ''

            # 1 запрос: все RAW данные через batch_update (B-H + K)
            await AsyncSheetsWrapper.run_sync(
                self.worksheet.batch_update,
                [
                    {'range': f'B{target_row}', 'values': [[student_data.get('getcourse_url', '')]]},
                    {'range': f'C{target_row}', 'values': [[first_name]]},
                    {'range': f'D{target_row}', 'values': [[student_data.get('course', '')]]},
                    {'range': f'E{target_row}', 'values': [[nocodb_url if nocodb_url else '']]},
                    {'range': f'F{target_row}', 'values': [[tracker_url if tracker_url else '']]},
                    {'range': f'G{target_row}', 'values': [[invite_link if invite_link else '']]},
                    {'range': f'K{target_row}', 'values': [[kpi_manager_name]]},
                ],
                value_input_option='RAW'
            )

            # 2 запрос: формулы USER_ENTERED (A, I, J) через batch_update
            await AsyncSheetsWrapper.run_sync(
                self.worksheet.batch_update,
                [
                    {'range': f'A{target_row}', 'values': [[id_formula]]},
                    {'range': f'H{target_row}', 'values': [[h_formula]]},
                    {'range': f'I{target_row}', 'values': [[support_end_formula]]},
                    {'range': f'J{target_row}', 'values': [[profitability_end_formula]]},
                ],
                value_input_option='USER_ENTERED'
            )
            
            logger.info(f"✅ Основные данные добавлены в строку {target_row}")
            
            # НЕ добавляем месячные формулы - они уже есть в скопированной строке
            # await self._add_monthly_formulas(target_row, month_config) - УБРАНО
            
            logger.info(f"✅ Студент {student_data['getcourse_id']} успешно добавлен в KPI Sheets")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении студента в KPI Sheets: {e}", exc_info=True)
            return False
    
    async def _add_monthly_formulas(self, row_number: int, month_config: Dict[str, str]) -> bool:
        """
        Добавляет формулы для месячных метрик.
        
        Args:
            row_number: Номер строки
            month_config: Конфигурация месяца {'sheet': 'Октябрь25', 'start_col': 'T'}
            
        Returns:
            True если успешно
        """
        try:
            month_sheet = month_config['sheet']
            start_col = month_config['start_col']
            
            # Формулы для 5 колонок месяца:
            # T (0): Дата последнего ДЗ
            # U (1): Последнее ДЗ
            # V (2): Статус (dropdown, по умолчанию "Новый")
            # W (3): Количество ДЗ
            # X (4): KPI
            
            # T: Дата последнего ДЗ
            last_hw_date_formula = f'=ЕСЛИОШИБКА(МАКС(FILTER(\'{month_sheet}\'!$I:$I; \'{month_sheet}\'!$A:$A = $A{row_number}));"не сдавал")'
            
            # U: Последнее ДЗ
            last_hw_formula = f'=ЕСЛИОШИБКА(ИНДЕКС(FILTER(\'{month_sheet}\'!$G:$G; \'{month_sheet}\'!$A:$A = $A{row_number});ПОИСКПОЗ(МАКС(FILTER(\'{month_sheet}\'!$I:$I; \'{month_sheet}\'!$A:$A = $A{row_number}));FILTER(\'{month_sheet}\'!$I:$I; \'{month_sheet}\'!$A:$A = $A{row_number});0));"-")'
            
            # V: Статус - просто текст "Новый" для новых студентов
            status_value = "Новый"
            
            # W: Количество ДЗ
            hw_count_formula = f'=ЕСЛИОШИБКА(ВПР($A{row_number};\'KPI Общая октябрь25\'!$A:$T;10;0);0)'
            
            # X: KPI (зависит от статуса V и количества W)
            status_col = self._get_column_letter(start_col, 2)  # V = T+2
            hw_col = self._get_column_letter(start_col, 3)  # W = T+3
            
            kpi_formula = f'=ЕСЛИ(ИЛИ({status_col}{row_number}="Заморозка";{status_col}{row_number}="Окупился";{status_col}{row_number}="Окупается";{status_col}{row_number}="Стажировка";{status_col}{row_number}="Пропал";{status_col}{row_number}="Выпускной";{status_col}{row_number}="Новый";{status_col}{row_number}="Модуль ОК";{status_col}{row_number}="Закончил";{status_col}{row_number}="Не с нами";{hw_col}{row_number}>6);ИСТИНА;ЛОЖЬ)'
            
            # Вычисляем колонки для месячных данных
            col_t = start_col
            col_u = self._get_column_letter(start_col, 1)
            col_v = self._get_column_letter(start_col, 2)
            col_w = self._get_column_letter(start_col, 3)
            col_x = self._get_column_letter(start_col, 4)
            
            # Обновляем формулы по отдельности
            self.worksheet.update(f'{col_t}{row_number}', [[last_hw_date_formula]])
            self.worksheet.update(f'{col_u}{row_number}', [[last_hw_formula]])
            self.worksheet.update(f'{col_v}{row_number}', [[status_value]])
            self.worksheet.update(f'{col_w}{row_number}', [[hw_count_formula]])
            self.worksheet.update(f'{col_x}{row_number}', [[kpi_formula]])
            
            logger.info(f"✅ Месячные формулы добавлены для строки {row_number}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении месячных формул: {e}", exc_info=True)
            return False
    
    def _get_column_letter(self, start_col: str, offset: int) -> str:
        """
        Получает букву колонки со смещением.
        
        Args:
            start_col: Начальная колонка (например, 'T')
            offset: Смещение (0 = та же колонка, 1 = следующая, и т.д.)
            
        Returns:
            Буква колонки
        """
        # Конвертируем букву в число
        col_num = 0
        for char in start_col:
            col_num = col_num * 26 + (ord(char.upper()) - ord('A') + 1)
        
        # Добавляем смещение
        col_num += offset
        
        # Конвертируем обратно в букву
        result = ''
        while col_num > 0:
            col_num -= 1
            result = chr(col_num % 26 + ord('A')) + result
            col_num //= 26
        
        return result
    
    async def _get_all_data_cached(self, force_refresh: bool = False) -> list:
        """
        Возвращает все данные из worksheet с кешированием (TTL 120 сек).
        Все методы, которым нужны данные таблицы, должны использовать этот метод.
        При ошибке возвращает устаревший кеш если есть.
        """
        import time
        now = time.time()
        if not force_refresh and self._all_data_cache is not None and (now - self._all_data_cache_time) < self._CACHE_TTL:
            return self._all_data_cache
        
        # Retry с переподключением при ошибках
        last_exc = None
        for attempt in range(3):  # 3 попытки вместо 5 (с timeout 30с это ~90с макс)
            try:
                all_data = await asyncio.to_thread(self.worksheet.get_all_values)
                self._all_data_cache = all_data
                self._all_data_cache_time = time.time()
                return all_data
            except Exception as e:
                last_exc = e
                error_text = str(e).lower()
                is_transient = any(m in error_text for m in [
                    '503', '500', '502', '404', '429', 'timeout',
                    'unavailable', 'service is currently', 'not found',
                    'remotedisconnected', 'connection aborted',
                    'connection reset', 'broken pipe', 'internal error'
                ])
                if is_transient and attempt < 2:
                    wait = 2 ** attempt  # 1, 2 сек
                    logger.warning(f"Transient ошибка get_all_values (попытка {attempt+1}/3): {e}. Ждём {wait}с...")
                    # Переподключаем worksheet
                    try:
                        self.worksheet = self.spreadsheet.worksheet(self.tab_name)
                        logger.info(f"♻️ Worksheet '{self.tab_name}' переподключен")
                    except Exception:
                        pass
                    await asyncio.sleep(wait)
                    continue
                # Не-transient ошибка — пробуем вернуть stale cache
                break
        
        # Все попытки провалились — возвращаем stale cache если есть
        if self._all_data_cache is not None:
            logger.warning(f"Google API недоступен, использую устаревший кеш (возраст {int(now - self._all_data_cache_time)}с): {last_exc}")
            return self._all_data_cache
        raise last_exc
    
    def invalidate_cache(self):
        """Сбрасывает кеш (вызывать после записи в таблицу)."""
        self._all_data_cache = None
        self._all_data_cache_time = 0
        self._enrolled_ids_cache = None
        self._enrolled_ids_cache_time = 0

    async def get_all_enrolled_ids(self) -> set:
        """
        Возвращает множество всех getcourse_id из колонки A листа "Общий список new".
        Используется для фильтрации Manager_Assignments. Кешируется на 2 минуты.
        """
        import time
        now = time.time()
        if self._enrolled_ids_cache is not None and (now - self._enrolled_ids_cache_time) < self._CACHE_TTL:
            return self._enrolled_ids_cache
        
        try:
            all_data = await self._get_all_data_cached()
            ids = set()
            import re as _re
            for i in range(20, len(all_data)):
                row = all_data[i]
                if len(row) > 0 and row[0]:
                    ids.add(str(row[0]).strip())
                # Fallback: колонка B (URL)
                if len(row) > 1 and row[1]:
                    m = _re.search(r'id/(\d+)', row[1])
                    if m:
                        ids.add(m.group(1))
            logger.info(f"get_all_enrolled_ids: найдено {len(ids)} ID в 'Общий список new'")
            self._enrolled_ids_cache = ids
            self._enrolled_ids_cache_time = now
            return ids
        except Exception as e:
            logger.error(f"Ошибка get_all_enrolled_ids: {e}", exc_info=True)
            # Возвращаем стухший кеш если есть
            if self._enrolled_ids_cache is not None:
                logger.warning("Используем устаревший кеш enrolled_ids")
                return self._enrolled_ids_cache
            return set()

    async def _find_student_row_in_kpi(self, getcourse_id: str) -> Optional[int]:
        """
        Находит строку с записью о студенте по GetCourse ID в листе "Общий список new".
        Использует кешированные данные таблицы.
        
        Args:
            getcourse_id: ID студента в GetCourse
            
        Returns:
            Номер строки или None если не найдено
        """
        try:
            all_data = await self._get_all_data_cached()
            
            # Ищем совпадение в первой колонке для строк начиная с 21
            import re
            for i in range(20, len(all_data)):
                if len(all_data[i]) > 0:
                    # Проверяем колонку A (результат формулы REGEXEXTRACT)
                    if all_data[i][0] == getcourse_id:
                        return i + 1  # +1 потому что индексация с 0, а строки с 1
                    
                    # Если в колонке A нет точного совпадения, проверяем колонку B (URL)
                    if len(all_data[i]) > 1 and getcourse_id in all_data[i][1]:
                        match = re.search(r'id/(\d+)', all_data[i][1])
                        if match and match.group(1) == getcourse_id:
                            return i + 1
            
            # Не нашли в кеше — попробуем свежие данные (если кеш не совсем свежий)
            import time
            if (time.time() - self._all_data_cache_time) > 5:
                all_data = await self._get_all_data_cached(force_refresh=True)
                for i in range(20, len(all_data)):
                    if len(all_data[i]) > 0:
                        if all_data[i][0] == getcourse_id:
                            return i + 1
                        if len(all_data[i]) > 1 and getcourse_id in all_data[i][1]:
                            match = re.search(r'id/(\d+)', all_data[i][1])
                            if match and match.group(1) == getcourse_id:
                                return i + 1
            
            logger.debug(f"Студент {getcourse_id} не найден в таблице KPI Sheets")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при поиске студента {getcourse_id} в KPI Sheets: {e}", exc_info=True)
            return None
    
    async def update_tracker_link(self, row_number: int, tracker_url: str) -> bool:
        """
        Обновляет ссылку на трекер студента в колонке F.
        
        Args:
            row_number: Номер строки
            tracker_url: URL трекера студента
            
        Returns:
            True если успешно
        """
        try:
            self.worksheet.update(f'F{row_number}', [[tracker_url]])
            logger.info(f"\u2705 \u0421\u0441\u044b\u043b\u043a\u0430 \u043d\u0430 \u0442\u0440\u0435\u043a\u0435\u0440 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0430 \u0432 \u0441\u0442\u0440\u043e\u043a\u0435 {row_number}")
            self.invalidate_cache()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении ссылки на трекер: {e}", exc_info=True)
            logger.error(f"Row number: {row_number}, Tracker URL: {tracker_url}")
            return False
    
    async def update_nocodb_link(self, row_number: int, nocodb_url: str) -> bool:
        """
        Обновляет ссылку на запись студента в NocoDB в колонке E.
        
        Args:
            row_number: Номер строки
            nocodb_url: URL записи студента в NocoDB
            
        Returns:
            True если успешно
        """
        try:
            self.worksheet.update(f'E{row_number}', [[nocodb_url]])
            logger.info(f"\u2705 \u0421\u0441\u044b\u043b\u043a\u0430 \u043d\u0430 NocoDB \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0430 \u0432 \u0441\u0442\u0440\u043e\u043a\u0435 {row_number}")
            self.invalidate_cache()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении ссылки на NocoDB: {e}", exc_info=True)
            logger.error(f"Row number: {row_number}, NocoDB URL: {nocodb_url}")
            return False
    
    async def update_chat_link(self, row_number: int, invite_link: str) -> bool:
        """
        Обновляет invite-ссылку на чат Telegram в колонке G.
        
        Args:
            row_number: Номер строки
            invite_link: Invite-ссылка на чат (формат https://t.me/+...)
            
        Returns:
            True если успешно
        """
        try:
            if not invite_link:
                logger.warning(f"Пустая invite-ссылка для строки {row_number}")
                return False
            
            self.worksheet.update(f'G{row_number}', [[invite_link]])
            logger.info(f"\u2705 Invite-\u0441\u0441\u044b\u043b\u043a\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0430 \u0432 \u0441\u0442\u0440\u043e\u043a\u0435 {row_number}: {invite_link}")
            self.invalidate_cache()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении invite-ссылки: {e}", exc_info=True)
            logger.error(f"Row number: {row_number}, Invite link: {invite_link}")
            return False
    
    async def update_or_sync_chat_link(self, getcourse_id: str, invite_link: str) -> bool:
        """
        Обновляет invite-ссылку в листе "Общий список new" (колонка G).
        
        Логика:
        1. Находит студента по getcourse_id
        2. Проверяет колонку G:
           - Если пусто → записывает invite_link
           - Если заполнено → сравнивает и перезаписывает при несовпадении
        
        Args:
            getcourse_id: ID студента в GetCourse
            invite_link: Invite-ссылка на чат
            
        Returns:
            True если успешно, False если студент не найден или ошибка
        """
        try:
            if not invite_link:
                logger.warning(f"Пустая invite-ссылка для студента {getcourse_id}")
                return False
            
            # 1. Находим строку студента
            row_number = await self._find_student_row_in_kpi(getcourse_id)
            
            if not row_number:
                logger.warning(f"Студент {getcourse_id} не найден в 'Общий список new'")
                return False
            
            # 2. Читаем текущее значение колонки G
            import asyncio
            existing_value = await asyncio.to_thread(
                self.worksheet.cell,
                row_number,
                7  # Колонка G = 7
            )
            existing_link = existing_value.value if existing_value else ''
            
            # 3. Проверяем логику
            if not existing_link or existing_link.strip() == '':
                # Пусто → записываем
                await asyncio.to_thread(
                    self.worksheet.update,
                    f'G{row_number}',
                    [[invite_link]]
                )
                logger.info(f"✅ Invite-ссылка добавлена для студента {getcourse_id} (строка {row_number})")
                return True
            
            elif existing_link.strip() != invite_link.strip():
                # Заполнено, но не совпадает → перезаписываем
                await asyncio.to_thread(
                    self.worksheet.update,
                    f'G{row_number}',
                    [[invite_link]]
                )
                logger.info(
                    f"✅ Invite-ссылка обновлена для студента {getcourse_id} (строка {row_number}):\n"
                    f"   Старая: {existing_link}\n"
                    f"   Новая: {invite_link}"
                )
                return True
            
            else:
                # Совпадает → ничего не делаем
                logger.info(f"ℹ️ Invite-ссылка для студента {getcourse_id} уже актуальна")
                return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении invite-ссылки для {getcourse_id}: {e}", exc_info=True)
            return False
    
    async def get_chat_link_by_getcourse_id(self, getcourse_id: str) -> Optional[str]:
        """
        Получает invite-ссылку из колонки G (столбец 7) листа "Общий список new" по GetCourse ID.
        
        Args:
            getcourse_id: ID студента в GetCourse
            
        Returns:
            Invite-ссылка или None если не найдена
        """
        try:
            # Находим строку студента
            row_number = await self._find_student_row_in_kpi(getcourse_id)
            
            if not row_number:
                logger.debug(f"Студент {getcourse_id} не найден в 'Общий список new'")
                return None
            
            # Читаем значение колонки G (столбец 7)
            existing_value = await asyncio.to_thread(
                self.worksheet.cell,
                row_number,
                7  # Колонка G = 7
            )
            existing_link = existing_value.value if existing_value else ''
            
            if existing_link and existing_link.strip() != '':
                logger.info(f"✅ Найдена invite-ссылка для студента {getcourse_id} в столбце G: {existing_link}")
                return existing_link.strip()
            else:
                logger.debug(f"Invite-ссылка для студента {getcourse_id} не заполнена в столбце G")
                return None
            
        except Exception as e:
            logger.error(f"Ошибка при получении invite-ссылки для {getcourse_id}: {e}", exc_info=True)
            return None
    
    async def create_student_tracker(self, student_data: Dict[str, Any]) -> Optional[str]:
        """
        Создает персональный трекер для студента (новый лист в таблице).
        
        Args:
            student_data: Данные студента
            
        Returns:
            URL трекера или None в случае ошибки
        """
        try:
            tracker_name = f"Трекер - {student_data['name']} ({student_data['getcourse_id']})"
            
            logger.info(f"Создание трекера: {tracker_name}")
            
            # TODO: Реализовать создание нового листа
            # Это будет добавлено в следующей итерации (Фаза 3)
            
            # Пока возвращаем заглушку
            tracker_url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}#gid=TODO"
            
            logger.warning("Создание трекеров будет реализовано в Фазе 3")
            return tracker_url
            
        except Exception as e:
            logger.error(f"Ошибка при создании трекера: {e}", exc_info=True)
            return None
    
    async def sync_dates_to_nocodb(self, getcourse_id: str, nocodb_integration) -> bool:
        """
        Синхронизирует даты из KPI Sheets в NocoDB.
        Читает даты из столбцов H, I, J и обновляет соответствующие поля в NocoDB.
        
        Args:
            getcourse_id: ID студента в GetCourse
            nocodb_integration: Экземпляр VipalinaNocoDBIntegration
            
        Returns:
            True если успешно
        """
        try:
            # Находим строку студента в KPI Sheets
            row_number = await self._find_student_row_in_kpi(getcourse_id)
            if not row_number:
                logger.warning(f"Студент {getcourse_id} не найден в KPI Sheets")
                return False
            
            # Читаем даты из колонок H, I, J
            dates_range = self.worksheet.get(f'H{row_number}:J{row_number}')[0]
            
            if len(dates_range) < 3:
                logger.warning(f"Не удалось прочитать даты для студента {getcourse_id}")
                return False
            
            training_start = dates_range[0] if len(dates_range) > 0 else ''
            support_end = dates_range[1] if len(dates_range) > 1 else ''
            profitability_end = dates_range[2] if len(dates_range) > 2 else ''
            
            # Пропускаем синхронизацию, если нет даты начала учебы
            if not training_start or training_start.strip() == '':
                logger.debug(f"Дата начала учебы еще не установлена для студента {getcourse_id}")
                return False
            
            # Находим студента в NocoDB
            student_record = await nocodb_integration.find_student_by_getcourse_id(getcourse_id)
            if not student_record:
                logger.warning(f"Студент {getcourse_id} не найден в NocoDB")
                return False
            
            record_id = student_record['id']
            
            # Обновляем даты в NocoDB
            # ВАЖНО: Названия полей должны соответствовать структуре NocoDB
            date_fields = {
                'Дата начала учебы': training_start,
                'Дата окончания поддержки': support_end,
                'Дата окончания окупаемости': profitability_end
            }
            
            # Удаляем пустые значения
            date_fields = {k: v for k, v in date_fields.items() if v and v.strip() != ''}
            
            if not date_fields:
                logger.debug(f"Нет дат для синхронизации для студента {getcourse_id}")
                return False
            
            # Обновляем запись
            update_result = await nocodb_integration.update_student_dates(record_id, date_fields)
            
            if update_result:
                logger.info(f"✅ Даты синхронизированы в NocoDB для студента {getcourse_id}")
                return True
            else:
                logger.warning(f"⚠️ Не удалось обновить даты в NocoDB для студента {getcourse_id}")
                return False
            
        except Exception as e:
            logger.error(f"Ошибка при синхронизации дат для {getcourse_id}: {e}", exc_info=True)
            return False


# Функция для быстрой инициализации
def create_kpi_sheets_integration() -> VipalinaKPISheetsIntegration:
    """
    Создает и возвращает экземпляр интеграции с KPI Sheets.
    
    Returns:
        VipalinaKPISheetsIntegration: Готовый к работе объект интеграции
    """
    return VipalinaKPISheetsIntegration()
