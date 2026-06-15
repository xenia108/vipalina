#!/usr/bin/env python3
"""
Менеджер создания листов курсов в трекерах тарифов.
Работает с Google Sheets API для создания листов на основе выбора в G5:G10.
"""

import gspread
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
import logging
import re
from typing import Dict, List, Optional, Any
from config import USER_OAUTH_TOKEN_PATH

logger = logging.getLogger('vipalina_telethon')


class TariffTrackerManager:
    """
    Управление трекерами для тарифов.
    Создает листы курсов на основе выбора VIP-менеджера.
    """
    
    # ID таблицы ГАНТ с уроками
    GANT_SHEET_ID = '1iJyzqiGGCgrtDnbV-zqjY08P8Vq8HfOElwz7o4S743w'
    
    def __init__(self, credentials_path: str = 'vipalina_google_service_account.json'):
        """Инициализация"""
        self.credentials_path = credentials_path
        self.sheets_client = None
        self.drive_service = None
        self._authorize()
    
    def _authorize(self):
        """Авторизация в Google Sheets и Drive API"""
        try:
            scope = [
                'https://www.googleapis.com/auth/drive',
                'https://www.googleapis.com/auth/spreadsheets'
            ]
            
            creds = None
            
            # Пытаемся User OAuth (vipzerocoder) для копирования
            try:
                if USER_OAUTH_TOKEN_PATH:
                    creds = Credentials.from_authorized_user_file(USER_OAUTH_TOKEN_PATH, scope)
                    logger.info("✅ Авторизация через User OAuth (Tariff Tracker Manager)")
            except Exception as e:
                logger.warning(f"⚠️ User OAuth недоступен: {e}")
            
            # Fallback на Service Account
            if creds is None:
                creds = ServiceAccountCredentials.from_service_account_file(
                    self.credentials_path, scopes=scope
                )
                logger.info("✅ Авторизация через Service Account (Tariff Tracker Manager)")
            
            self.drive_service = build('drive', 'v3', credentials=creds)
            self.sheets_client = gspread.authorize(creds)
            
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации Tariff Tracker Manager: {e}")
            raise
    
    def create_course_sheets(self, tracker_url: str) -> Dict[str, Any]:
        """
        Создает листы курсов для трекера тарифа.
        Читает выбранные курсы из ячеек G5:G10 на листе "📈 Статистика".
        
        Args:
            tracker_url: URL или ID трекера тарифа
            
        Returns:
            {
                'success': bool,
                'tracker_id': str,
                'tracker_url': str,
                'total_courses': int,
                'created_sheets': List[str],
                'skipped_sheets': List[str],
                'errors': List[str]
            }
        """
        try:
            # Извлекаем ID из URL
            tracker_id = self._extract_tracker_id(tracker_url)
            logger.info(f"📋 Обработка трекера тарифа: {tracker_id}")
            
            # Открываем трекер
            tracker = self.sheets_client.open_by_key(tracker_id)
            
            # Находим главный лист "📈 Статистика" (ранее "Инфо о программе")
            main_sheet = None
            for sheet in tracker.worksheets():
                if sheet.title in ["📈 Статистика", "Инфо о программе"]:  # Поддержка обоих названий
                    main_sheet = sheet
                    break
            
            if not main_sheet:
                return {
                    'success': False,
                    'error': 'Не найден лист "📈 Статистика" или "Инфо о программе". Это трекер тарифа?'
                }
            
            # Читаем выбранные курсы из G5:G10
            selected_courses = main_sheet.range('G5:G10')
            course_names = [cell.value for cell in selected_courses if cell.value]
            
            if not course_names:
                return {
                    'success': False,
                    'error': 'Не выбрано ни одного курса в ячейках G5:G10'
                }
            
            logger.info(f"📚 Выбрано курсов: {len(course_names)}")
            for idx, course in enumerate(course_names, 1):
                logger.info(f"   {idx}. {course}")
            
            # Получаем конфигурацию курсов
            config_sheet = None
            for sheet in tracker.worksheets():
                if sheet.title == "⚙️ Конфигурация":
                    config_sheet = sheet
                    break
            
            if not config_sheet:
                return {
                    'success': False,
                    'error': 'Не найден лист "⚙️ Конфигурация"'
                }
            
            # Читаем данные конфигурации (A4:H100) - включаем столбец A с названиями курсов
            config_data = config_sheet.get('A4:H100')
            
            # Создаем словарь курсов {название: данные}
            courses_config = {}
            for row in config_data:
                if len(row) >= 8:  # Минимум 8 столбцов (A-H)
                    course_name = row[0]  # A - название
                    if course_name:
                        courses_config[course_name] = {
                            'name': course_name,
                            'gant_sheet': row[5] if len(row) > 5 else '',  # F - тег ГАНТ
                            'lesson_count': row[1] if len(row) > 1 else 0,  # B - уроки
                            'access_months': row[2] if len(row) > 2 else 0,  # C - доступ
                            'curator_months': row[3] if len(row) > 3 else 0,  # D - куратор
                            'vip_months': row[4] if len(row) > 4 else 0,  # E - VIP
                            'program_type': row[7] if len(row) > 7 else ''  # H - тип программы
                        }
            
            # Создаем листы для каждого выбранного курса
            created_sheets = []
            skipped_sheets = []
            errors = []
            
            # Находим лист-шаблон "📚 Доп. модули" (основной шаблон для всех курсов)
            template_sheet = None
            for sheet in tracker.worksheets():
                if sheet.title == "📚 Доп. модули":
                    template_sheet = sheet
                    break
            
            # Проверяем наличие шаблона
            if not template_sheet:
                return {
                    'success': False,
                    'error': 'Не найден лист-шаблон "📚 Доп. модули" в трекере тарифа'
                }
            
            # Обрабатываем каждый курс
            for idx, course_name in enumerate(course_names):
                row_index = 5 + idx  # G5 = строка 5, G6 = строка 6, и т.д.
                
                try:
                    result = self._create_course_sheet(
                        tracker=tracker,
                        template_sheet=template_sheet,
                        course_name=course_name,
                        course_config=courses_config.get(course_name),
                        main_sheet=main_sheet,
                        row_index=row_index
                    )
                    
                    if result['created']:
                        created_sheets.append(course_name)
                    else:
                        skipped_sheets.append(course_name)
                    
                except Exception as e:
                    error_msg = f"Ошибка при создании листа для '{course_name}': {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            # Формируем результат
            return {
                'success': True,
                'tracker_id': tracker_id,
                'tracker_url': f'https://docs.google.com/spreadsheets/d/{tracker_id}',
                'total_courses': len(course_names),
                'created_sheets': created_sheets,
                'skipped_sheets': skipped_sheets,
                'errors': errors
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания листов курсов: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_course_sheet(
        self,
        tracker,
        template_sheet,
        course_name: str,
        course_config: Optional[Dict],
        main_sheet,
        row_index: int
    ) -> Dict[str, bool]:
        """
        Создает лист для одного курса.
        
        Returns:
            {'created': bool} - True если создан новый, False если уже существовал
        """
        sheet_name = f"📚 {course_name}"
        
        # Проверяем, существует ли уже такой лист
        existing_sheet = None
        for sheet in tracker.worksheets():
            if sheet.title == sheet_name:
                existing_sheet = sheet
                break
        
        if existing_sheet:
            logger.info(f"⏭️ Лист уже существует: {sheet_name}")
            # Обновляем формулы прогресса (на случай если они были очищены)
            self._update_progress_formulas(main_sheet, row_index, course_name)
            return {'created': False}
        
        # Проверяем, что это курс, а не тариф
        if course_config and course_config.get('program_type') in ['Бандл', 'Абонемент', 'Премиум']:
            logger.warning(f"⚠️ Пропущен тариф (не курс): {course_name}")
            return {'created': False}
        
        logger.info(f"📋 Создание листа: {sheet_name}")
        new_sheet = template_sheet.duplicate(new_sheet_name=sheet_name)
        
        # Увеличиваем размер листа до 100 строк и 26 столбцов (Z), чтобы иметь доступ к ячейке Z1
        try:
            new_sheet.resize(100, 26)  # 100 строк, 26 столбцов (A-Z)
            logger.info("✅ Размер листа увеличен до 100x26")
        except Exception as resize_error:
            logger.warning(f"⚠️ Ошибка при изменении размера листа: {resize_error}")
        
        # Настраиваем IMPORTRANGE для загрузки уроков из ГАНТ
        # Ищем строку курса в листе "⚙️ Конфигурация" (A4:A) и подставляем тег из столбца F
        gant_row = None
        try:
            config_sheet = None
            for sheet in tracker.worksheets():
                if sheet.title == "⚙️ Конфигурация":
                    config_sheet = sheet
                    break

            if config_sheet:
                course_names_column = config_sheet.col_values(1)  # столбец A
                for idx, cell_value in enumerate(course_names_column, start=1):
                    if idx >= 4 and cell_value == course_name:
                        gant_row = idx
                        logger.info(f"✅ Курс '{course_name}' найден в '⚙️ Конфигурация' на строке {gant_row}")
                        break

            if gant_row:
                # 1. Заголовки в первой строке
                headers = [[
                    "Номер урока",
                    "Название урока",
                    "Формат проведения",
                    "Урок сдан"
                ]]
                new_sheet.update('A1:D1', headers, value_input_option='USER_ENTERED')

                # 2. Берем формулу из A2 (из шаблона) и заменяем F2 на F{gant_row}
                current_formula = new_sheet.acell('A2').value
                if current_formula:
                    new_ref = f"F{gant_row}"
                    new_formula = current_formula.replace("F2", new_ref)
                    new_sheet.update('A2', [[new_formula]], value_input_option='USER_ENTERED')
                    logger.info(f"✅ Формула IMPORTRANGE обновлена для курса '{course_name}' (ссылка на F{gant_row})")
                else:
                    logger.warning(f"⚠️ В листе '{sheet_name}' ячейка A2 пуста, формулу IMPORTRANGE обновить нельзя")
            else:
                logger.warning(f"⚠️ Курс '{course_name}' не найден в листе '⚙️ Конфигурация' (A4:A)")
        except Exception as e:
            logger.error(f"❌ Ошибка при настройке формулы IMPORTRANGE для курса '{course_name}': {e}")
        
        # 3. Формула проверки ДЗ в D2
        check_formula = '=IF(B2<>"";IF(COUNTIF(\'📊 Сданные ДЗ\'!D:D;B2)>0;TRUE;FALSE);"")'  
        new_sheet.update('D2', [[check_formula]], value_input_option='USER_ENTERED')
                
        # 4. Добавляем чекбоксы в столбец D
        sheet_id = new_sheet.id
        checkbox_request = {
            "requests": [
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,  # Строка 2 (0-based)
                            "endRowIndex": 500,
                            "startColumnIndex": 3,  # Столбец D
                            "endColumnIndex": 4
                        },
                        "rule": {
                            "condition": {
                                "type": "BOOLEAN"
                            },
                            "showCustomUi": True,
                            "strict": False
                        }
                    }
                }
            ]
        }
        tracker.batch_update(checkbox_request)
                
        logger.info(f"✅ Добавлена формула IMPORTRANGE и проверка ДЗ для строки G{row_index}")
        
        # Обновляем формулы прогресса на главном листе
        self._update_progress_formulas(main_sheet, row_index, course_name)
        
        # Получаем тип программы из конфигурации
        program_type = course_config.get('program_type') if course_config else None
        
        # Для всех типов тарифов (subscription, bundle, premium) лист "📚 Доп. модули" 
        # остается видимым для создания листов курсов
        # if program_type == 'bundle':
        #     try:
        #         hide_request = {
        #             "requests": [
        #                 {
        #                     "updateSheetProperties": {
        #                         "properties": {
        #                             "sheetId": template_sheet.id,
        #                             "hidden": True
        #                         },
        #                         "fields": "hidden"
        #                     }
        #                 }
        #             ]
        #         }
        #         tracker.batch_update(hide_request)
        #         logger.info("✅ Шаблонный лист '📚 Доп. модули' скрыт для бандла")
        #     except Exception as e:
        #         logger.warning(f"⚠️ Не удалось скрыть шаблонный лист: {e}")
        # else:
        logger.info("ℹ️ Шаблонный лист '📚 Доп. модули' остается видимым для всех типов тарифов")
        
        logger.info(f"✅ Лист создан: {sheet_name}")
        return {'created': True}
    
    def _update_progress_formulas(self, main_sheet, row_index: int, course_name: str):
        """Обновляет формулы прогресса в строке (H, I, J) с проверкой на текстовые значения"""
        # H - Сдано уроков (количество TRUE в столбце D)
        # Добавляем проверку ISNUMBER для обработки текстовых значений
        formula_done = f'=IF(G{row_index}<>"";IF(ISNUMBER(INDIRECT("\'📚 "&G{row_index}&"\'!A2"));COUNTIF(INDIRECT("\'📚 "&G{row_index}&"\'!D:D");TRUE);"-");"-")'
        main_sheet.update(f'H{row_index}', [[formula_done]], value_input_option='USER_ENTERED')
        
        # I - Всего уроков
        # Добавляем проверку ISNUMBER для обработки текстовых значений
        formula_total = f'=IF(G{row_index}<>"";IF(ISNUMBER(INDIRECT("\'📚 "&G{row_index}&"\'!A2"));COUNTA(INDIRECT("\'📚 "&G{row_index}&"\'!A:A"))-1;"-");"-")'
        main_sheet.update(f'I{row_index}', [[formula_total]], value_input_option='USER_ENTERED')
        
        # J - Процент
        # Добавляем проверку ISNUMBER для обработки текстовых значений
        formula_percent = f'=IF(AND(G{row_index}<>"";I{row_index}<>"-";ISNUMBER(I{row_index}));TEXT(H{row_index}/I{row_index};"0%");IF(AND(G{row_index}<>"";NOT(ISNUMBER(I{row_index})));I{row_index};"-"))'
        main_sheet.update(f'J{row_index}', [[formula_percent]], value_input_option='USER_ENTERED')
        
        logger.info(f"✅ Обновлены формулы прогресса для строки {row_index} с проверкой текстовых значений")
    
    def _extract_tracker_id(self, tracker_url_or_id: str) -> str:
        """Извлекает ID трекера из URL или возвращает ID как есть"""
        # Если это уже ID (без слешей и точек)
        if '/' not in tracker_url_or_id and '.' not in tracker_url_or_id:
            return tracker_url_or_id
        
        # Извлекаем ID из URL
        match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', tracker_url_or_id)
        if match:
            return match.group(1)
        
        # Если не удалось извлечь, возвращаем как есть
        return tracker_url_or_id
