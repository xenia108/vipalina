"""
Упрощенное создание трекеров через копирование шаблона.
Решает проблему квоты Google Drive.

ВАЖНО: Использует копирование существующего шаблона вместо создания нового файла!
"""

import gspread
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google.oauth2.credentials import Credentials
import logging
import os
import json
import time
from typing import Dict, Any, Optional
from course_config_v2 import CourseConfig
from datetime import datetime
from config import TRACKER_OWNER_EMAIL, TRACKER_FOLDER_ID, USER_OAUTH_TOKEN_PATH
import asyncio
from auth_error_notifier import notify_oauth_error

logger = logging.getLogger('vipalina_telethon')


def _is_retryable_google_error(error: Exception) -> bool:
    """Определяет временные ошибки Google API/сети, которые можно безопасно повторить."""
    error_text = str(error).lower()
    retry_markers = [
        '429', 'quota exceeded', '500', '502', '503', '504',
        'service is currently unavailable', 'internal error',
        'read operation timed out', 'timed out', 'timeout',
        'remote end closed connection', 'connection aborted',
        'connection reset', 'ssl', 'eof occurred'
    ]
    return any(marker in error_text for marker in retry_markers)


def _sheets_call_with_retry(func, *args, max_retries=5, **kwargs):
    """Обёртка для gspread-вызовов с retry при квотах, 5xx и сетевых таймаутах."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if not _is_retryable_google_error(e) or attempt == max_retries - 1:
                raise
            wait = min(30, 2 ** attempt)
            logger.warning(f"⚠️ Временная ошибка Google Sheets (попытка {attempt+1}/{max_retries}): {e}. Жду {wait}с...")
            time.sleep(wait)
    raise last_error


class TrackerCreator:
    """
    Создает трекеры студентов копированием шаблона.
    
    Преимущества:
    - ✅ Не требует квоты на создание файлов
    - ✅ Быстрое создание
    - ✅ Сохраняет форматирование шаблона
    - ✅ Формулы работают сразу
    """
    
    # ID шаблона трекера (для обычных курсов)
    TEMPLATE_ID = '1gH1Sd7BCeUFBqufXUy63nVjWPcNmGNq312iL8-_Y_rQ'
    
    # ID шаблона для тарифов (Бандлы, Абонементы, Премиум)
    TEMPLATE_TARIFF_ID = os.getenv('TEMPLATE_TARIFF_TRACKER_ID', '1WDtCWwCDxgmv106v5nRAiy1V_zNOFRhz3PH481NuWAw')
    
    def __init__(self, credentials_path: str = 'vipalina_google_service_account.json'):
        """Инициализация с путем к credentials"""
        self.credentials_path = credentials_path
        self.drive_service = None
        self.sheets_client = None
        self.auth_mode = 'service_account'
        self._authorize()
    
    def _authorize(self):
        """Авторизация в Google Sheets и Drive API (User OAuth при наличии токена, иначе Service Account)"""
        try:
            scope = [
                'https://www.googleapis.com/auth/drive',
                'https://www.googleapis.com/auth/spreadsheets'
            ]
            creds = None

            # Пытаемся авторизоваться через пользовательский токен (vipzerocoder)
            try:
                if USER_OAUTH_TOKEN_PATH and os.path.exists(USER_OAUTH_TOKEN_PATH):
                    # Загружаем токен вручную чтобы избежать ошибки при истёкшем токене
                    with open(USER_OAUTH_TOKEN_PATH, 'r') as token_file:
                        token_data = json.load(token_file)
                    
                    creds = Credentials.from_authorized_user_info(token_data, scope)
                    self._creds = creds
                    self.auth_mode = 'user_oauth'
                    logger.info("✅ Авторизация через User OAuth (Drive + Sheets)")
                    
                    # Проверяем, не истек ли токен, и пытаемся обновить его
                    if creds.expired and creds.refresh_token:
                        from google.auth.transport.requests import Request
                        logger.info("🔄 Попытка обновить истекший User OAuth токен...")
                        creds.refresh(Request())
                        # ВАЖНО: всегда сохраняем обновлённый токен обратно на диск,
                        # иначе новый refresh_token теряется и следующий refresh упадёт с invalid_grant
                        with open(USER_OAUTH_TOKEN_PATH, 'w') as token_file:
                            token_file.write(creds.to_json())
                        self._creds = creds  # обновляем in-memory ссылку
                        logger.info("✅ User OAuth токен успешно обновлен и сохранён на диск")
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"⚠️ Не удалось авторизоваться через User OAuth: {error_msg}")
                # Отправляем уведомление руководителю VIP-отдела
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(notify_oauth_error(error_msg))
                except RuntimeError:
                    asyncio.run(notify_oauth_error(error_msg))
                except Exception as notification_error:
                    logger.error(f"❌ Ошибка при отправке уведомления: {notification_error}")
                creds = None

            # Если пользовательская авторизация недоступна — используем сервисный аккаунт
            if creds is None:
                creds = ServiceAccountCredentials.from_service_account_file(
                    self.credentials_path, scopes=scope
                )
                self.auth_mode = 'service_account'
                logger.info("✅ Авторизация через Service Account (Drive + Sheets)")
            
            # Drive API для копирования файлов
            self.drive_service = build('drive', 'v3', credentials=creds)
            
            # Sheets API для работы с данными
            # При User OAuth — используем те же credentials для gspread (не сервисный аккаунт)
            if self.auth_mode == 'user_oauth':
                self.sheets_client = gspread.authorize(creds)
                logger.info("✅ Gspread инициализирован через User OAuth")
            else:
                from shared_gspread_client import get_shared_gspread_client
                self.sheets_client = get_shared_gspread_client(self.credentials_path)

            logger.info("✅ Авторизация успешна (Drive + Sheets)")
            
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            # Отправляем уведомление руководителю VIP-отдела
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(notify_oauth_error(str(e)))
            except RuntimeError:
                asyncio.run(notify_oauth_error(str(e)))
            except Exception as notification_error:
                logger.error(f"❌ Ошибка при отправке уведомления: {notification_error}")
            raise
    
    def create_tracker(
        self,
        student_name: str,
        course_tag: str,
        manager_name: str,
        getcourse_id: str,
        parent_folder_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создает трекер студента копированием шаблона.
        
        Args:
            student_name: Имя студента (например, "Иван Иванов")
            course_tag: Тег курса из GetCourse (например, "[python-ai-2.0] Тариф \"VIP\"")
            manager_name: Имя VIP-менеджера
            getcourse_id: ID из GetCourse
            parent_folder_id: ID папки на Google Drive (опционально)
        
        Returns:
            Dict с данными созданного трекера
        """
        # Внешний retry для всего create_tracker при ошибках квоты/сети
        import time as _time
        max_outer_retries = 3
        for outer_attempt in range(max_outer_retries):
            try:
                return self._create_tracker_impl(
                    student_name, course_tag, manager_name, getcourse_id, parent_folder_id
                )
            except Exception as e:
                if _is_retryable_google_error(e) and outer_attempt < max_outer_retries - 1:
                    wait = min(60, 10 * (outer_attempt + 1))
                    logger.warning(
                        f"⚠️ Ошибка создания трекера (попытка {outer_attempt+1}/{max_outer_retries}): {e}. "
                        f"Жду {wait}с и повторяю..."
                    )
                    _time.sleep(wait)
                    continue
                raise
        raise RuntimeError("Не удалось создать трекер после всех попыток")

    def _create_tracker_impl(
        self,
        student_name: str,
        course_tag: str,
        manager_name: str,
        getcourse_id: str,
        parent_folder_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создает трекер студента копированием шаблона.
        
        Args:
            student_name: Имя студента (например, "Иван Иванов")
            course_tag: Тег курса из GetCourse (например, "[python-ai-2.0] Тариф \"VIP\"")
            manager_name: Имя VIP-менеджера
            getcourse_id: ID из GetCourse
            parent_folder_id: ID папки на Google Drive (опционально)
        
        Returns:
            Dict с данными созданного трекера:
            {
                'spreadsheet_id': str,
                'url': str,
                'title': str,
                'course_params': dict
            }
        """
        try:
            # Обновляем credentials только если токен истёк (не каждый раз)
            try:
                if hasattr(self, '_creds') and self._creds and getattr(self._creds, 'expired', False):
                    logger.info("🔄 Токен истёк, обновляем перед созданием трекера...")
                    self._authorize()
            except Exception:
                pass  # если проверка не удалась — продолжаем с текущими кредами

            # 1. Получаем параметры курса из маппинга
            course_params = CourseConfig.get_course_params(course_tag)
            tracker_name = CourseConfig.get_tracker_course_name(course_tag)
            
            # Определяем тип программы (обычный курс или тариф)
            is_tariff = CourseConfig.is_tariff_program(course_tag)
            program_type = course_params.get('program_type', 'regular')
            
            logger.info(f"📚 Создание трекера для {student_name}")
            logger.info(f"   is_tariff: {is_tariff}")
            logger.info(f"   Тип: {program_type.upper()}")
            logger.info(f"   Курс/Тариф: {tracker_name}")
            logger.info(f"   Уроков: {course_params['lesson_count']}")
            logger.info(f"   Доступ: {course_params['access_days']} дней")
            logger.info(f"   VIP поддержка: {course_params['vip_support_days']} дней")
            
            # Извлекаем только имя (без фамилии) из полного имени
            first_name = student_name.split()[0] if student_name else student_name
            
            # 2. Копируем шаблон через Drive API
            # Название: Имя - Курс, GetCourse ID
            new_title = f"{first_name} - {tracker_name}, {getcourse_id}"
            new_tracker_id = self._copy_template(new_title, parent_folder_id, is_tariff=is_tariff)
            
            logger.info(f"✅ Шаблон скопирован: {new_tracker_id}")
            
            # 3. Передаём ownership на vipzerocoder@gmail.com (чтобы файл занимал место на их диске)
            self._transfer_ownership(new_tracker_id)
            
            # 4. Открываем скопированный трекер (с retry при 429)
            tracker = _sheets_call_with_retry(self.sheets_client.open_by_key, new_tracker_id)
            
            # 4.1. Синхронизируем данные курсов из "Условия курсов" в Конфигурацию
            self._sync_courses_to_config(tracker)
            
            # 5. Копируем данные курса в лист "⚠️ Конфигурация" (ДО удаления листов)
            self._copy_course_data_to_config(tracker, tracker_name, course_tag, course_params)
            
            # 6. Удаляем внутренние листы
            self._remove_internal_sheets(tracker)
            
            # 6.1. Скрываем лист "⚠️ Конфигурация" (нужен для формул, но не для просмотра)
            self._hide_config_sheet(tracker)
            
            # 7. Заполняем данными студента
            self._fill_tracker_data(
                tracker, 
                student_name, 
                tracker_name,
                course_tag,
                manager_name,
                getcourse_id,
                course_params
            )
            
            # 8. Для тарифов проверяем необходимость скрытия листа "📚 Доп. модули"
            program_type = course_params.get('program_type', 'regular')
            if program_type in ['subscription', 'bundle', 'premium']:
                # Проверяем значение F2 в листе "⚙️ Конфигурация"
                try:
                    config_sheet = None
                    for variant in ["⚙️ Конфигурация", "Конфигурация", "Configuration"]:
                        try:
                            config_sheet = tracker.worksheet(variant)
                            break
                        except:
                            continue
                    
                    if config_sheet is not None:
                        f2_value = config_sheet.acell('F2').value
                        # Если F2 пустой, скрываем лист "📚 Доп. модули"
                        if not f2_value or not f2_value.strip():
                            self._hide_additional_modules_sheet(tracker)
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при проверке значения F2: {e}")            
            tracker_url = f'https://docs.google.com/spreadsheets/d/{new_tracker_id}'
            logger.info(f"✅ Трекер создан: {tracker_url}")
            
            return {
                'spreadsheet_id': new_tracker_id,
                'url': tracker_url,
                'title': new_title,
                'course_params': course_params
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания трекера: {e}")
            # Отправляем уведомление если это ошибка токена
            error_msg = str(e)
            if 'invalid_grant' in error_msg or 'Token has been expired' in error_msg:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(notify_oauth_error(error_msg))
                except RuntimeError:
                    asyncio.run(notify_oauth_error(error_msg))
                except Exception as notification_error:
                    logger.error(f"❌ Ошибка при отправке уведомления: {notification_error}")
            raise
    
    def _copy_template(self, new_title: str, parent_folder_id: Optional[str] = None, is_tariff: bool = False) -> str:
        """
        Копирует шаблон трекера через Drive API.
        
        Args:
            new_title: Название для нового трекера
            parent_folder_id: ID папки для размещения (опционально)
            is_tariff: True если это тариф (бандл, абонемент, премиум)
        
        Returns:
            ID скопированного файла
        """
        import time
        
        # Выбираем шаблон в зависимости от типа программы
        template_id = self.TEMPLATE_TARIFF_ID if is_tariff else self.TEMPLATE_ID
        template_type = "Тариф" if is_tariff else "Курс"
        
        logger.info(f"📋 Используем шаблон: {template_type} ({template_id})")
        
        file_metadata = {'name': new_title}
        
        # Если указана папка, добавляем её в метаданные
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]
        
        # Retry логика для временных ошибок Google Drive/API
        max_retries = 5
        for attempt in range(max_retries):
            try:
                # Копируем файл
                copied_file = self.drive_service.files().copy(
                    fileId=template_id,
                    body=file_metadata,
                    supportsAllDrives=True
                ).execute(num_retries=2)
                
                logger.info(f"✅ Шаблон скопирован: {copied_file['id']}")
                return copied_file['id']
                
            except Exception as e:
                error_msg = str(e)
                if _is_retryable_google_error(e):
                    if attempt < max_retries - 1:
                        wait_time = min(45, 5 * (attempt + 1))
                        logger.warning(f"⚠️ Временная ошибка копирования шаблона (попытка {attempt + 1}/{max_retries}): {error_msg}")
                        logger.info(f"🔄 Повторная попытка копирования через {wait_time} сек...")
                        time.sleep(wait_time)
                        continue
                    logger.error(f"❌ Не удалось скопировать шаблон после {max_retries} попыток: {error_msg}")
                    raise
                logger.error(f"❌ Ошибка копирования шаблона: {e}")
                raise
    
    def _transfer_ownership(self, file_id: str) -> bool:
        """
        Передаёт ownership файла на vipzerocoder@gmail.com.
        Это позволяет избежать использования квоты Service Account.
        
        Args:
            file_id: ID файла для передачи ownership
        
        Returns:
            True если успешно
        """
        try:
            # Если авторизация от имени пользователя — передача владельца не требуется
            if getattr(self, 'auth_mode', 'service_account') == 'user_oauth':
                logger.info("ℹ️ Пропускаем передачу владельца: файл уже принадлежит пользователю")
                return True
            
            logger.info(f"📤 Передача ownership трекера на {TRACKER_OWNER_EMAIL}...")
            
            # Шаг 1: Получаем текущих родителей (папки) файла
            file_info = self.drive_service.files().get(
                fileId=file_id,
                fields='parents'
            ).execute()
            
            current_parents = file_info.get('parents', [])
            logger.info(f"📁 Текущие папки файла: {current_parents}")
            
            # Шаг 2: Создаём разрешение с ролью owner и включаем transferOwnership
            permission = {
                'type': 'user',
                'role': 'owner',
                'emailAddress': TRACKER_OWNER_EMAIL
            }
            
            self.drive_service.permissions().create(
                fileId=file_id,
                body=permission,
                transferOwnership=True,  # Ключевой параметр!
                sendNotificationEmail=False  # Не отправляем уведомление
            ).execute()
            
            logger.info(f"✅ Ownership передан на {TRACKER_OWNER_EMAIL}")
            
            # Шаг 3: Удаляем файл из старых папок (чтобы не занимал место на Service Account)
            # После передачи ownership файл остаётся в папке назначения (TRACKER_FOLDER_ID)
            if current_parents:
                # Получаем информацию о текущих папках после передачи
                updated_file = self.drive_service.files().get(
                    fileId=file_id,
                    fields='parents'
                ).execute()
                
                updated_parents = updated_file.get('parents', [])
                
                # Если файл всё ещё в нескольких папках, очищаем старые
                if len(updated_parents) > 1 or (updated_parents and updated_parents[0] != TRACKER_FOLDER_ID):
                    logger.info(f"🧹 Очистка файла из старых папок...")
                    
                    # Удаляем из всех папок кроме целевой
                    parents_to_remove = [p for p in updated_parents if p != TRACKER_FOLDER_ID]
                    
                    if parents_to_remove:
                        self.drive_service.files().update(
                            fileId=file_id,
                            removeParents=','.join(parents_to_remove),
                            fields='id, parents'
                        ).execute()
                        
                        logger.info(f"✅ Файл удалён из {len(parents_to_remove)} старых папок")
            
            logger.info(f"💾 Теперь файл занимает место на диске {TRACKER_OWNER_EMAIL}, а не Service Account")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка передачи ownership: {e}")
            logger.warning("⚠️ Файл создан, но остался на диске Service Account")
            # Не пробрасываем ошибку дальше - файл всё равно создан
            return False
    
    def _fill_tracker_data(
        self,
        tracker,
        student_name: str,
        course_name: str,
        course_tag: str,
        manager_name: str,
        getcourse_id: str,
        params: Dict[str, Any]
    ):
        """
        Заполняет данными студента в скопированном трекере.
        
        Обновляет:
        - Информацию о студенте (имя, курс, менеджер, ID)
        - Параметры курса (доступ, поддержка)
        - Помесячный прогресс
        """
        try:
            # Ищем лист "Инфо о курсе" или первый лист
            try:
                main_sheet = tracker.worksheet("Инфо о курсе")
            except:
                main_sheet = tracker.sheet1
            
            logger.info(f"📝 Заполнение данных в лист: {main_sheet.title}")
            
            # Обновляем заголовок: B1="Трекер студента", C1=курс, D1=getcourse_id
            # A1 остается пустой
            # C1 должна ссылаться на A2 листа Конфигурация
            main_sheet.update([["='⚙️ Конфигурация'!A2"]], 'C1', value_input_option='USER_ENTERED')
            
            # D1 = GetCourse ID
            main_sheet.update([[getcourse_id]], 'D1', value_input_option='USER_ENTERED')
            logger.info(f"✅ GetCourse ID заполнен в D1: {getcourse_id}")
            
            # Добавляем текущую дату в G1 (для использования в формулах)
            main_sheet.update([['=TODAY()']], 'G1', value_input_option='USER_ENTERED')
            logger.info("✅ Добавлена формула =TODAY() в G1")
            
            # Копируем данные курса в лист Конфигурация
            self._copy_course_data_to_config(tracker, course_name, course_tag, params)
            
            # Настраиваем VLOOKUP формулы в листе Конфигурация
            try:
                config_sheet = None
                for variant in ["⚠️ Конфигурация", "Конфигурация", "Configuration"]:
                    try:
                        config_sheet = tracker.worksheet(variant)
                        break
                    except:
                        continue
                
                if config_sheet is None:
                    for ws in tracker.worksheets():
                        if "Конфиг" in ws.title or "config" in ws.title.lower():
                            config_sheet = ws
                            break
                
                if config_sheet:
                    self._setup_config_formulas(config_sheet)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при настройке формул конфигурации: {e}")
            
            # Обновляем формулы для расчета сроков (если нужно)
            # В шаблоне уже должны быть формулы, но можем обновить параметры
            self._update_course_parameters(main_sheet, params)
            
            # Обновляем формулы в помесячном прогрессе
            self._update_monthly_progress_formulas(main_sheet, params)
            
            # Настраиваем лист "📚 Все уроки курса" (или "📚 Доп. модули" для тарифов) с формулой IMPORTRANGE
            self._setup_lessons_sheet(tracker, params)
            
            # Настраиваем формулы в листе "📊 Сданные ДЗ" (Модуль, Урок, Дата ДЗ)
            self._setup_hw_sheet_formulas(tracker)
            
            logger.info("✅ Данные студента заполнены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка заполнения данных: {e}")
            raise
    
    def _copy_course_data_to_config(self, tracker, course_name: str, course_tag: str, params: Dict[str, Any]):
        """
        Копирует данные курса из маппинга в лист "⚙️ Конфигурация".
        Заполняет A2 названием курса и B2:F2 формулами VLOOKUP для динамического обновления.
        """
        try:
            logger.info(f"📋 Копирование данных курса в Конфигурацию: {course_name}")
            
            # Ищем лист "⚙️ Конфигурация"
            config_sheet = None
            for variant in ["⚙️ Конфигурация", "Конфигурация", "Configuration"]:
                try:
                    config_sheet = tracker.worksheet(variant)
                    logger.info(f"✅ Найден лист: '{variant}'")
                    break
                except:
                    continue
            
            if config_sheet is None:
                # Поиск по всем листам
                for ws in tracker.worksheets():
                    if "Конфиг" in ws.title or "config" in ws.title.lower():
                        config_sheet = ws
                        logger.info(f"✅ Найден лист: '{ws.title}'")
                        break
            
            if config_sheet is None:
                raise Exception("Не найден лист Конфигурации")
            
            # Заполняем только ячейку A2 с названием курса
            course_data = [[course_name]]
            config_sheet.update(course_data, 'A2', value_input_option='USER_ENTERED')
            logger.info(f"✅ Название курса '{course_name}' заполнено в A2")
            
            # Устанавливаем VLOOKUP формулы в ячейках B2:F2 для динамического обновления
            # при изменении значения в A2 - ссылаемся на данные на том же листе (строки 4+)
            try:
                # B2: Количество уроков - VLOOKUP из данных на том же листе
                lesson_count_formula = "=IFERROR(VLOOKUP(A2;A$4:H$1000;2;FALSE);\"\")"
                config_sheet.update([[lesson_count_formula]], 'B2', value_input_option='USER_ENTERED')
                
                # C2: Доступ (мес) - VLOOKUP из данных на том же листе
                access_formula = "=IFERROR(VLOOKUP(A2;A$4:H$1000;3;FALSE);\"\")"
                config_sheet.update([[access_formula]], 'C2', value_input_option='USER_ENTERED')
                
                # D2: Куратор (мес) - VLOOKUP из данных на том же листе
                curator_formula = "=IFERROR(VLOOKUP(A2;A$4:H$1000;4;FALSE);\"\")"
                config_sheet.update([[curator_formula]], 'D2', value_input_option='USER_ENTERED')
                
                # E2: VIP (мес) - VLOOKUP из данных на том же листе
                vip_formula = "=IFERROR(VLOOKUP(A2;A$4:H$1000;5;FALSE);\"\")"
                config_sheet.update([[vip_formula]], 'E2', value_input_option='USER_ENTERED')
                
                # F2: Тег ГАНТ - VLOOKUP из данных на том же листе
                gant_formula = "=IFERROR(VLOOKUP(A2;A$4:H$1000;6;FALSE);\"\")"
                config_sheet.update([[gant_formula]], 'F2', value_input_option='USER_ENTERED')
                
                logger.info("✅ VLOOKUP формулы установлены в ячейках B2:F2")
            except Exception as formula_error:
                logger.warning(f"⚠️ Не удалось установить VLOOKUP формулы: {formula_error}")
                logger.info("ℹ️ Ячейки B2:F2 должны содержать VLOOKUP формулы из шаблона")
            
        except Exception as e:
            logger.error(f"❌ Ошибка копирования данных курса: {e}")
            raise
    
    def _setup_config_formulas(self, config_sheet):
        """
        Устанавливает VLOOKUP формулы в конфигурационном листе.
        Это позволяет ячейкам B2:F2 автоматически обновляться при изменении A2.
        """
        try:
            logger.info("🔧 Настройка VLOOKUP формул в листе Конфигурация...")
            
            # Устанавливаем формулы только если они еще не установлены или сломаны
            formulas_to_set = [
                ('B2', "=IFERROR(VLOOKUP(A2;A$4:H$1000;2;FALSE);\"\")"),  # Количество уроков
                ('C2', "=IFERROR(VLOOKUP(A2;A$4:H$1000;3;FALSE);\"\")"),  # Доступ (мес)
                ('D2', "=IFERROR(VLOOKUP(A2;A$4:H$1000;4;FALSE);\"\")"),  # Куратор (мес)
                ('E2', "=IFERROR(VLOOKUP(A2;A$4:H$1000;5;FALSE);\"\")"),  # VIP (мес)
                ('F2', "=IFERROR(VLOOKUP(A2;A$4:H$1000;6;FALSE);\"\")")   # Тег ГАНТ
            ]
            
            for cell, formula in formulas_to_set:
                try:
                    current_value = config_sheet.acell(cell, value_render_option='FORMULA').value
                    # Если формула отсутствует или не является VLOOKUP, устанавливаем новую
                    if not current_value or 'VLOOKUP' not in current_value:
                        config_sheet.update([[formula]], cell, value_input_option='USER_ENTERED')
                        logger.info(f"✅ Формула установлена в {cell}")
                except Exception as cell_error:
                    logger.warning(f"⚠️ Ошибка при установке формулы в {cell}: {cell_error}")
            
            logger.info("✅ VLOOKUP формулы настроены в листе Конфигурация")
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при настройке формул конфигурации: {e}")
    
    def _format_months_value(self, original_value, days_value):
        """
        Форматирует значение месяцев для отображения.
        Если оригинальное значение текстовое, возвращает его как есть.
        Если числовое, конвертирует дни в месяцы.
        """
        # Если оригинальное значение текстовое, возвращаем его как есть
        if isinstance(original_value, str) and not original_value.isdigit():
            # Для специальных текстовых значений возвращаем их как есть
            if original_value.lower().strip() in ['навсегда', 'бессрочно', 'forever', 'unlimited', 'бесконечно']:
                return original_value
            # Для других текстовых значений тоже возвращаем как есть
            return original_value
        
        # Если оригинальное значение числовое, конвертируем дни в месяцы
        try:
            # Обрабатываем случай, когда days_value может быть текстовым значением
            if isinstance(days_value, str) and not days_value.isdigit():
                return days_value
                
            days = int(days_value) if days_value else 0
            months = days // 30 if days > 0 else 0
            return str(months) if months > 0 else "0"
        except (ValueError, TypeError):
            # Если не можем конвертировать, возвращаем оригинальное значение
            if isinstance(original_value, str):
                return original_value
            return "0"
    
    def _sync_courses_to_config(self, tracker):
        """
        Синхронизирует данные курсов из листа "Условия курсов" в лист "⚙️ Конфигурация".
        Проверяет наличие новых курсов и автоматически обновляет данные.
        """
        try:
            logger.info("🔄 Проверка актуальности данных курсов...")
            
            # Ищем листы
            try:
                conditions_sheet = tracker.worksheet('Условия курсов')
            except:
                logger.info("ℹ️ Лист 'Условия курсов' не найден в трекере, пропускаем синхронизацию")
                return
            
            config_sheet = None
            for variant in ["⚙️ Конфигурация", "Конфигурация", "Configuration"]:
                try:
                    config_sheet = tracker.worksheet(variant)
                    break
                except:
                    continue
            
            if config_sheet is None:
                logger.warning("⚠️ Лист Конфигурации не найден")
                return
            
            # Получаем данные из 'Условия курсов' (со строки 2, без заголовка)
            # Столбцы: A-Тег ГК, B-Название, C-ГАНТ, D-Уроки, E-Доступ, F-Куратор, G-VIP, H-Тип
            all_courses = _sheets_call_with_retry(conditions_sheet.get, 'A2:H200')  # Максимум 199 курсов
            
            # Получаем текущие данные из Конфигурации
            current_config = _sheets_call_with_retry(config_sheet.col_values, 1)[3:]  # Начиная с строки 4
            current_count = len([c for c in current_config if c.strip()])
            
            # Подготавливаем новые данные для строк 4 и далее (это список всех курсов)
            config_data = []
            for row in all_courses:
                if len(row) >= 2 and row[1]:  # Если есть название для трекера в столбце B
                    config_data.append([
                        row[1] if len(row) > 1 else '',  # B: Название для трекера → A
                        row[3] if len(row) > 3 else '',  # D: Количество уроков → B
                        row[4] if len(row) > 4 else '',  # E: Доступ → C
                        row[5] if len(row) > 5 else '',  # F: Куратор → D
                        row[6] if len(row) > 6 else '',  # G: VIP → E
                        row[2] if len(row) > 2 else '',  # C: Тег ГАНТ → F
                        '',  # G: Резерв (пусто)
                        row[7] if len(row) > 7 else ''   # H: Тип программы → H
                    ])
            
            new_count = len(config_data)
            
            # Сравниваем количество
            if new_count == current_count:
                logger.info(f"✅ Данные курсов актуальны ({current_count} курсов)")
                return
            
            # Обновляем данные
            logger.info(f"🆕 Обнаружены изменения: {current_count} → {new_count} курсов")
            
            if config_data:
                end_row = 3 + len(config_data)
                _sheets_call_with_retry(config_sheet.update, config_data, f'A4:H{end_row}', value_input_option='USER_ENTERED')
                logger.info(f"✅ Обновлено {len(config_data)} курсов в строках 4-{end_row}")
            
            # Убеждаемся, что VLOOKUP формулы настроены правильно
            self._setup_config_formulas(config_sheet)
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при синхронизации курсов: {e}")
            # Не пробрасываем ошибку - это не критично
    
    def _update_course_parameters(self, worksheet, params: Dict[str, Any]):
        """
        Параметры курса уже настроены в шаблоне через VLOOKUP к листу Конфигурация.
        Этот метод больше не нужен, так как:
        - C9, C10, C11 используют VLOOKUP из шаблона
        - C15 ссылается на '⚙️ Конфигурация'!B2
        """
        logger.info("ℹ️ Параметры курса берутся из листа Конфигурация через формулы шаблона")
        pass
    
    def _update_monthly_progress_formulas(self, worksheet, params: Dict[str, Any]):
        """
        Создает динамические строки для помесячного прогресса.
        Количество строк = количество месяцев поддержки куратора (D10).
        """
        try:
            # Находим строку 21 с заголовками (Месяц | Цель | Факт | Прогресс | Статус)
            all_values = worksheet.get_all_values()
            
            progress_header_row = None
            for i, row in enumerate(all_values):
                if len(row) >= 5 and row[1] == "Месяц" and row[2] == "Цель" and row[3] == "Факт":
                    progress_header_row = i + 1  # Это строка 21 (1-based)
                    break
            
            if progress_header_row is None:
                logger.warning("⚠️ Не найден блок помесячного прогресса (строка 21)")
                return
            
            logger.info(f"📊 Найден заголовок помесячного прогресса в строке {progress_header_row}")
            
            # ЧИТАЕМ количество месяцев из D10 ТРЕКЕРА (поддержка куратора)
            # params['curator_support_months'] используем как надёжный fallback
            params_months = params.get('curator_support_months', 0)
            try:
                d10_raw = worksheet.acell('D10').value
                
                # Удаляем текст "мес." если есть
                d10_stripped = d10_raw.replace('мес.', '').replace('mes.', '').strip() if d10_raw and isinstance(d10_raw, str) else d10_raw
                
                # Проверяем: текстовое значение ("Навсегда", "Бессрочно") или числовое
                if d10_stripped and isinstance(d10_stripped, str) and not d10_stripped.isdigit():
                    # Текстовое значение — создаём 1 строку с этим текстом
                    curator_months = 1
                    is_text_value = True
                    text_value = d10_stripped
                else:
                    d10_months = int(float(d10_stripped)) if d10_stripped else 0
                    # Если D10 вернул 0 или пусто — берём из params (надёжный источник)
                    curator_months = d10_months if d10_months > 0 else params_months
                    is_text_value = False
                    text_value = None
                
                logger.info(f"📌 D10={d10_raw!r} → {curator_months} месяцев (params={params_months})")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось прочитать D10: {e}")
                curator_months = params_months
                is_text_value = False
                text_value = None
                logger.info(f"🔄 Используем curator_support_months из params: {curator_months} месяцев")
            
            logger.info(f"📅 Создаем {curator_months} строк для помесячного прогресса")
            
            # Подготавливаем данные для всех месяцев
            rows_data = []
            
            # Если это текстовое значение, создаем одну строку с этим значением
            if is_text_value and text_value:
                row_num = progress_header_row + 1  # Строка 22
                
                # B: Название месяца
                month_label = text_value  # Отображаем текстовое значение
                
                # C: Цель (пусто для текстовых значений)
                monthly_goal = ""
                
                # D: Факт (пусто для текстовых значений)
                fact_formula = ""
                
                # E: Процент выполнения (пусто для текстовых значений)
                progress_formula = ""
                
                # F: Статус (пусто для текстовых значений)
                status_formula = ""
                
                # G: Визуальный прогресс-бар (пусто для текстовых значений)
                visual_formula = ""
                
                rows_data.append([
                    month_label,      # B: Месяц
                    monthly_goal,     # C: Цель
                    fact_formula,     # D: Факт
                    progress_formula, # E: Прогресс
                    status_formula,   # F: Статус
                    visual_formula    # G: Визуальный прогресс
                ])
            else:
                # Для числовых значений создаем обычные строки
                for month in range(1, curator_months + 1):
                    row_num = progress_header_row + month  # Строка 22, 23, 24...
                    
                    # B: Название месяца
                    month_label = f"Месяц {month}"
                    
                    # C: Цель (количество уроков в месяц) - фиксированное значение
                    monthly_goal = 7
                    
                    # D: Факт - формула подсчета выполненных уроков за КАЛЕНДАРНЫЙ месяц
                    # Используем ГОД и МЕСЯЦ для определения календарного месяца от даты начала
                    # Месяц 1 = тот же месяц что C4, Месяц 2 = следующий месяц и т.д.
                    fact_formula = f'=СЧЁТЕСЛИМН(\'📊 Сданные ДЗ\'!F:F;ИСТИНА;\'📊 Сданные ДЗ\'!E:E;">="&ДАТА(ГОД(ДАТАМЕС(C4;{month-1}));МЕСЯЦ(ДАТАМЕС(C4;{month-1}));1);\'📊 Сданные ДЗ\'!E:E;"<"&ДАТА(ГОД(ДАТАМЕС(C4;{month}));МЕСЯЦ(ДАТАМЕС(C4;{month}));1))'
                    
                    # E: Процент выполнения
                    progress_formula = f'=ЕСЛИ(C{row_num}=0;0;ОКРУГЛ(D{row_num}/C{row_num}*100;0))&"%"'
                    
                    # F: Статус — пропорциональные пороги: >=цели ✅, >70% цели 🆗, >30% цели ⚠️, иначе ❌
                    status_formula = f'=ЕСЛИ(D{row_num}>=C{row_num};"✅";ЕСЛИ(D{row_num}>4;"🆗";ЕСЛИ(D{row_num}>2;"⚠️";"❌")))'
                    
                    # G: Визуальный прогресс-бар (поддерживает >100%)
                    visual_formula = f'=ПОВТОР("█";МИН(10;ОКРУГЛ(D{row_num}/C{row_num}*10;0)))&ПОВТОР("░";МАКС(0;10-ОКРУГЛ(D{row_num}/C{row_num}*10;0)))&" "&ТЕКСТ(D{row_num}/C{row_num};"0%")'
                    
                    rows_data.append([
                        month_label,      # B: Месяц
                        monthly_goal,     # C: Цель
                        fact_formula,     # D: Факт
                        progress_formula, # E: Прогресс
                        status_formula,   # F: Статус
                        visual_formula    # G: Визуальный прогресс
                    ])
            
            # Записываем все строки одним запросом
            if rows_data:
                start_row = progress_header_row + 1  # Строка 22
                end_row = progress_header_row + (1 if is_text_value and text_value else curator_months)
                range_name = f'B{start_row}:G{end_row}'  # Расширено до столбца G
                
                # Логируем первые 3 формулы ПЕРЕД отправкой
                for i in range(min(3, len(rows_data))):
                    print(f"DEBUG: Месяц {i+1} перед отправкой: {rows_data[i][2]}")
                    logger.info(f"🔍 Перед отправкой - Месяц {i+1}: {rows_data[i][2][:80]}...")
                
                _sheets_call_with_retry(worksheet.update, rows_data, range_name, value_input_option='USER_ENTERED')
                logger.info(f"✅ Создано {curator_months if not (is_text_value and text_value) else 1} строк помесячного прогресса ({range_name})")
                
                # Копируем форматирование из строки 21 на все строки месяцев
                try:
                    sheet_id = worksheet.id
                    
                    if curator_months >= 1 or (is_text_value and text_value):
                        copy_format_request = {
                            "requests": [
                                {
                                    "copyPaste": {
                                        "source": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": 20,  # Строка 21 (0-based)
                                            "endRowIndex": 21,     # Только строка 21
                                            "startColumnIndex": 1, # Столбец B
                                            "endColumnIndex": 7    # До столбца G
                                        },
                                        "destination": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": start_row - 1,  # Строки 22+ (0-based)
                                            "endRowIndex": end_row,
                                            "startColumnIndex": 1,
                                            "endColumnIndex": 7
                                        },
                                        "pasteType": "PASTE_FORMAT"  # Только форматирование
                                    }
                                }
                            ]
                        }
                        
                        _sheets_call_with_retry(worksheet.spreadsheet.batch_update, copy_format_request)
                        logger.info(f"✅ Форматирование скопировано из строки 21 на строки {start_row}-{end_row}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось скопировать форматирование: {e}")
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось создать помесячный прогресс: {e}")
    
    def _remove_internal_sheets(self, tracker):
        """
        Удаляет внутренние листы, которые не должны быть в трекерах студентов.
        Например, лист "Условия курсов" содержит внутреннюю информацию.
        """
        try:
            # Список листов, которые нужно удалить из трекеров студентов
            # Лист "⚠️ Конфигурация" НЕ удаляем - он нужен для хранения данных курса
            internal_sheets = ["Условия курсов"]
            
            # Получаем все листы в трекере
            worksheets = tracker.worksheets()
            
            # Удаляем внутренние листы
            for worksheet in worksheets:
                if worksheet.title in internal_sheets:
                    try:
                        tracker.del_worksheet(worksheet)
                        logger.info(f"✅ Удален внутренний лист: {worksheet.title}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось удалить лист {worksheet.title}: {e}")
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при удалении внутренних листов: {e}")
    
    def _hide_config_sheet(self, tracker):
        """
        Скрывает лист "⚠️ Конфигурация" от студента.
        Лист нужен для работы формул VLOOKUP, но не должен быть виден.
        """
        try:
            # Ищем лист Конфигурация
            config_sheet = None
            for variant in ["⚠️ Конфигурация", "Конфигурация", "Configuration"]:
                try:
                    config_sheet = tracker.worksheet(variant)
                    logger.info(f"🔍 Найден лист Конфигурации: '{variant}'")
                    break
                except:
                    continue
            
            if config_sheet is None:
                # Поиск по всем листам
                for ws in tracker.worksheets():
                    if "Конфиг" in ws.title or "config" in ws.title.lower():
                        config_sheet = ws
                        logger.info(f"🔍 Найден лист Конфигурации: '{ws.title}'")
                        break
            
            if config_sheet is None:
                logger.warning("⚠️ Не найден лист Конфигурации для скрытия")
                return
            
            # Скрываем лист через batch_update API
            try:
                # Определяем количество непустых строк в столбце A (курсы)
                all_courses = config_sheet.col_values(1)  # Получаем все значения из столбца A
                
                # Находим последнюю непустую строку
                last_row = len(all_courses)
                for i in range(len(all_courses) - 1, 2, -1):  # Идем с конца, начиная со строки 3 (индекс 2)
                    if all_courses[i].strip():  # Если строка не пустая
                        last_row = i + 1  # +1 потому что индексация с 0
                        break
                
                # Если курсов меньше 4, значит данных вообще нет
                if last_row < 4:
                    logger.warning("⚠️ Не найдены данные курсов в Конфигурации (строки 4+)")
                    last_row = 60  # Используем дефолтное значение
                
                logger.info(f"📊 Найдено {last_row - 3} курсов, скрываем строки 4-{last_row}")
                
                request = {
                    "requests": [
                        {
                            "updateDimensionProperties": {
                                "range": {
                                    "sheetId": config_sheet.id,
                                    "dimension": "ROWS",
                                    "startIndex": 3,  # Строка 4 (0-based)
                                    "endIndex": last_row  # Последняя непустая строка
                                },
                                "properties": {
                                    "hiddenByUser": True
                                },
                                "fields": "hiddenByUser"
                            }
                        },
                        {
                            "updateSheetProperties": {
                                "properties": {
                                    "sheetId": config_sheet.id,
                                    "hidden": True
                                },
                                "fields": "hidden"
                            }
                        }
                    ]
                }
                
                tracker.batch_update(request)
                logger.info(f"✅ Лист '{config_sheet.title}' скрыт, строки 4-{last_row} скрыты")
                
            except Exception as e:
                logger.warning(f"⚠️ Не удалось скрыть лист '{config_sheet.title}': {e}")
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при скрытии листа Конфигурации: {e}")
    
    def _setup_lessons_sheet(self, tracker, params: Dict[str, Any]):
        """
        Настраивает лист с уроками:
        - "📚 Все уроки курса" (обычные курсы)
        - "📚 Доп. модули" (тарифы)
        
        Формула импортирует данные из таблицы ГАНТ по тегу курса.
        Добавляет столбец D "Урок сдан" с проверкой по листу "📊 Сданные ДЗ".
        
        ЛОГИКА ДЛЯ ТАРИФОВ (subscription/bundle/premium):
        - Если тег ГАНТ ПУСТОЙ → УДАЛЯЕМ лист (абонемент/бандл без уроков, только курсы)
        - Если тег ГАНТ ЕСТЬ → СОЗДАЕМ лист с уроками (премиум с спецблоками)
        
        ЛОГИКА ДЛЯ ОБЫЧНЫХ КУРСОВ (regular):
        - Если тег ГАНТ ПУСТОЙ → ПРОПУСКАЕМ (предупреждение)
        - Если тег ГАНТ ЕСТЬ → СОЗДАЕМ лист с уроками
        
        Фильтрация уроков:
        - Только столбцы A, D, E из ГАНТа
        - Только строки где A от 1 до 100 ИЛИ E = 'Онлайн'
        - Заголовки в строке 1, данные со строки 2
        """
        try:
            gant_tag = params.get('gant_sheet', '')
            program_type = params.get('program_type', 'regular')
            
            # Ищем лист с уроками (название зависит от типа программы)
            lessons_sheet = None
            
            # Для тарифов ищем "📚 Доп. модули"
            if program_type in ['subscription', 'bundle', 'premium']:
                for variant in [" 📚 Доп. модули", "📚 Доп. модули", "Доп. модули"]:
                    try:
                        lessons_sheet = tracker.worksheet(variant)
                        logger.info(f"✅ Найден лист доп. модулей: '{variant}'")
                        break
                    except:
                        continue
            else:
                # Для обычных курсов ищем "📚 Все уроки курса"
                for variant in [" 📚 Все уроки курса", "📚 Все уроки курса", "Все уроки курса"]:
                    try:
                        lessons_sheet = tracker.worksheet(variant)
                        logger.info(f"✅ Найден лист уроков: '{variant}'")
                        break
                    except:
                        continue
            
            if lessons_sheet is None:
                sheet_name = "📚 Доп. модули" if program_type in ['subscription', 'bundle', 'premium'] else "📚 Все уроки курса"
                logger.warning(f"⚠️ Не найден лист '{sheet_name}'")
                return
            
            # Проверяем тег ГАНТ
            if not gant_tag or not gant_tag.strip():
                # Для всех типов тарифов (subscription, bundle, premium) лист "📚 Доп. модули" 
                # должен быть скрыт если F2 в "⚙️ Конфигурация" пустой
                if program_type in ['subscription', 'bundle', 'premium']:
                    logger.info(f"ℹ️ Тег ГАНТ пустой для тарифа ({program_type}) - скрываем лист '📚 Доп. модули'")
                    # Скрываем лист "📚 Доп. модули"
                    self._hide_additional_modules_sheet(tracker)
                else:
                    # Для обычных курсов - только предупреждение
                    logger.warning("⚠️ Тег курса для ГАНТ пустой, пропускаем настройку листа '📚 Все уроки курса'")
                return            
            sheet_name = "📚 Доп. модули" if program_type in ['subscription', 'bundle', 'premium'] else "📚 Все уроки курса"
            logger.info(f"📚 Настройка листа '{sheet_name}' для тега: '{gant_tag}' (program_type: {program_type})")
            
            # Очищаем лист перед заполнением
            lessons_sheet.clear()
            
            # 1. Добавляем заголовки в первую строку
            headers = [[
                "Номер урока",
                "Название урока",
                "Формат проведения",
                "Урок сдан"
            ]]
            lessons_sheet.update(headers, 'A1:D1', value_input_option='USER_ENTERED')
            logger.info("✅ Заголовки добавлены в строку 1 (A-D)")
            
            # 2. ID таблицы ГАНТ
            gant_spreadsheet_id = '1iJyzqiGGCgrtDnbV-zqjY08P8Vq8HfOElwz7o4S743w'
            
            # 3. Создаем формулу IMPORTRANGE с фильтрацией для строки 2
            # Использует динамическую ссылку на '⚙️ Конфигурация'!F2 с СЖПРОБЕЛЫ
            # Fallback логика: если Col1 пустой, пробует Col2
            formula = f"""=ЕСЛИ('⚙️ Конфигурация'!F2="";"";ЕСЛИ(
  СЧЁТЗ(ЕСЛИОШИБКА(QUERY(
    IMPORTRANGE("{gant_spreadsheet_id}";"'"&СЖПРОБЕЛЫ('⚙️ Конфигурация'!F2)&"'!A:F");
    "select Col1,Col4,Col5 where (Col1>=1 and Col1<=100) or Col5='Онлайн'";
    0
  ); ))=0;
  ЕСЛИОШИБКА(QUERY(
    IMPORTRANGE("{gant_spreadsheet_id}";"'"&СЖПРОБЕЛЫ('⚙️ Конфигурация'!F2)&"'!A:F");
    "select Col2,Col5,Col6 where (Col2>=1 and Col2<=100) or Col6='Онлайн'";
    0
  ); );
  ЕСЛИОШИБКА(QUERY(
    IMPORTRANGE("{gant_spreadsheet_id}";"'"&СЖПРОБЕЛЫ('⚙️ Конфигурация'!F2)&"'!A:F");
    "select Col1,Col4,Col5 where (Col1>=1 and Col1<=100) or Col5='Онлайн'";
    0
  ); )
))"""

            
            # Вставляем формулу в ячейку A2
            lessons_sheet.update([[formula]], 'A2', value_input_option='USER_ENTERED')
            logger.info("✅ Формула IMPORTRANGE добавлена в A2")
            
            # 3.1. Проверяем есть ли уже формула в D2 из шаблона
            existing_formula = lessons_sheet.acell('D2', value_render_option='FORMULA').value
            
            if not existing_formula or '\\U' in existing_formula:
                # Формулы нет ИЛИ она сломана (\\U escape) - записываем заново
                emoji_chart = chr(0x1F4CA)  # 📊
                check_formula = f'=IF(B2<>"";IF(COUNTIF(\'{emoji_chart} Сданные ДЗ\'!D:D;B2)>0;TRUE;FALSE);"")'
                lessons_sheet.update([[check_formula]], 'D2', value_input_option='USER_ENTERED')
                logger.info("✅ Формула проверки ДЗ добавлена в D2")
            else:
                logger.info(f"ℹ️ Формула в D2 уже есть из шаблона: {existing_formula[:80]}...")
            
            # 4. Настраиваем форматирование
            # Получаем ID листа для batch_update
            sheet_id = lessons_sheet.id
            
            # Форматирование: черный шрифт, размер 12, чекбоксы в столбце D
            format_request = {
                "requests": [
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 0,  # Строка 1 (0-based)
                                "startColumnIndex": 0,  # Столбец A
                                "endColumnIndex": 4  # До столбца D включительно
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "textFormat": {
                                        "foregroundColor": {
                                            "red": 0,
                                            "green": 0,
                                            "blue": 0
                                        },
                                        "fontSize": 12
                                    }
                                }
                            },
                            "fields": "userEnteredFormat.textFormat"
                        }
                    },
                    {
                        # Добавляем чекбоксы в столбец D (со строки 2, так как в D2 формула)
                        "setDataValidation": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,  # Строка 2 (0-based)
                                "endRowIndex": 500,  # До 500 строки
                                "startColumnIndex": 3,  # Столбец D (0-based)
                                "endColumnIndex": 4  # Только D
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
            
            tracker.batch_update(format_request)
            logger.info("✅ Форматирование применено: черный шрифт, размер 12, чекбоксы в D")
            
            logger.info(f"✅ Лист '{sheet_name}' настроен")
            logger.info(f"   Тег: {gant_tag}")
            logger.info(f"   Формула в A2: {formula[:80]}...")
            logger.info(f"   Формула проверки ДЗ добавлена в D2")
            
            # Для всех типов тарифов (subscription, bundle, premium) лист "📚 Доп. модули" 
            # остается видимым для создания листов курсов
            # if program_type == 'bundle':
            #     self._hide_additional_modules_sheet(tracker)
            
        except Exception as e:
            sheet_name = "📚 Доп. модули" if params.get('program_type') in ['subscription', 'bundle', 'premium'] else "📚 Все уроки курса"
            logger.error(f"❌ Ошибка при настройке листа '{sheet_name}': {e}")
            # Не пробрасываем ошибку - это не критично
    
    def _setup_hw_sheet_formulas(self, tracker):
        """
        Устанавливает правильные формулы в листе "📊 Сданные ДЗ".
        Формулы для столбцов B, C (Модуль), D (Урок), E (Дата ДЗ).

        Источник данных: таблица "ВСЕ ДЗ" (1fCh5T_aV0DqYBCD4yvqnf4r33KBy7RbgQybu8lEcdxE)
        - B2: Статус из столбца B
        - C2: Модуль из столбца E
        - D2: Урок из столбца F
        - E2: Дата ДЗ из столбца H
        """
        try:
            HW_SPREADSHEET_ID = "1fCh5T_aV0DqYBCD4yvqnf4r33KBy7RbgQybu8lEcdxE"

            hw_sheet = None
            for variant in ["📊 Сданные ДЗ", "Сданные ДЗ"]:
                try:
                    hw_sheet = tracker.worksheet(variant)
                    logger.info(f"✅ Найден лист: '{variant}'")
                    break
                except:
                    continue

            if hw_sheet is None:
                logger.info("ℹ️ Лист '📊 Сданные ДЗ' не найден, пропускаем настройку формул")
                return

            formula_b2 = f'=ЕСЛИ(A2="";"";FILTER(IMPORTRANGE("{HW_SPREADSHEET_ID}";"\'ВСЕ ДЗ\'!B:B");ТЕКСТ(IMPORTRANGE("{HW_SPREADSHEET_ID}";"\'ВСЕ ДЗ\'!A:A");"0")=ТЕКСТ(A2;"0")))' 
            formula_c2 = f'=ЕСЛИ(A2="";"";FILTER(IMPORTRANGE("{HW_SPREADSHEET_ID}";"\'ВСЕ ДЗ\'!E:E");ТЕКСТ(IMPORTRANGE("{HW_SPREADSHEET_ID}";"\'ВСЕ ДЗ\'!A:A");"0")=ТЕКСТ(A2;"0")))' 
            formula_d2 = f'=ЕСЛИ(A2="";"";FILTER(IMPORTRANGE("{HW_SPREADSHEET_ID}";"\'ВСЕ ДЗ\'!F:F");ТЕКСТ(IMPORTRANGE("{HW_SPREADSHEET_ID}";"\'ВСЕ ДЗ\'!A:A");"0")=ТЕКСТ(A2;"0")))' 
            formula_e2 = f'=ЕСЛИ(A2="";"";FILTER(IMPORTRANGE("{HW_SPREADSHEET_ID}";"\'ВСЕ ДЗ\'!H:H");ТЕКСТ(IMPORTRANGE("{HW_SPREADSHEET_ID}";"\'ВСЕ ДЗ\'!A:A");"0")=ТЕКСТ(A2;"0")))'

            _sheets_call_with_retry(hw_sheet.update, [[formula_b2]], 'B2', value_input_option='USER_ENTERED')
            _sheets_call_with_retry(hw_sheet.update, [[formula_c2]], 'C2', value_input_option='USER_ENTERED')
            _sheets_call_with_retry(hw_sheet.update, [[formula_d2]], 'D2', value_input_option='USER_ENTERED')
            _sheets_call_with_retry(hw_sheet.update, [[formula_e2]], 'E2', value_input_option='USER_ENTERED')

            logger.info("✅ Формулы IMPORTRANGE установлены в листе '📊 Сданные ДЗ' (B2, C2, D2, E2)")

        except Exception as e:
            logger.warning(f"⚠️ Ошибка при настройке формул листа '📊 Сданные ДЗ': {e}")



    def _hide_additional_modules_sheet(self, tracker):
        """
        Скрывает шаблонный лист "📚 Доп. модули" после создания курсовых листов.
        Используется для тарифов (абонементов/бандлов/премиум).
        """
        try:
            # Ищем лист "📚 Доп. модули"
            additional_modules_sheet = None
            for variant in [" 📚 Доп. модули", "📚 Доп. модули", "Доп. модули"]:
                try:
                    additional_modules_sheet = tracker.worksheet(variant)
                    logger.info(f"✅ Найден лист доп. модулей: '{variant}'")
                    break
                except:
                    continue
            
            if additional_modules_sheet is None:
                logger.info("ℹ️ Лист '📚 Доп. модули' не найден, пропускаем скрытие")
                return
            
            # Скрываем лист через batch_update API
            hide_request = {
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": additional_modules_sheet.id,
                                "hidden": True
                            },
                            "fields": "hidden"
                        }
                    }
                ]
            }
            
            tracker.batch_update(hide_request)
            logger.info("✅ Шаблонный лист '📚 Доп. модули' скрыт")
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось скрыть лист '📚 Доп. модули': {e}")
    
    def share_tracker(self, spreadsheet_id: str, email: str, role: str = 'writer'):
        """
        Открывает доступ к трекеру для пользователя.
        
        Args:
            spreadsheet_id: ID таблицы
            email: Email пользователя
            role: Роль доступа ('writer', 'reader', 'owner')
        """
        try:
            permission = {
                'type': 'user',
                'role': role,
                'emailAddress': email
            }
            
            self.drive_service.permissions().create(
                fileId=spreadsheet_id,
                body=permission,
                sendNotificationEmail=False
            ).execute()
            
            logger.info(f"✅ Доступ предоставлен: {email} ({role})")
            
        except Exception as e:
            logger.error(f"❌ Ошибка предоставления доступа: {e}")
            raise
    
    def move_to_folder(self, spreadsheet_id: str, folder_id: str):
        """
        Перемещает трекер в указанную папку.
        
        Args:
            spreadsheet_id: ID таблицы
            folder_id: ID папки назначения
        """
        try:
            # Получаем текущие родительские папки
            file = self.drive_service.files().get(
                fileId=spreadsheet_id,
                fields='parents'
            ).execute()
            
            previous_parents = ",".join(file.get('parents', []))
            
            # Перемещаем в новую папку
            self.drive_service.files().update(
                fileId=spreadsheet_id,
                addParents=folder_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            
            logger.info(f"✅ Трекер перемещен в папку: {folder_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка перемещения: {e}")
            raise
    
    def add_course_to_classifier(self, getcourse_tag: str, internal_name: str) -> bool:
        """
        Добавляет новый курс во все три таблицы:
        1. 🎓 ШАБЛОН Трекера Студента (Новый) -> лист "Условия курсов"
        2. 🎓 ШАБЛОН Трекера Студента (Абоны) -> лист "Условия курсов"
        3. KPI Ultra -> лист "Матрица курсов"
        
        Args:
            getcourse_tag: Тег курса из GetCourse (например, "[test2] Второй тест")
            internal_name: Внутреннее название (например, "Второй тест, VIP")
        
        Returns:
            True если успешно добавлено хотя бы в одну таблицу
        """
        success_count = 0
        
        # ID таблиц
        tables = [
            {
                'id': self.TEMPLATE_ID,  # 🎓 ШАБЛОН Трекера Студента (Новый)
                'name': '🎓 ШАБЛОН Трекера Студента (Новый)',
                'sheet': 'Условия курсов'
            },
            {
                'id': self.TEMPLATE_TARIFF_ID,  # 🎓 ШАБЛОН Трекера Студента (Абоны)
                'name': '🎓 ШАБЛОН Трекера Студента (Абоны)',
                'sheet': 'Условия курсов'
            },
            {
                'id': '1MhDUG9IuYJN9lWG_p88UviOnQeiDM3Hj1eVqaoqPqYM',  # KPI Ultra
                'name': 'KPI Ultra',
                'sheet': 'Матрица курсов'
            }
        ]
        
        logger.info(f"📚 Начало синхронизации курса во все таблицы: {getcourse_tag} -> {internal_name}")
        
        for table in tables:
            try:
                # Открываем таблицу
                spreadsheet = self.sheets_client.open_by_key(table['id'])
                
                # Ищем лист
                try:
                    sheet = spreadsheet.worksheet(table['sheet'])
                except Exception as e:
                    logger.error(f"❌ Не найден лист '{table['sheet']}' в таблице '{table['name']}': {e}")
                    continue
                
                # Проверяем, не существует ли уже такой курс
                all_values = sheet.get_all_values()
                course_exists = False
                
                for row in all_values[1:]:  # Пропускаем заголовок
                    if len(row) >= 1 and row[0] == getcourse_tag:
                        logger.info(f"ℹ️ Курс {getcourse_tag} уже есть в '{table['name']}' -> '{table['sheet']}'")
                        course_exists = True
                        success_count += 1
                        break
                
                if course_exists:
                    continue
                
                # Добавляем новую строку в конец
                # Столбец A: Название с ГК, Столбец B: Название для AT, KPI Ultra, трекера и группы в телеграм
                new_row = [getcourse_tag, internal_name]
                sheet.append_row(new_row, value_input_option='RAW')
                
                logger.info(f"✅ Курс добавлен в '{table['name']}' -> '{table['sheet']}': {getcourse_tag} | {internal_name}")
                success_count += 1
                
            except Exception as e:
                logger.error(f"❌ Ошибка при добавлении курса в '{table['name']}': {e}", exc_info=True)
        
        if success_count > 0:
            logger.info(f"🎉 Курс успешно добавлен в {success_count} из {len(tables)} таблиц")
            return True
        else:
            logger.error(f"❌ Не удалось добавить курс ни в одну таблицу")
            return False


# Вспомогательная функция для быстрого использования

def create_student_tracker(
    student_name: str,
    course_tag: str,
    manager_name: str,
    getcourse_id: str,
    credentials_path: str = 'vipalina_google_credentials.json',
    folder_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Быстрое создание трекера для студента.
    
    Args:
        student_name: Имя студента
        course_tag: Тег курса из GetCourse
        manager_name: Имя VIP-менеджера
        getcourse_id: ID из GetCourse
        credentials_path: Путь к credentials файлу
        folder_id: ID папки на Google Drive (опционально)
    
    Returns:
        Dict с данными трекера
    
    Example:
        result = create_student_tracker(
            student_name="Иван Иванов",
            course_tag="[python-ai-2.0] Тариф \"VIP\"",
            manager_name="Марина Иванова",
            getcourse_id="12345"
        )
        print(result['url'])
    """
    creator = TrackerCreator(credentials_path)
    return creator.create_tracker(
        student_name=student_name,
        course_tag=course_tag,
        manager_name=manager_name,
        getcourse_id=getcourse_id,
        parent_folder_id=folder_id
    )


# Пример использования
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("\n" + "="*60)
    print("🚀 ТЕСТИРОВАНИЕ СОЗДАНИЯ ТРЕКЕРА")
    print("="*60 + "\n")
    
    try:
        result = create_student_tracker(
            student_name="Тестовый Студент",
            course_tag="[python-ai-2.0] Тариф \"VIP\"",
            manager_name="Марина Иванова",
            getcourse_id="TEST_" + str(int(datetime.now().timestamp()))
        )
        
        print("\n" + "="*60)
        print("✅ ТРЕКЕР УСПЕШНО СОЗДАН!")
        print("="*60)
        print(f"\n📊 URL: {result['url']}")
        print(f"идентификатор: {result['spreadsheet_id']}")
        print(f"Название: {result['title']}")
        print(f"\nЛист параметров курса:")
        for key, value in result['course_params'].items():
            print(f"   {key}: {value}")
        print("\n" + "="*60 + "\n")
        
    except Exception as e:
        print("\n" + "="*60)
        print("❌ ОШИБКА!")
        print("="*60)
        print(f"\n{e}\n")
        import traceback
        traceback.print_exc()
        print("\n" + "="*60 + "\n")
        print("\n" + "="*60)
        print("❌ ОШИБКА!")
        print("="*60)
        print(f"\n{e}\n")
        import traceback
        traceback.print_exc()
        print("\n" + "="*60 + "\n")
