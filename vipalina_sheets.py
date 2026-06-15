"""
Интеграция с Google Sheets для таблицы "Випалина"
"""

import gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as UserCredentials
import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from config import (
    GOOGLE_SHEETS_CREDENTIALS_FILE, 
    GOOGLE_SHEETS_ID, 
    GOOGLE_SHEETS_VIPALINA_TAB,
    GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE
)
from async_sheets_wrapper import AsyncSheetsWrapper

logger = logging.getLogger('vipalina_telethon')


class VipalinaSheetIntegration:
    """
    Интеграция с Google Sheets для отслеживания VIP-студентов.
    Управляет таблицей "Випалина" с информацией о студентах.
    """
    
    def __init__(self):
        self.credentials_file = GOOGLE_SHEETS_CREDENTIALS_FILE
        self.service_account_file = GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE
        self.spreadsheet_id = GOOGLE_SHEETS_ID
        self.tab_name = GOOGLE_SHEETS_VIPALINA_TAB
        self.worksheet = None
        self._initialize_connection()
    
    def _initialize_connection(self):
        """Инициализирует подключение к Google Sheets"""
        try:
            from shared_gspread_client import get_shared_gspread_client
            gc = get_shared_gspread_client(self.service_account_file)
            spreadsheet = gc.open_by_key(self.spreadsheet_id)
            
            # Пытаемся открыть существующий лист или создаем новый
            try:
                self.worksheet = spreadsheet.worksheet(self.tab_name)
                logger.info(f"Подключен к существующему листу '{self.tab_name}'")
            except gspread.exceptions.WorksheetNotFound:
                self.worksheet = spreadsheet.add_worksheet(
                    title=self.tab_name,
                    rows=1000,
                    cols=20
                )
                logger.info(f"Создан новый лист '{self.tab_name}'")
                self._initialize_headers()
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации подключения к Google Sheets: {e}", exc_info=True)
            raise
    
    def _initialize_headers(self):
        """Инициализирует заголовки таблицы"""
        try:
            headers = [
                'GetCourse ID',           # A
                'Telegram ID',            # B
                'Chat ID',                # C
                'Имя студента',           # D
                'Курс',                   # E
                'Username',               # F
                'Менеджер ID',            # G
                'Менеджер Имя',           # H
                'Трекер',                 # I
                'Ссылка на чат',          # J
                'Дата создания чата',     # K
                'Статус',                 # L
                'Последнее обновление',   # M
                'Сегмент рассылок',       # N
                'Дата последнего контакта', # O
                'Выходит на связь?',      # P
                'Уведомление о пропаже',  # Q
                'Дата начала обучения',   # R (из трекера "📈 Статистика" C4)
                'Дата начала окупаемости', # S (из трекера "📈 Статистика" C10)
                'Окупить до'              # T (из трекера "📈 Статистика" C11)
            ]
            
            self.worksheet.update('A1:T1', [headers])
            
            # Форматируем заголовки (жирный шрифт)
            self.worksheet.format('A1:T1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })
            
            logger.info("Инициализированы заголовки таблицы 'Випалина'")
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации заголовков: {e}", exc_info=True)
    
    async def add_student_record(
        self,
        getcourse_id: str,
        telegram_id: Optional[int],
        chat_id: int,
        student_data: Dict[str, Any],
        manager_id: int,
        manager_name: str,
        tracker_url: str = "-",
        invite_link: str = "-",
        resolved_course_name: str = None  # Новое поле для правильного названия курса
    ) -> bool:
        """
        Добавляет запись о студенте в таблицу (асинхронно).
        
        Args:
            getcourse_id: ID студента в GetCourse
            telegram_id: Telegram ID студента
            chat_id: ID созданного группового чата
            student_data: Данные о студенте (name, course, username)
            manager_id: Telegram ID менеджера
            manager_name: Имя менеджера
            tracker_url: Ссылка на трекер студента (по умолчанию "-")
            invite_link: Invite-ссылка на чат (по умолчанию "-")
            
        Returns:
            True если запись добавлена успешно
        """
        try:
            # Проверяем, существует ли уже запись для этого студента
            existing_row = await self._find_student_row(getcourse_id)
            
            if existing_row:
                logger.info(f"Найдена существующая запись для студента {getcourse_id} в строке {existing_row}")
            else:
                logger.info(f"Студент {getcourse_id} не найден, будет создана новая запись")
            
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Извлекаем только имя (первое слово) из полного имени студента
            full_name = student_data.get('name', '')
            first_name = full_name.split()[0] if full_name else full_name
            
            row_data = [
                getcourse_id,
                str(telegram_id) if telegram_id else '-',
                str(chat_id) if chat_id else '-',
                first_name,  # Только имя, без фамилии
                resolved_course_name if resolved_course_name else student_data.get('course', '-'),  # Используем правильное название курса
                student_data.get('telegram_username', '-'),
                str(manager_id) if manager_id else '-',
                manager_name if manager_name else '-',
                tracker_url,  # Ссылка на трекер
                invite_link if invite_link else '-',  # Invite-ссылка на чат
                current_time,
                'Активен',
                current_time,
                '',  # Сегмент рассылок (заполняется вручную)
                '',  # Дата последнего контакта (O)
                '',  # Выходит на связь? (P) - будет формула
                '',  # Уведомление о пропаже (Q)
                '',  # Дата начала обучения (R) - заполнится из трекера
                '',  # Дата начала окупаемости (S) - заполнится из трекера
                ''   # Окупить до (T) - заполнится из трекера
            ]
            
            if existing_row:
                # Обновляем существующую запись (асинхронно), без сегмента и дат из трекера
                # Включаем invite_link (колонка J) и tracker_url (колонка I)
                await AsyncSheetsWrapper.run_sync(
                    self.worksheet.update,
                    f'A{existing_row}:J{existing_row}',
                    [row_data[:10]]  # Обновляем до колонки J (invite_link), без сегмента и дат из трекера
                )
                logger.info(f"Обновлена запись для студента {getcourse_id} в строке {existing_row}")
            else:
                # Добавляем новую запись (асинхронно)
                await AsyncSheetsWrapper.run_sync(
                    self.worksheet.append_row,
                    row_data
                )
                
                # Находим номер добавленной строки и добавляем формулу для колонки P
                new_row = await self._find_student_row(getcourse_id)
                if new_row:
                    formula = f'=IF(O{new_row}="";"-";IF(TODAY()-DATEVALUE(LEFT(O{new_row};10))<=3;"🟢 Активен";IF(TODAY()-DATEVALUE(LEFT(O{new_row};10))<=7;"🔵 Средне";IF(TODAY()-DATEVALUE(LEFT(O{new_row};10))<=14;"🟡 Редко";IF(TODAY()-DATEVALUE(LEFT(O{new_row};10))>30;"🔴 Пропал";"🟡 Редко")))))'
                    await AsyncSheetsWrapper.run_sync(
                        self.worksheet.update,
                        f'P{new_row}',
                        [[formula]],
                        value_input_option='USER_ENTERED'
                    )
                    
                    # Добавляем формулы IMPORTRANGE для дат обучения (R, S, T)
                    if tracker_url and tracker_url != '-':
                        await self._add_training_dates_formulas(new_row, tracker_url)
                
                logger.info(f"Добавлена новая запись для студента {getcourse_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении записи о студенте {getcourse_id}: {e}", exc_info=True)
            return False
    
    async def _find_student_row(self, getcourse_id: str) -> Optional[int]:
        """
        Находит строку с записью о студенте по GetCourse ID (асинхронно).
        
        Args:
            getcourse_id: ID студента в GetCourse
            
        Returns:
            Номер строки или None если не найдено
        """
        try:
            # Получаем все значения в первой колонке (GetCourse ID) асинхронно
            all_values = await AsyncSheetsWrapper.run_sync(
                self.worksheet.col_values,
                1
            )
            
            # Ищем совпадение (начиная со второй строки, т.к. первая - заголовки)
            for i, value in enumerate(all_values[1:], start=2):
                # Приводим к строке и убираем пробелы для надёжного сравнения
                if str(value).strip() == str(getcourse_id).strip():
                    return i
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при поиске студента {getcourse_id}: {e}", exc_info=True)
            return None
    
    async def _add_training_dates_formulas(self, row_number: int, tracker_url: str = None):
        """
        Добавляет формулы IMPORTRANGE для автоматического подтягивания дат из трекера.
        Формулы динамически берут ссылку из столбца I.
        
        Args:
            row_number: Номер строки в таблице
            tracker_url: Ссылка на трекер студента (не используется, параметр для совместимости)
        """
        try:
            # Формулы IMPORTRANGE для дат из трекера, берут URL из колонки I
            # R - Дата начала обучения (Лист "📈 Статистика", ячейка C4)
            # S - Дата начала окупаемости (Лист "📈 Статистика", ячейка C10)
            # T - Окупить до (Лист "📈 Статистика", ячейка C11)
            # БЕЗ ЕСЛИОШИБКА - чтобы Google Sheets показывал запрос доступа
            
            formula_start_date = f'=IMPORTRANGE(I{row_number}; "📈 Статистика!C4")'
            formula_breakeven_start = f'=IMPORTRANGE(I{row_number}; "📈 Статистика!C10")'
            formula_breakeven_deadline = f'=IMPORTRANGE(I{row_number}; "📈 Статистика!C11")'
            
            # Добавляем формулы в ячейки
            await AsyncSheetsWrapper.run_sync(
                self.worksheet.update,
                f'R{row_number}:T{row_number}',
                [[formula_start_date, formula_breakeven_start, formula_breakeven_deadline]],
                value_input_option='USER_ENTERED'
            )
            
            logger.info(f"✅ Добавлены формулы IMPORTRANGE с динамической ссылкой на I{row_number}")
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении формул IMPORTRANGE: {e}", exc_info=True)
    
    async def get_student_info(self, getcourse_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о студенте по GetCourse ID (асинхронно).
        
        Args:
            getcourse_id: ID студента в GetCourse
            
        Returns:
            Dict с данными студента или None
        """
        try:
            row_number = await self._find_student_row(getcourse_id)
            
            if not row_number:
                logger.info(f"Студент {getcourse_id} не найден в таблице")
                return None
            
            # Получаем данные из строки (асинхронно)
            row_data = await AsyncSheetsWrapper.run_sync(
                self.worksheet.row_values,
                row_number
            )
            
            # Проверяем, что данных достаточно
            if len(row_data) < 12:
                logger.warning(f"Недостаточно данных в строке {row_number}")
                return None
            
            student_info = {
                'getcourse_id': row_data[0],
                'telegram_id': int(row_data[1]) if row_data[1] and row_data[1] != '-' else None,
                'chat_id': int(row_data[2]) if row_data[2] and row_data[2] != '-' else None,
                'name': row_data[3],
                'course': row_data[4],
                'username': row_data[5],
                'manager_id': int(row_data[6]) if row_data[6] and row_data[6] != '-' else None,
                'manager_name': row_data[7],
                'tracker_url': row_data[8] if len(row_data) > 8 else '-',
                'invite_link': row_data[9] if len(row_data) > 9 else '-',
                'created_at': row_data[10] if len(row_data) > 10 else '',
                'status': row_data[11] if len(row_data) > 11 else '',
                'updated_at': row_data[12] if len(row_data) > 12 else ''
            }
            
            logger.info(f"Получена информация о студенте {getcourse_id}")
            return student_info
            
        except Exception as e:
            logger.error(f"Ошибка при получении информации о студенте {getcourse_id}: {e}", exc_info=True)
            return None
    
    async def get_student_info_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о студенте по Telegram ID (асинхронно).
        
        Args:
            telegram_id: Telegram ID студента
            
        Returns:
            Dict с данными студента или None
        """
        try:
            # Получаем все данные из таблицы (асинхронно)
            all_data = await AsyncSheetsWrapper.run_sync(
                self.worksheet.get_all_values
            )
            
            if len(all_data) <= 1:
                logger.info("В таблице нет данных о студентах")
                return None
            
            # Ищем студента по Telegram ID (колонка B, индекс 1)
            for row in all_data[1:]:  # Пропускаем заголовки
                if len(row) >= 2 and row[1] == str(telegram_id):
                    if len(row) < 13:
                        logger.warning(f"Недостаточно данных в строке")
                        return None
                    
                    student_info = {
                        'getcourse_id': row[0],
                        'telegram_id': int(row[1]) if row[1] and row[1] != '-' else None,
                        'chat_id': int(row[2]) if row[2] and row[2] != '-' else None,
                        'name': row[3],
                        'course': row[4],
                        'username': row[5],
                        'manager_id': int(row[6]) if row[6] and row[6] != '-' else None,
                        'manager_name': row[7],
                        'tracker_url': row[8] if len(row) > 8 else '-',
                        'invite_link': row[9] if len(row) > 9 else '-',
                        'created_at': row[10] if len(row) > 10 else '',
                        'status': row[11] if len(row) > 11 else '',
                        'updated_at': row[12] if len(row) > 12 else ''
                    }
                    
                    logger.info(f"Найден студент с Telegram ID {telegram_id}")
                    return student_info
            
            logger.info(f"Студент с Telegram ID {telegram_id} не найден в таблице")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при поиске студента по Telegram ID {telegram_id}: {e}", exc_info=True)
            return None
    
    async def update_student_status(self, getcourse_id: str, status: str) -> bool:
        """
        Обновляет статус студента (асинхронно).
        
        Args:
            getcourse_id: ID студента в GetCourse
            status: Новый статус
            
        Returns:
            True если статус обновлен успешно
        """
        try:
            row_number = await self._find_student_row(getcourse_id)
            
            if not row_number:
                logger.warning(f"Студент {getcourse_id} не найден в таблице")
                return False
            
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Обновляем статус и время обновления (асинхронно, параллельно)
            await AsyncSheetsWrapper.batch_run_sync([
                (self.worksheet.update, ([[status]],), {'range_name': f'L{row_number}'}),
                (self.worksheet.update, ([[current_time]],), {'range_name': f'M{row_number}'})
            ])
            
            logger.info(f"Обновлен статус студента {getcourse_id} на '{status}'")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса студента {getcourse_id}: {e}", exc_info=True)
            return False
    
    async def update_chat_id(self, getcourse_id: str, chat_id: int) -> bool:
        """
        Обновляет ID чата для студента (асинхронно).
        
        Args:
            getcourse_id: ID студента в GetCourse
            chat_id: ID группового чата
            
        Returns:
            True если ID обновлен успешно
        """
        try:
            row_number = await self._find_student_row(getcourse_id)
            
            if not row_number:
                logger.warning(f"Студент {getcourse_id} не найден в таблице")
                return False
            
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Обновляем chat_id и время обновления (асинхронно, параллельно)
            await AsyncSheetsWrapper.batch_run_sync([
                (self.worksheet.update, ([[str(chat_id)]],), {'range_name': f'C{row_number}'}),
                (self.worksheet.update, ([[current_time]],), {'range_name': f'L{row_number}'})
            ])
            
            logger.info(f"Обновлен chat_id студента {getcourse_id} на {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении chat_id студента {getcourse_id}: {e}", exc_info=True)
            return False
    
    async def get_all_active_students(self) -> List[Dict[str, Any]]:
        """
        Получает список всех активных студентов (асинхронно).
        
        Returns:
            List of Dict с данными студентов
        """
        try:
            # Получаем все данные из таблицы (асинхронно)
            all_data = await AsyncSheetsWrapper.run_sync(
                self.worksheet.get_all_values
            )
            
            if len(all_data) <= 1:
                logger.info("В таблице нет данных о студентах")
                return []
            
            # Пропускаем заголовки
            students = []
            for row in all_data[1:]:
                if len(row) >= 13 and row[11] == 'Активен':
                    student_info = {
                        'getcourse_id': row[0],
                        'telegram_id': int(row[1]) if row[1] and row[1] != '-' else None,
                        'chat_id': int(row[2]) if row[2] and row[2] != '-' else None,
                        'name': row[3],
                        'course': row[4],
                        'username': row[5],
                        'manager_id': int(row[6]) if row[6] and row[6] != '-' else None,
                        'manager_name': row[7],
                        'tracker_url': row[8] if len(row) > 8 else '-',
                        'invite_link': row[9] if len(row) > 9 else '-',
                        'created_at': row[10] if len(row) > 10 else '',
                        'status': row[11] if len(row) > 11 else '',
                        'updated_at': row[12] if len(row) > 12 else ''
                    }
                    students.append(student_info)
            
            logger.info(f"Получено {len(students)} активных студентов")
            return students
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка активных студентов: {e}", exc_info=True)
            return []
    
    async def get_broadcast_segments(self) -> Dict[int, str]:
        """
        Получает сегменты рассылок для всех активных чатов.
        
        Returns:
            Dict[int, str]: chat_id -> сегменты (например, "#чатботы, #лухари")
        """
        try:
            all_data = await AsyncSheetsWrapper.run_sync(
                self.worksheet.get_all_values
            )
            
            if len(all_data) <= 1:
                return {}
            
            result = {}
            for row in all_data[1:]:  # Пропускаем заголовки
                # Проверяем наличие chat_id (колонка C, индекс 2)
                if len(row) >= 3 and row[2] and row[2] != '-':
                    try:
                        chat_id = int(row[2])
                        # Сегмент рассылок в колонке N (индекс 13)
                        segment = row[13].strip() if len(row) > 13 else ''
                        result[chat_id] = segment
                    except (ValueError, IndexError):
                        continue
            
            logger.info(f"Получено {len(result)} чатов для рассылок")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении сегментов рассылок: {e}", exc_info=True)
            return {}
    
    async def clear_broadcast_segment(self, chat_id: int) -> bool:
        """
        Деактивирует чат: очищает сегмент рассылок (N) и устанавливает статус "Неактивен" (L).
        
        Args:
            chat_id: ID чата
            
        Returns:
            True если успешно
        """
        try:
            all_data = await AsyncSheetsWrapper.run_sync(
                self.worksheet.get_all_values
            )
            
            if len(all_data) <= 1:
                return False
            
            # Ищем строку с этим chat_id
            for row_idx, row in enumerate(all_data[1:], start=2):  # Начинаем с 2 (пропускаем заголовки)
                if len(row) >= 3 and row[2] and row[2] != '-':
                    try:
                        row_chat_id = int(row[2])
                        if row_chat_id == chat_id:
                            # Устанавливаем статус "Неактивен" в колонке L (12-я)
                            await AsyncSheetsWrapper.run_sync(
                                self.worksheet.update,
                                f'L{row_idx}',
                                [['Неактивен']]
                            )
                            # Очищаем сегмент рассылок в колонке N (14-я)
                            await AsyncSheetsWrapper.run_sync(
                                self.worksheet.update,
                                f'N{row_idx}',
                                [['']]
                            )
                            logger.info(f"Чат {chat_id} деактивирован: статус=Неактивен, сегмент очищен")
                            return True
                    except ValueError:
                        continue
            
            logger.warning(f"Чат {chat_id} не найден в таблице")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при деактивации чата: {e}", exc_info=True)
            return False
    
    async def update_tracker_url_by_getcourse_id(self, getcourse_id: str, tracker_url: str) -> bool:
        """
        Обновляет ссылку на трекер для студента по GetCourse ID.
        
        Args:
            getcourse_id: ID студента в GetCourse
            tracker_url: Новая ссылка на трекер
            
        Returns:
            True если успешно обновлено
        """
        try:
            row_number = await self._find_student_row(getcourse_id)
            
            if not row_number:
                logger.warning(f"Студент {getcourse_id} не найден в таблице Випалина")
                return False
            
            # Обновляем трекер (колонка I, 9-я колонка)
            await AsyncSheetsWrapper.run_sync(
                self.worksheet.update,
                f'I{row_number}',
                [[tracker_url]]
            )
            
            # Обновляем формулы IMPORTRANGE для дат обучения
            try:
                await self._add_training_dates_formulas(row_number, tracker_url)
                logger.info(f"Обновлена ссылка на трекер и формулы IMPORTRANGE для студента {getcourse_id}")
            except Exception as formula_error:
                logger.warning(f"⚠️ Трекер обновлён, но не удалось добавить формулы IMPORTRANGE: {formula_error}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении трекера для {getcourse_id}: {e}", exc_info=True)
            return False
    
    async def update_chat_id_if_missing(self, getcourse_id: str, telegram_id=None, chat_id=None) -> bool:
        """
        Заполняет колонки B (telegram_id) и C (chat_id) если они пустые или '-'.
        Вызывается при /createtracker когда уже известен активный чат студента.
        
        Returns:
            True если хотя бы одно поле было обновлено
        """
        if not telegram_id and not chat_id:
            return False
        try:
            row_number = await self._find_student_row(getcourse_id)
            if not row_number:
                return False
            
            row_data = await AsyncSheetsWrapper.run_sync(
                self.worksheet.row_values,
                row_number
            )
            
            updates = []
            # Колонка B (индекс 1) — telegram_id
            if telegram_id:
                current_b = row_data[1] if len(row_data) > 1 else ''
                if not current_b or current_b == '-':
                    updates.append(AsyncSheetsWrapper.run_sync(
                        self.worksheet.update,
                        f'B{row_number}',
                        [[str(telegram_id)]]
                    ))
            # Колонка C (индекс 2) — chat_id
            if chat_id:
                current_c = row_data[2] if len(row_data) > 2 else ''
                if not current_c or current_c == '-':
                    updates.append(AsyncSheetsWrapper.run_sync(
                        self.worksheet.update,
                        f'C{row_number}',
                        [[str(chat_id)]]
                    ))
            
            if updates:
                for upd in updates:
                    await upd
                logger.info(f"✅ Обновлены B/C для студента {getcourse_id}: telegram_id={telegram_id}, chat_id={chat_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка update_chat_id_if_missing для {getcourse_id}: {e}", exc_info=True)
            return False

    async def update_last_contact(self, chat_id: int) -> bool:
        """
        Обновляет дату последнего контакта студента (колонка O).
        
        Args:
            chat_id: ID чата
            
        Returns:
            True если успешно
        """
        try:
            all_data = await AsyncSheetsWrapper.run_sync(
                self.worksheet.get_all_values
            )
            
            if len(all_data) <= 1:
                return False
            
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Ищем строку с этим chat_id
            for row_idx, row in enumerate(all_data[1:], start=2):
                if len(row) >= 3 and row[2] and row[2] != '-':
                    try:
                        row_chat_id = int(row[2])
                        if row_chat_id == chat_id:
                            # Обновляем дату последнего контакта в колонке O (15-я)
                            await AsyncSheetsWrapper.run_sync(
                                self.worksheet.update,
                                f'O{row_idx}',
                                [[current_time]]
                            )
                            return True
                    except ValueError:
                        continue
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении даты последнего контакта: {e}", exc_info=True)
            logger.error(f"Chat ID: {chat_id}")
            return False
    
    async def get_missing_students(self, days_threshold: int = 30) -> List[Dict[str, Any]]:
        """
        Получает список "пропавших" студентов, которым нужно отправить уведомление.
        Условия: >30 дней без контакта И (нет уведомления ИЛИ прошло 7+ дней).
        
        Args:
            days_threshold: Количество дней без контакта
            
        Returns:
            Список студентов с информацией и row_idx
        """
        try:
            all_data = await AsyncSheetsWrapper.run_sync(
                self.worksheet.get_all_values
            )
            
            if len(all_data) <= 1:
                return []
            
            missing_students = []
            today = datetime.now()
            
            for row_idx, row in enumerate(all_data[1:], start=2):  # Пропускаем заголовки
                # Проверяем, что есть данные и статус не "Неактивен"
                if len(row) < 15:
                    continue
                
                status = row[11] if len(row) > 11 else ''
                if status == 'Неактивен':
                    continue
                
                last_contact = row[14] if len(row) > 14 else ''  # Колонка O
                if not last_contact:
                    continue
                
                try:
                    # Парсим дату последнего контакта (формат: YYYY-MM-DD HH:MM:SS)
                    last_date = datetime.strptime(last_contact[:10], '%Y-%m-%d')
                    days_since = (today - last_date).days
                    
                    if days_since <= days_threshold:
                        continue
                    
                    # Проверяем дату последнего уведомления (колонка Q, индекс 16)
                    last_notification = row[16] if len(row) > 16 else ''
                    
                    should_notify = False
                    if not last_notification:
                        # Ещё не уведомляли
                        should_notify = True
                    else:
                        # Проверяем, прошло ли 7+ дней
                        try:
                            notif_date = datetime.strptime(last_notification[:10], '%Y-%m-%d')
                            days_since_notif = (today - notif_date).days
                            if days_since_notif >= 7:
                                should_notify = True
                        except ValueError:
                            should_notify = True
                    
                    if should_notify:
                        missing_students.append({
                            'row_idx': row_idx,
                            'getcourse_id': row[0],
                            'telegram_id': int(row[1]) if row[1] and row[1] != '-' else None,
                            'chat_id': int(row[2]) if row[2] and row[2] != '-' else None,
                            'name': row[3],
                            'course': row[4],
                            'manager_id': int(row[6]) if row[6] and row[6] != '-' else None,
                            'manager_name': row[7],
                            'last_contact': last_contact,
                            'days_since': days_since,
                            'invite_link': row[9] if len(row) > 9 else '-'
                        })
                except (ValueError, IndexError):
                    continue
            
            logger.info(f"Найдено {len(missing_students)} пропавших студентов для уведомления")
            return missing_students
            
        except Exception as e:
            logger.error(f"Ошибка при получении пропавших студентов: {e}", exc_info=True)
            return []
    
    async def mark_notification_sent(self, row_idx: int) -> bool:
        """
        Записывает дату отправки уведомления о пропаже (колонка Q).
        
        Args:
            row_idx: Номер строки
            
        Returns:
            True если успешно
        """
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await AsyncSheetsWrapper.run_sync(
                self.worksheet.update,
                f'Q{row_idx}',
                [[current_time]]
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка при записи даты уведомления: {e}", exc_info=True)
            return False
    
    async def update_training_dates(self, getcourse_id: str, tracker_url: str) -> bool:
        """
        Обновляет даты начала обучения из трекера студента.
        Извлекает данные из листа "📈 Статистика" трекера:
        - C4: Дата начала обучения
        - C10: Дата начала окупаемости
        - C11: Окупить до
        
        Args:
            getcourse_id: ID студента
            tracker_url: Ссылка на трекер
            
        Returns:
            True если успешно
        """
        try:
            import re
            
            # Извлекаем ID таблицы из URL
            match = re.search(r'/d/([a-zA-Z0-9-_]+)', tracker_url)
            if not match:
                logger.warning(f"Неверный формат URL трекера: {tracker_url}")
                return False
            
            tracker_id = match.group(1)
            
            # Открываем трекер используя сервисный аккаунт
            from shared_gspread_client import get_shared_gspread_client
            gc = get_shared_gspread_client(self.service_account_file)
            
            try:
                tracker = gc.open_by_key(tracker_id)
            except Exception as e:
                logger.warning(f"Не удалось открыть трекер {tracker_id}: {e}")
                return False
            
            # Читаем данные с листа "📈 Статистика"
            try:
                stats_sheet = tracker.worksheet('📈 Статистика')
                
                start_date = stats_sheet.acell('C4').value or '-'
                payback_start = stats_sheet.acell('C10').value or '-'
                payback_due = stats_sheet.acell('C11').value or '-'
                
                logger.debug(f"Получены даты из трекера {tracker_id}: начало={start_date}, окупаемость={payback_start}, до={payback_due}")
            except gspread.exceptions.WorksheetNotFound:
                logger.warning(f"Лист '📈 Статистика' не найден в трекере {tracker_id}")
                return False
            except Exception as e:
                logger.error(f"Ошибка при чтении данных из трекера {tracker_id}: {e}", exc_info=True)
                return False
            
            # Находим строку студента
            row_number = await self._find_student_row(getcourse_id)
            if not row_number:
                logger.warning(f"Студент {getcourse_id} не найден в таблице")
                return False
            
            # Обновляем колонки R, S, T
            try:
                await AsyncSheetsWrapper.run_sync(
                    self.worksheet.update,
                    f'R{row_number}:T{row_number}',
                    [[start_date, payback_start, payback_due]]
                )
                
                logger.info(f"Обновлены даты обучения для {getcourse_id}: начало={start_date}, окупаемость={payback_start}, до={payback_due}")
                return True
            except Exception as e:
                logger.error(f"Ошибка при обновлении дат обучения в таблице для студента {getcourse_id}: {e}", exc_info=True)
                return False
            
        except Exception as e:
            logger.error(f"Критическая ошибка при обновлении дат обучения для студента {getcourse_id}: {e}", exc_info=True)
            return False
    
    async def get_all_students_with_trackers(self):
        """
        Получает список всех студентов, у которых есть трекеры.
        
        Returns:
            List[Dict]: Список студентов с трекерами
        """
        try:
            # Получаем все данные из листа
            all_values = await AsyncSheetsWrapper.run_sync(
                self.worksheet.get_all_values
            )
            
            if len(all_values) <= 1:
                logger.info("В таблице нет данных о студентах")
                return []
            
            headers = all_values[0]
            data_rows = all_values[1:]
            
            # Находим индексы нужных колонок
            getcourse_id_idx = headers.index('GetCourse ID') if 'GetCourse ID' in headers else 0
            tracker_idx = headers.index('Трекер') if 'Трекер' in headers else 8  # Колонка I по умолчанию
            created_at_idx = headers.index('Дата создания чата') if 'Дата создания чата' in headers else 10  # Колонка K по умолчанию
            
            students = []
            for i, row in enumerate(data_rows):
                try:
                    if len(row) > max(getcourse_id_idx, tracker_idx, created_at_idx):
                        getcourse_id = row[getcourse_id_idx] if len(row) > getcourse_id_idx else ''
                        tracker_url = row[tracker_idx] if len(row) > tracker_idx else ''
                        created_at = row[created_at_idx] if len(row) > created_at_idx else ''
                        
                        # Добавляем только студентов с трекерами
                        if getcourse_id and tracker_url and tracker_url != '-':
                            students.append({
                                'getcourse_id': getcourse_id,
                                'tracker_url': tracker_url,
                                'created_at': created_at
                            })
                except Exception as e:
                    logger.warning(f"Ошибка при обработке строки {i+2} данных студента: {e}")
                    continue
            
            logger.info(f"Найдено {len(students)} студентов с трекерами")
            return students
            
        except Exception as e:
            logger.error(f"Критическая ошибка при получении студентов с трекерами: {e}", exc_info=True)
            return []
