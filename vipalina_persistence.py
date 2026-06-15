import logging
import typing
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

from config import (
    VIPALINA_LOGS_SPREADSHEET_ID
)

# Для персистенции используем сервисный аккаунт
PERSISTENCE_CREDENTIALS_FILE = "vipalina_google_service_account.json"

# Названия листов (соответствуют реальным названиям в Google Sheets)
SHEET_CHAT_TO_STUDENT = "Chat_To_Student"
SHEET_STUDENTS_DATA = "Students_Data"
SHEET_MANAGER_ASSIGNMENTS = "Manager_Assignments"
SHEET_QUEUE_STATE = "Queue_State"
SHEET_ACTIVE_SLA = "Active_SLA_Requests"
SHEET_ONBOARDING_PROGRESS = "Onboarding_Progress"
SHEET_SYSTEM_EVENTS = "System_Events"
SHEET_STUDENT_MESSAGES = "Student_Messages"
SHEET_PENDING_CORRECTIONS = "Pending_Corrections"

logger = logging.getLogger('vipalina_persistence')


class VipalinaPersistence:
    """
    Модуль персистенции - сохраняет все runtime-состояние в Google Sheets.
    Реализует паттерн Singleton.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VipalinaPersistence, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.gc = None
            self.spreadsheet = None
            self.worksheets = {}
            self._initialized = True
            self.telethon_client = None  # Будет установлен внешне
            self.vip_head_id = None  # Будет установлен внешне
    
    def set_notification_channel(self, client, vip_head_id: int):
        """
        Устанавливает Telethon клиент для уведомлений об ошибках.
        
        Args:
            client: Telethon клиент
            vip_head_id: Telegram ID руководителя VIP-отдела
        """
        self.telethon_client = client
        self.vip_head_id = vip_head_id
    
    async def _notify_persistence_error(self, operation: str, details: str):
        """
        Отправляет уведомление руководителю о сбое персистенции.
        
        Args:
            operation: Описание операции (например, "Chat_To_Student")
            details: Детали (например, "chat_id=123, getcourse_id=456")
        """
        if not self.telethon_client or not self.vip_head_id:
            return
        
        try:
            message = (
                f"⚠️ **Персистенция недоступна**\n\n"
                f"Не удалось сохранить: **{operation}**\n"
                f"{details}\n\n"
                f"🚨 Данные могут быть потеряны при перезапуске бота.\n"
                f"Проверьте доступ к Google Sheets \"\u041bо\u0433\u0438 \u0412\u0438\u043f\u0430\u043b\u0438\u043d\u0430\"."
            )
            await self.telethon_client.send_message(self.vip_head_id, message)
            logger.info(f"✉️ Уведомление о сбое персистенции ({operation}) отправлено")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о персистенции: {e}")
    
    def _get_credentials(self):
        """Получает учетные данные сервисного аккаунта"""
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        return Credentials.from_service_account_file(
            PERSISTENCE_CREDENTIALS_FILE,  # Используем правильный файл учетных данных
            scopes=scopes
        )
    
    def initialize(self) -> bool:
        """
        Инициализирует подключение к Google Sheets и создает необходимые листы.
        
        Returns:
            True если инициализация успешна
        """
        try:
            logger.info("Инициализация VipalinaPersistence...")
            
            from shared_gspread_client import get_shared_gspread_client
            credentials = self._get_credentials()
            self.gc = get_shared_gspread_client(PERSISTENCE_CREDENTIALS_FILE)
            self.spreadsheet = self.gc.open_by_key(VIPALINA_LOGS_SPREADSHEET_ID)
            
            # Создаем/получаем все необходимые листы
            self._ensure_sheet_exists(SHEET_CHAT_TO_STUDENT, [
                "chat_id", "getcourse_id", "student_name", "invite_link", "created_at", "updated_at"
            ])
            
            self._ensure_sheet_exists(SHEET_STUDENTS_DATA, [
                "getcourse_id", "name", "email", "phone", "course", 
                "telegram_username", "telegram_id", "getcourse_url",
                "is_test_student", "created_at", "updated_at"
            ])
            
            self._ensure_sheet_exists(SHEET_MANAGER_ASSIGNMENTS, [
                "getcourse_id", "manager_id", "manager_name", "course_tag",
                "status", "student_name", "student_telegram", "student_telegram_id",
                "created_at", "updated_at"
            ])
            
            self._ensure_sheet_exists(SHEET_QUEUE_STATE, [
                "queue_type", "current_index", "updated_at"
            ])
            
            self._ensure_sheet_exists(SHEET_ACTIVE_SLA, [
                "chat_id", "student_id", "student_name", "request_text",
                "request_time", "is_working_hours", "created_at"
            ])
            
            self._ensure_sheet_exists(SHEET_ONBOARDING_PROGRESS, [
                "getcourse_id", "student_name", "manager_name", "telegram_id",
                "telegram_username", "start_time", "message_id", "steps_json",
                "overall_status", "errors_json", "updated_at"
            ])
            
            self._ensure_sheet_exists(SHEET_SYSTEM_EVENTS, [
                "timestamp", "event_type", "description", "data_json"
            ])
            
            self._ensure_sheet_exists(SHEET_STUDENT_MESSAGES, [
                "timestamp", "date", "time", "chat_id", "student_id", 
                "getcourse_id", "student_name", "manager_name",
                "message_type", "message_text", "course"
            ])
            
            self._ensure_sheet_exists(SHEET_PENDING_CORRECTIONS, [
                "message_id", "getcourse_id", "student_name", "manager_id",
                "manager_name", "student_data_json", "created_at", "status"
            ])
            
            self._initialized = True
            logger.info("✅ VipalinaPersistence инициализирован успешно")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации VipalinaPersistence: {e}", exc_info=True)
            return False
    
    def is_initialized(self) -> bool:
        """Проверяет, инициализирован ли менеджер персистенции."""
        return self._initialized

    def _ensure_sheet_exists(self, sheet_name: str, headers: list):
        """
        Проверяет существование листа и создает его при необходимости.
        
        Args:
            sheet_name: Название листа
            headers: Заголовки столбцов
        """
        try:
            try:
                worksheet = self.spreadsheet.worksheet(sheet_name)
                logger.info(f"Лист '{sheet_name}' уже существует")
            except gspread.exceptions.WorksheetNotFound:
                # Проверяем, есть ли лист с похожим именем (регистрозависимо)
                all_sheets = self.spreadsheet.worksheets()
                existing_sheet_names = [ws.title for ws in all_sheets]
                
                if sheet_name in existing_sheet_names:
                    # Если лист с таким именем уже существует, используем его
                    worksheet = self.spreadsheet.worksheet(sheet_name)
                    logger.info(f"Лист '{sheet_name}' уже существует")
                else:
                    # Создаем новый лист
                    worksheet = self.spreadsheet.add_worksheet(
                        title=sheet_name,
                        rows=1000,
                        cols=len(headers)
                    )
                    # Добавляем заголовки
                    worksheet.update('A1', [headers])
                    # Форматируем заголовки
                    worksheet.format('A1:' + chr(ord('A') + len(headers) - 1) + '1', {
                        'textFormat': {'bold': True},
                        'backgroundColor': {'red': 0.2, 'green': 0.6, 'blue': 0.2}
                    })
                    logger.info(f"✅ Создан лист '{sheet_name}' с заголовками")
            
            self.worksheets[sheet_name] = worksheet
            
        except Exception as e:
            logger.error(f"Ошибка при создании листа '{sheet_name}': {e}")
            raise
    
    # ========== CHAT_TO_STUDENT ==========
    
    def save_chat_to_student_mapping(self, chat_id: int, getcourse_id: str, student_name: str = "", invite_link: str = "") -> bool:
        """
        Сохраняет связь chat_id -> getcourse_id с invite-ссылкой.
        
        Args:
            chat_id: ID чата
            getcourse_id: ID студента в GetCourse
            student_name: Имя студента (опционально)
            invite_link: Invite-ссылка на чат (опционально)
            
        Returns:
            True если сохранено успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_CHAT_TO_STUDENT)
            if not worksheet:
                logger.error(f"Лист '{SHEET_CHAT_TO_STUDENT}' не найден")
                return False
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Проверяем, существует ли уже запись
            existing_row = self._find_row_by_value(worksheet, 1, str(chat_id))
            
            row_data = [str(chat_id), getcourse_id, student_name, invite_link, now, now]
            
            if existing_row:
                # Обновляем существующую запись
                worksheet.update(f'A{existing_row}:F{existing_row}', [row_data])
                logger.debug(f"Обновлена связь chat_id={chat_id} -> getcourse_id={getcourse_id}")
            else:
                # Добавляем новую запись
                worksheet.append_row(row_data)
                logger.info(f"Сохранена связь chat_id={chat_id} -> getcourse_id={getcourse_id} с invite-ссылкой")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении chat_to_student: {e}", exc_info=True)
            
            # Уведомляем руководителя
            import asyncio
            try:
                asyncio.create_task(self._notify_persistence_error(
                    "Chat_To_Student",
                    f"chat_id={chat_id}, getcourse_id={getcourse_id}"
                ))
            except:
                pass
            
            return False
    
    def load_all_chat_to_student(self) -> dict[int, str]:
        """
        Загружает все связи chat_id -> getcourse_id.
        
        Returns:
            dict[int, str]: chat_id -> getcourse_id
        """
        try:
            worksheet = self.worksheets.get(SHEET_CHAT_TO_STUDENT)
            if not worksheet:
                return {}
            
            all_data = worksheet.get_all_values()
            result = {}
            
            for row in all_data[1:]:  # Пропускаем заголовки
                if len(row) >= 2 and row[0] and row[1]:
                    try:
                        chat_id = int(row[0])
                        getcourse_id = row[1]
                        result[chat_id] = getcourse_id
                    except ValueError:
                        continue
            
            logger.info(f"Загружено {len(result)} связей chat_to_student")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке chat_to_student: {e}", exc_info=True)
            return {}
    
    def delete_chat_student_mapping(self, chat_id: int) -> bool:
        """Удаляет запись chat_id из листа Chat_To_Student."""
        try:
            worksheet = self.worksheets.get(SHEET_CHAT_TO_STUDENT)
            if not worksheet:
                return False
            row_num = self._find_row_by_value(worksheet, 1, str(chat_id))
            if row_num:
                worksheet.delete_rows(row_num)
                logger.info(f"Удалена связь chat_id={chat_id} из Chat_To_Student")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при удалении chat_to_student mapping: {e}")
            return False

    def get_invite_link_by_chat_id(self, chat_id: int) -> typing.Optional[str]:
        """
        Получает invite-ссылку для чата по его ID.
        
        Args:
            chat_id: ID чата
            
        Returns:
            Invite-ссылка или None
        """
        try:
            worksheet = self.worksheets.get(SHEET_CHAT_TO_STUDENT)
            if not worksheet:
                return None
            
            all_data = worksheet.get_all_values()
            
            for row in all_data[1:]:  # Пропускаем заголовки
                if len(row) >= 4 and row[0]:
                    try:
                        if int(row[0]) == chat_id:
                            return row[3] if row[3] else None
                    except ValueError:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при получении invite_link для chat_id={chat_id}: {e}")
            return None
    
    # ========== STUDENTS_DATA ==========
    
    def save_student_data(self, getcourse_id: str, student_data: dict[str, typing.Any]) -> bool:
        """
        Сохраняет данные студента.
        
        Args:
            getcourse_id: ID студента в GetCourse
            student_data: Данные студента
            
        Returns:
            True если сохранено успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_STUDENTS_DATA)
            if not worksheet:
                return False
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Проверяем существующую запись
            existing_row = self._find_row_by_value(worksheet, 1, getcourse_id)
            
            row_data = [
                getcourse_id,
                student_data.get('name', ''),
                student_data.get('email', ''),
                student_data.get('phone', ''),
                student_data.get('course', ''),
                student_data.get('telegram_username', ''),
                str(student_data.get('telegram_id', '')),
                student_data.get('getcourse_url', ''),
                str(student_data.get('is_test_student', False)),
                now,
                now
            ]
            
            if existing_row:
                worksheet.update(f'A{existing_row}:K{existing_row}', [row_data])
                logger.debug(f"Обновлены данные студента {getcourse_id}")
            else:
                worksheet.append_row(row_data)
                logger.info(f"Сохранены данные студента {getcourse_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных студента: {e}", exc_info=True)
            return False
    
    def load_all_students_data(self) -> dict[str, dict[str, typing.Any]]:
        """
        Загружает данные всех студентов.
        
        Returns:
            dictstr, Dict]: getcourse_id -> student_data
        """
        try:
            worksheet = self.worksheets.get(SHEET_STUDENTS_DATA)
            if not worksheet:
                return {}
            
            all_data = worksheet.get_all_values()
            result = {}
            
            for row in all_data[1:]:
                if len(row) >= 9 and row[0]:
                    getcourse_id = row[0]
                    result[getcourse_id] = {
                        'name': row[1] if len(row) > 1 else '',
                        'email': row[2] if len(row) > 2 else '',
                        'phone': row[3] if len(row) > 3 else '',
                        'course': row[4] if len(row) > 4 else '',
                        'telegram_username': row[5] if len(row) > 5 else '',
                        'telegram_id': int(row[6]) if len(row) > 6 and row[6].isdigit() else None,
                        'getcourse_url': row[7] if len(row) > 7 else '',
                        'is_test_student': row[8].lower() == 'true' if len(row) > 8 else False,
                        'getcourse_id': getcourse_id
                    }
            
            logger.info(f"Загружены данные {len(result)} студентов")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных студентов: {e}", exc_info=True)
            return {}
    
    # ========== MANAGER_ASSIGNMENTS ==========
    
    def save_manager_assignment(self, getcourse_id: str, assignment_data: dict[str, typing.Any]) -> bool:
        """
        Сохраняет назначение менеджера студенту.
        
        Args:
            getcourse_id: ID студента в GetCourse
            assignment_data: Данные назначения
            
        Returns:
            True если сохранено успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_MANAGER_ASSIGNMENTS)
            if not worksheet:
                return False
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Проверяем существующую запись
            existing_row = self._find_row_by_value(worksheet, 1, getcourse_id)
            
            row_data = [
                getcourse_id,
                str(assignment_data.get('manager_id', '')),
                assignment_data.get('manager_name', ''),
                assignment_data.get('course_tag', ''),
                assignment_data.get('status', 'assigned'),
                assignment_data.get('student_name', ''),
                assignment_data.get('student_telegram', ''),
                str(assignment_data.get('student_telegram_id', '')),
                now,
                now
            ]
            
            if existing_row:
                worksheet.update(f'A{existing_row}:J{existing_row}', [row_data])
                logger.debug(f"Обновлено назначение менеджера для студента {getcourse_id}")
            else:
                worksheet.append_row(row_data)
                logger.info(f"Сохранено назначение менеджера для студента {getcourse_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении назначения менеджера: {e}", exc_info=True)
            return False
    
    def delete_manager_assignment(self, getcourse_id: str) -> bool:
        """
        Удаляет назначение менеджера для студента.
        
        Args:
            getcourse_id: ID студента в GetCourse
            
        Returns:
            True если удалено успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_MANAGER_ASSIGNMENTS)
            if not worksheet:
                return False
            
            # Находим строку с назначением
            row_index = self._find_row_by_value(worksheet, 1, getcourse_id)
            if row_index:
                # Удаляем строку
                worksheet.delete_rows(row_index)
                logger.info(f"Удалено назначение менеджера для студента {getcourse_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при удалении назначения менеджера: {e}", exc_info=True)
            return False
    
    def load_all_manager_assignments(self) -> dict[str, dict[str, typing.Any]]:
        """
        Загружает все назначения менеджеров.
        
        Returns:
            dictstr, Dict]: getcourse_id -> assignment_data
        """
        try:
            worksheet = self.worksheets.get(SHEET_MANAGER_ASSIGNMENTS)
            if not worksheet:
                return {}
            
            all_data = worksheet.get_all_values()
            result = {}
            
            for row in all_data[1:]:
                if len(row) >= 8 and row[0]:
                    getcourse_id = row[0]
                    result[getcourse_id] = {
                        'manager_id': int(row[1]) if row[1].isdigit() else None,
                        'manager_name': row[2] if len(row) > 2 else '',
                        'course_tag': row[3] if len(row) > 3 else '',
                        'status': row[4] if len(row) > 4 else 'assigned',
                        'student_name': row[5] if len(row) > 5 else '',
                        'student_telegram': row[6] if len(row) > 6 else '',
                        'student_telegram_id': int(row[7]) if len(row) > 7 and row[7].isdigit() else None,
                        'getcourse_id': getcourse_id
                    }
            
            logger.info(f"Загружено {len(result)} назначений менеджеров")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке назначений менеджеров: {e}", exc_info=True)
            return {}
    
    # ========== QUEUE_STATE ==========
    
    def save_queue_indices(self, vip_index: int, luxury_index: int) -> bool:
        """
        Сохраняет индексы очередей.
        Перезаписывает ВСЕ строки с данным queue_type, чтобы избежать дублей.
        
        Args:
            vip_index: Индекс очереди VIP
            luxury_index: Индекс очереди Luxury
            
        Returns:
            True если сохранено успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_QUEUE_STATE)
            if not worksheet:
                return False
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # VIP: удаляем ВСЕ старые строки с 'vip', добавляем одну новую
            all_data = worksheet.get_all_values()
            for i in range(len(all_data) - 1, 0, -1):  # снизу вверх, пропуская заголовок
                if all_data[i][0] == 'vip':
                    worksheet.delete_rows(i + 1, i + 1)
            worksheet.append_row(['vip', str(vip_index), now])
            
            # Luxury: то же самое
            all_data = worksheet.get_all_values()
            for i in range(len(all_data) - 1, 0, -1):
                if all_data[i][0] == 'luxury':
                    worksheet.delete_rows(i + 1, i + 1)
            worksheet.append_row(['luxury', str(luxury_index), now])
            
            logger.info(f"Сохранены индексы очередей: VIP={vip_index}, Luxury={luxury_index}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении индексов очередей: {e}", exc_info=True)
            return False
    
    def load_queue_indices(self) -> dict[str, int]:
        """
        Загружает индексы очередей.
        
        Returns:
            dict[str, int]: {'vip': index, 'luxury': index}
        """
        try:
            worksheet = self.worksheets.get(SHEET_QUEUE_STATE)
            if not worksheet:
                return {'vip': 0, 'luxury': 0}
            
            all_data = worksheet.get_all_values()
            result = {'vip': 0, 'luxury': 0}
            
            for row in all_data[1:]:
                if len(row) >= 2 and row[0] and row[1]:
                    queue_type = row[0]
                    try:
                        index = int(row[1])
                        if queue_type in result:
                            result[queue_type] = index
                    except ValueError:
                        continue
            
            logger.info(f"Загружены индексы очередей: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке индексов очередей: {e}", exc_info=True)
            return {'vip': 0, 'luxury': 0}
    
    # ========== ACTIVE_SLA ==========
    
    def save_sla_request(self, chat_id: int, student_id: int, request_data: dict[str, typing.Any]) -> bool:
        """
        Сохраняет активный SLA-запрос.
        
        Args:
            chat_id: ID чата
            student_id: ID студента
            request_data: Данные запроса
            
        Returns:
            True если сохранено успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_ACTIVE_SLA)
            if not worksheet:
                return False
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Проверяем существующую запись
            existing_row = self._find_row_by_value(worksheet, 1, str(chat_id))
            
            row_data = [
                str(chat_id),
                str(student_id),
                request_data.get('student_name', ''),
                request_data.get('request_text', '')[:100],  # Первые 100 символов
                request_data.get('request_time', '').strftime('%Y-%m-%d %H:%M:%S') if hasattr(request_data.get('request_time', ''), 'strftime') else str(request_data.get('request_time', '')),
                str(request_data.get('is_working_hours', False)),
                now
            ]
            
            if existing_row:
                worksheet.update(f'A{existing_row}:G{existing_row}', [row_data])
                logger.debug(f"Обновлен SLA-запрос для чата {chat_id}")
            else:
                worksheet.append_row(row_data)
                logger.info(f"Сохранен SLA-запрос для чата {chat_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении SLA-запроса: {e}", exc_info=True)
            return False
    
    def delete_sla_request(self, chat_id: int, student_id: int) -> bool:
        """
        Удаляет активный SLA-запрос.
        
        Args:
            chat_id: ID чата
            student_id: ID студента
            
        Returns:
            True если удалено успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_ACTIVE_SLA)
            if not worksheet:
                return False
            
            # Находим строку с запросом
            row_index = self._find_row_by_value(worksheet, 1, str(chat_id))
            if row_index:
                # Удаляем строку
                worksheet.delete_rows(row_index)
                logger.info(f"Удален SLA-запрос для чата {chat_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при удалении SLA-запроса: {e}", exc_info=True)
            return False
    
    def load_all_sla_requests(self) -> dict[int, dict[int, dict[str, typing.Any]]]:
        """
        Загружает все активные SLA-запросы.
        
        Returns:
            dictint, dictint, Dict]]: chat_id -> {student_id -> request_data}
        """
        try:
            worksheet = self.worksheets.get(SHEET_ACTIVE_SLA)
            if not worksheet:
                return {}
            
            all_data = worksheet.get_all_values()
            result = {}
            
            for row in all_data[1:]:
                if len(row) >= 7 and row[0] and row[1]:
                    try:
                        chat_id = int(row[0])
                        student_id = int(row[1])
                        
                        if chat_id not in result:
                            result[chat_id] = {}
                        
                        result[chat_id][student_id] = {
                            'student_name': row[2] if len(row) > 2 else '',
                            'request_text': row[3] if len(row) > 3 else '',
                            'request_time': row[4] if len(row) > 4 else '',
                            'is_working_hours': row[5].lower() == 'true' if len(row) > 5 else False
                        }
                    except ValueError:
                        continue
            
            logger.info(f"Загружено {sum(len(v) for v in result.values())} активных SLA-запросов")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке SLA-запросов: {e}", exc_info=True)
            return {}
    
    # ========== ONBOARDING_PROGRESS ==========
    
    def save_onboarding_progress(self, getcourse_id: str, progress_data: dict[str, typing.Any]) -> bool:
        """
        Сохраняет прогресс онбординга студента.
        
        Args:
            getcourse_id: ID студента в GetCourse
            progress_data: Данные прогресса
            
        Returns:
            True если сохранено успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_ONBOARDING_PROGRESS)
            if not worksheet:
                return False
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Проверяем существующую запись
            existing_row = self._find_row_by_value(worksheet, 1, getcourse_id)
            
            # Сериализуем сложные структуры данных
            steps_json = json.dumps(progress_data.get('steps', {}), ensure_ascii=False)
            errors_json = json.dumps(progress_data.get('errors', []), ensure_ascii=False)
            
            row_data = [
                getcourse_id,
                progress_data.get('student_name', ''),
                progress_data.get('manager_name', ''),
                str(progress_data.get('telegram_id', '')),
                progress_data.get('telegram_username', ''),
                progress_data.get('start_time', '').strftime('%Y-%m-%d %H:%M:%S') if hasattr(progress_data.get('start_time', ''), 'strftime') else str(progress_data.get('start_time', '')),
                str(progress_data.get('message_id', '')),
                steps_json,
                progress_data.get('overall_status', 'in_progress'),
                errors_json,
                now
            ]
            
            if existing_row:
                worksheet.update(f'A{existing_row}:K{existing_row}', [row_data])
                logger.debug(f"Обновлен прогресс онбординга для студента {getcourse_id}")
            else:
                worksheet.append_row(row_data)
                logger.info(f"Сохранен прогресс онбординга для студента {getcourse_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении прогресса онбординга: {e}", exc_info=True)
            return False
    
    def delete_onboarding_progress(self, getcourse_id: str) -> bool:
        """
        Удаляет прогресс онбординга студента.
        
        Args:
            getcourse_id: ID студента в GetCourse
            
        Returns:
            True если удалено успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_ONBOARDING_PROGRESS)
            if not worksheet:
                return False
            
            # Находим строку с прогрессом
            row_index = self._find_row_by_value(worksheet, 1, getcourse_id)
            if row_index:
                # Удаляем строку
                worksheet.delete_rows(row_index)
                logger.info(f"Удален прогресс онбординга для студента {getcourse_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при удалении прогресса онбординга: {e}", exc_info=True)
            return False
    
    def load_all_onboarding_progress(self) -> dict[str, dict[str, typing.Any]]:
        """
        Загружает весь прогресс онбординга.
        
        Returns:
            dictstr, Dict]: getcourse_id -> progress_data
        """
        try:
            worksheet = self.worksheets.get(SHEET_ONBOARDING_PROGRESS)
            if not worksheet:
                return {}
            
            all_data = worksheet.get_all_values()
            result = {}
            
            for row in all_data[1:]:
                if len(row) >= 11 and row[0]:
                    try:
                        getcourse_id = row[0]
                        start_time = datetime.strptime(row[5], '%Y-%m-%d %H:%M:%S') if row[5] else None
                        
                        # Десериализуем JSON данные
                        steps = json.loads(row[7]) if row[7] else {}
                        errors = json.loads(row[9]) if row[9] else []
                        
                        result[getcourse_id] = {
                            'student_name': row[1] if len(row) > 1 else '',
                            'manager_name': row[2] if len(row) > 2 else '',
                            'telegram_id': int(row[3]) if len(row) > 3 and row[3].isdigit() else None,
                            'telegram_username': row[4] if len(row) > 4 else '',
                            'start_time': start_time,
                            'message_id': int(row[6]) if len(row) > 6 and row[6].isdigit() else None,
                            'steps': steps,
                            'overall_status': row[8] if len(row) > 8 else 'in_progress',
                            'errors': errors,
                            'getcourse_id': getcourse_id
                        }
                    except (ValueError, json.JSONDecodeError) as e:
                        logger.warning(f"Ошибка при парсинге данных онбординга для {getcourse_id}: {e}")
                        continue
            
            logger.info(f"Загружено {len(result)} активных онбордингов")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке прогресса онбордингов: {e}", exc_info=True)
            return {}
    
    # ========== SYSTEM_EVENTS ==========
    
    def log_event(self, event_type: str, description: str, data: typing.Optional[dict[str, typing.Any]] = None) -> bool:
        """
        Записывает событие в лог.
        
        Args:
            event_type: Тип события (startup, shutdown, error, etc.)
            description: Описание события
            data: Дополнительные данные (опционально)
            
        Returns:
            True если записано успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_SYSTEM_EVENTS)
            if not worksheet:
                return False
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            data_json = json.dumps(data, ensure_ascii=False, default=str) if data else ''
            
            worksheet.append_row([now, event_type, description, data_json])
            logger.debug(f"Записано событие: {event_type} - {description}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при записи события: {e}", exc_info=True)
            return False
    
    # ========== STUDENT_MESSAGES ==========
    
    def save_student_message(
        self,
        chat_id: int,
        student_id: int,
        getcourse_id: str,
        student_name: str,
        manager_name: str,
        message_text: str,
        message_type: str = "text",
        course: str = ""
    ) -> bool:
        """
        Сохраняет сообщение студента в лог.
        
        Args:
            chat_id: ID чата
            student_id: Telegram ID студента
            getcourse_id: ID студента в GetCourse
            student_name: Имя студента
            manager_name: Имя менеджера
            message_text: Текст сообщения (первые 500 символов)
            message_type: Тип сообщения (text, photo, document, voice, video)
            course: Название курса
            
        Returns:
            True если сохранено успешно
        """
        try:
            worksheet = self.worksheets.get(SHEET_STUDENT_MESSAGES)
            if not worksheet:
                logger.warning(f"Лист '{SHEET_STUDENT_MESSAGES}' не найден")
                return False
            
            now = datetime.now()
            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            date_str = now.strftime('%Y-%m-%d')
            time_str = now.strftime('%H:%M:%S')
            
            # Ограничиваем текст сообщения до 500 символов
            message_text_short = message_text[:500] if message_text else ""
            
            row_data = [
                timestamp,
                date_str,
                time_str,
                str(chat_id),
                str(student_id),
                getcourse_id,
                student_name,
                manager_name,
                message_type,
                message_text_short,
                course
            ]
            
            worksheet.append_row(row_data, value_input_option='RAW')
            logger.debug(f"Сообщение студента {student_name} сохранено")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении сообщения студента: {e}")
            return False
    
    # ========== PENDING CORRECTIONS ==========
    
    def save_pending_correction(self, message_id: int, student_data: dict, manager_id: int, manager_name: str) -> bool:
        """
        Сохраняет ожидающую коррекцию данных студента.
        
        Args:
            message_id: ID сообщения с запросом коррекции
            student_data: Данные студента
            manager_id: ID менеджера
            manager_name: Имя менеджера
            
        Returns:
            True если успешно
        """
        try:
            if not self.is_initialized():
                return False
            
            worksheet = self.spreadsheet.worksheet(SHEET_PENDING_CORRECTIONS)
            
            # Удаляем старую запись для этого message_id, если есть
            existing_row = self._find_row_by_value(worksheet, 1, str(message_id))
            if existing_row:
                worksheet.delete_rows(existing_row)
            
            # Добавляем новую запись
            row_data = [
                str(message_id),
                student_data.get('getcourse_id', ''),
                student_data.get('name', ''),
                str(manager_id),
                manager_name,
                json.dumps(student_data, ensure_ascii=False),
                datetime.now().isoformat(),
                'pending'
            ]
            
            worksheet.append_row(row_data, value_input_option='RAW')
            logger.info(f"✅ Сохранёна коррекция для message_id={message_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении pending correction: {e}")
            return False
    
    def get_pending_correction(self, message_id: int) -> typing.Optional[dict]:
        """
        Получает ожидающую коррекцию по message_id.
        
        Args:
            message_id: ID сообщения
            
        Returns:
            Словарь с данными или None
        """
        try:
            if not self.is_initialized():
                return None
            
            worksheet = self.spreadsheet.worksheet(SHEET_PENDING_CORRECTIONS)
            row_num = self._find_row_by_value(worksheet, 1, str(message_id))
            
            if not row_num:
                return None
            
            row = worksheet.row_values(row_num)
            if len(row) < 8:
                return None
            
            return {
                'message_id': int(row[0]),
                'getcourse_id': row[1],
                'student_name': row[2],
                'manager_id': int(row[3]),
                'manager_name': row[4],
                'student_data': json.loads(row[5]),
                'created_at': row[6],
                'status': row[7]
            }
            
        except Exception as e:
            logger.error(f"Ошибка при получении pending correction: {e}")
            return None
    
    def get_all_pending_corrections(self) -> dict:
        """
        Получает все ожидающие коррекции.
        
        Returns:
            Словарь {message_id: context}
        """
        try:
            if not self.is_initialized():
                return {}
            
            worksheet = self.spreadsheet.worksheet(SHEET_PENDING_CORRECTIONS)
            all_rows = worksheet.get_all_values()
            
            corrections = {}
            for row in all_rows[1:]:  # Пропускаем заголовок
                if len(row) < 8 or row[7] != 'pending':
                    continue
                
                try:
                    message_id = int(row[0])
                    corrections[message_id] = {
                        'student_data': json.loads(row[5]),
                        'manager_id': int(row[3]),
                        'manager_name': row[4]
                    }
                except (ValueError, json.JSONDecodeError) as e:
                    logger.warning(f"Пропускаем невалидную строку: {e}")
                    continue
            
            logger.info(f"Загружено {len(corrections)} ожидающих коррекций")
            return corrections
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке pending corrections: {e}")
            return {}
    
    def delete_pending_correction(self, message_id: int) -> bool:
        """
        Удаляет ожидающую коррекцию.
        
        Args:
            message_id: ID сообщения
            
        Returns:
            True если успешно
        """
        try:
            if not self.is_initialized():
                return False
            
            worksheet = self.spreadsheet.worksheet(SHEET_PENDING_CORRECTIONS)
            row_num = self._find_row_by_value(worksheet, 1, str(message_id))
            
            if row_num:
                worksheet.delete_rows(row_num)
                logger.info(f"✅ Удалена коррекция message_id={message_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при удалении pending correction: {e}")
            return False
    
    # ========== HELPERS ==========
    
    def _find_row_by_value(self, worksheet: gspread.Worksheet, col: int, value: str) -> typing.Optional[int]:
        """
        Находит строку по значению в указанном столбце.
        
        Args:
            worksheet: Рабочий лист
            col: Номер столбца (1-based)
            value: Искомое значение
            
        Returns:
            Номер строки или None
        """
        try:
            all_values = worksheet.col_values(col)
            for i, v in enumerate(all_values[1:], start=2):  # Пропускаем заголовок
                if v == value:
                    return i
            return None
        except Exception:
            return None

# Глобальный экземпляр для использования в других модулях
_persistence_instance: typing.Optional['VipalinaPersistence'] = None


def get_persistence() -> 'VipalinaPersistence':
    """
    Возвращает глобальный экземпляр VipalinaPersistence.
    Создает и инициализирует его при первом вызове.
    """
    global _persistence_instance
    
    if _persistence_instance is None:
        _persistence_instance = VipalinaPersistence()
        if not _persistence_instance.initialize():
            logger.error("Не удалось инициализировать VipalinaPersistence")
    
    return _persistence_instance