"""
Основной модуль автоматизации VIP-отдела Zerocoder University
Интегрирует все компоненты системы в единую автоматизацию
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import re

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.custom import Button
from telethon.tl import types

# Импорт конфигурации
import os
from config import (
    API_ID, API_HASH, 
    VIP_DEPARTMENT_CHAT_ID, 
    VIP_MANAGERS_VIP, VIP_MANAGERS_LUXURY, 
    VIP_HEAD, VIP_DEVELOPER, HEAD_IDS, ON_DUTY_ACCOUNTS,
    ALL_MANAGER_IDS, MOSCOW_TZ,
    GOOGLE_SHEETS_ID, GOOGLE_SHEETS_KPI_TAB,
    AIRTABLE_FIELD_GETCOURSE_ID, AIRTABLE_FIELD_MANAGER,
    TELETHON_BOT_TOKEN, AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID
)

# Импорт модулей системы
from vip_chat_monitor import VIPChatMonitor, StudentData
from manager_queue import ManagerQueue
from student_onboarding import StudentOnboardingModule
from vipalina_sheets import VipalinaSheetIntegration
from manual_student_add import ManualStudentAddition
from onboarding_tracker import OnboardingTracker
from tracker_creator import TrackerCreator
from user_management import UserRoleManager, get_manager_info
from unknown_course_handler import UnknownCourseHandler

# Импорт интеграций
from vipalina_nocodb import create_nocodb_integration  # Заменяет Airtable
from vipalina_kpi_sheets import create_kpi_sheets_integration

from sla_tracker import SLATracker
from sla_sheets import SLASheetsIntegration
from oauth_handler import oauth_handler
from csi_scheduler import CSIScheduler
from training_dates_scheduler import TrainingDatesScheduler
from sla_reporter import SLAReporter
from info_updater import setup_info_updater

# Модуль персистенции - сохраняет все runtime-состояние в Google Sheets
from vipalina_persistence import get_persistence, VipalinaPersistence

# Модули касаний и напоминаний
from touch_buttons_handler import setup_touch_buttons_handler
from touch_auto_updater import TouchAutoUpdater

# Настройка централизованного логирования
from centralized_logger import setup_centralized_logging, get_logger
setup_centralized_logging()

logger = get_logger('vipalina_telethon')

# Список возможных статусов студента (как в KPI Ultra)
STATUS_OPTIONS = [
    "Новый",
    "Учится",
    "Заморозка",
    "Пропал",
    "Выпускной",
    "Стажировка",
    "Модуль ОК",
    "Окупается",
    "Закончил",
    "Не с нами",
    "Окупился",
    "Возврат",
]



class VipAutomationOrchestrator:
    """Основной оркестратор автоматизации VIP-отдела"""
    
    def __init__(self):
        """Инициализация оркестратора"""
        # SOCKS5 прокси через Tor (если Telegram заблокирован провайдером)
        # Проверяем доступность прокси, иначе подключаемся напрямую
        _proxy = None
        try:
            import socks as _socks
            import socket as _socket
            _test_sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            _test_sock.settimeout(1)
            _test_sock.connect(('127.0.0.1', 9050))
            _test_sock.close()
            _proxy = (_socks.SOCKS5, '127.0.0.1', 9050)
            logger.info("✅ SOCKS5 прокси доступен на 127.0.0.1:9050")
        except Exception:
            logger.info("ℹ️ SOCKS5 прокси недоступен — подключение к Telegram напрямую")

        # Создаем User Client для создания чатов и личных сообщений
        # Используем StringSession вместо файловой сессии (нет database lock!)
        _client_kwargs = {
            'proxy': _proxy,
            'connection_retries': 10,
            'retry_delay': 5,
            'request_retries': 5,
            'timeout': 30,
        } if _proxy else {
            'connection_retries': 10,
            'retry_delay': 5,
            'request_retries': 5,
            'timeout': 30,
        }
        session_string = os.getenv('TELETHON_SESSION_STRING')
        if session_string:
            logger.info("✅ Используем StringSession для Telethon client")
            self.client = TelegramClient(StringSession(session_string), API_ID, API_HASH, **_client_kwargs)
        else:
            logger.warning("⚠️ TELETHON_SESSION_STRING не найден в .env, используем файловую сессию")
            self.client = TelegramClient('ultralina_session', API_ID, API_HASH, **_client_kwargs)
        
        # Создаем Bot Client для отправки сообщений с inline-кнопками
        # (User аккаунты НЕ МОГУТ отправлять inline-кнопки!)
        bot_session_string = os.getenv('BOT_SESSION_STRING', '')
        if bot_session_string:
            logger.info("✅ Используем StringSession для Bot Client")
            self.bot_client = TelegramClient(StringSession(bot_session_string), API_ID, API_HASH, **_client_kwargs)
        else:
            logger.warning("⚠️ BOT_SESSION_STRING не найден, используем файловую сессию")
            self.bot_client = TelegramClient('bot_session', API_ID, API_HASH, **_client_kwargs)
        
        # Инициализация модулей
        # ManagerQueue использует bot_client для отправки кнопок
        self.manager_queue = ManagerQueue(self.bot_client)
        # Остальные модули используют user client для создания чатов
        self.chat_monitor = VIPChatMonitor(self.client)
        self.onboarding_module = StudentOnboardingModule(self.client, bot_client=self.bot_client)
        
        # Кеш entities - используем из onboarding_module для единообразия
        self.entity_cache = self.onboarding_module.entity_cache
        
        self.sheets_integration = VipalinaSheetIntegration()
        self.manual_add_module = ManualStudentAddition(self.client)
        
        # Инициализация трекера онбординга
        self.onboarding_tracker = OnboardingTracker(self.client)
        
        # Инициализация создателя трекеров (Фаза 3)
        try:
            self.tracker_creator = TrackerCreator()
            logger.info("✅ Создатель трекеров (Фаза 3) инициализирован")
        except Exception as e:
            logger.error(f"❌ Не удалось инициализировать создатель трекеров: {e}")
            self.tracker_creator = None
        
        # Инициализация обработчика неизвестных курсов
        try:
            # Передаём callback для запуска онбординга после маппинга + tracker_creator для классификатора
            self.unknown_course_handler = UnknownCourseHandler(
                client=self.client,
                onboarding_callback=self.start_onboarding_after_mapping,
                tracker_creator=self.tracker_creator  # Для записи в Google Sheets
            )
            logger.info("✅ Обработчик неизвестных курсов инициализирован")
        except Exception as e:
            logger.error(f"❌ Не удалось инициализировать обработчик неизвестных курсов: {e}")
            self.unknown_course_handler = None
        
        # Модуль обновления информации (только для руководителя)
        self.info_updater = setup_info_updater(self.client)
        
        # Интеграция с NocoDB (заменяет Airtable)
        try:
            from config import (
                NOCODB_API_URL,
                NOCODB_API_TOKEN,
                NOCODB_BASE_ID,
                NOCODB_TABLE_ID,
                NOCODB_VIEW_ID
            )
            self.nocodb = create_nocodb_integration(
                api_url=NOCODB_API_URL,
                api_token=NOCODB_API_TOKEN,
                base_id=NOCODB_BASE_ID,
                table_id=NOCODB_TABLE_ID,
                view_id=NOCODB_VIEW_ID
            )
            logger.info("✅ Интеграция с NocoDB инициализирована (база студентов)")
        except Exception as e:
            logger.error(f"❌ Не удалось инициализировать NocoDB: {e}")
            self.nocodb = None
        
        # Сохраняем ссылку для обратной совместимости (код может использовать self.airtable)
        self.airtable = self.nocodb
        
        # Интеграция с KPI Sheets (Фаза 2)
        try:
            self.kpi_sheets = create_kpi_sheets_integration()
            logger.info("✅ Интеграция с KPI Sheets (Фаза 2) инициализирована")
        except Exception as e:
            logger.error(f"❌ Не удалось инициализировать KPI Sheets: {e}")
            self.kpi_sheets = None
        
        # SLA/CSI модули
        try:
            self.sla_tracker = SLATracker()
            self.sla_sheets = SLASheetsIntegration()
            self.csi_scheduler = CSIScheduler(self.client, self.sheets_integration)
            self.training_dates_scheduler = TrainingDatesScheduler(self.sheets_integration)
            self.sla_reporter = SLAReporter(self.client, self.sla_sheets)
            logger.info("✅ SLA/CSI модули инициализированы")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации SLA/CSI: {e}")
            self.sla_tracker = None
            self.sla_sheets = None
            self.csi_scheduler = None
            self.training_dates_scheduler = None
            self.sla_reporter = None
            # Уведомляем руководителя о критической ошибке
            try:
                import asyncio
                asyncio.create_task(self.client.send_message(
                    VIP_HEAD['telegram_id'],
                    f"❌ **Критическая ошибка: SLA Tracker не инициализирован**\n\n"
                    f"Ошибка: {str(e)[:200]}\n\n"
                    f"⚠️ SLA-трекинг НЕ РАБОТАЕТ!\n"
                    f"Проверьте подключение к Google Sheets SLA."
                ))
            except:
                pass
        
        # Устанавливаем callback для принятия студента
        self.manager_queue.set_student_accepted_callback(self.on_manager_accepted_student)
        
        # Хранилище данных о студентах (getcourse_id -> student_data)
        self.students_data: Dict[str, Dict[str, Any]] = {}
        
        # Словарь для связи chat_id -> getcourse_id (для SLA)
        self.chat_to_student: Dict[int, str] = {}
        
        # Состояние диалога для выбора менеджера в отчётах
        # {user_id: {'command': '/bigreport', 'awaiting_manager': True}}
        self.report_dialog_state: Dict[int, Dict[str, Any]] = {}
        
        # Состояние для подтверждения рассылки
        # {user_id: {'text': str, 'target_chats': list, 'timestamp': datetime}}
        self.broadcast_confirmation_state: Dict[int, Dict[str, Any]] = {}
        
        # Состояние для выбора студента при активации чата
        # {manager_id: {'chat_id': int, 'getcourse_id': str, 'candidates': [user_objects], 'invite_link': str}}
        self.activate_student_selection_state: Dict[int, Dict[str, Any]] = {}
        
        # Словарь назначений менеджеров (нужен для /activate)
        self.manager_assignments: Dict[str, Dict[str, Any]] = {}
        
        # ID бота (user client) для фильтрации в /activate
        self.bot_user_id: Optional[int] = None
        
        # Хранилище для ожидающих уточнения /createtracker запросов
        self.pending_createtracker_clarifications: Dict[int, Dict[str, Any]] = {}  # {message_id: clarification_data}
        self.pending_tracker_overwrite_confirmations: Dict[int, Dict[str, Any]] = {}  # {manager_id: confirm_data}
        
        # Хранилище для ожидающих уточнения курса при /activate
        self.pending_activate_course_clarifications: Dict[int, Dict[str, Any]] = {}  # {manager_id: clarification_data}
        
        # Флаг для предотвращения повторной регистрации обработчиков
        self._handlers_registered = False
        
        # Дедупликация обработанных сообщений (ограничено 1000 элементами)
        self._processed_private_messages: set = set()
        
        # Rate-limit для приветственных сообщений в ЛС (предотвращает дубли)
        # {user_id: timestamp последнего приветствия}
        self._last_greeting_time: Dict[int, datetime] = {}
        
        # Время запуска бота - игнорируем сообщения старше этого времени (используем UTC)
        from datetime import timezone
        self._startup_time = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # Rate-limiting для уведомлений "чат не активирован" - предотвращает спам
        # {chat_id: last_warning_time} - отправляем не чаще раза в 30 минут
        self._unactivated_chat_warnings: Dict[int, datetime] = {}
        
        # Хранилище telegram_id студентов (для старых чатов)
        self.student_telegram_ids: Dict[str, int] = {}  # {getcourse_id: telegram_id}
        
        # Менеджер персистенции - сохраняет состояние при перезапусках
        try:
            self.persistence = get_persistence()
            # Устанавливаем канал уведомлений об ошибках персистенции
            self.persistence.set_notification_channel(self.client, VIP_HEAD['telegram_id'])
            logger.info("✅ Модуль персистенции инициализирован")
        except Exception as e:
            logger.error(f"❌ Не удалось инициализировать персистенцию: {e}")
            self.persistence = None
        
        # Инициализация менеджера ролей пользователей
        self.role_manager = UserRoleManager(self.sheets_integration)
        
        # Инициализация менеджера еженедельных напоминаний
        try:
            from weekly_reminders import WeeklyRemindersManager
            self.weekly_reminders = WeeklyRemindersManager(
                client=self.client,
                bot_client=self.bot_client,  # Используем Bot Client для кнопок
                nocodb_integration=self.nocodb
            )
            logger.info("✅ Модуль еженедельных напоминаний инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации еженедельных напоминаний: {e}")
            self.weekly_reminders = None
        
        # Инициализация авто-обновления касаний
        try:
            self.touch_updater = TouchAutoUpdater(
                nocodb_integration=self.nocodb,
                vipalina_sheets=self.sheets_integration
            )
            self.touch_updater.telethon_client = self.client  # Для уведомлений
            logger.info("✅ Модуль авто-обновления касаний инициализирован")
        except Exception as e:
            logger.error(f"❌ Не удалось инициализировать авто-обновление касаний: {e}")
            self.touch_updater = None
        
        # Инициализация сборщика месячных планов
        try:
            from monthly_plan_collector import MonthlyPlanCollector
            self.monthly_plan_collector = MonthlyPlanCollector()
            logger.info("✅ Модуль сбора месячных планов инициализирован")
        except Exception as e:
            logger.error(f"❌ Не удалось инициализировать сборщик месячных планов: {e}")
            self.monthly_plan_collector = None
        
        # Инициализация планировщика рассылки планов
        try:
            from monthly_plan_scheduler import MonthlyPlanScheduler
            self.monthly_plan_scheduler = MonthlyPlanScheduler(
                client=self.client,
                monthly_plan_collector=self.monthly_plan_collector,
                chat_to_student=self.chat_to_student,
                students_data=self.students_data
            )
            logger.info("✅ Планировщик рассылки месячных планов инициализирован")
        except Exception as e:
            logger.error(f"❌ Не удалось инициализировать планировщик: {e}")
            self.monthly_plan_scheduler = None
        
        logger.info("Инициализирован оркестратор автоматизации VIP-отдела")
    
    async def _preload_manager_entities(self):
        """
        Предзагружает entities всех VIP-менеджеров из VIP-чата отдела.
        Критично для добавления менеджеров в чаты студентов - без валидного access_hash
        InviteToChannelRequest не работает!
        """
        logger.info("🔄 Предзагрузка entities менеджеров из VIP-чата отдела...")
        
        # Собираем ID всех менеджеров, дежурных, руководителя
        all_manager_ids = set()
        manager_names = {}
        
        for m in VIP_MANAGERS_VIP + VIP_MANAGERS_LUXURY:
            all_manager_ids.add(m['telegram_id'])
            manager_names[m['telegram_id']] = m['name']
        for d in ON_DUTY_ACCOUNTS:
            all_manager_ids.add(d['telegram_id'])
            manager_names[d['telegram_id']] = d['name']
        all_manager_ids.add(VIP_HEAD['telegram_id'])
        manager_names[VIP_HEAD['telegram_id']] = VIP_HEAD['name']
        
        loaded = 0
        
        try:
            # Загружаем участников VIP-чата отдела
            from telethon.tl.functions.channels import GetParticipantsRequest
            from telethon.tl.types import ChannelParticipantsSearch
            
            participants = await self.client(GetParticipantsRequest(
                channel=VIP_DEPARTMENT_CHAT_ID,
                filter=ChannelParticipantsSearch(''),
                offset=0,
                limit=200,
                hash=0
            ))
            
            # Кешируем всех менеджеров из чата
            for user in participants.users:
                if user.id in all_manager_ids:
                    if self.entity_cache:
                        self.entity_cache.put_to_cache(user.id, user)
                    loaded += 1
                    name = manager_names.get(user.id, user.first_name)
                    logger.debug(f"   ✅ {name} (ID: {user.id})")
            
            logger.info(f"✅ Предзагрузка завершена: {loaded}/{len(all_manager_ids)} менеджеров загружено из VIP-чата")
            
            # Предупреждаем если не все загружены
            if loaded < len(all_manager_ids):
                missing = all_manager_ids - {u.id for u in participants.users if u.id in all_manager_ids}
                for mid in missing:
                    logger.warning(f"   ⚠️ {manager_names.get(mid, '?')} (ID: {mid}) не найден в VIP-чате!")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка предзагрузки из VIP-чата: {e}")
            logger.info("Пробуем альтернативный метод...")
            
            # Альтернативный метод: загрузка через get_entity
            for manager_id in all_manager_ids:
                try:
                    entity = await self.client.get_entity(manager_id)
                    if self.entity_cache:
                        self.entity_cache.put_to_cache(manager_id, entity)
                    loaded += 1
                except Exception as ex:
                    logger.warning(f"   ⚠️ Не удалось загрузить {manager_names.get(manager_id, '?')}: {ex}")
    
    async def _restore_state_from_persistence(self):
        """
        Восстанавливает состояние бота из Google Sheets после перезапуска.
        Загружает все сохраненные данные: студенты, чаты, назначения, SLA-запросы.
        """
        if not self.persistence or not self.persistence.is_initialized():
            logger.warning("⚠️ Персистенция не инициализирована, состояние не восстановлено")
            return
        
        try:
            logger.info("🔄 Восстановление состояния из Google Sheets...")
            
            # 1. Загружаем chat_to_student
            self.chat_to_student = self.persistence.load_all_chat_to_student()
            logger.info(f"   ✅ Загружено {len(self.chat_to_student)} связей chat_id -> getcourse_id")
            
            # 2. Загружаем students_data
            self.students_data = self.persistence.load_all_students_data()
            logger.info(f"   ✅ Загружено {len(self.students_data)} студентов")
            
            # 2.1. Строим student_telegram_ids из students_data для быстрого поиска
            self.student_telegram_ids = {}
            for getcourse_id, student_data in self.students_data.items():
                telegram_id = student_data.get('telegram_id')
                if telegram_id:
                    self.student_telegram_ids[getcourse_id] = telegram_id
            logger.info(f"   ✅ Построено {len(self.student_telegram_ids)} маппингов getcourse_id -> telegram_id")
            
            # 3. Загружаем индексы очередей менеджеров
            queue_indices = self.persistence.load_queue_indices()
            self.manager_queue.current_vip_index = queue_indices.get('vip', 0)
            self.manager_queue.current_luxury_index = queue_indices.get('luxury', 0)
            logger.info(f"   ✅ Восстановлены индексы очередей: VIP={queue_indices.get('vip', 0)}, Luxury={queue_indices.get('luxury', 0)}")
            
            # 4. Загружаем назначения менеджеров
            assignments_data = self.persistence.load_all_manager_assignments()
            # Получаем ID уже зарегистрированных студентов из "Общий список new" колонка A
            enrolled_ids: set = set()
            if self.kpi_sheets:
                try:
                    enrolled_ids = await self.kpi_sheets.get_all_enrolled_ids()
                except Exception as _e:
                    logger.warning(f"⚠️ Не удалось загрузить enrolled_ids из KPI Sheets: {_e}")
            from manager_queue import ManagerAssignment
            from datetime_utils import get_moscow_now
            skipped_stale = 0
            for getcourse_id, data in assignments_data.items():
                # Если ID студента есть в "Общий список new" — он уже заведён, чистим
                if str(getcourse_id) in enrolled_ids:
                    try:
                        self.persistence.delete_manager_assignment(getcourse_id)
                    except Exception:
                        pass
                    skipped_stale += 1
                    continue
                self.manager_queue.assignments[getcourse_id] = ManagerAssignment(
                    student_getcourse_id=getcourse_id,
                    manager_id=data.get('manager_id', 0),
                    manager_name=data.get('manager_name', ''),
                    course_tag=data.get('course_tag', ''),
                    timestamp=get_moscow_now(),
                    status=data.get('status', 'pending'),
                    student_name=data.get('student_name', 'Unknown'),
                    student_telegram=data.get('student_telegram', ''),
                    student_telegram_id=data.get('student_telegram_id')
                )
            loaded_count = len(assignments_data) - skipped_stale
            logger.info(f"   ✅ Загружено {loaded_count} активных назначений (пропущено {skipped_stale} уже онбордированных)")
            
            # 5. Загружаем активные SLA-запросы и очищаем "мёртвые"
            if self.sla_tracker:
                self.sla_tracker.active_requests = self.persistence.load_all_sla_requests()
                total_before = sum(len(students) for students in self.sla_tracker.active_requests.values())
                logger.info(f"   ✅ Загружено {total_before} активных SLA-запросов из Google Sheets")
                
                # Очищаем "мёртвые" SLA-запросы (менеджер уже ответил, но запись не удалилась)
                if self.sla_sheets and self.sla_tracker.active_requests:
                    cleaned = await self._cleanup_stale_sla_requests()
                    if cleaned > 0:
                        total_after = sum(len(students) for students in self.sla_tracker.active_requests.values())
                        logger.info(f"   🧹 Очищено {cleaned} 'мёртвых' SLA-запросов (осталось {total_after})")
            
            # 6. Загружаем активные онбординги
            if self.onboarding_tracker:
                self.onboarding_tracker.load_from_persistence()
                logger.info(f"   ✅ Загружено {len(self.onboarding_tracker.tracking_data)} активных онбордингов")
            
            logger.info("✅ Состояние успешно восстановлено из Google Sheets!")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при восстановлении состояния: {e}", exc_info=True)
    
    async def _cleanup_stale_sla_requests(self) -> int:
        """
        Очищает 'мёртвые' SLA-запросы при старте бота.
        
        Сравнивает Active_SLA_Requests с SLA_Data:
        если в SLA_Data есть запись о том, что менеджер уже ответил на запрос,
        то удаляем его из Active_SLA_Requests.
        
        Returns:
            Количество очищенных запросов
        """
        try:
            logger.info("🔍 Проверка 'мёртвых' SLA-запросов...")
            
            # Загружаем все закрытые SLA из SLA_Data
            sla_data_rows = []
            try:
                sla_ws = self.sla_sheets.worksheet
                if sla_ws:
                    sla_data_rows = await asyncio.to_thread(sla_ws.get_all_values)
            except Exception as e:
                logger.warning(f"Не удалось загрузить SLA_Data: {e}")
                return 0
            
            if not sla_data_rows or len(sla_data_rows) <= 1:
                logger.info("✅ SLA_Data пуста, нет записей для сверки")
                return 0
            
            # Строим множество закрытых запросов: (chat_id, student_id)
            closed_requests = set()
            for row in sla_data_rows[1:]:
                if len(row) >= 11:
                    # Колонки SLA_Data (0-based):
                    # 0=date, 1=time, 2=student_name, 3=getcourse_id, 4=manager,
                    # 5=response_time, 6=response_duration, 7=is_working_hours,
                    # 8=sla_met, 9=chat_id, 10=student_id, 11=manager_id, ...
                    chat_id_str = row[9].strip() if len(row) > 9 else ""
                    student_id_str = row[10].strip() if len(row) > 10 else ""
                    
                    if chat_id_str and student_id_str:
                        try:
                            chat_id = int(chat_id_str)
                            student_id = int(student_id_str)
                            closed_requests.add((chat_id, student_id))
                        except ValueError:
                            pass
            
            if not closed_requests:
                logger.info("✅ Нет закрытых SLA-записей для сверки")
                return 0
            
            logger.info(f"📊 Найдено {len(closed_requests)} закрытых SLA-записей в SLA_Data")
            
            # Проверяем каждый активный запрос
            cleaned = 0
            to_delete = []
            
            for chat_id, students in self.sla_tracker.active_requests.items():
                for student_id, request_data in students.items():
                    if (chat_id, student_id) in closed_requests:
                        # Этот запрос уже закрыт - помечаем на удаление
                        to_delete.append((chat_id, student_id))
            
            # Удаляем "мёртвые" запросы
            for chat_id, student_id in to_delete:
                try:
                    # Удаляем из Google Sheets
                    if self.persistence and self.persistence.is_initialized():
                        self.persistence.delete_sla_request(chat_id, student_id)
                    
                    # Удаляем из памяти
                    if chat_id in self.sla_tracker.active_requests:
                        if student_id in self.sla_tracker.active_requests[chat_id]:
                            del self.sla_tracker.active_requests[chat_id][student_id]
                        if not self.sla_tracker.active_requests[chat_id]:
                            del self.sla_tracker.active_requests[chat_id]
                    
                    cleaned += 1
                    logger.info(f"   🧹 Удалён 'мёртвый' SLA: chat={chat_id}, student={student_id}")
                except Exception as e:
                    logger.error(f"Ошибка при удалении SLA {chat_id}/{student_id}: {e}")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Ошибка при очистке 'мёртвых' SLA: {e}", exc_info=True)
            return 0

    def _get_user_role(self, user_id: int) -> str:
        """
        Определяет роль пользователя по его ID.
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            Роль пользователя: "vip_manager", "vip_student", "on_duty", "head" или "unauthorized"
        """
        return self.role_manager.get_user_role(user_id)
    
    async def _forward_message_to_manager(self, event, user, user_role, message_text):
        """Пересылает сообщение VIP-менеджеру"""
        try:
            user_id = user.id
            logger.info(f"Пересылаю сообщение от {user_id} ({user_role}) VIP-менеджерам")
            
            # Отправляем уведомление пользователю
            await event.reply("Ваш запрос передан VIP-менеджеру. Ожидайте ответа.")
            
            # Отправляем уведомление всем VIP-менеджерам
            notification = f"Новый запрос от VIP-студента @{user.username or user.first_name} (ID: {user_id}):\n\n{message_text}"
            for manager_id in ALL_MANAGER_IDS:
                try:
                    await self.client.send_message(manager_id, notification)
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления менеджеру {manager_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Ошибка при пересылке сообщения менеджеру: {e}", exc_info=True)
    
    async def _handle_vip_student_message(self, event, user, message_text, category, confidence):
        """Обработчик сообщений от VIP-студентов с функционалом Telethon"""
        try:
            user_id = user.id
            logger.info(f"Обработка сообщения от VIP-студента {user_id}: {message_text[:50]}...")
            
            # Формируем персонализированный ответ в зависимости от категории
            response = f"🤖 Привет, {user.first_name}! Я Vipalina - ваш помощник в VIP-программе.\n\n"
            
            if category == "course_inquiry":
                response += "🎓 Я могу предоставить информацию о VIP-курсах.\n\n"
                # Здесь можно добавить логику поиска курсов через RAG систему
                response += "Пожалуйста, уточните, какой курс вас интересует?"
            elif category == "payment_inquiry":
                response += "💳 По вопросам оплаты рекомендую обратиться к вашему VIP-менеджеру.\n\n"
                response += "Если у вас срочный вопрос по оплате, я могу передать его менеджеру."
            elif category == "technical_support":
                response += "🛠 По техническим вопросам рекомендую обратиться к вашему VIP-менеджеру.\n\n"
                response += "Если у вас срочный технический вопрос, я могу передать его менеджеру."
            elif category == "general_inquiry":
                response += "ℹ️ Я получил ваш запрос и передал его вашему VIP-менеджеру.\n\n"
                response += "Ожидайте ответа в ближайшее время."
            else:
                response += f"Категория вашего запроса: {category}\n"
                response += f"Уверенность: {confidence:.2f}\n\n"
                response += "Ваш запрос будет передан VIP-менеджеру."
            
            await event.reply(response)
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения студента: {e}", exc_info=True)
            await event.reply("❌ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.")
    

    
    async def start(self):
        """Запускает все модули автоматизации"""
        logger.info("Запуск автоматизации VIP-отдела...")
        
        # Защита от повторной регистрации обработчиков
        if self._handlers_registered:
            logger.warning("⚠️ Обработчики уже зарегистрированы, пропускаем повторную регистрацию")
            return
        
        # ПРЕДЗАГРУЗКА ENTITIES МЕНЕДЖЕРОВ - критично для добавления в чаты!
        await self._preload_manager_entities()
        
        # Восстанавливаем состояние из Google Sheets
        await self._restore_state_from_persistence()
        
        # Обработчик личных сообщений для Telethon-аккаунта
        @self.client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and not e.is_group))
        async def handle_private_message(event):
            try:
                # ИГНОРИРУЕМ сообщения отправленные ДО запуска бота (предотвращаем обработку старых сообщений)
                if event.message.date.replace(tzinfo=None) < self._startup_time:
                    return
                
                # Дедупликация: пропускаем уже обработанные сообщения
                msg_id = event.message.id
                if msg_id in self._processed_private_messages:
                    return
                
                # Ограничиваем размер кеша
                if len(self._processed_private_messages) > 1000:
                    self._processed_private_messages.clear()
                self._processed_private_messages.add(msg_id)
                
                sender = await event.get_sender()
                user_id = sender.id
                username = sender.username or "Нет username"
                message_text = event.message.text if event.message.text else "[медиа/стикер]"
                
                # Пропускаем команды (проверяем до других проверок)
                if message_text and message_text.strip().startswith('/'):
                    return
                
                # Если сейчас идёт диалог формирования отчёта — НЕ шлём приветствие
                if user_id in self.report_dialog_state:
                    logger.info(f"ℹ️ Пропускаем приветствие для {user_id} — активен диалог отчёта")
                    return
                
                # Если идёт диалог выбора студента при /activate — НЕ шлём приветствие
                if user_id in self.activate_student_selection_state:
                    logger.info(f"ℹ️ Пропускаем приветствие для {user_id} — активен диалог /activate")
                    return
                
                # Если ожидается ответ да/нет на перезапись трекера — НЕ шлём приветствие
                if user_id in self.pending_tracker_overwrite_confirmations:
                    logger.info(f"ℹ️ Пропускаем приветствие для {user_id} — ожидается ответ на перезапись трекера")
                    return
                
                logger.info(f"📨 Личное сообщение от {username} (ID: {user_id}): {message_text}")

                # Rate-limit: не отвечаем приветствием чаще раза в 60 секунд
                last_greet = self._last_greeting_time.get(user_id)
                if last_greet and (datetime.now() - last_greet).total_seconds() < 60:
                    logger.info(f"ℹ️ Пропускаем дубль приветствия для {user_id} (rate-limit)")
                    raise events.StopPropagation
                
                # Только менеджерам/руководителю показываем служебный ответ
                if not self._is_vip_manager(user_id) and user_id not in HEAD_IDS:
                    self._last_greeting_time[user_id] = datetime.now()
                    await event.reply(
                        "👋 Здравствуйте!\n\nЕсли у вас есть вопросы по обучению, обратитесь к своему VIP-менеджеру в чат обучения."
                    )
                    raise events.StopPropagation

                # Ответ для сотрудников VIP-отдела
                response = """👋 Привет! Я Випалина - бот для автоматизации VIP-отдела.
Используй `/help` чтобы увидеть доступные команды."""

                self._last_greeting_time[user_id] = datetime.now()
                await event.reply(response, parse_mode='md')
                # Останавливаем дальнейшую обработку другими обработчиками
                raise events.StopPropagation
                
            except events.StopPropagation:
                raise  # Пропускаем StopPropagation
            except Exception as e:
                logger.error(f"❌ Ошибка обработки личного сообщения: {e}", exc_info=True)
        
        logger.info("✅ Обработчик личных сообщений (User Client) зарегистрирован")
        
        # Обработчик команды /start для Bot Client
        @self.bot_client.on(events.NewMessage(incoming=True, pattern='/start', func=lambda e: e.is_private))
        async def handle_bot_start(event):
            try:
                sender = await event.get_sender()
                user_id = sender.id
                username = sender.username or "Нет username"
                
                logger.info(f"📨 /start от {username} (ID: {user_id}) в Bot Client")
                
                # Определяем кто пишет
                is_manager = user_id in [m['telegram_id'] for m in VIP_MANAGERS_VIP + VIP_MANAGERS_LUXURY]
                is_head = user_id in HEAD_IDS
                is_duty = user_id in [acc['telegram_id'] for acc in ON_DUTY_ACCOUNTS]
                
                if is_manager or is_head or is_duty:
                    # Ответ менеджерам/руководителю
                    response = f"""🤖 Привет! Я @zerocoder_ultralina_bot — Bot Client для автоматизации VIP-отдела.

✅ Что я делаю:
• Отправлю уведомления о новых студентах с inline-кнопками
• Обрабатываю нажатия на кнопки "Принять", "Пропустить", "Не заводим"
• Работаю вместе с User Client @ultralina_zerocoder

🔹 Твой ID: {user_id}
🔹 Роль: {'Руководитель' if is_head else 'Дежурный' if is_duty else 'Менеджер'}

Используй кнопки под сообщениями о новых студентах для управления онбордингом."""
                    
                    await event.reply(response)
                else:
                    # Ответ для всех остальных пользователей (студентов и неавторизованных)
                    response = """👋 Здравствуйте!

Я @zerocoder_ultralina_bot — бот для автоматизации работы VIP-отдела Zerocoder University.

Если у вас есть вопросы по обучению, обратитесь к своему VIP-менеджеру в чат обучения."""
                    await event.reply(response)
                logger.info(f"✅ Ответ на /start отправлен пользователю {user_id}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки /start в Bot Client: {e}", exc_info=True)
        
        logger.info("✅ Обработчик /start для Bot Client зарегистрирован")
        
        # Обработчик /oauth для Bot Client (уведомления приходят от него)
        @self.bot_client.on(events.NewMessage(incoming=True, pattern=r'/oauth', func=lambda e: e.is_private))
        async def handle_bot_oauth_command(event):
            """Генерирует ссылку для авторизации Google OAuth"""
            try:
                sender_id = event.sender_id
                logger.info(f"📨 /oauth от {sender_id} в Bot Client")
                
                # Только для руководителя VIP-отдела
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Эта команда доступна только руководителю VIP-отдела.")
                    return
                
                # Проверяем, есть ли уже код в сообщении
                message_text = event.message.text.strip()
                parts = message_text.split(maxsplit=1)
                
                if len(parts) > 1:
                    # Передан код авторизации: /oauth КОД
                    code = parts[1].strip()
                    success, message = oauth_handler.exchange_code(sender_id, code)
                    # ВАЖНО: перезагружаем credentials в TrackerCreator из нового файла на диске,
                    # иначе он продолжает использовать старый in-memory токен до следующего рестарта
                    if success and self.tracker_creator:
                        try:
                            await asyncio.to_thread(self.tracker_creator._authorize)
                            logger.info("✅ TrackerCreator переавторизован с новым OAuth токеном")
                            message += "\n\n🔄 TrackerCreator перезагружен с новым токеном."
                        except Exception as reinit_err:
                            logger.error(f"⚠️ Не удалось переавторизовать TrackerCreator: {reinit_err}")
                            message += f"\n\n⚠️ Не удалось перезагрузить TrackerCreator: {reinit_err}"
                    await event.reply(message)
                else:
                    # Генерируем URL авторизации
                    auth_url, error = oauth_handler.generate_auth_url(sender_id)
                    
                    if error:
                        await event.reply(error)
                        return
                    
                    message = f"""🔐 **Авторизация Google OAuth**

1. Перейдите по ссылке:
{auth_url}

2. Войдите в аккаунт `vipzerocoder@gmail.com`

3. Разрешите доступ к Google Drive и Sheets

4. Скопируйте код авторизации со страницы

5. Отправьте мне код командой:
`/oauth ВАШ_КОД`"""
                    
                    await event.reply(message)
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке /oauth в Bot Client: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        logger.info("✅ Обработчик /oauth для Bot Client зарегистрирован")
        
        # Настраиваем мониторинг чата VIP-отдела
        self.chat_monitor.setup_monitor(self.on_new_student_detected)
        
        # Настраиваем обработчик сообщений #этокурс и ответов на уточнения в чате VIP-отдела
        if self.unknown_course_handler:
            @self.client.on(events.NewMessage(chats=VIP_DEPARTMENT_CHAT_ID, incoming=True))
            async def handle_course_mapping_message(event):
                """Обработчик сообщений с #этокурс и ответов на уточнения"""
                try:
                    # Обработка сообщений с #этокурс (для неизвестных курсов)
                    if event.message and event.message.text and '#этокурс' in event.message.text.lower():
                        await self.unknown_course_handler.process_mapping_response(event.message)
                    
                    # Обработка ответов на уточнения (для неоднозначных курсов)
                    elif event.message and hasattr(event.message, 'reply_to_msg_id') and event.message.reply_to_msg_id:
                        await self.unknown_course_handler.handle_clarification_response(event.message)
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке сообщения в VIP-чате: {e}", exc_info=True)
            
            logger.info("✅ Обработчик #этокурс и уточнений курсов зарегистрирован")
        
        # Обработчик ответов на коррекцию данных онбординга в VIP-чате (через userbot)
        @self.client.on(events.NewMessage(chats=VIP_DEPARTMENT_CHAT_ID, incoming=True))
        async def handle_correction_reply_in_vip_chat(event):
            """Обработчик ответов на запрос коррекции данных студента в VIP-чате."""
            try:
                if not event.message.is_reply or not event.message.reply_to_msg_id:
                    return
                
                reply_to_msg_id = event.message.reply_to_msg_id
                
                if not self.onboarding_module or reply_to_msg_id not in self.onboarding_module.pending_corrections:
                    return
                
                response_text = event.message.text if event.message.text else ""
                logger.info(f"📨 Обнаружен ответ на запрос коррекции (message_id={reply_to_msg_id})")
                corrected_data = await self.onboarding_module.handle_correction_reply(reply_to_msg_id, response_text)
                
                if corrected_data:
                    logger.info(f"✅ Данные исправлены, продолжаем онбординг студента {corrected_data.get('name')}")
                    
                    correction_context = self.onboarding_module.pending_corrections.get(reply_to_msg_id, {})
                    manager_id = correction_context.get('manager_id')
                    manager_name = correction_context.get('manager_name', 'Unknown')
                    
                    if not manager_id:
                        logger.error(f"❌ Не найден manager_id в контексте коррекции для message_id={reply_to_msg_id}")
                        return
                    
                    logger.info(f"👩‍💼 Используем оригинального менеджера: {manager_name} (ID: {manager_id})")
                    
                    await self.onboarding_module.onboard_student(
                        student_data=corrected_data,
                        manager_id=manager_id,
                        manager_name=manager_name
                    )
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке коррекции в VIP-чате: {e}", exc_info=True)
        
        logger.info("✅ Обработчик коррекции онбординга в VIP-чате зарегистрирован")
        
        # Настраиваем обработчик ответов на уточнения в личных сообщениях для /createtracker
        @self.client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def handle_private_clarification_response(event):
            """Обработчик ответов менеджера на уточнения курса в ЛС"""
            try:
                # ИГНОРИРУЕМ сообщения отправленные ДО запуска бота
                if event.message.date.replace(tzinfo=None) < self._startup_time:
                    return
                
                sender_id = event.sender_id

                # 0. Ожидающее подтверждение да/нет на перезапись трекера
                if sender_id in self.pending_tracker_overwrite_confirmations:
                    answer = (event.raw_text or '').strip().lower()
                    if answer in ('да', 'нет', 'yes', 'no', 'y', 'n'):
                        conf = self.pending_tracker_overwrite_confirmations.pop(sender_id)
                        if answer in ('да', 'yes', 'y'):
                            await event.reply(f"⏳ Создаю новый трекер для {conf['student_name']}...")
                            await self._run_createtracker_flow(
                                manager_id=sender_id,
                                getcourse_id=conf['getcourse_id'],
                                student_name=conf['student_name'],
                                course_tag=conf['course_tag'],
                                manager_name=conf['manager_name'],
                                row_number=conf['row_number'],
                            )
                        else:
                            await event.reply("✅ Отменено. Существующий трекер сохранён.")
                        return


                # Проверяем, есть ли ожидающее уточнение для /activate
                if sender_id in self.pending_activate_course_clarifications:
                    handled = await self._handle_activate_course_clarification_response(event.message)
                    if handled:
                        logger.info("✅ Обработан ответ на уточнение курса для /activate")
                        return

                # Проверяем, что это ответ на сообщение
                if hasattr(event.message, 'reply_to_msg_id') and event.message.reply_to_msg_id:
                    # Пытаемся обработать как ответ на уточнение /createtracker
                    handled = await self._handle_createtracker_clarification_response(event.message)
                    if handled:
                        logger.info("✅ Обработан ответ на уточнение курса для /createtracker")
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке ответа в личных сообщениях: {e}", exc_info=True)
        
        logger.info("✅ Обработчик уточнений /createtracker в ЛС зарегистрирован")
        
        # Настраиваем обработчик callback-запросов для менеджера очереди
        # ВАЖНО: Используем bot_client, т.к. кнопки отправляются от Bot Client!
        self.manager_queue.setup_callback_handler(self.bot_client)
        
        # Настраиваем обработчик кнопок касаний (на Bot Client!)
        if self.nocodb:
            setup_touch_buttons_handler(self.bot_client, self.nocodb)
            logger.info("✅ Обработчик кнопок касаний зарегистрирован")
        
        # Обработчик ссылок на чаты в ЛС боту (@zerocoder_ultralina_bot)
        @self.bot_client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def handle_kpi_chat_link_message(event):
            """VIP-менеджер/дежурный/руководитель шлёт ссылку на чат → меню статусов KPI."""
            try:
                # Фильтруем по правам
                sender_id = event.sender_id
                if sender_id not in ALL_MANAGER_IDS:
                    return
                
                text = event.raw_text or ""
                if "t.me/" not in text:
                    return
                
                import re as _re
                match = _re.search(r"(https://t\.me/\S+)", text)
                if not match:
                    return
                invite_link = match.group(1).strip()
                
                from shared_gspread_client import get_shared_gspread_client
                import asyncio as _asyncio
                
                gc = get_shared_gspread_client()
                spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
                worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_KPI_TAB)
                all_data = await _asyncio.to_thread(worksheet.get_all_values)
                
                # Ищем по колонке G (index 6)
                matches = []
                for idx, row in enumerate(all_data[1:], start=2):
                    if len(row) > 6 and row[6].strip() == invite_link:
                        matches.append((idx, row))
                
                if not matches:
                    await event.reply("⚠️ Чат не найден в листе 'Общий список new' (колонка G).")
                    return
                
                row_index, row = matches[0]
                getcourse_id = row[0].strip() if len(row) > 0 else ""
                student_name = row[2].strip() if len(row) > 2 else ""
                manager_name = row[10].strip() if len(row) > 10 else ""
                
                # Формируем ссылку на GetCourse
                getcourse_url = f"https://university.zerocoder.ru/user/control/user/update/id/{getcourse_id}" if getcourse_id else ""
                
                text = (
                    f"Студент: {student_name or '-'}"\
                    f"\nМенеджер: {manager_name or '-'}"\
                    f"\nGetCourse ID: `{getcourse_id or '-'}`"
                )
                
                if getcourse_url:
                    text += f"\nGetCourse: {getcourse_url}"
                
                text += f"\nСтрока: {row_index}"
                
                buttons = [
                    [Button.inline("Поменять статус", data=f"kpi_action:change:{row_index}".encode())],
                    [Button.inline("Поменять менеджера", data=f"kpi_action:manager:{row_index}".encode())],
                    [Button.inline("Закрыть", data=b"kpi_action:close")],
                ]
                
                await event.reply(text, buttons=buttons)
            except Exception as e:
                logger.error(f"Ошибка обработки ссылки KPI: {e}", exc_info=True)
                try:
                    await event.reply(f"❌ Ошибка: {e}")
                except Exception:
                    pass
        
        # Обработчик ссылок GetCourse в ЛС боту (@zerocoder_ultralina_bot)
        @self.bot_client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def handle_getcourse_link_message(event):
            """VIP-менеджер/дежурный/руководитель шлёт ссылку на GetCourse → информация о студенте."""
            try:
                # Фильтруем по правам
                sender_id = event.sender_id
                if sender_id not in ALL_MANAGER_IDS:
                    return
                
                text = event.raw_text or ""
                
                # Проверяем наличие ссылки GetCourse (с https или без)
                if "university.zerocoder.ru/user/control/user/update/id/" not in text:
                    return
                
                import re as _re
                # Извлекаем ID из ссылки (с https:// или без)
                match = _re.search(r"(?:https?://)?university\.zerocoder\.ru/user/control/user/update/id/(\d+)", text)
                if not match:
                    return
                
                getcourse_id = match.group(1).strip()
                
                from shared_gspread_client import get_shared_gspread_client
                import asyncio as _asyncio
                
                gc = get_shared_gspread_client()
                spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
                worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_KPI_TAB)
                all_data = await _asyncio.to_thread(worksheet.get_all_values)
                
                # Ищем по колонке B (GetCourse URL, index 1)
                matches = []
                for idx, row in enumerate(all_data[1:], start=2):
                    if len(row) > 1 and getcourse_id in row[1]:
                        matches.append((idx, row))
                
                if not matches:
                    await event.reply(f"⚠️ Студент с GetCourse ID `{getcourse_id}` не найден в листе 'Общий список new'.")
                    return
                
                row_index, row = matches[0]
                student_name = row[2].strip() if len(row) > 2 else "-"
                course = row[3].strip() if len(row) > 3 else "-"
                manager_name = row[10].strip() if len(row) > 10 else "-"
                
                # Получаем последний доступный статус (колонка AX = Статус Февраль26, index 49)
                status = row[49].strip() if len(row) > 49 else "-"
                
                response_text = (
                    f"**Студент:** {student_name}\n"
                    f"**Курс:** {course}\n"
                    f"**Менеджер:** {manager_name}\n"
                    f"**Статус:** {status}\n"
                    f"**GetCourse ID:** `{getcourse_id}`\n"
                    f"**Строка:** {row_index}"
                )
                
                await event.reply(response_text)
                
            except Exception as e:
                logger.error(f"Ошибка обработки ссылки GetCourse: {e}", exc_info=True)
                try:
                    await event.reply(f"❌ Ошибка: {e}")
                except Exception:
                    pass
        
        @self.bot_client.on(events.CallbackQuery(pattern=b'^kpi_action:'))
        async def handle_kpi_action_callback(event):
            """Обработка кнопок 'Поменять статус' / 'Узнать ГК' / 'Закрыть'."""
            try:
                sender_id = event.sender_id
                if sender_id not in ALL_MANAGER_IDS:
                    await event.answer("Нет прав", alert=True)
                    return
                
                data = event.data.decode('utf-8')
                parts = data.split(':')
                if len(parts) < 2:
                    return
                action = parts[1]
                
                if action == 'close':
                    await event.edit("Меню закрыто.")
                    return
                
                if len(parts) < 3:
                    return
                row_index = int(parts[2])
                
                from shared_gspread_client import get_shared_gspread_client
                import asyncio as _asyncio
                
                gc = get_shared_gspread_client()
                spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
                worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_KPI_TAB)
                all_data = await _asyncio.to_thread(worksheet.get_all_values)
                
                if row_index <= 0 or row_index > len(all_data):
                    await event.answer("Строка не найдена", alert=True)
                    return
                
                row = all_data[row_index - 1]
                getcourse_id = row[0].strip() if len(row) > 0 else ""
                student_name = row[2].strip() if len(row) > 2 else ""
                manager_name = row[10].strip() if len(row) > 10 else ""
                
                if action == 'manager':
                    # Список менеджеров
                    managers = [
                        "Марина Иванова",
                        "Катя Пилипенко",
                        "Оля Антипанова",
                        "Кристина Махмудян",
                        "Не с нами",
                        "Дежурный",
                        "Лиза Виноградова",
                        "Катя Чайка",
                        "Оля Тихонова",
                    ]
                    buttons = []
                    for idx, mgr in enumerate(managers):
                        buttons.append([Button.inline(mgr, data=f"kpi_manager:{row_index}:{idx}".encode())])
                    
                    text = (
                        f"Студент: {student_name or '-'}"\
                        f"\nТекущий менеджер: {manager_name or '-'}"\
                        f"\nGetCourse ID: `{getcourse_id or '- '}`"\
                        "\nВыберите нового менеджера:"
                    )
                    await event.edit(text, buttons=buttons)
                    return
                
                if action == 'change':
                    from report_generator import get_report_generator
                    from datetime import datetime as _dt
                    
                    report_gen = get_report_generator()
                    now = _dt.now()
                    year = now.year
                    month = now.month
                    
                    month_configs = []
                    for offset in range(0, 3):
                        m = month - offset
                        y = year
                        if m <= 0:
                            m += 12
                            y -= 1
                        key = report_gen._get_month_key(m, y)
                        config = report_gen.MONTH_COLUMNS.get(key)
                        if config:
                            month_configs.append((key, config))
                    
                    if not month_configs:
                        await event.answer("Нет доступных месяцев", alert=True)
                        return
                    
                    buttons = []
                    for key, cfg in month_configs:
                        label = cfg['name']
                        buttons.append([Button.inline(label, data=f"kpi_month:{row_index}:{key}".encode())])
                    
                    text = (
                        f"Студент: {student_name or '-'}"\
                        f"\nGetCourse ID: `{getcourse_id or '- '}`"\
                        "\nВыберите месяц для изменения статуса:"
                    )
                    await event.edit(text, buttons=buttons)
            except Exception as e:
                logger.error(f"Ошибка callback kpi_action: {e}", exc_info=True)
                try:
                    await event.answer("Ошибка", alert=True)
                except Exception:
                    pass
        
        @self.bot_client.on(events.CallbackQuery(pattern=b'^kpi_month:'))
        async def handle_kpi_month_callback(event):
            """Выбор месяца → показываем список статусов."""
            try:
                sender_id = event.sender_id
                if sender_id not in ALL_MANAGER_IDS:
                    await event.answer("Нет прав", alert=True)
                    return
                
                data = event.data.decode('utf-8')
                parts = data.split(':')
                if len(parts) != 3:
                    return
                row_index = int(parts[1])
                month_key = int(parts[2])
                
                from report_generator import get_report_generator
                report_gen = get_report_generator()
                config = report_gen.MONTH_COLUMNS.get(month_key)
                if not config:
                    await event.answer("Месяц не найден", alert=True)
                    return
                
                # Строим кнопки статусов
                buttons = []
                for idx, status in enumerate(STATUS_OPTIONS):
                    buttons.append([
                        Button.inline(status, data=f"kpi_status:{row_index}:{month_key}:{idx}".encode())
                    ])
                
                text = (
                    f"Строка: {row_index}"\
                    f"\nМесяц: {config['name']}"\
                    "\nВыберите новый статус:"
                )
                await event.edit(text, buttons=buttons)
            except Exception as e:
                logger.error(f"Ошибка callback kpi_month: {e}", exc_info=True)
                try:
                    await event.answer("Ошибка", alert=True)
                except Exception:
                    pass
        
        @self.bot_client.on(events.CallbackQuery(pattern=b'^kpi_status:'))
        async def handle_kpi_status_callback(event):
            """Финальный выбор статуса → обновляем KPI Ultra."""
            try:
                sender_id = event.sender_id
                if sender_id not in ALL_MANAGER_IDS:
                    await event.answer("Нет прав", alert=True)
                    return
                
                data = event.data.decode('utf-8')
                parts = data.split(':')
                if len(parts) != 4:
                    return
                row_index = int(parts[1])
                month_key = int(parts[2])
                status_idx = int(parts[3])
                
                if status_idx < 0 or status_idx >= len(STATUS_OPTIONS):
                    await event.answer("Неизвестный статус", alert=True)
                    return
                new_status = STATUS_OPTIONS[status_idx]
                
                from report_generator import get_report_generator
                from shared_gspread_client import get_shared_gspread_client
                import asyncio as _asyncio
                
                report_gen = get_report_generator()
                config = report_gen.MONTH_COLUMNS.get(month_key)
                if not config:
                    await event.answer("Месяц не найден", alert=True)
                    return
                status_col_index = config['status']  # 0-based индекс в строке
                
                gc = get_shared_gspread_client()
                spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
                worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_KPI_TAB)
                all_data = await _asyncio.to_thread(worksheet.get_all_values)
                
                if row_index <= 0 or row_index > len(all_data):
                    await event.answer("Строка не найдена", alert=True)
                    return
                
                row = all_data[row_index - 1]
                getcourse_id = row[0].strip() if len(row) > 0 else ""
                student_name = row[2].strip() if len(row) > 2 else ""
                
                # Преобразуем индекс колонки в A1-нотацию
                col_number = status_col_index + 1
                def _col_to_letter(n: int) -> str:
                    s = ""
                    while n > 0:
                        n, r = divmod(n - 1, 26)
                        s = chr(65 + r) + s
                    return s
                col_letter = _col_to_letter(col_number)
                cell = f"{col_letter}{row_index}"
                
                await _asyncio.to_thread(worksheet.update, cell, [[new_status]])
                
                text = (
                    f"Статус обновлён."\
                    f"\nСтудент: {student_name or '-'}"\
                    f"\nGetCourse ID: `{getcourse_id or '- '}`"\
                    f"\nМесяц: {config['name']}"\
                    f"\nНовый статус: {new_status}"
                )
                await event.edit(text, buttons=None)
                await event.answer("Готово", alert=False)
            except Exception as e:
                logger.error(f"Ошибка callback kpi_status: {e}", exc_info=True)
                try:
                    await event.answer("Ошибка", alert=True)
                except Exception:
                    pass
        
        @self.bot_client.on(events.CallbackQuery(pattern=b'^kpi_manager:'))
        async def handle_kpi_manager_callback(event):
            """Финальный выбор менеджера → обновляем колонку K."""
            try:
                sender_id = event.sender_id
                if sender_id not in ALL_MANAGER_IDS:
                    await event.answer("Нет прав", alert=True)
                    return
                
                data = event.data.decode('utf-8')
                parts = data.split(':')
                if len(parts) != 3:
                    return
                row_index = int(parts[1])
                manager_idx = int(parts[2])
                
                managers = [
                    "Марина Иванова",
                    "Катя Пилипенко",
                    "Оля Антипанова",
                    "Кристина Махмудян",
                    "Не с нами",
                    "Дежурный",
                    "Лиза Виноградова",
                    "Катя Чайка",
                    "Оля Тихонова",
                ]
                
                if manager_idx < 0 or manager_idx >= len(managers):
                    await event.answer("Неизвестный менеджер", alert=True)
                    return
                new_manager = managers[manager_idx]
                
                from shared_gspread_client import get_shared_gspread_client
                import asyncio as _asyncio
                
                gc = get_shared_gspread_client()
                spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
                worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_KPI_TAB)
                all_data = await _asyncio.to_thread(worksheet.get_all_values)
                
                if row_index <= 0 or row_index > len(all_data):
                    await event.answer("Строка не найдена", alert=True)
                    return
                
                row = all_data[row_index - 1]
                getcourse_id = row[0].strip() if len(row) > 0 else ""
                student_name = row[2].strip() if len(row) > 2 else ""
                
                # Колонка K = индекс 10 (0-based)
                cell = f"K{row_index}"
                await _asyncio.to_thread(worksheet.update, cell, [[new_manager]])
                
                text = (
                    f"Менеджер обновлён."\
                    f"\nСтудент: {student_name or '-'}"\
                    f"\nGetCourse ID: `{getcourse_id or '- '}`"\
                    f"\nНовый менеджер: {new_manager}"
                )
                await event.edit(text, buttons=None)
                await event.answer("Готово", alert=False)
            except Exception as e:
                logger.error(f"Ошибка callback kpi_manager: {e}", exc_info=True)
                try:
                    await event.answer("Ошибка", alert=True)
                except Exception:
                    pass
        
        # Настраиваем обработчики команд /принять и /пропустить
        self._setup_command_handlers()
        
        # Настраиваем AI-анализ сообщений от студентов
        # DISABLED: from vip_automation_main import setup_ai_message_handler
        # DISABLED: await setup_ai_message_handler(self)
        
        # Устанавливаем подсказки команд для User Client
        await self._setup_bot_commands()
        
        # Настраиваем модуль ручного добавления студентов
        self.manual_add_module.setup_handlers(self.on_manual_student_added)
        
        # Настраиваем SLA-трекинг в групповых чатах
        if self.sla_tracker:
            self._setup_sla_tracking()
        
        # Запускаем CSI планировщик
        if self.csi_scheduler:
            await self.csi_scheduler.start()
            logger.info("✅ CSI-планировщик запущен")
        
        # Запускаем SLA репортер
        if self.sla_reporter:
            await self.sla_reporter.start()
            logger.info("✅ SLA-репортер запущен")
        
        # Планировщик обновления дат обучения ОТКЛЮЧЕН (используются формулы IMPORTRANGE)
        # if self.training_dates_scheduler:
        #     await self.training_dates_scheduler.start()
        #     logger.info("✅ Планировщик обновления дат обучения запущен")
        
        # Запускаем ежедневные напоминания
        if self.weekly_reminders:
            await self.weekly_reminders.start_weekly_reminders()
            logger.info("✅ Ежедневные напоминания запущены (Пн-Пт в 11:30 МСК)")
        
        logger.info("Автоматизация VIP-отдела успешно запущена!")
        logger.info(f"Мониторинг чата: {VIP_DEPARTMENT_CHAT_ID}")
        logger.info(f"Количество менеджеров в очереди: {len(VIP_MANAGERS_VIP) + len(VIP_MANAGERS_LUXURY)}")
        logger.info("Доступна команда /addnew для ручного добавления студентов")
        logger.info("Доступна команда #обновитьинфу для руководителя VIP-отдела")
        logger.info("✅ SLA-трекинг активирован для групповых чатов")
        logger.info("✅ Бот реагирует ТОЛЬКО на новых студентов в реальном времени")
        logger.info("✅ Персистенция активна - состояние сохраняется в Google Sheets")
        logger.info("✅ Даты обучения синхронизируются через IMPORTRANGE")
        
        # Записываем событие запуска
        if self.persistence and self.persistence.is_initialized():
            self.persistence.log_event(
                'startup',
                'Бот VipAlina запущен',
                {'chat_to_student_count': len(self.chat_to_student), 'students_count': len(self.students_data)}
            )
        
        # Отмечаем что обработчики зарегистрированы
        self._handlers_registered = True
        logger.info("✅ Все обработчики успешно зарегистрированы")
    
    async def on_new_student_detected(self, student: StudentData):
        """
        Callback, вызывается когда обнаружен новый студент.
        
        Args:
            student: Данные о студенте
        """
        try:
            logger.info(f"Обнаружен новый VIP-студент: {student.name}")
            
            # Проверяем, является ли это тестовым пользователем
            from config import TEST_STUDENT
            is_test_student = (
                student.getcourse_id == TEST_STUDENT['getcourse_id'] or
                str(student.telegram_id) == str(TEST_STUDENT['telegram_id']) or
                student.email == TEST_STUDENT['email']
            )
            
            if is_test_student:
                logger.info(f"🧪 Тестовый студент обнаружен: {student.name} - обрабатываем как нового (игнорируем проверки на дубликаты)")
            
            # Сохраняем данные студента
            if student.getcourse_id:  # Проверяем, что getcourse_id не None
                student_data = {
                    'name': student.name,
                    'getcourse_id': student.getcourse_id,
                    'getcourse_url': student.getcourse_url,
                    'email': student.email,
                    'phone': student.phone,
                    'course': student.course,
                    'telegram_username': student.telegram_username,
                    'telegram_id': student.telegram_id,
                    'is_test_student': is_test_student  # Флаг для тестового студента
                }
                
                self.students_data[student.getcourse_id] = student_data
                
                # Сохраняем в персистенцию
                if self.persistence and self.persistence.is_initialized():
                    self.persistence.save_student_data(student.getcourse_id, student_data)
                
                # Проверяем, является ли курс неизвестным или неоднозначным
                from course_config_v2 import CourseConfig
                
                # Пытаемся определить курс (новая логика с поддержкой неоднозначных курсов)
                course_data = CourseConfig.get_course_by_tag(student.course) if student.course else None
                
                if course_data is None and student.course:
                    # Проверяем, есть ли несколько кандидатов (неоднозначность)
                    if CourseConfig.has_ambiguous_course():
                        candidates = CourseConfig.get_ambiguous_candidates()
                        logger.warning(
                            f"⚠️ Найдено несколько вариантов курса для {student.course}: "
                            f"{[c.get('internal_name', c.get('kpi_name', 'Unknown')) for c in candidates]}"
                        )
                        
                        # Отправляем запрос уточнения в VIP-отдел
                        if self.unknown_course_handler:
                            await self.unknown_course_handler.handle_ambiguous_course(
                                student_data=student_data,
                                manager_id=VIP_HEAD['telegram_id'],
                                candidates=candidates
                            )
                            logger.info(f"📨 Запрос уточнения курса для '{student.course}' отправлен")
                        
                        # Очищаем состояние кандидатов
                        CourseConfig.clear_ambiguous_course()
                        return  # НЕ продолжаем онбординг до уточнения
                    
                    # Курс не найден и нет неоднозначных кандидатов - отправляем запрос на маппинг
                    # Пытаемся найти кандидатов по названию
                    candidates = CourseConfig.get_name_candidates_for_unknown(student.course)
                    
                    logger.warning(f"⚠️ Неизвестный курс: {student.course}")
                    
                    # Отправляем запрос на маппинг в чат VIP-отдела
                    if self.unknown_course_handler:
                        await self.unknown_course_handler.handle_unknown_course(
                            student_data=student_data,
                            manager_id=VIP_HEAD['telegram_id'],
                            candidates=candidates or None,
                        )
                        logger.info(f"📨 Запрос маппинга для курса '{student.course}' отправлен")
                        
                        # НЕ продолжаем онбординг до получения маппинга
                        return
                    else:
                        logger.error("❌ Обработчик неизвестных курсов не инициализирован")
                
                # Отправляем уведомление в VIP-чат с очередью менеджера
                success = await self.manager_queue.post_student_notification(student_data)
                
                if success:
                    logger.info(f"Уведомление о студенте {student.name} отправлено в VIP-чат")
                else:
                    logger.error(f"Не удалось отправить уведомление о студенте {student.name}")
            else:
                logger.error(f"Не удалось сохранить данные студента {student.name}: отсутствует getcourse_id")
                
        except Exception as e:
            logger.error(f"Ошибка при обработке нового студента: {e}", exc_info=True)
    
    async def start_onboarding_after_mapping(self, student_data: Dict[str, Any]):
        """
        Запускает онбординг после успешного маппинга курса.
        
        Args:
            student_data: Данные о студенте
        """
        try:
            logger.info(f"🚀 Запуск онбординга для студента {student_data.get('name')} после маппинга курса...")
            
            # Отправляем уведомление в VIP-чат с очередью менеджера
            success = await self.manager_queue.post_student_notification(student_data)
            
            if success:
                logger.info(f"✅ Уведомление о студенте {student_data.get('name')} отправлено в VIP-чат после маппинга")
            else:
                logger.error(f"❌ Не удалось отправить уведомление о студенте {student_data.get('name')}")
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске онбординга после маппинга: {e}", exc_info=True)
    
    async def on_manager_accepted_student(self, getcourse_id: str, manager_id: int):
        """
        Callback, вызывается когда менеджер принимает студента.
        
        Args:
            getcourse_id: ID студента в GetCourse
            manager_id: Telegram ID менеджера
        """
        try:
            logger.info(f"Менеджер {manager_id} приняла студента {getcourse_id}")
            
            # Получаем данные студента
            student_data = self.students_data.get(getcourse_id)
            if not student_data:
                logger.error(f"Не найдены данные студента {getcourse_id}")
                return
            
            # Преобразуем курс через CourseConfig для получения resolved названия
            from course_config_v2 import CourseConfig
            original_course = student_data.get('course', '')
            resolved_course = CourseConfig.get_kpi_course_name(original_course)
            if resolved_course != original_course:
                logger.info(f"📚 Курс преобразован: '{original_course}' -> '{resolved_course}'")
                student_data['course'] = resolved_course
                # Сохраняем обновленные данные
                self.students_data[getcourse_id] = student_data
                if self.persistence and self.persistence.is_initialized():
                    self.persistence.save_student_data(getcourse_id, student_data)
            
            # Получаем данные менеджера
            manager_info = self._get_manager_info(manager_id)
            if not manager_info:
                logger.error(f"Не найдена информация о менеджере {manager_id}")
                return
            
            # Начинаем отслеживание онбординга с Telegram ID и username
            await self.onboarding_tracker.start_tracking(
                student_name=student_data['name'],
                manager_name=manager_info['name'],
                getcourse_id=getcourse_id,
                telegram_id=student_data.get('telegram_id'),
                telegram_username=student_data.get('telegram_username')
            )
            
            # Выполняем онбординг студента
            onboarding_result = await self.onboarding_module.onboard_student(
                student_data=student_data,
                manager_id=manager_id,
                manager_name=manager_info['name']
            )
            
            if not onboarding_result:
                logger.error(f"Не удалось выполнить онбординг студента {getcourse_id}")
                
                # Проверяем, была ли ошибка приватности
                error_type = onboarding_result.get('error_type', 'unknown') if isinstance(onboarding_result, dict) else 'unknown'
                
                if error_type == 'privacy':
                    # Ошибка приватности - студент запретил добавлять в группы
                    await self.onboarding_tracker.update_step(
                        getcourse_id=getcourse_id,
                        step_name="chat_creation",
                        status="error",
                        error="Студент запретил добавлять себя в группы (настройки приватности)"
                    )
                    await self.onboarding_tracker.finish_tracking(getcourse_id, success=False)
                    
                    # Отправляем специальное уведомление менеджеру с инструкциями
                    await self._notify_privacy_error(
                        manager_id=manager_id,
                        student_name=student_data['name'],
                        student_username=student_data.get('telegram_username', 'неизвестно'),
                        getcourse_id=getcourse_id
                    )
                else:
                    # Общая ошибка онбординга
                    await self.onboarding_tracker.update_step(
                        getcourse_id=getcourse_id,
                        step_name="chat_creation",
                        status="error",
                        error="Не удалось создать чат"
                    )
                    await self.onboarding_tracker.finish_tracking(getcourse_id, success=False)
                    
                    # Уведомление об ошибке уже отображается в OnboardingTracker
                return
            
            # Обновляем трекер об успешном создании чата
            invite_link = onboarding_result.get('invite_link', '')
            chat_link_display = invite_link if invite_link else f"https://t.me/c/{str(onboarding_result['chat_id'])[4:]}"
            await self.onboarding_tracker.update_step(
                getcourse_id=getcourse_id,
                step_name="chat_creation",
                status="success",
                details=f"💬 Чат: [Перейти в чат]({chat_link_display})\n   🆔 ID: {onboarding_result['chat_id']}"
            )
            
            # Обновляем трекер об отправке приветственного сообщения
            welcome_sent = onboarding_result.get('welcome_message_sent', False)
            if welcome_sent:
                await self.onboarding_tracker.update_step(
                    getcourse_id=getcourse_id,
                    step_name="welcome_message",
                    status="success",
                    details="Приветственное сообщение отправлено"
                )
            else:
                await self.onboarding_tracker.update_step(
                    getcourse_id=getcourse_id,
                    step_name="welcome_message",
                    status="error",
                    error="Не удалось отправить приветственное сообщение"
                )
            
            # Сохраняем связь chat_id -> getcourse_id для SLA-трекинга и активации чата
            # ВАЖНО: Регистрируем чат ВСЕГДА, даже если SLA-трекер не инициализирован
            self.chat_to_student[onboarding_result['chat_id']] = getcourse_id
            logger.info(f"Чат {onboarding_result['chat_id']} привязан к студенту {getcourse_id}")
            
            # КРИТИЧНО ДЛЯ SLA: Добавляем студента в students_data и student_telegram_ids
            # Без этого SLA-трекинг не будет работать до рестарта!
            self.students_data[getcourse_id] = {
                'name': student_data.get('name', ''),
                'email': student_data.get('email', ''),
                'phone': student_data.get('phone', ''),
                'course': student_data.get('course', ''),
                'telegram_username': student_data.get('telegram_username', ''),
                'telegram_id': student_data.get('telegram_id'),
                'getcourse_url': student_data.get('getcourse_url', ''),
                'getcourse_id': getcourse_id
            }
            if student_data.get('telegram_id'):
                self.student_telegram_ids[getcourse_id] = student_data.get('telegram_id')
            logger.info(f"✅ Студент {getcourse_id} добавлен в память для SLA-трекинга (telegram_id={student_data.get('telegram_id')})")
            
            # Сохраняем в персистенцию с invite-ссылкой
            if self.persistence and self.persistence.is_initialized():
                self.persistence.save_chat_to_student_mapping(
                    chat_id=onboarding_result['chat_id'],
                    getcourse_id=getcourse_id,
                    student_name=student_data.get('name', ''),
                    invite_link=invite_link
                )
                
                # Сохраняем данные студента для SLA-трекинга при следующих рестартах
                self.persistence.save_student_data(
                    getcourse_id=getcourse_id,
                    student_data=self.students_data[getcourse_id]
                )
            
            # Если SLA-трекер не инициализирован, логируем предупреждение
            if not self.sla_tracker:
                logger.warning(f"⚠️ SLA-трекер не инициализирован, но чат {onboarding_result['chat_id']} зарегистрирован")
            
            # Интеграция с KPI Sheets ("Общий список new")
            if self.kpi_sheets:
                try:
                    # Получаем название курса для KPI
                    from course_config_v2 import CourseConfig
                    kpi_course_name = CourseConfig.get_kpi_course_name(student_data.get('course', ''))
                    
                    kpi_student_data = {
                        'getcourse_id': getcourse_id,
                        'getcourse_url': student_data.get('getcourse_url', ''),
                        'name': student_data.get('name', ''),
                        'course': kpi_course_name,
                        'manager_name': manager_info['name'],
                        'telegram_id': student_data.get('telegram_id')
                    }
                    
                    # Формируем URL для NocoDB (если синхронизация прошла успешно)
                    nocodb_url = None
                    if self.nocodb:
                        try:
                            # Получаем URL записи студента в NocoDB
                            student_record = await self.nocodb.find_student_by_getcourse_id(getcourse_id)
                            if student_record:
                                nocodb_url = student_record.get('record_url')
                                logger.info(f"✅ URL NocoDB для студента {getcourse_id}: {nocodb_url}")
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось получить URL NocoDB: {e}")
                    
                    # Tracker URL будет передан позже, после создания трекера
                    kpi_success = await self.kpi_sheets.add_student_to_kpi_sheet(
                        student_data=kpi_student_data,
                        invite_link=invite_link,
                        tracker_url=None,  # Будет обновлено позже
                        nocodb_url=nocodb_url
                    )
                    
                    if kpi_success:
                        logger.info(f"✅ Студент {getcourse_id} добавлен в KPI Sheets с invite-ссылкой")
                        await self.onboarding_tracker.update_step(
                            getcourse_id=getcourse_id,
                            step_name="kpi_sheets",
                            status="success",
                            details="Добавлен в 'Общий список new'"
                        )
                        
                        # Invite-ссылка уже была добавлена в add_student_to_kpi_sheet, дополнительное обновление не требуется
                    else:
                        logger.warning(f"⚠️ Не удалось добавить студента {getcourse_id} в KPI Sheets")
                        await self.onboarding_tracker.update_step(
                            getcourse_id=getcourse_id,
                            step_name="kpi_sheets",
                            status="error",
                            error="Ошибка при добавлении"
                        )
                except Exception as e:
                    logger.error(f"❌ Ошибка KPI Sheets: {e}", exc_info=True)
                    await self.onboarding_tracker.update_step(
                        getcourse_id=getcourse_id,
                        step_name="kpi_sheets",
                        status="error",
                        error=str(e)
                    )
            
            # Обновляем статус NocoDB (синхронизация менеджера)
            if self.nocodb:
                try:
                    sync_result = await self.nocodb.sync_after_manager_acceptance(
                        getcourse_id=getcourse_id,
                        manager_name=manager_info['name'],
                        bot_manager_name=manager_info['name']
                    )
                    if sync_result['success']:
                        await self.onboarding_tracker.update_step(
                            getcourse_id=getcourse_id,
                            step_name="nocodb",
                            status="success",
                            details="Менеджер обновлён в NocoDB"
                        )
                    else:
                        await self.onboarding_tracker.update_step(
                            getcourse_id=getcourse_id,
                            step_name="nocodb",
                            status="warning",
                            details=f"Не удалось обновить NocoDB: {sync_result.get('error', 'Unknown')}"
                        )
                except Exception as e:
                    logger.error(f"❌ Ошибка синхронизации с NocoDB: {e}", exc_info=True)
                    await self.onboarding_tracker.update_step(
                        getcourse_id=getcourse_id,
                        step_name="nocodb",
                        status="error",
                        error=str(e)
                    )
                    
                    # Уведомляем руководителя о NocoDB недоступности
                    try:
                        await self.client.send_message(
                            VIP_HEAD['telegram_id'],
                            f"❌ **NocoDB недоступен**\n\n"
                            f"Студент: {student_data.get('name', 'Неизвестно')}\n"
                            f"GetCourse ID: `{getcourse_id}`\n"
                            f"Менеджер: {manager_info['name']}\n\n"
                            f"Ошибка: {str(e)[:200]}\n\n"
                            f"🚨 Онбординг не может быть завершён."
                        )
                    except:
                        pass
            else:
                await self.onboarding_tracker.update_step(
                    getcourse_id=getcourse_id,
                    step_name="nocodb",
                    status="warning",
                    details="NocoDB не инициализирован"
                )
            
            # Создание трекера студента (если tracker_creator инициализирован)
            tracker_url = "-"
            if self.tracker_creator:
                try:
                    tracker_result = self.tracker_creator.create_tracker(
                        student_name=student_data.get('name', ''),
                        course_tag=student_data.get('course', ''),
                        manager_name=manager_info['name'],
                        getcourse_id=getcourse_id
                    )
                    
                    tracker_url = tracker_result['url']
                    
                    await self.onboarding_tracker.update_step(
                        getcourse_id=getcourse_id,
                        step_name="tracker_creation",
                        status="success",
                        details=f"[Открыть трекер]({tracker_url})"
                    )
                    
                    logger.info(f"✅ Трекер создан для студента {getcourse_id}: {tracker_url}")
                    
                    # Обновляем ссылку на трекер в KPI Sheets
                    if self.kpi_sheets:
                        try:
                            kpi_row = await self.kpi_sheets._find_student_row_in_kpi(getcourse_id)
                            if kpi_row:
                                await self.kpi_sheets.update_tracker_link(kpi_row, tracker_url)
                                logger.info(f"✅ Ссылка на трекер обновлена в KPI Sheets для студента {getcourse_id}")
                            else:
                                logger.warning(f"⚠️ Студент {getcourse_id} не найден в KPI Sheets для обновления ссылки на трекер")
                        except Exception as e:
                            logger.error(f"❌ Ошибка обновления ссылки на трекер в KPI Sheets: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"❌ Ошибка создания трекера для студента {getcourse_id}: {e}", exc_info=True)
                    await self.onboarding_tracker.update_step(
                        getcourse_id=getcourse_id,
                        step_name="tracker_creation",
                        status="error",
                        error=str(e)
                    )
                    
                    # Уведомляем руководителя о сбое создания трекера (от @zerocoder_ultralina_bot)
                    try:
                        await self.bot_client.send_message(
                            VIP_HEAD['telegram_id'],
                            f"❌ **Не удалось создать трекер**\n\n"
                            f"Студент: {student_data.get('name', 'Неизвестно')}\n"
                            f"GetCourse ID: `{getcourse_id}`\n"
                            f"Курс: {student_data.get('course', 'н/д')}\n\n"
                            f"Ошибка: {str(e)[:200]}\n\n"
                            f"🔧 Проверьте квоту Google Drive."
                        )
                    except:
                        pass
            else:
                # Обновляем статус создания трекера (если не было создано)
                await self.onboarding_tracker.update_step(
                    getcourse_id=getcourse_id,
                    step_name="tracker_creation",
                    status="warning",
                    details="Трекер не создан (необходимо создать вручную)"
                )
            
            await self.onboarding_tracker.finish_tracking(getcourse_id, success=True)
            
            # Сохраняем информацию в Google Sheets (В КОНЦЕ ОНБОРДИНГА)
            # Собираем все данные, даже если некоторые этапы не выполнились
            tracker_url = tracker_url if 'tracker_url' in locals() else "-"
            
            # Получаем правильное название курса для Випалина (не тег!)
            from course_config_v2 import CourseConfig
            resolved_course_name = CourseConfig.get_tracker_course_name(student_data.get('course', ''))
            logger.info(f"📝 Для Випалина курс: '{resolved_course_name}' (вместо тега '{student_data.get('course')}')")
            
            sheets_success = await self.sheets_integration.add_student_record(
                getcourse_id=getcourse_id,
                telegram_id=student_data.get('telegram_id') if student_data.get('telegram_id') else None,
                chat_id=onboarding_result.get('chat_id') if onboarding_result else None,
                student_data=student_data,
                manager_id=manager_id,
                manager_name=manager_info['name'],
                tracker_url=tracker_url,
                invite_link=invite_link if invite_link else '-',
                resolved_course_name=resolved_course_name  # Передаём правильное название
            )
            
            if sheets_success:
                logger.info(f"✅ Данные студента {getcourse_id} сохранены в лист 'Випалина'")
            else:
                logger.warning(f"⚠️ Не удалось сохранить данные студента {getcourse_id} в лист 'Випалина'")
            
            logger.info(f"Онбординг студента {student_data['name']} завершен успешно!")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке принятия студента {getcourse_id}: {e}", exc_info=True)
    
    async def on_manual_student_added(self, student: StudentData, manager_id: int):
        """
        Callback, вызывается когда менеджер добавляет студента вручную.
        
        Args:
            student: Данные студента
            manager_id: Telegram ID менеджера
        """
        try:
            logger.info(f"Менеджер {manager_id} добавила студента {student.name} вручную")
            
            # Проверяем, что у студента есть getcourse_id
            if not student.getcourse_id:
                logger.error(f"Не удалось добавить студента {student.name}: отсутствует getcourse_id")
                return
            
            # Сохраняем данные студента
            student_data = {
                'name': student.name,
                'getcourse_id': student.getcourse_id,
                'getcourse_url': student.getcourse_url,
                'email': student.email,
                'phone': student.phone,
                'course': student.course,
                'telegram_username': student.telegram_username,
                'telegram_id': student.telegram_id
            }
            
            self.students_data[student.getcourse_id] = student_data
            
            # Получаем данные менеджера
            manager_info = self._get_manager_info(manager_id)
            if not manager_info:
                logger.error(f"Не найдена информация о менеджере {manager_id}")
                return
            
            # Создаем назначение и сразу запускаем онбординг (без ожидания /принять)
            from manager_queue import ManagerAssignment
            from datetime import datetime, timedelta
            self.manager_queue.assignments[student.getcourse_id] = ManagerAssignment(
                student_getcourse_id=student.getcourse_id,
                manager_id=manager_id,
                manager_name=manager_info['name'],
                course_tag=student.course or '',
                timestamp=datetime.now(),
                status="accepted"
            )
            
            # Отправляем уведомление в VIP-чат (информационное, без кнопок)
            await self._notify_manual_addition(
                student_data=student_data,
                manager_name=manager_info['name']
            )
            
            logger.info(f"Студент {student.name} добавлен вручную менеджером {manager_info['name']}, запускаем онбординг...")
            
            # Сразу запускаем онбординг — как будто менеджер нажал /принять
            if self.manager_queue.on_student_accepted:
                try:
                    await self.manager_queue.on_student_accepted(student.getcourse_id, manager_id)
                except Exception as onb_err:
                    logger.error(f"Ошибка при запуске онбординга после ручного добавления: {onb_err}", exc_info=True)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке ручного добавления студента: {e}", exc_info=True)
    
    def _setup_command_handlers(self):
        """Настраивает обработчики команд /принять и /пропустить"""
        
        @self.client.on(events.NewMessage(pattern=r'/start'))
        async def handle_start_command(event):
            """Обработчик команды /start"""
            try:
                # Получаем информацию о пользователе
                user = await event.get_sender()
                user_id = user.id
                user_role = self._get_user_role(user_id)
                
                logger.info(f"Пользователь {user_id} ({user_role}) вызвал команду /start")
                
                # Формируем персонализированное приветствие в зависимости от роли
                if user_role in ["vip_manager", "on_duty", "head"]:
                    welcome_message = f"""🤖 Привет, {user.first_name}! Я @Vipalina_zerocoder_bot - автоматизированный помощник VIP-отдела.

Моя основная задача - упростить работу VIP-менеджеров и автоматизировать процессы онбординга студентов.

✅ Что я умею:
• Мониторить чат VIP-отдела на наличие новых студентов
• Распределять студентов между менеджерами по очереди
• Создавать учебные чаты со студентами
• Отправлять уведомления с кнопками для управления студентами
• Интегрироваться с Google Sheets, NocoDB и KPI-системами
• Отслеживать SLA и CSI показатели

💡 Основные команды:
• /принять_[ID] - принять студента и начать онбординг
• /пропустить_[ID] - передать студента следующему менеджеру
• /addnew - добавить студента вручную
• /tracker [ссылка] - создать листы курсов в трекере тарифа
• /createtracker [ID] - создать трекер существующему студенту

Если у вас есть вопросы по работе системы, обратитесь к руководителю VIP-отдела."""
                elif user_role == "vip_student":
                    welcome_message = f"""🤖 Привет, {user.first_name}! Я @Vipalina_zerocoder_bot - ваш помощник в VIP-программе.

Я помогаю VIP-менеджерам в работе с вами и автоматизирую процессы обучения.

Если у вас есть вопросы по обучению или вам нужна помощь, пожалуйста:
1. Обратитесь к вашему персональному VIP-менеджеру
2. Или напишите в ваш учебный чат

Команда Zerocoder University 🚀"""
                else:
                    welcome_message = f"""🤖 Привет, {user.first_name}! Я @Vipalina_zerocoder_bot - автоматизированный помощник VIP-отдела.

Информация о доступных функциях:
• Для VIP-менеджеров: помощь в онбординге студентов
• Для VIP-студентов: поддержка в обучении

Если вы являетесь VIP-менеджером или студентом, но не получаете доступ, обратитесь к руководителю VIP-отдела."""
                
                await event.reply(welcome_message)
                
            except Exception as e:
                logger.error(f"Ошибка при обработке команды /start: {e}", exc_info=True)
                await event.reply("❌ Произошла ошибка при обработке команды. Пожалуйста, попробуйте позже.")
        
        @self.client.on(events.NewMessage(pattern=r'/принять_(\d+)'))
        async def handle_accept_command(event):
            """Обработчик команды /принять_[getcourse_id]"""
            try:
                # Получаем getcourse_id из команды
                match = re.search(r'/принять_(\d+)', event.message.text)
                if not match:
                    return
                
                getcourse_id = match.group(1)
                
                # Получаем ID менеджера
                manager_id = event.sender_id
                
                # Проверяем, что это VIP-менеджер
                if not self._is_vip_manager(manager_id):
                    await event.reply("У вас нет прав для выполнения этой команды.")
                    return
                
                # Обрабатываем принятие студента
                success = await self.manager_queue.handle_accept_command(getcourse_id, manager_id)
                
                if success:
                    await event.reply(f"✅ Вы приняли студента! Начинаю онбординг...")
                else:
                    await event.reply("❌ Не удалось принять студента. Возможно, студент уже назначен другому менеджеру.")
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке команды /принять: {e}", exc_info=True)
        
        @self.client.on(events.NewMessage(pattern=r'/пропустить_(\d+)'))
        async def handle_skip_command(event):
            """Обработчик команды /пропустить_[getcourse_id]"""
            try:
                # Получаем getcourse_id из команды
                match = re.search(r'/пропустить_(\d+)', event.message.text)
                if not match:
                    return
                
                getcourse_id = match.group(1)
                
                # Получаем ID менеджера
                manager_id = event.sender_id
                
                # Проверяем, что это VIP-менеджер
                if not self._is_vip_manager(manager_id):
                    await event.reply("У вас нет прав для выполнения этой команды.")
                    return
                
                # Обрабатываем пропуск студента
                success = await self.manager_queue.handle_skip_command(getcourse_id, manager_id)
                
                if success:
                    await event.reply("➡️ Студент передан следующему менеджеру в очереди.")
                else:
                    await event.reply("❌ Не удалось пропустить студента.")
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке команды /пропустить: {e}", exc_info=True)
        
        @self.client.on(events.NewMessage(pattern=r'/help'))
        async def handle_help_command(event):
            """Показывает список доступных команд для VIP-отдела"""
            try:
                # Только в личных сообщениях
                if not event.is_private:
                    return
                
                # Только для VIP-отдела
                sender_id = event.sender_id
                logger.info(f"📨 /help от пользователя {sender_id} в User Client")
                if not self._is_vip_manager(sender_id):
                    logger.warning(f"⚠️ /help отклонён: пользователь {sender_id} не найден среди сотрудников VIP-отдела")
                    await event.reply("❌ У вас нет прав для выполнения этой команды.")
                    return
                
                help_text = (
                    "📖 **Команды Випалины**\n\n"
                    
                    "📊 **ОТЧЁТЫ:**\n\n"
                    
                    "📈 `/bigreport`\n"
                    "Большой сводный отчёт (статусы, менеджеры, SLA)\n\n"
                    
                    "📅 `/reportmonth`\n"
                    "Месячный отчёт (по себе или выбор менеджера)\n\n"
                    
                    "🗓 `/reportweek`\n"
                    "Недельный отчёт по активности\n\n"
                    
                    "📊 `/sla <месяц>`\n"
                    "SLA-отчёт за месяц (пример: `/sla март` или `/sla март26`)\n\n"
                    
                    "👥 `/очередь`\n"
                    "Текущее состояние очереди менеджеров и ожидающие студенты\n\n"
                    
                    "👤 `/report [getcourse_id]`\n"
                    "• Без параметра - ваш отчёт\n"
                    "• С ID - детальный отчёт по студенту\n\n"
                    
                    "📋 `/minireport <getcourse_id>`\n"
                    "Краткий отчёт по студенту (как в напоминаниях)\n\n"
                    
                    "➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
                    
                    "📊 **СТАТИСТИКА ПРОГРЕССА:**\n\n"
                    
                    "📈 `/monthstats [менеджер]`\n"
                    "Статистика выполнения нормы за текущий месяц\n"
                    "• Без параметра - ваша статистика\n"
                    "• С именем - статистика менеджера\n"
                    "• Для руководителя: статистика всего отдела\n\n"
                    
                    "🔄 `/syncprogress`\n"
                    "Обновить сводную таблицу прогресса\n"
                    "(синхронизация данных из трекеров)\n\n"
                    
                    "📊 `/kpi` или `/kpi февраль26`\n"
                    "KPI по норме уроков за текущий или указанный месяц\n\n"
                    
                    "➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
                    
                    "📝 **ТРЕКЕРЫ:**\n\n"
                    
                    "📝 `/createtracker <getcourse_id>`\n"
                    "Создать трекер существующему студенту\n\n"
                    
                    "📊 `/tracker <ссылка>`\n"
                    "Заполнить трекер листами курсов (для тарифов)\n\n"
                    
                    "➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
                    
                    "📢 **РАССЫЛКИ:**\n\n"
                    
                    "📢 `/broadcast <текст>`\n"
                    "Рассылка во все активные чаты\n\n"
                    
                    "📢 `/broadcast #сегмент <текст>`\n"
                    "Рассылка по сегменту (из колонки N листа 'Випалина')\n\n"
                    
                    "✅ `/confirm`\n"
                    "Подтвердить рассылку\n\n"
                    
                    "❌ `/cancel`\n"
                    "Отменить текущий диалог\n\n"
                    
                    "🛑 `/stop`\n"
                    "Остановить выполнение текущей операции\n\n"
                )
                
                # Добавляем команды для руководителя и дежурного
                if sender_id in HEAD_IDS or sender_id in [acc['telegram_id'] for acc in ON_DUTY_ACCOUNTS]:
                    help_text += (
                        "➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
                        
                        "🔧 **ДЛЯ РУКОВОДИТЕЛЯ:**\n\n"
                        
                        "🧪 `/testreminders`\n"
                        "Тестовая отправка еженедельных напоминаний\n\n"
                        
                        "🧹 `/cleanprivchats`\n"
                        "Удалить старые личные чаты Випалины со студентами (>30 дней)\n\n"
                        
                        "📅 `/sendmonthlyplans [группа]`\n"
                        "Ручной запуск рассылки месячных планов\n"
                        "• Без параметра - всем студентам\n"
                        "• С номером (1/2/3) - группе по дню рассылки\n\n"
                    )
                
                help_text += (
                    "➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"

                    "📈 **АНАЛИТИКА:**\n\n"

                    "📊 `/compare [месяц]`\n"
                    "Сравнение менеджеров за месяц (напр. /compare 2025-06)\n"
                    "Без параметра — текущий месяц\n\n"

                    "🔄 `/retention [курс]`\n"
                    "Удержание студентов по курсу на 30/60/90 дней\n"
                    "Без аргумента — список курсов\n\n"

                    "🏆 `/topactive`\n"
                    "Топ-20 самых активных студентов за 30 дней\n\n"

                    "📋 `/coursestats`\n"
                    "Детальная статистика по курсам за текущий месяц\n\n"

                    "🔒 `/stuck [статус] [N]`\n"
                    "Студенты с неизменным статусом N+ месяцев подряд (по умолчанию 3)\n"
                    "Доступные: Заморозка, Новый, Пропал, Выпускной, Модуль ОК, Учится...\n\n"

                    "📉 `/kpidrop`\n"
                    "Студенты, у которых KPI упал (✅→❌) по сравнению с прошлым месяцем\n\n"

                    "🧟 `/nohw [N]`\n"
                    "0 ДЗ за N месяцев подряд (зомби-студенты, по умолчанию 3 мес.)\n\n"

                    "📊 `/managerload`\n"
                    "Нагрузка менеджеров: каждый менеджер × кол-во студентов по статусам\n\n"
                )
                
                help_text += (
                    "➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
                    
                    "👥 **ГРУППОВЫЕ ЧАТЫ:**\n\n"
                    
                    "✅ `/activate <getcourse_id>`\n"
                    "Активировать чат для SLA-трекинга\n\n"
                    
                    "❓ `/status`\n"
                    "Проверить статус активации\n\n"
                    
                    "🚫 `/deactivate`\n"
                    "Деактивировать чат\n\n"

                    "⚠️ `/notactivated`\n"
                    "Список чатов, где Випалина есть, но не активирована\n"
                    "(менеджер — только свои, руководитель — все)\n\n"

                    "➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"

                    "📊 **АНАЛИТИКА:**\n\n"

                    "💤 `/inactive [N]`\n"
                    "Студенты без контакта >N дней (по умолчанию 14)\n"
                    "(менеджер — только свои, руководитель — все)\n\n"

                    "🔗 `/notracker`\n"
                    "Студенты в статусе Новый/Учится без трекера\n"
                    "(менеджер — только свои, руководитель — все)\n\n"

                    "🆘 `/nosla`\n"
                    "Открытые SLA-запросы без ответа\n"
                    "(менеджер — только свои, руководитель — все)\n\n"

                    "📚 `/courses`\n"
                    "Распределение студентов по курсам\n"
                    "(менеджер — только свои, руководитель — все)\n\n"

                    "📝 `/hw0`\n"
                    "Студенты с 0 ДЗ в текущем месяце (Новый/Учится/Модуль ОК)\n"
                    "(менеджер — только свои, руководитель — все)\n\n"

                    "📝 `/hw1`\n"
                    "Студенты с 1 ДЗ в текущем месяце (Новый/Учится/Модуль ОК)\n"
                    "(менеджер — только свои, руководитель — все)\n\n"

                    f"ℹ️ Активных чатов: {len(self.chat_to_student)}"
                )
                
                max_message_length = 3500
                if len(help_text) <= max_message_length:
                    await event.reply(help_text, parse_mode='md')
                    logger.info(f"✅ /help отправлен пользователю {sender_id} одним сообщением")
                else:
                    parts = help_text.split("➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n")
                    current_part = ""
                    sent_parts = 0

                    for part in parts:
                        separator = "" if not current_part else "➖➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
                        candidate = current_part + separator + part
                        if len(candidate) > max_message_length and current_part:
                            await event.respond(current_part, parse_mode='md')
                            sent_parts += 1
                            current_part = part
                        else:
                            current_part = candidate

                    if current_part:
                        await event.respond(current_part, parse_mode='md')
                        sent_parts += 1

                    logger.info(f"✅ /help отправлен пользователю {sender_id} частями: {sent_parts}")
            except Exception as e:
                logger.error(f"Ошибка при обработке /help: {e}", exc_info=True)
        
        @self.client.on(events.NewMessage(pattern=r'^/report(?:\s|$)'))
        async def handle_report_command(event):
            """
            Обработчик команды /report.
            
            Форматы:
            - /report - личный отчёт менеджера (для руководителя - сводный)
            - /report <getcourse_id> - отчёт по конкретному студенту
            """
            try:
                # Только в личных сообщениях
                if not event.is_private:
                    return
                
                # Только для VIP-отдела
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                message_text = event.message.text.strip()
                
                # Проверяем, есть ли getcourse_id
                match = re.search(r'/report\s+(\d+)', message_text)
                
                if match:
                    # Отчёт по конкретному студенту
                    getcourse_id = match.group(1)
                    
                    # Валидация: проверяем, существует ли студент
                    from report_generator import get_report_generator
                    report_gen = get_report_generator()
                    
                    student = await report_gen.get_student_by_id(getcourse_id)
                    if not student:
                        await event.reply(
                            f"❌ Студент с ID `{getcourse_id}` не найден в базе.\n\n"
                            f"Проверьте правильность ID в таблице KPI Ultra."
                        )
                        return
                    
                    await event.reply("🔄 Формирую отчёт...")
                    report = await report_gen.generate_student_report(getcourse_id)
                    await event.reply(report, parse_mode='md')
                else:
                    # Без ID - обычный отчёт
                    await event.reply("🔄 Формирую отчёт...")
                    
                    from report_generator import get_report_generator
                    report_gen = get_report_generator()
                    
                    # Руководитель получает сводный отчёт
                    if sender_id in HEAD_IDS:
                        report = await report_gen.generate_leadership_report()
                    else:
                        # Обычный менеджер — отчёт по его студентам
                        report = await report_gen.generate_manager_report(sender_id)
                    
                    await event.reply(report, parse_mode='md')
                
                logger.info(f"Отчёт /report отправлен менеджеру {sender_id}")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке /report: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка генерации отчёта: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/minireport'))
        async def handle_minireport_command(event):
            """
            Обработчик команды /minireport <getcourse_id> - краткий отчёт.
            
            Формат такой же, как в уведомлениях о следующем общении.
            """
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                message_text = event.message.text.strip()
                match = re.search(r'/minireport\s+(\d+)', message_text)
                
                if not match:
                    await event.reply(
                        "❌ Укажи GetCourse ID студента\n\n"
                        "Например: `/minireport 12345678`",
                        parse_mode='md'
                    )
                    return
                
                getcourse_id = match.group(1)
                
                # Проверяем существование студента
                from report_generator import get_report_generator
                report_gen = get_report_generator()
                
                kpi_students = await report_gen.get_kpi_data()
                student = next((s for s in kpi_students if s['getcourse_id'] == getcourse_id), None)
                
                if not student:
                    await event.reply(
                        f"❌ Студент с ID `{getcourse_id}` не найден в базе.\n\n"
                        f"Проверьте правильность ID в таблице KPI Ultra."
                    )
                    return
                
                # Используем логику из weekly_reminders
                vipalina_data = await report_gen.get_vipalina_data()
                vipalina_info = vipalina_data.get(getcourse_id, {})
                
                # Получаем данные о ДЗ
                hw_week, hw_month = await self._get_minireport_homework_stats(getcourse_id)
                
                # Получаем ссылку на чат
                chat_link = await self._get_minireport_chat_link(getcourse_id, vipalina_info)
                
                # Дни без контакта
                last_contact = vipalina_info.get('last_contact', '')
                if last_contact:
                    try:
                        contact_date = datetime.strptime(last_contact[:10], '%Y-%m-%d')
                        days_no_contact = (datetime.now() - contact_date).days
                        last_contact_formatted = contact_date.strftime('%d.%m.%Y')
                    except:
                        days_no_contact = '30+'
                        last_contact_formatted = 'никогда'
                else:
                    days_no_contact = '30+'
                    last_contact_formatted = 'никогда'
                
                # Формируем сообщение
                name = student.get('name', 'Без имени')
                course = student.get('course', '-')
                tracker_url = student.get('tracker_url', '')
                
                message = f"**{name}**\n"
                message += f"📚 Курс: {course}\n"
                message += f"⏱ Без контакта: {days_no_contact} дней (посл. {last_contact_formatted})\n"
                
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
                if tracker_url and tracker_url != '-':
                    # Валидация URL
                    if tracker_url.startswith('http://') or tracker_url.startswith('https://'):
                        message += f"\n📋 [Трекер]({tracker_url})"
                    else:
                        logger.warning(f"Невалидный tracker_url для {getcourse_id}: {tracker_url}")
                
                if chat_link:
                    message += f"\n💬 [Открыть чат]({chat_link})"
                
                # Кнопки
                buttons = [
                    [
                        Button.inline("✅ Написал", data=f"touch_done:{getcourse_id}"),
                        Button.inline("⏰ +7 дней", data=f"touch_delay_7:{getcourse_id}"),
                        Button.inline("⏰ +14 дней", data=f"touch_delay_14:{getcourse_id}")
                    ]
                ]
                
                await event.reply(message, buttons=buttons, parse_mode='md')
                logger.info(f"Краткий отчёт /minireport отправлен менеджеру {sender_id} по студенту {getcourse_id}")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке /minireport: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка генерации отчёта: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/bigreport'))
        async def handle_bigreport_command(event):
            """
            Обработчик команды /bigreport - большой сводный отчёт.
            
            Для менеджеров: отчёт по своим студентам
            Для дежурных/руководителя: диалог выбора менеджера
            """
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                from report_generator import get_report_generator
                report_gen = get_report_generator()
                
                # Проверяем, это дежурный или руководитель
                is_duty = sender_id in [acc['telegram_id'] for acc in ON_DUTY_ACCOUNTS]
                is_head = sender_id in HEAD_IDS
                
                if is_duty or is_head:
                    # Диалог выбора менеджера
                    managers = report_gen.get_manager_list()
                    manager_list = '\n'.join([f"  • {m}" for m in managers])
                    
                    self.report_dialog_state[sender_id] = {
                        'command': 'bigreport',
                        'awaiting_manager': True,
                        'is_head': is_head,  # Сохраняем для сравнения менеджеров
                        'timestamp': datetime.now()  # Для таймаута
                    }
                    
                    await event.reply(
                        f"📊 **Большой отчёт**\n\n"
                        f"Укажи имя менеджера или напиши **все** для отчёта по всем:\n\n"
                        f"{manager_list}\n\n"
                        f"Например: `Катя Чайка` или `все`",
                        parse_mode='md'
                    )
                else:
                    # Обычный менеджер - отчёт по своим студентам
                    manager_name = report_gen._get_manager_name_by_id(sender_id)
                    status_msg = await event.reply("🔄 Формирую большой отчёт...")
                    
                    report = await report_gen.generate_big_report(manager_name, is_head=False)
                    await status_msg.edit(report, parse_mode='md')
                    logger.info(f"Отчёт /bigreport отправлен менеджеру {sender_id}")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке /bigreport: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/reportmonth'))
        async def handle_reportmonth_command(event):
            """
            Обработчик команды /reportmonth - месячный отчёт.
            """
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                from report_generator import get_report_generator
                report_gen = get_report_generator()
                
                is_duty = sender_id in [acc['telegram_id'] for acc in ON_DUTY_ACCOUNTS]
                is_head = sender_id in HEAD_IDS
                
                if is_duty or is_head:
                    # Диалог выбора менеджера
                    managers = report_gen.get_manager_list()
                    manager_list = '\n'.join([f"  • {m}" for m in managers])
                    
                    self.report_dialog_state[sender_id] = {
                        'command': 'reportmonth',
                        'awaiting_manager': True,
                        'is_head': is_head,
                        'timestamp': datetime.now()
                    }
                    
                    await event.reply(
                        f"📅 **Месячный отчёт**\n\n"
                        f"Укажи имя менеджера или напиши **все**:\n\n"
                        f"{manager_list}\n\n"
                        f"Например: `Оля Тихонова` или `все`",
                        parse_mode='md'
                    )
                else:
                    # Обычный менеджер
                    manager_name = report_gen._get_manager_name_by_id(sender_id)
                    status_msg = await event.reply("🔄 Формирую месячный отчёт...")
                    
                    report = await report_gen.generate_month_report(manager_name, is_head=False)
                    await status_msg.edit(report, parse_mode='md')
                    logger.info(f"Отчёт /reportmonth отправлен менеджеру {sender_id}")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке /reportmonth: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/reportweek'))
        async def handle_reportweek_command(event):
            """
            Обработчик команды /reportweek - недельный отчёт.
            """
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                from report_generator import get_report_generator
                report_gen = get_report_generator()
                
                is_duty = sender_id in [acc['telegram_id'] for acc in ON_DUTY_ACCOUNTS]
                is_head = sender_id in HEAD_IDS
                
                if is_duty or is_head:
                    # Диалог выбора менеджера
                    managers = report_gen.get_manager_list()
                    manager_list = '\n'.join([f"  • {m}" for m in managers])
                    
                    self.report_dialog_state[sender_id] = {
                        'command': 'reportweek',
                        'awaiting_manager': True,
                        'is_head': is_head,
                        'timestamp': datetime.now()
                    }
                    
                    await event.reply(
                        f"🗓 **Недельный отчёт**\n\n"
                        f"Укажи имя менеджера или напиши **все**:\n\n"
                        f"{manager_list}\n\n"
                        f"Например: `Лиза Виноградова` или `все`",
                        parse_mode='md'
                    )
                else:
                    # Обычный менеджер
                    manager_name = report_gen._get_manager_name_by_id(sender_id)
                    status_msg = await event.reply("🔄 Формирую недельный отчёт...")
                    
                    report = await report_gen.generate_week_report(manager_name, is_head=False)
                    await status_msg.edit(report, parse_mode='md')
                    logger.info(f"Отчёт /reportweek отправлен менеджеру {sender_id}")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке /reportweek: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/sla(?:\s+(.+))?$'))
        async def handle_sla_command(event):
            """
            Обработчик команды /sla <месяц> — SLA-отчёт за указанный месяц.
            Формат: /sla март  или  /sla март26  или  /sla март 2026
            """
            try:
                if not event.is_private:
                    return

                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return

                if not self.sla_reporter:
                    await event.reply("❌ SLA-модуль не инициализирован")
                    return

                # Парсим месяц из текста команды
                message_text = event.message.text.strip()
                month_arg = message_text[len('/sla'):].strip()

                if not month_arg:
                    await event.reply(
                        "📊 **SLA-отчёт**\n\n"
                        "Укажи месяц: `/sla март` или `/sla март26`\n\n"
                        "Доступные месяцы: январь, февраль, март, апрель, май, июнь, "
                        "июль, август, сентябрь, октябрь, ноябрь, декабрь",
                        parse_mode='md'
                    )
                    return

                ru_months = {
                    'январь': 1, 'января': 1,
                    'февраль': 2, 'февраля': 2,
                    'март': 3, 'марта': 3,
                    'апрель': 4, 'апреля': 4,
                    'май': 5, 'мая': 5,
                    'июнь': 6, 'июня': 6,
                    'июль': 7, 'июля': 7,
                    'август': 8, 'августа': 8,
                    'сентябрь': 9, 'сентября': 9,
                    'октябрь': 10, 'октября': 10,
                    'ноябрь': 11, 'ноября': 11,
                    'декабрь': 12, 'декабря': 12,
                }

                import pytz as _pytz
                import re as _re
                now = datetime.now(_pytz.timezone('Europe/Moscow'))
                target_year = now.year
                target_month = None

                # Разбираем аргумент: "март" / "март26" / "март 2026" / "март 26"
                m = _re.match(r'([а-яёА-ЯЁ]+)\s*(\d{2,4})?', month_arg.lower())
                if m:
                    month_word = m.group(1)
                    year_part = m.group(2)
                    target_month = ru_months.get(month_word)
                    if year_part:
                        yr = int(year_part)
                        target_year = 2000 + yr if yr < 100 else yr

                if not target_month:
                    await event.reply(f"❌ Не распознан месяц: `{month_arg}`", parse_mode='md')
                    return

                status_msg = await event.reply("🔄 Формирую SLA-отчёт...")

                stats = self.sla_reporter.sla_sheets.get_monthly_stats(target_year, target_month)
                report = self.sla_reporter._format_report(stats, target_year, target_month)

                await status_msg.edit(report, parse_mode='md')
                logger.info(f"/sla отчёт за {target_month}/{target_year} отправлен пользователю {sender_id}")

            except Exception as e:
                logger.error(f"Ошибка при обработке /sla: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        @self.client.on(events.NewMessage(pattern=r'/очередь'))
        async def handle_queue_command(event):
            """Показывает текущее состояние очереди менеджеров."""
            try:
                sender_id = event.sender_id
                # Разрешаем: личка менеджера/руководителя ИЛИ чат VIP-отдела
                is_vip_chat = (not event.is_private and event.chat_id == VIP_DEPARTMENT_CHAT_ID)
                is_private_allowed = event.is_private and (self._is_vip_manager(sender_id) or sender_id == VIP_HEAD['telegram_id'])
                if not (is_vip_chat or is_private_allowed):
                    return

                mq = self.manager_queue

                def fmt_queue(managers, current_idx, label):
                    if not managers:
                        return f"**{label}:** пусто\n"
                    lines = [f"**{label}:**"]
                    for i, m in enumerate(managers):
                        offset = (i - current_idx) % len(managers)
                        if offset == 0:
                            prefix = "👉"
                        elif offset == 1:
                            prefix = "2️⃣"
                        elif offset == 2:
                            prefix = "3️⃣"
                        else:
                            prefix = f"  {offset+1}."
                        lines.append(f"{prefix} {m['name']}")
                    return "\n".join(lines)

                vip_block = fmt_queue(mq.vip_managers, mq.current_vip_index, "VIP очередь")
                lux_block = fmt_queue(mq.luxury_managers, mq.current_luxury_index, "Luxury очередь")

                # Ожидающие назначения — только те, кого нет в "Общий список new"
                enrolled_ids: set = set()
                if self.kpi_sheets:
                    try:
                        enrolled_ids = await asyncio.wait_for(
                            self.kpi_sheets.get_all_enrolled_ids(), timeout=10
                        )
                    except (asyncio.TimeoutError, Exception):
                        pass
                # Runtime-очистка: убираем из памяти и листа тех, кто уже в "Общий список new"
                stale_ids = [
                    gid for gid in list(mq.assignments.keys())
                    if str(gid) in enrolled_ids
                ]
                for stale_gid in stale_ids:
                    del mq.assignments[stale_gid]
                    try:
                        self.persistence.delete_manager_assignment(stale_gid)
                    except Exception:
                        pass
                pending = [
                    (gid, a) for gid, a in mq.assignments.items()
                    if a.status == "pending"
                ]
                if pending:
                    plines = [f"\n⏳ **Ожидают принятия ({len(pending)}):**"]
                    for gid, a in pending:
                        tg_part = f" @{a.student_telegram.lstrip('@')}" if a.student_telegram else ""
                        plines.append(f"• {a.student_name} (GC:{gid}){tg_part} → {a.manager_name}")
                    pending_block = "\n".join(plines)
                else:
                    pending_block = "\n✅ Нет студентов в ожидании"

                text = f"{vip_block}\n\n{lux_block}{pending_block}"
                await event.reply(text, parse_mode='md')

            except Exception as e:
                logger.error(f"Ошибка при обработке /очередь: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        @self.client.on(events.NewMessage(func=lambda e: e.is_private))
        async def handle_report_dialog_response(event):
            """
            Обработчик ответов в диалоге выбора менеджера.
            """
            try:
                # ИГНОРИРУЕМ сообщения отправленные ДО запуска бота
                if event.message.date.replace(tzinfo=None) < self._startup_time:
                    return
                
                # 2. Проверяем диалог выбора менеджера для отчётов
                sender_id = event.sender_id
                
                # Проверяем, есть ли активный диалог
                if sender_id not in self.report_dialog_state:
                    return
                
                dialog = self.report_dialog_state.get(sender_id)
                if not dialog or not dialog.get('awaiting_manager'):
                    return
                
                # Проверяем таймаут (30 минут)
                if 'timestamp' in dialog:
                    timestamp = dialog['timestamp']
                    if (datetime.now() - timestamp).seconds > 1800:
                        del self.report_dialog_state[sender_id]
                        await event.reply("❌ Время ожидания истекло. Начните заново с /bigreport, /reportmonth или /reportweek")
                        return
                
                message_text = event.message.text.strip()
                
                # Пропускаем команды
                if message_text.startswith('/'):
                    return
                
                # Удаляем состояние диалога
                command = dialog['command']
                del self.report_dialog_state[sender_id]
                
                from report_generator import get_report_generator
                report_gen = get_report_generator()
                
                # Определяем имя менеджера
                manager_name = None
                if message_text.lower() in ['все', 'all', '*']:
                    manager_name = 'все'
                else:
                    # Проверяем, есть ли такой менеджер
                    managers = report_gen.get_manager_list()
                    for m in managers:
                        if message_text.lower() in m.lower():
                            manager_name = m
                            break
                    
                    if not manager_name:
                        await event.reply(
                            f"❌ Менеджер '{message_text}' не найден.\n\n"
                            f"Доступные менеджеры:\n" +
                            '\n'.join([f"  • {m}" for m in managers])
                        )
                        return
                
                status_msg = await event.reply("🔄 Формирую отчёт...")
                
                # Генерируем отчёт в зависимости от команды
                is_head = dialog.get('is_head', False)
                
                if command == 'bigreport':
                    report = await report_gen.generate_big_report(manager_name, is_head=is_head)
                elif command == 'reportmonth':
                    report = await report_gen.generate_month_report(manager_name, is_head=is_head)
                elif command == 'reportweek':
                    report = await report_gen.generate_week_report(manager_name, is_head=is_head)
                else:
                    report = await report_gen.generate_big_report(manager_name, is_head=is_head)
                
                await status_msg.edit(report, parse_mode='md')
                logger.info(f"Отчёт {command} для '{manager_name}' отправлен {sender_id}")
                
            except Exception as e:
                logger.error(f"Ошибка в диалоге отчёта: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/createtracker'))
        async def handle_createtracker_command(event):
            """Обработчик команды /createtracker <getcourse_id> - создать трекер существующему студенту"""
            try:
                # Проверяем, что это личное сообщение
                if not event.is_private:
                    return
                
                # Проверяем, что это VIP-менеджер
                manager_id = event.sender_id
                if not self._is_vip_manager(manager_id):
                    await event.reply("У вас нет прав для выполнения этой команды.")
                    return
                
                message_text = event.message.text
                match = re.search(r'/createtracker\s+(\d+)', message_text)
                
                if not match:
                    await event.reply(
                        "❓ **Создание трекера для существующего студента**\n\n"
                        "👉 Использование:\n"
                        "`/createtracker <getcourse_id>`\n\n"
                        "📌 Пример:\n"
                        "`/createtracker 123456789`\n\n"
                        "💡 Трекер будет создан для студента из KPI Ultra."
                    )
                    return
                
                getcourse_id = match.group(1)
                
                await event.reply("🔄 Начинаю создание трекера...")
                
                # Получаем данные студента из KPI Sheets
                if not self.kpi_sheets:
                    await event.reply("❌ KPI Sheets не инициализирован.")
                    return
                
                try:
                    row_number = await self.kpi_sheets._find_student_row_in_kpi(getcourse_id)
                    if not row_number:
                        await event.reply(f"\u274c \u0421\u0442\u0443\u0434\u0435\u043d\u0442 \u0441 ID `{getcourse_id}` \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0432 KPI Ultra.")
                        return
                                    
                    # \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u043c \u043a\u0435\u0448\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 (\u0443\u0436\u0435 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u044b \u043f\u0440\u0438 _find_student_row_in_kpi)
                    all_data = await self.kpi_sheets._get_all_data_cached()
                    row_data = all_data[row_number - 1] if row_number <= len(all_data) else None
                    
                    if not row_data or len(row_data) < 4:
                        await event.reply(f"❌ Недостаточно данных о студенте {getcourse_id}")
                        return
                    
                    # Парсим данные (A=0, B=1, C=2, D=3, E=4, F=5, G=6, K=10)
                    student_name = row_data[2] if len(row_data) > 2 else ''  # C
                    course_tag = row_data[3] if len(row_data) > 3 else ''    # D
                    existing_tracker = row_data[5] if len(row_data) > 5 else ''  # F
                    
                    if not student_name or not course_tag:
                        await event.reply(f"❌ Не удалось прочитать имя или курс студента {getcourse_id}")
                        return
                    
                    # Проверяем, нет ли уже трекера
                    if existing_tracker and existing_tracker != '-' and 'docs.google.com' in existing_tracker:
                        manager_info = self._get_manager_info(manager_id)
                        manager_name_conf = manager_info['name'] if manager_info else ''
                        self.pending_tracker_overwrite_confirmations[manager_id] = {
                            'getcourse_id': getcourse_id,
                            'student_name': student_name,
                            'course_tag': course_tag,
                            'manager_name': manager_name_conf,
                            'row_number': row_number,
                        }
                        await event.reply(
                            f"⚠️ У студента **{student_name}** уже есть трекер:\n"
                            f"🔗 {existing_tracker}\n\n"
                            f"Хотите создать новый трекер всё равно? (да/нет)"
                        )
                        return
                    
                    # Получаем менеджера
                    manager_info = self._get_manager_info(manager_id)
                    if not manager_info:
                        await event.reply("❌ Не удалось определить данные менеджера.")
                        return
                    
                    manager_name = manager_info['name']
                    
                except Exception as e:
                    logger.error(f"Ошибка получения данных студента {getcourse_id}: {e}", exc_info=True)
                    await event.reply(f"❌ Ошибка получения данных студента: {e}")
                    return
                
                # ✅ Курс уже определён при онбординге и записан в столбец D
                # Значение в course_tag - это уже internal_name из столбца B "Условия курсов"
                # НЕ НУЖНО определять курс заново!
                logger.info(f"📚 Используем курс из KPI Ultra (столбец D): {course_tag}")
                
                # Создаём трекер
                if not self.tracker_creator:
                    await event.reply("❌ TrackerCreator не инициализирован.")
                    return
                
                try:
                    tracker_result = await asyncio.to_thread(
                        self.tracker_creator.create_tracker,
                        student_name=student_name,
                        course_tag=course_tag,
                        manager_name=manager_name,
                        getcourse_id=getcourse_id
                    )
                    
                    tracker_url = tracker_result['url']
                    logger.info(f"✅ Трекер создан для студента {getcourse_id}: {tracker_url}")
                    
                    # Обновляем ссылку на трекер в KPI Sheets
                    try:
                        await self.kpi_sheets.update_tracker_link(row_number, tracker_url)
                        logger.info(f"✅ Ссылка на трекер обновлена в KPI Sheets для студента {getcourse_id}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка обновления ссылки на трекер в KPI Sheets: {e}", exc_info=True)
                    
                    # Обновляем в листе Випалина (если студент там есть, иначе добавляем)
                    try:
                        if self.sheets_integration:
                            vipalina_updated = await self.sheets_integration.update_tracker_url_by_getcourse_id(
                                getcourse_id=getcourse_id,
                                tracker_url=tracker_url
                            )
                            if vipalina_updated:
                                logger.info(f"✅ Трекер обновлён в листе Випалина для {getcourse_id}")
                                # Заполняем B/C если ещё пустые (студент мог быть добавлен раньше без chat_id)
                                known_chat_id_for_update = None
                                known_tg_id_for_update = None
                                for cid, gid in self.chat_to_student.items():
                                    if str(gid) == str(getcourse_id):
                                        known_chat_id_for_update = cid
                                        break
                                sd2 = self.students_data.get(getcourse_id) or self.students_data.get(str(getcourse_id))
                                if sd2:
                                    known_tg_id_for_update = sd2.get('telegram_id')
                                if known_chat_id_for_update or known_tg_id_for_update:
                                    try:
                                        await self.sheets_integration.update_chat_id_if_missing(
                                            getcourse_id=getcourse_id,
                                            telegram_id=known_tg_id_for_update,
                                            chat_id=known_chat_id_for_update
                                        )
                                    except Exception as _fill_err:
                                        logger.warning(f"⚠️ Не удалось обновить B/C в Випалина: {_fill_err}")
                            else:
                                # Студент не найден в Випалина - добавляем новую запись
                                logger.info(f"ℹ️ Студент {getcourse_id} не найден в Випалина, добавляем новую запись...")
                                
                                # Получаем полные данные студента из KPI
                                student_data = {
                                    'name': student_name,
                                    'course': course_tag,
                                    'telegram_username': '-',
                                    'getcourse_id': getcourse_id
                                }
                                
                                # Получаем invite_link из KPI если есть
                                invite_link = '-'
                                try:
                                    if len(row_data) > 6:
                                        invite_link = row_data[6] if row_data[6] else '-'
                                except:
                                    pass
                                
                                # Ищем уже известный chat_id для этого студента
                                known_chat_id = None
                                for cid, gid in self.chat_to_student.items():
                                    if str(gid) == str(getcourse_id):
                                        known_chat_id = cid
                                        break
                                
                                # Ищем telegram_id из students_data
                                known_telegram_id = None
                                sd = self.students_data.get(getcourse_id) or self.students_data.get(str(getcourse_id))
                                if sd:
                                    known_telegram_id = sd.get('telegram_id')
                                    if sd.get('telegram_username') and sd['telegram_username'] != '-':
                                        student_data['telegram_username'] = sd['telegram_username']
                                
                                if known_chat_id:
                                    logger.info(f"✅ Найден активный chat_id={known_chat_id} для студента {getcourse_id}")
                                
                                sheets_success = await self.sheets_integration.add_student_record(
                                    getcourse_id=getcourse_id,
                                    telegram_id=known_telegram_id,
                                    chat_id=known_chat_id,
                                    student_data=student_data,
                                    manager_id=manager_id,
                                    manager_name=manager_name,
                                    tracker_url=tracker_url,
                                    invite_link=invite_link,
                                    resolved_course_name=course_tag
                                )
                                
                                if sheets_success:
                                    logger.info(f"✅ Студент {getcourse_id} добавлен в лист 'Випалина' с трекером")
                                else:
                                    logger.warning(f"⚠️ Не удалось добавить студента {getcourse_id} в лист 'Випалина'")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось обновить/добавить трекер в Випалина: {e}")
                    
                    # Отправляем успешное сообщение
                    await event.reply(
                        f"✅ **Трекер успешно создан!**\n\n"
                        f"👤 Студент: **{student_name}**\n"
                        f"🆔 GetCourse ID: `{getcourse_id}`\n"
                        f"📚 Курс: {course_tag}\n"
                        f"👩‍💼 Менеджер: {manager_name}\n\n"
                        f"🔗 [Открыть трекер]({tracker_url})"
                    )
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка создания трекера для студента {getcourse_id}: {e}", exc_info=True)
                    await event.reply(
                        f"❌ **Ошибка создания трекера**\n\n"
                        f"Студент: {student_name}\n"
                        f"GetCourse ID: `{getcourse_id}`\n\n"
                        f"Ошибка: {str(e)[:200]}\n\n"
                        f"🔧 Проверьте квоту Google Drive."
                    )
                    
                    # Уведомляем руководителя (от @zerocoder_ultralina_bot)
                    try:
                        await self.bot_client.send_message(
                            VIP_HEAD['telegram_id'],
                            f"❌ **Не удалось создать трекер (команда /createtracker)**\n\n"
                            f"Студент: {student_name}\n"
                            f"GetCourse ID: `{getcourse_id}`\n"
                            f"Курс: {course_tag}\n"
                            f"Менеджер: {manager_name}\n\n"
                            f"Ошибка: {str(e)[:200]}\n\n"
                            f"🔧 Проверьте квоту Google Drive."
                        )
                    except:
                        pass
            
            except Exception as e:
                logger.error(f"Критическая ошибка в /createtracker: {e}", exc_info=True)
                await event.reply(f"❌ Критическая ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/tracker'))
        async def handle_create_sheets_command(event):
            """Обработчик команды /tracker [ссылка на трекер] - только в личных сообщениях"""
            try:
                # Проверяем, что это личное сообщение
                if not event.is_private:
                    return  # Игнорируем в группах
                
                # Проверяем, что это VIP-менеджер, дежурный или руководитель
                manager_id = event.sender_id
                if not self._is_vip_manager(manager_id):
                    await event.reply("У вас нет прав для выполнения этой команды.")
                    return
                
                # Ищем ссылку на Google Sheets в сообщении
                message_text = event.message.text
                url_match = re.search(r'https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)', message_text)
                
                if not url_match:
                    await event.reply(
                        "❓ Команда для создания листов курсов в трекере тарифа\n\n"
                        "👉 Использование:\n"
                        "/tracker https://docs.google.com/spreadsheets/d/xxx\n\n"
                        "📌 Отправьте команду вместе со ссылкой на трекер тарифа.\n\n"
                        "💡 Бот проверит ячейки G5:G10 на листе '📈 Статистика' и создаст листы для каждого выбранного курса."
                    )
                    return
                
                tracker_url = url_match.group(0)
                
                # Отправляем уведомление о начале обработки
                await event.reply("🔄 Начинаю создание листов курсов...")
                
                # Импортируем TariffTrackerManager
                from tariff_tracker_manager import TariffTrackerManager
                
                # Создаем экземпляр менеджера
                tariff_manager = TariffTrackerManager()
                
                # Создаем листы курсов
                result = tariff_manager.create_course_sheets(tracker_url)
                
                # Формируем ответ
                if result['success']:
                    response = f"✅ Листы курсов успешно созданы!\n\n"
                    
                    if result['created_sheets']:
                        response += f"✨ Создано листов: {len(result['created_sheets'])}\n"
                        for sheet_name in result['created_sheets']:
                            response += f"  • {sheet_name}\n"
                    
                    if result['skipped_sheets']:
                        response += f"\nℹ️ Пропущено (уже существуют): {len(result['skipped_sheets'])}\n"
                        for sheet_name in result['skipped_sheets']:
                            response += f"  • {sheet_name}\n"
                    
                    response += f"\n🔗 Трекер: {tracker_url}"
                else:
                    response = f"❌ Ошибка при создании листов:\n"
                    for error in result.get('errors', []):
                        response += f"  • {error}\n"
                
                await event.reply(response)
                
            except ImportError as e:
                logger.error(f"Ошибка импорта TariffTrackerManager: {e}", exc_info=True)
                await event.reply("❌ Ошибка: модуль TariffTrackerManager не найден.")
            except Exception as e:
                logger.error(f"Ошибка при обработке команды /tracker: {e}", exc_info=True)
                await event.reply(f"❌ Произошла ошибка: {str(e)}")
        
        @self.client.on(events.NewMessage(pattern=r'/broadcast'))
        async def handle_broadcast_command(event):
            """
            Обработчик команды /broadcast.
            
            Форматы:
            - /broadcast текст              → всем активным чатам
            - /broadcast #хештег текст    → только чатам с этим хештегом
            
            Только в личных сообщениях, только для VIP-отдела.
            """
            try:
                # Проверяем, что это личное сообщение
                if not event.is_private:
                    return  # Игнорируем в группах
                
                # Проверяем права (менеджер, дежурный, руководитель)
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return  # Игнорируем неавторизованных
                
                message_text = event.message.text
                match = re.search(r'/broadcast\s+(.+)', message_text, re.DOTALL)
                
                if not match:
                    await event.reply(
                        "📢 **Рассылка**\n\n"
                        "📝 **Форматы:**\n"
                        "`/broadcast текст` — всем активным чатам\n"
                        "`/broadcast #хештег текст` — по сегменту\n\n"
                        "💡 **Примеры:**\n"
                        "`/broadcast 👋 Привет всем!`\n"
                        "`/broadcast #чатботы Напоминание о вебинаре`\n\n"
                        f"Всего активных чатов: {len(self.chat_to_student)}"
                    )
                    return
                
                content = match.group(1).strip()
                
                # Убираем возможные кавычки в начале и конце
                if content.startswith('"') and content.endswith('"') and len(content) >= 2:
                    content = content[1:-1]
                elif content.startswith("'") and content.endswith("'") and len(content) >= 2:
                    content = content[1:-1]
                
                # Парсим: #хештег текст или просто текст
                filter_tag = None
                broadcast_text = content
                
                # Проверяем, начинается ли с #хештега
                hashtag_match = re.match(r'^(#\S+)\s+(.+)', content, re.DOTALL)
                if hashtag_match:
                    filter_tag = hashtag_match.group(1).lower()  # #чатботы
                    broadcast_text = hashtag_match.group(2).strip()
                
                if len(broadcast_text) < 3:
                    await event.reply("❌ Сообщение слишком короткое.")
                    return
                
                if not self.chat_to_student:
                    await event.reply("❌ Нет активных чатов.")
                    return
                
                # Получаем сегменты из листа "Випалина"
                broadcast_segments = {}
                if self.sheets_integration:
                    try:
                        broadcast_segments = await self.sheets_integration.get_broadcast_segments()
                    except Exception as e:
                        logger.warning(f"Не удалось получить сегменты: {e}")
                
                # Фильтруем чаты
                target_chats = []
                for chat_id in self.chat_to_student.keys():
                    if filter_tag:
                        # Фильтруем по хештегу
                        segment = broadcast_segments.get(chat_id, '').lower()
                        # Проверяем наличие хештега (может быть "#чатботы, #лухари")
                        if filter_tag in segment:
                            target_chats.append(chat_id)
                    else:
                        # Все чаты
                        target_chats.append(chat_id)
                
                if not target_chats:
                    if filter_tag:
                        await event.reply(f"❌ Нет чатов с сегментом {filter_tag}")
                    else:
                        await event.reply("❌ Нет чатов для рассылки.")
                    return
                
                # ПОДТВЕРЖДЕНИЕ РАССЫЛКИ
                segment_info = f" (сегмент {filter_tag})" if filter_tag else ""
                preview_text = broadcast_text if len(broadcast_text) <= 100 else broadcast_text[:100] + "..."
                
                confirmation_msg = (
                    f"📢 **ПОДТВЕРЖДЕНИЕ РАССЫЛКИ**\n\n"
                    f"📊 Получателей: {len(target_chats)} чатов{segment_info}\n\n"
                    f"📝 Текст сообщения:\n"
                    f"```\n{preview_text}\n```\n\n"
                    f"⚠️ **Подтвердите отправку:**\n"
                    f"✅ `/confirm` — отправить рассылку\n"
                    f"❌ `/cancel` — отменить рассылку\n"
                    f"🛑 `/stop` — закрыть все диалоги"
                )
                
                # Сохраняем состояние для подтверждения
                self.broadcast_confirmation_state[sender_id] = {
                    'text': broadcast_text,
                    'target_chats': target_chats,
                    'filter_tag': filter_tag,
                    'timestamp': datetime.now()
                }
                
                await event.reply(confirmation_msg, parse_mode='md')
                return
                
            except Exception as e:
                logger.error(f"Ошибка при рассылке: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка при рассылке: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/sendmonthlyplans'))
        async def handle_sendmonthlyplans_command(event):
            """
            Обработчик команды /sendmonthlyplans.
            Ручной запуск рассылки запросов месячных планов студентам.
            
            Форматы:
            - /sendmonthlyplans              → всем студентам
            - /sendmonthlyplans 1            → группе 1 (день 1)
            - /sendmonthlyplans 2            → группе 2 (день 2)
            - /sendmonthlyplans 3            → группе 3 (день 3)
            
            Только в личных сообщениях, только для VIP-отдела.
            """
            try:
                # Проверяем, что это личное сообщение
                if not event.is_private:
                    return
                
                # Проверяем права (руководитель или дежурный)
                sender_id = event.sender_id
                if sender_id != VIP_DEPARTMENT_HEAD_ID and sender_id != VIP_DUTY_MANAGER_ID:
                    return  # Только руководитель и дежурный
                
                if not self.monthly_plan_scheduler:
                    await event.reply("❌ Планировщик месячных планов не инициализирован")
                    return
                
                message_text = event.message.text
                match = re.search(r'/sendmonthlyplans(?:\s+(\d+))?', message_text)
                
                if not match:
                    await event.reply(
                        "📅 **Рассылка месячных планов**\n\n"
                        "📝 **Форматы:**\n"
                        "`/sendmonthlyplans` — всем студентам\n"
                        "`/sendmonthlyplans 1` — группе 1 (день 1)\n"
                        "`/sendmonthlyplans 2` — группе 2 (день 2)\n"
                        "`/sendmonthlyplans 3` — группе 3 (день 3)"
                    )
                    return
                
                day_arg = match.group(1)
                
                if day_arg:
                    # Рассылка конкретной группы
                    day = int(day_arg)
                    if day not in [1, 2, 3]:
                        await event.reply("❌ Номер группы должен быть 1, 2 или 3")
                        return
                    
                    await event.reply(f"📤 Запускаю рассылку для группы {day}...")
                    
                    await self.monthly_plan_scheduler.send_monthly_plan_requests(day)
                    
                    await event.reply(f"✅ Рассылка для группы {day} завершена")
                else:
                    # Рассылка всем
                    await event.reply("📤 Запускаю рассылку всем студентам...")
                    
                    sent_count = await self.monthly_plan_scheduler.manual_send_all_plans()
                    
                    await event.reply(f"✅ Рассылка завершена!\n📊 Отправлено: {sent_count} студентов")
                
            except Exception as e:
                logger.error(f"Ошибка при /sendmonthlyplans: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/onboard'))
        async def handle_onboard_command(event):
            """
            Ручной запуск онбординга для студента по getcourse_id.
            Используется когда маппинг курса создан, но онбординг не запустился автоматически.
            
            Формат: /onboard <getcourse_id>
            Только в личных сообщениях, только для VIP-отдела.
            """
            try:
                # Проверяем, что это личное сообщение
                if not event.is_private:
                    return
                
                # Проверяем права (руководитель или дежурный)
                sender_id = event.sender_id
                if sender_id != VIP_DEPARTMENT_HEAD_ID and sender_id != VIP_DUTY_MANAGER_ID:
                    return  # Только руководитель и дежурный
                
                message_text = event.message.text
                match = re.search(r'/onboard\s+(\d+)', message_text)
                
                if not match:
                    await event.reply(
                        "🎓 **Ручной запуск онбординга**\n\n"
                        "📝 **Формат:**\n"
                        "`/onboard <getcourse_id>`\n\n"
                        "**Пример:**\n"
                        "`/onboard 483649791`"
                    )
                    return
                
                getcourse_id = match.group(1)
                
                # Проверяем есть ли данные студента в персистенции
                if getcourse_id not in self.students_data:
                    await event.reply(f"❌ Студент {getcourse_id} не найден в памяти")
                    return
                
                student_data = self.students_data[getcourse_id]
                logger.info(f"🚀 Ручной запуск онбординга для студента {getcourse_id} ({student_data.get('name')})")
                
                await event.reply(f"🎓 Запускаю онбординг для студента {student_data.get('name')} (ID: {getcourse_id})...")
                
                # Запускаем онбординг
                await self.start_onboarding_after_mapping(student_data)
                
                await event.reply(f"✅ Онбординг запущен!")
                
            except Exception as e:
                logger.error(f"Ошибка при /onboard: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/confirm'))
        async def handle_confirm_broadcast(event):
            """Подтверждение рассылки"""
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                # Проверяем, есть ли ожидающая рассылка
                if sender_id not in self.broadcast_confirmation_state:
                    await event.reply("❌ Нет ожидающей рассылки для подтверждения.")
                    return
                
                broadcast_data = self.broadcast_confirmation_state[sender_id]
                
                # Проверяем таймаут (30 минут)
                timestamp = broadcast_data['timestamp']
                if (datetime.now() - timestamp).seconds > 1800:
                    del self.broadcast_confirmation_state[sender_id]
                    await event.reply("❌ Время подтверждения истекло. Создайте рассылку заново.")
                    return
                
                # Выполняем рассылку
                target_chats = broadcast_data['target_chats']
                broadcast_text = broadcast_data['text']
                filter_tag = broadcast_data.get('filter_tag')
                
                await event.reply(f"📨 Начинаю рассылку в {len(target_chats)} чатов...")
                
                sent_count = 0
                failed_count = 0
                
                for chat_id in target_chats:
                    try:
                        await self.bot_client.send_message(chat_id, broadcast_text)
                        sent_count += 1
                        await asyncio.sleep(0.5)  # Защита от флуда
                    except Exception as e:
                        failed_count += 1
                        logger.warning(f"Не удалось отправить в чат {chat_id}: {e}")
                
                # Удаляем состояние
                del self.broadcast_confirmation_state[sender_id]
                
                result_msg = f"✅ Рассылка завершена!\n\n📊 Отправлено: {sent_count}\n"
                if failed_count > 0:
                    result_msg += f"❌ Ошибок: {failed_count}"
                
                await event.reply(result_msg)
                logger.info(f"Рассылка от {sender_id}: {sent_count} успешно, {failed_count} ошибок")
                
            except Exception as e:
                logger.error(f"Ошибка при подтверждении рассылки: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/cancel'))
        async def handle_cancel_broadcast(event):
            """Отмена рассылки"""
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                # Отменяем только подтверждение рассылки
                if sender_id in self.broadcast_confirmation_state:
                    del self.broadcast_confirmation_state[sender_id]
                    await event.reply("✅ Рассылка отменена.")
                else:
                    await event.reply("❌ Нет активной рассылки для отмены.")
                
            except Exception as e:
                logger.error(f"Ошибка при отмене рассылки: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/stop'))
        async def handle_stop_command(event):
            """Универсальная остановка любого диалога"""
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                cancelled = False
                
                # Отменяем диалог выбора менеджера
                if sender_id in self.report_dialog_state:
                    del self.report_dialog_state[sender_id]
                    cancelled = True
                
                # Отменяем подтверждение рассылки
                if sender_id in self.broadcast_confirmation_state:
                    del self.broadcast_confirmation_state[sender_id]
                    cancelled = True
                
                if cancelled:
                    await event.reply("✅ Диалог отменён.")
                else:
                    await event.reply("ℹ️ Нет активных диалогов для отмены.")
                
            except Exception as e:
                logger.error(f"Ошибка при отмене диалога: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/monthstats'))
        async def handle_monthstats_command(event):
            """
            Обработчик команды /monthstats [менеджер].
            Показывает статистику выполнения нормы за текущий месяц.
            """
            try:
                # Только в личных сообщениях
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                message_text = event.message.text.strip()
                
                # Импортируем progress_aggregator
                from progress_aggregator import get_progress_aggregator
                aggregator = get_progress_aggregator()
                
                # Парсим команду
                match = re.search(r'/monthstats(?:\s+(.+))?', message_text)
                manager_name = match.group(1).strip() if match and match.group(1) else None
                
                # Определяем имя менеджера
                if not manager_name:
                    # Без параметра - статистика того, кто запросил
                    manager_name = self._get_manager_name_by_id(sender_id)
                    if not manager_name:
                        await event.reply("❌ Не удалось определить ваше имя в системе.")
                        return
                
                # Для руководителя показываем общую статистику
                if sender_id == VIP_HEAD['telegram_id'] and not match.group(1):
                    # Показываем статистику по всем менеджерам
                    await event.reply("📊 Собираю статистику по всему отделу...")
                    
                    # Список всех менеджеров
                    all_managers = [
                        "Марина Иванова",
                        "Оля Антипанова",
                        "Кристина Махмудян",
                        "Лиза Виноградова",
                        "Катя Чайка",
                        "Оля Тихонова",
                        "Катя Пилипенко",
                        "Ксюша Уланова"
                    ]
                    
                    total_students = 0
                    total_completed = 0
                    total_not_completed = 0
                    
                    manager_reports = []
                    
                    for mgr in all_managers:
                        stats = await aggregator.get_manager_stats(mgr)
                        if stats['total_students'] > 0:
                            total_students += stats['total_students']
                            total_completed += stats['completed_norm']
                            total_not_completed += stats['not_completed']
                            
                            manager_reports.append(
                                f"• {mgr}: {stats['completed_norm']}/{stats['total_students']} ({stats['completion_rate']}%)"
                            )
                    
                    overall_rate = (total_completed / total_students * 100) if total_students > 0 else 0
                    
                    response = (
                        f"📊 **СТАТИСТИКА ОТДЕЛА** (текущий месяц)\n\n"
                        f"👥 Всего студентов: {total_students}\n"
                        f"✅ Выполнили норму: {total_completed} ({round(overall_rate, 1)}%)\n"
                        f"❌ Не выполнили: {total_not_completed}\n\n"
                        f"📋 **По менеджерам:**\n"
                    )
                    
                    for report in manager_reports:
                        response += report + "\n"
                    
                    await event.reply(response)
                    return
                
                # Статистика по конкретному менеджеру
                await event.reply(f"📊 Собираю статистику для {manager_name}...")
                
                stats = await aggregator.get_manager_stats(manager_name)
                
                if stats['total_students'] == 0:
                    await event.reply(
                        f"ℹ️ У менеджера **{manager_name}** нет студентов в статусе 'Учится'."
                    )
                    return
                
                # Формируем отчёт
                response = (
                    f"📊 **СТАТИСТИКА: {manager_name}** (текущий месяц)\n\n"
                    f"👥 Всего студентов: {stats['total_students']}\n"
                    f"✅ Выполнили норму: {stats['completed_norm']} ({stats['completion_rate']}%)\n"
                    f"❌ Не выполнили: {stats['not_completed']}\n\n"
                )
                
                # Детализация по студентам
                if stats['students']:
                    response += "📋 **Детали:**\n\n"
                    
                    # Сначала те, кто выполнил норму
                    completed = [s for s in stats['students'] if s['completed'] == '✅']
                    not_completed = [s for s in stats['students'] if s['completed'] != '✅']
                    
                    if completed:
                        response += "✅ **Выполнили норму:**\n"
                        for student in completed:
                            response += (
                                f"• {student['name']} (месяц {student['current_month']}): "
                                f"{student['fact']}/{student['goal']} уроков\n"
                            )
                        response += "\n"
                    
                    if not_completed:
                        response += "❌ **Не выполнили:**\n"
                        for student in not_completed:
                            response += (
                                f"• {student['name']} (месяц {student['current_month']}): "
                                f"{student['fact']}/{student['goal']} уроков ({student['percentage']})\n"
                            )
                
                # Разбиваем на части если длиннее 4096 символов
                MAX_LEN = 4096
                if len(response) <= MAX_LEN:
                    await event.reply(response, parse_mode='md')
                else:
                    parts = []
                    chunk = ''
                    for line in response.split('\n'):
                        if len(chunk) + len(line) + 1 > MAX_LEN:
                            parts.append(chunk)
                            chunk = line + '\n'
                        else:
                            chunk += line + '\n'
                    if chunk.strip():
                        parts.append(chunk)
                    for part in parts:
                        await event.reply(part, parse_mode='md')
                logger.info(f"Статистика monthstats для {manager_name} отправлена {sender_id}")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке /monthstats: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка при получении статистики: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/syncprogress'))
        async def handle_syncprogress_command(event):
            """
            Обработчик команды /syncprogress.
            Синхронизирует сводную таблицу прогресса с данными из "Общий список new" и трекеров.
            Использование: /syncprogress месяцГод  например /syncprogress март26
            """
            try:
                # Только в личных сообщениях
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                # Только руководитель может запускать /syncprogress
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Команда `/syncprogress` доступна только руководителю.", parse_mode='md')
                    return
                
                # Парсим обязательный аргумент месяца
                import re as _re
                parts = event.message.text.strip().split(maxsplit=1)
                if len(parts) < 2 or not parts[1].strip():
                    await event.reply(
                        "❌ Нужно указать месяц.\n\n"
                        "Формат: `/syncprogress апрель26`\n"
                        "Чистая команда `/syncprogress` отключена, чтобы бот не выбирал месяц автоматически.",
                        parse_mode='md'
                    )
                    return

                arg = parts[1].strip().lower().replace(' ', '')
                month_map = {
                    'январь': 'Январь', 'февраль': 'Февраль', 'март': 'Март',
                    'апрель': 'Апрель', 'май': 'Май', 'июнь': 'Июнь',
                    'июль': 'Июль', 'август': 'Август', 'сентябрь': 'Сентябрь',
                    'октябрь': 'Октябрь', 'ноябрь': 'Ноябрь', 'декабрь': 'Декабрь',
                }
                m = _re.fullmatch(r'([а-яё]+)(\d{2})', arg)
                if not m:
                    await event.reply("❌ Формат: `/syncprogress апрель26`", parse_mode='md')
                    return

                word, yr = m.group(1), m.group(2)
                if word not in month_map:
                    await event.reply(f"❌ Неизвестный месяц: `{word}`\n\nПример: `/syncprogress апрель26`", parse_mode='md')
                    return

                month_label = month_map[word] + yr
                label_display = month_label
                await event.reply(f"🔄 Синхронизирую сводную таблицу прогресса за {label_display}...")
                
                # Импортируем progress_aggregator
                from progress_aggregator import get_progress_aggregator
                aggregator = get_progress_aggregator()
                
                # Синхронизируем
                await aggregator.sync_students_from_vipalina(month_label=month_label)
                
                await event.reply(
                    f"✅ Синхронизация завершена!\n\n"
                    f"📊 Сводная таблица 'Прогресс менеджеров' обновлена за {label_display}.\n"
                    "Данные о выполнении нормы подтягиваются из трекеров через IMPORTRANGE."
                )
                logger.info(f"Синхронизация прогресса выполнена пользователем {sender_id}, месяц: {label_display}")
                
            except Exception as e:
                logger.error(f"Ошибка при синхронизации прогресса: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка при синхронизации: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/kpi(?:\s|$)'))
        async def handle_kpi_command(event):
            """Обработчик команды /kpi — KPI по норме уроков за указанный или текущий месяц.
            
            Использование:
                /kpi — KPI за текущий месяц
                /kpi февраль26 — KPI за февраль 2026
            """
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                
                from report_generator import get_report_generator
                from progress_aggregator import get_progress_aggregator
                
                report_gen = get_report_generator()
                manager_name = report_gen._get_manager_name_by_id(sender_id)
                if not manager_name:
                    await event.reply("❌ Не удалось определить ваше имя менеджера в KPI Ultra.")
                    return
                
                # Парсим аргумент (название месяца, например "февраль26")
                message_text = event.message.text.strip()
                parts = message_text.split(maxsplit=1)
                
                month_label = None
                if len(parts) > 1:
                    # Есть аргумент
                    arg = parts[1].strip().lower()
                    
                    # Маппинг русских названий месяцев на капитализированные формы
                    month_map = {
                        'январь': 'Январь',
                        'февраль': 'Февраль',
                        'март': 'Март',
                        'апрель': 'Апрель',
                        'май': 'Май',
                        'июнь': 'Июнь',
                        'июль': 'Июль',
                        'август': 'Август',
                        'сентябрь': 'Сентябрь',
                        'октябрь': 'Октябрь',
                        'ноябрь': 'Ноябрь',
                        'декабрь': 'Декабрь',
                    }
                    
                    # Выделяем название месяца и год (например, "февраль26" → "февраль" + "26")
                    import re
                    match = re.match(r'([a-яа-я]+)(\d{2})?', arg)
                    if match:
                        month_word = match.group(1)
                        year_suffix = match.group(2) if match.group(2) else None
                        
                        if month_word in month_map:
                            month_name_cap = month_map[month_word]
                            if year_suffix:
                                month_label = f"{month_name_cap}{year_suffix}"
                            else:
                                await event.reply(
                                    "❌ Не указан год.\n\n"
                                    "Пример: `/kpi февраль26` или `/kpi январь27`",
                                    parse_mode='md'
                                )
                                return
                        else:
                            await event.reply(
                                f"❌ Неизвестный месяц: `{month_word}`.\n\n"
                                "Пример: `/kpi февраль26`, `/kpi январь26`",
                                parse_mode='md'
                            )
                            return
                    else:
                        await event.reply(
                            "❌ Некорректный формат месяца.\n\n"
                            "Пример: `/kpi февраль26` или `/kpi январь27`",
                            parse_mode='md'
                        )
                        return
                
                aggregator = get_progress_aggregator()
                
                # Для руководителя — сводка по всему отделу
                if sender_id in HEAD_IDS:
                    await event.reply(f"📊 Собираю статистику отдела за {month_label if month_label else 'текущий месяц'}...")
                    all_managers = [
                        "Марина Иванова",
                        "Оля Антипанова",
                        "Кристина Махмудян",
                        "Лиза Виноградова",
                        "Катя Чайка",
                        "Оля Тихонова",
                        "Катя Пилипенко",
                        "Ксюша Уланова"
                    ]
                    total_students = 0
                    total_completed = 0
                    total_not_completed = 0
                    manager_reports = []
                    for mgr in all_managers:
                        st = await aggregator.get_manager_stats(mgr, month_label=month_label)
                        if st['total_students'] > 0:
                            total_students += st['total_students']
                            total_completed += st['completed_norm']
                            total_not_completed += st['not_completed']
                            manager_reports.append(
                                f"• {mgr}: {st['completed_norm']}/{st['total_students']} ({st['completion_rate']}%)"
                            )
                    overall_rate = round(total_completed / total_students * 100, 1) if total_students > 0 else 0
                    month_label_display = month_label if month_label else 'текущий месяц'
                    response = (
                        f"📊 **СТАТИСТИКА ОТДЕЛА** ({month_label_display})\n\n"
                        f"👥 Всего студентов: {total_students}\n"
                        f"✅ Выполнили норму: {total_completed} ({overall_rate}%)\n"
                        f"❌ Не выполнили: {total_not_completed}\n\n"
                        f"📋 **По менеджерам:**\n"
                    )
                    for report in manager_reports:
                        response += report + "\n"
                    await event.reply(response)
                    return
                
                stats = await aggregator.get_manager_stats(manager_name, month_label=month_label)
                month_label_display = stats.get('month_label', '') or 'текущий месяц'
                total = stats.get('total_students', 0)
                completed = stats.get('completed_norm', 0)
                not_completed = stats.get('not_completed', 0)
                rate = stats.get('completion_rate', 0)
                
                if total == 0:
                    await event.reply(
                        f"📊 KPI по норме уроков за {month_label_display}\n\n"
                        f"У вас нет студентов в статусе 'Учится' для этого месяца в таблице 'Прогресс менеджеров'."
                    )
                    return
                
                text = (
                    f"📊 **KPI по норме уроков**\n"
                    f"👤 Менеджер: {manager_name}\n"
                    f"📅 Месяц: {month_label_display}\n\n"
                    f"👥 Всего студентов 'Учится': {total}\n"
                    f"✅ Выполнили норму: {completed}\n"
                    f"⚠️ Не выполнили норму: {not_completed}\n"
                    f"📈 KPI: {rate}%\n\n"
                    f"Детали по студентам смотрите на листе 'Прогресс менеджеров' (фильтр по менеджеру и месяцу)."
                )
                await event.reply(text)
            except Exception as e:
                logger.error(f"Ошибка при расчёте KPI: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка при расчёте KPI: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'^/testreminders(?:\s+(.+))?$'))
        async def handle_test_reminders_command(event):
            """Ручное тестирование еженедельных напоминаний (только для руководителя)"""
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                
                # Только для руководителя VIP-отдела
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Эта команда доступна только руководителю VIP-отдела.")
                    return
                
                if not self.weekly_reminders:
                    await event.reply("❌ Модуль еженедельных напоминаний не инициализирован.")
                    return
                
                # Парсим имя менеджера (если есть)
                match = event.pattern_match
                manager_name = match.group(1).strip() if match.group(1) else None
                
                if manager_name:
                    await event.reply(f"🧪 Тестовая отправка напоминаний для менеджера: {manager_name}...")
                    await self.weekly_reminders.send_manual_reminder_for_manager(manager_name)
                else:
                    await event.reply("🧪 Тестовая отправка еженедельных напоминаний всем менеджерам...")
                    await self.weekly_reminders.send_manual_reminder_now()
                
                await event.reply("✅ Тестовая отправка завершена!")
                logger.info(f"Тестовые напоминания отправлены вручную руководителем {sender_id}" + (f" для {manager_name}" if manager_name else ""))
                
            except Exception as e:
                logger.error(f"Ошибка при тестировании напоминаний: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/testreminder (\d+)'))
        async def handle_test_reminder_student_command(event):
            """Тестовое напоминание для одного студента (для руководителя и менеджеров)"""
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                
                # Для руководителя и всех VIP-менеджеров
                if sender_id != VIP_HEAD['telegram_id'] and not self._is_vip_manager(sender_id):
                    await event.reply("❌ Эта команда доступна только руководителю и VIP-менеджерам.")
                    return
                
                if not self.weekly_reminders:
                    await event.reply("❌ Модуль ежедневных напоминаний не инициализирован.")
                    return
                
                # Парсим getcourse_id
                match = event.pattern_match
                getcourse_id = match.group(1)
                
                await event.reply(f"🧪 Отправляю тестовое напоминание для студента {getcourse_id}...")
                
                success = await self.weekly_reminders.send_test_reminder_for_student(getcourse_id)
                
                if success:
                    await event.reply("✅ Тестовое напоминание отправлено!")
                else:
                    await event.reply("❌ Не удалось отправить напоминание")
                
                logger.info(f"Тестовое напоминание для {getcourse_id} отправлено руководителем {sender_id}")
                
            except Exception as e:
                logger.error(f"Ошибка при тестовом напоминании: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/activate'))
        @self.bot_client.on(events.NewMessage(pattern=r'/activate', func=lambda e: e.is_group))
        async def handle_activate_command(event):
            """
            Обработчик команды /activate <getcourse_id>
            Активирует существующий чат для SLA-трекинга и логирования.
            """
            import re
            try:
                # 1. Проверяем, что команду вызвал менеджер
                manager_id = event.sender_id
                if not self._is_vip_manager(manager_id):
                    await event.reply("У вас нет прав для выполнения этой команды.")
                    return
                
                # 2. Проверяем, что это групповой чат
                if not event.is_group:
                    await event.reply("❗ Эта команда работает только в групповых чатах.")
                    return
                
                chat_id = event.chat_id
                message_text = event.message.text
                
                # Извлекаем getcourse_id из команды
                match = re.search(r'/activate\s+(\d+)', message_text)
                if not match:
                    await event.reply(
                        "❓ **Активация чата**\n\n"
                        "Использование:\n"
                        "`/activate <getcourse_id>`\n\n"
                        "Пример:\n"
                        "`/activate 123456789`\n\n"
                        "Эта команда активирует отслеживание SLA и логирование сообщений студента в этом чате."
                    )
                    return
                
                getcourse_id = match.group(1)
                
                # Валидация: проверяем, существует ли студент в KPI Ultra
                from report_generator import get_report_generator
                report_gen = get_report_generator()
                
                student = await report_gen.get_student_by_id(getcourse_id)
                if not student:
                    await event.reply(
                        f"⚠️ Студент с ID `{getcourse_id}` не найден в KPI Ultra.\n\n"
                        f"Чат всё равно будет активирован, но данные студента не синхронизированы."
                    )
                
                # 3. Проверяем, что чат ещё не активирован
                existing_mapping = self.chat_to_student.get(chat_id)
                if existing_mapping == getcourse_id:
                    # Чат уже активирован для того же студента — переактивируем (пересинхронизация)
                    await event.reply(
                        f"⚠️ Чат уже активирован для `{existing_mapping}`.\n"
                        f"⚡ Пересинхронизирую данные..."
                    )
                elif existing_mapping:
                    # Чат активирован для другого студента — переактивируем
                    logger.warning(f"⚠️ Чат {chat_id} был активирован для {existing_mapping}, переактивируем для {getcourse_id}")
                    del self.chat_to_student[chat_id]
                    await event.reply("⚡ Активирую чат...")
                else:
                    await event.reply("⌛ Активирую чат...")
                                
                # 4. Получаем ID бота, если ещё не получен
                if self.bot_user_id is None:
                    try:
                        me = await event.client.get_me()
                        self.bot_user_id = me.id
                        logger.info(f"🤖 ID клиента (@{me.username}) закеширован: {self.bot_user_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось получить ID клиента: {e}")
                        self.bot_user_id = -1  # Используем -1 чтобы не повторять ошибку
                
                # 5. Получаем список участников чата
                candidate_users = []
                                
                try:
                    async for user in event.client.iter_participants(chat_id):
                        # Пропускаем ботов и менеджеров
                        if user.bot:
                            continue
                        if user.id in ALL_MANAGER_IDS:
                            continue
                        # Пропускаем самого бота (user client)
                        if self.bot_user_id and user.id == self.bot_user_id:
                            continue
                                        
                        # Это потенциальный студент
                        candidate_users.append(user)
                                        
                except Exception as e:
                    logger.error(f"Ошибка при получении участников чата: {e}")
                    await event.reply(f"❌ Ошибка при получении участников чата: {e}")
                    return
                                
                if not candidate_users:
                    await event.reply(
                        "❌ Не найден студент в чате.\n\n"
                        "Убедитесь, что в чате есть участник, который не является менеджером или ботом."
                    )
                    return
                                
                # 6. Получение invite-ссылки с приоритетом из столбца H (KPI Ultra)
                invite_link = ""
                
                # Приоритет 1: Проверяем столбец H в "Общий список new"
                if self.kpi_sheets:
                    try:
                        existing_link = await self.kpi_sheets.get_chat_link_by_getcourse_id(getcourse_id)
                        if existing_link:
                            invite_link = existing_link
                            logger.info(f"✅ Используем invite-ссылку из столбца H: {invite_link}")
                    except Exception as e:
                        logger.warning(f"Не удалось прочитать столбец H для {getcourse_id}: {e}")
                
                # Приоритет 2: Попытаемся создать invite-ссылку через Telegram API
                if not invite_link:
                    try:
                        from telethon.tl.functions.messages import ExportChatInviteRequest
                        result = await event.client(ExportChatInviteRequest(chat_id))
                        invite_link = result.link if hasattr(result, 'link') else ""
                        if invite_link:
                            logger.info(f"✅ Создана новая invite-ссылка через ExportChatInviteRequest")
                    except Exception as e:
                        logger.warning(f"Не удалось создать invite-ссылку: {e}")
                
                # Если ссылка не получена ни одним способом
                if not invite_link:
                    logger.warning(f"⚠️ Не удалось получить invite-ссылку для чата {chat_id}")
                                
                # 7. Если найден только один кандидат → активируем сразу
                if len(candidate_users) == 1:
                    student_user = candidate_users[0]
                    await self._complete_chat_activation(
                        chat_id=chat_id,
                        getcourse_id=getcourse_id,
                        student_user=student_user,
                        manager_id=manager_id,
                        invite_link=invite_link,
                        reply_event=event,
                        student_kpi_data=student,
                        active_client=event.client
                    )
                    return
                                
                # 8. Если несколько кандидатов → просим уточнить
                # Сохраняем состояние для диалога
                self.activate_student_selection_state[manager_id] = {
                    'chat_id': chat_id,
                    'getcourse_id': getcourse_id,
                    'candidates': candidate_users,
                    'invite_link': invite_link,
                    'student_kpi_data': student  # Сохраняем для последующего создания трекера
                }
                                
                # Формируем список кандидатов
                message = "⚠️ **НАЙДЕНО НЕСКОЛЬКО ПОТЕНЦИАЛЬНЫХ СТУДЕНТОВ**\n\n"
                message += "Укажите, кто из них является студентом?\n\n"
                                
                for idx, user in enumerate(candidate_users, 1):
                    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                    username = f"@{user.username}" if user.username else "Нет username"
                    message += f"{idx}. **{full_name}** ({username})\n"
                                
                message += "\n📝 **Как ответить:**\n"
                message += "Скопируйте **имя** студента из списка и отправьте в любом формате.\n"
                message += "Либо отправьте `/cancel` для отмены."
                                
                await event.reply(message)
                logger.info(f"Менеджер {manager_id} получил запрос на выбор студента из {len(candidate_users)} кандидатов")
                
            except Exception as e:
                logger.error(f"Ошибка при активации чата: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка при активации чата: {e}")
                
                # Уведомляем руководителя VIP-отдела
                try:
                    chat_id = event.chat_id
                    manager_id = event.sender_id
                    manager_info = self._get_manager_info(manager_id)
                    manager_name = manager_info['name'] if manager_info else f"ID {manager_id}"
                    
                    # Получаем getcourse_id если есть в команде
                    import re
                    match = re.search(r'/activate\s+(\d+)', event.message.text or '')
                    getcourse_id = match.group(1) if match else "неизвестно"
                    
                    chat_entity = await event.client.get_entity(chat_id)
                    chat_title = chat_entity.title if hasattr(chat_entity, 'title') else f"Chat {chat_id}"
                    
                    error_message = (
                        f"❌ **Ошибка активации чата**\n\n"
                        f"Чат: **{chat_title}**\n"
                        f"Chat ID: `{chat_id}`\n"
                        f"GetCourse ID: `{getcourse_id}`\n"
                        f"Менеджер: {manager_name}\n\n"
                        f"Ошибка: {str(e)[:200]}\n\n"
                        f"🔧 Проверьте логи для деталей."
                    )
                    
                    await self.bot_client.send_message(VIP_HEAD['telegram_id'], error_message)
                    logger.info(f"✉️ Уведомление об ошибке /activate отправлено руководителю")
                except Exception as notify_error:
                    logger.error(f"Ошибка при отправке уведомления об ошибке /activate: {notify_error}")
        
        @self.client.on(events.NewMessage(pattern=r'/deactivate'))
        @self.bot_client.on(events.NewMessage(pattern=r'/deactivate', func=lambda e: e.is_group))
        async def handle_deactivate_command(event):
            """Исключает чат из рассылок и сбрасывает активацию"""
            try:
                # Только в групповых чатах
                if not event.is_group:
                    return
                
                # Проверяем права (менеджер, дежурный, руководитель)
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    await event.reply("У вас нет прав для выполнения этой команды.")
                    return
                
                chat_id = event.chat_id
                
                # 1. Удаляем chat_to_student mapping
                removed_student = self.chat_to_student.pop(chat_id, None)
                
                # 2. Очищаем сегмент рассылок в таблице
                sheet_success = False
                if self.sheets_integration:
                    sheet_success = await self.sheets_integration.clear_broadcast_segment(chat_id)
                
                # 3. Удаляем из персистенса Chat_To_Student
                if removed_student and self.persistence:
                    try:
                        self.persistence.delete_chat_student_mapping(chat_id)
                    except Exception:
                        pass
                
                parts = []
                if removed_student:
                    parts.append(f"✅ Чат деактивирован (\u0441т\u0443\u0434\u0435\u043d\u0442 {removed_student})")
                elif sheet_success:
                    parts.append("✅ Чат деактивирован")
                else:
                    parts.append("✅ Чат деактивирован (не был в таблице, но mapping очищен)")
                
                if not sheet_success and not removed_student:
                    await event.reply("❌ Чат не был активирован")
                else:
                    await event.reply(parts[0])
                
            except Exception as e:
                logger.error(f"Ошибка при деактивации: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/status'))
        @self.bot_client.on(events.NewMessage(pattern=r'/status', func=lambda e: e.is_group))
        async def handle_status_command(event):
            """Показывает статус активации чата"""
            try:
                if not event.is_group:
                    await event.reply("❗ Эта команда работает только в групповых чатах.")
                    return
                
                chat_id = event.chat_id
                getcourse_id = self.chat_to_student.get(chat_id)
                
                if getcourse_id:
                    await event.reply("✅ Чат активирован")
                else:
                    await event.reply("❌ Чат не активирован")
                
            except Exception as e:
                logger.error(f"Ошибка при проверке статуса: {e}")
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/oauth'))
        async def handle_oauth_command(event):
            """Генерирует ссылку для авторизации Google OAuth"""
            try:
                if not event.is_private:
                    return
                
                sender_id = event.sender_id
                
                # Только для руководителя VIP-отдела
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Эта команда доступна только руководителю VIP-отдела.")
                    return
                
                # Проверяем, есть ли уже код в сообщении
                message_text = event.message.text.strip()
                parts = message_text.split(maxsplit=1)
                
                if len(parts) > 1:
                    # Передан код авторизации: /oauth КОД
                    code = parts[1].strip()
                    success, message = oauth_handler.exchange_code(sender_id, code)
                    # ВАЖНО: перезагружаем credentials в TrackerCreator из нового файла на диске
                    if success and self.tracker_creator:
                        try:
                            await asyncio.to_thread(self.tracker_creator._authorize)
                            logger.info("✅ TrackerCreator переавторизован с новым OAuth токеном")
                            message += "\n\n🔄 TrackerCreator перезагружен с новым токеном."
                        except Exception as reinit_err:
                            logger.error(f"⚠️ Не удалось переавторизовать TrackerCreator: {reinit_err}")
                            message += f"\n\n⚠️ Не удалось перезагрузить TrackerCreator: {reinit_err}"
                    await event.reply(message)
                else:
                    # Генерируем URL авторизации
                    auth_url, error = oauth_handler.generate_auth_url(sender_id)
                    
                    if error:
                        await event.reply(error)
                        return
                    
                    message = f"""🔐 **Авторизация Google OAuth**

1. Перейдите по ссылке:
{auth_url}

2. Войдите в аккаунт `vipzerocoder@gmail.com`

3. Разрешите доступ к Google Drive и Sheets

4. Скопируйте код авторизации со страницы

5. Отправьте мне код командой:
`/oauth ВАШ_КОД`"""
                    
                    await event.reply(message)
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке /oauth: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")
        
        @self.client.on(events.NewMessage(pattern=r'/cleanprivchats'))
        async def handle_cleanprivchats_command(event):
            """
            Удаляет личные чаты Випалины со студентами (только private DM, не группы).
            Критерий: приватный диалог с не-сотрудником, последнее сообщение >30 дней назад.
            Использование:
              /cleanprivchats        — показывает сколько чатов будет удалено
              /cleanprivchats да     — выполняет очистку
            """
            try:
                if not event.is_private:
                    return

                sender_id = event.sender_id
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Команда доступна только руководителю.")
                    return

                import asyncio
                from datetime import datetime, timezone, timedelta
                from telethon.tl.functions.messages import DeleteHistoryRequest

                message_text = event.message.text.strip()
                confirm_mode = message_text.lower().endswith(' да')

                cutoff = datetime.now(timezone.utc) - timedelta(days=30)

                await event.reply("🔍 Анализирую диалоги...")

                to_clean = []  # list of (entity, username_or_name, last_date)
                async for dialog in self.client.iter_dialogs():
                    # Только личные диалоги с пользователями (не группы, не каналы)
                    if not dialog.is_user:
                        continue
                    entity = dialog.entity
                    # Пропускаем сотрудников отдела
                    if entity.id in ALL_MANAGER_IDS:
                        continue
                    # Пропускаем самого себя (Saved Messages)
                    if getattr(entity, 'is_self', False):
                        continue
                    # Проверяем дату последнего сообщения
                    last_date = dialog.date
                    if last_date and last_date < cutoff:
                        name = getattr(entity, 'first_name', '') or ''
                        username = getattr(entity, 'username', '') or ''
                        label = f"{name} (@{username})" if username else name or str(entity.id)
                        to_clean.append((entity, label, last_date))

                if not to_clean:
                    await event.reply("✅ Нет личных чатов старше 30 дней для очистки.")
                    return

                preview_lines = [f"  • {label} — {dt.strftime('%d.%m.%Y')}" for _, label, dt in to_clean[:20]]
                preview = "\n".join(preview_lines)
                if len(to_clean) > 20:
                    preview += f"\n  ... и ещё {len(to_clean) - 20}"

                if not confirm_mode:
                    await event.reply(
                        f"🧹 **Очистка личных чатов со студентами**\n\n"
                        f"Будет удалено **{len(to_clean)}** личных диалогов (последнее сообщение >30 дней назад):\n\n"
                        f"{preview}\n\n"
                        f"Для подтверждения отправь:\n`/cleanprivchats да`",
                        parse_mode='md'
                    )
                    return

                # Выполняем очистку
                await event.reply(f"🗑 Удаляю {len(to_clean)} диалогов...")
                deleted = 0
                errors = 0
                for entity, label, _ in to_clean:
                    try:
                        await self.client(DeleteHistoryRequest(
                            peer=entity,
                            max_id=0,
                            just_clear=False,
                            revoke=False
                        ))
                        deleted += 1
                        await asyncio.sleep(0.3)  # небольшая задержка чтобы не словить флуд
                    except Exception as e:
                        logger.warning(f"Не удалось удалить диалог с {label}: {e}")
                        errors += 1

                result = f"✅ Очистка завершена!\n\nУдалено: {deleted} диалогов"
                if errors:
                    result += f"\nОшибок: {errors}"
                await event.reply(result)
                logger.info(f"[cleanprivchats] Удалено {deleted} личных диалогов, ошибок: {errors}")

            except Exception as e:
                logger.error(f"Ошибка при /cleanprivchats: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        @self.client.on(events.NewMessage(pattern=r'/notactivated'))
        async def handle_notactivated_command(event):
            """
            Показывает список групповых чатов, в которых Випалина есть,
            но которые НЕ активированы (нет в chat_to_student).
            Менеджер видит только свои чаты, руководитель — все.
            Использование: /notactivated (только в личке)
            """
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    await event.reply("❌ Команда доступна только VIP-менеджерам.")
                    return

                is_head = (sender_id in HEAD_IDS)
                sender_manager_info = self._get_manager_info(sender_id)
                sender_manager_name = sender_manager_info['name'] if sender_manager_info else None

                await event.reply("🔍 Сканирую чаты...")

                # 1. Строим индекс из листа Випалина: chat_id → {getcourse_id, manager_id}
                vipalina_chat_to_data = {}
                try:
                    if self.sheets_integration and self.sheets_integration.worksheet:
                        all_rows = await asyncio.to_thread(
                            self.sheets_integration.worksheet.get_all_values
                        )
                        for row in all_rows[1:]:
                            if len(row) > 2 and row[2] and row[2] not in ("-", ""):
                                try:
                                    cid = int(row[2])
                                    gcid = row[0].strip()
                                    mgr_id_str = row[6].strip() if len(row) > 6 else ""
                                    if gcid:
                                        vipalina_chat_to_data[cid] = {
                                            "getcourse_id": gcid,
                                            "manager_id": mgr_id_str,
                                        }
                                except ValueError:
                                    pass
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось прочитать Випалина для /notactivated: {e}")

                # 2. Строим индекс из KPI Общий список new:
                #    getcourse_id → {name, course, invite_link, manager_name}
                #    Столбцы: A=gcid(0), C=name(2), D=course(3), G=invite(6), K=manager(10)
                kpi_data = {}
                try:
                    if self.kpi_sheets and self.kpi_sheets.worksheet:
                        kpi_rows = await asyncio.to_thread(
                            self.kpi_sheets.worksheet.get_all_values
                        )
                        for row in kpi_rows[1:]:
                            if not row or not row[0]:
                                continue
                            gcid = row[0].strip()
                            if not gcid or not gcid.isdigit():
                                continue
                            kpi_data[gcid] = {
                                "name": row[2].strip() if len(row) > 2 else "",
                                "course": row[3].strip() if len(row) > 3 else "",
                                "invite_link": row[6].strip() if len(row) > 6 else "",
                                "manager_name": row[10].strip() if len(row) > 10 else "",
                            }
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось прочитать KPI Ultra для /notactivated: {e}")

                # 3. Индексы из Логи Випалина
                # chat_msgs_idx: chat_id(int) → {gcid, student_name, manager_name, course}
                # chat_to_student_logs_idx: chat_id(int) → {gcid, student_name, invite_link}
                # name_to_gcid: имя.lower() → gcid  (из Students_Data, полные ФИО)
                chat_msgs_idx = {}
                chat_to_student_logs_idx = {}
                name_to_gcid = {}

                try:
                    if self.persistence and self.persistence.is_initialized():
                        # Student_Messages: timestamp(0),date(1),time(2),chat_id(3),
                        #   student_id(4),getcourse_id(5),student_name(6),
                        #   manager_name(7),message_type(8),message_text(9),course(10)
                        _sm_ws = self.persistence.worksheets.get("Student_Messages")
                        if _sm_ws:
                            _sm_rows = await asyncio.to_thread(_sm_ws.get_all_values)
                            for _row in _sm_rows[1:]:
                                if len(_row) < 6 or not _row[3] or not _row[5]:
                                    continue
                                try:
                                    _cid = int(_row[3])
                                except ValueError:
                                    continue
                                if _cid not in chat_msgs_idx:
                                    chat_msgs_idx[_cid] = {
                                        "gcid": _row[5].strip(),
                                        "student_name": _row[6].strip() if len(_row) > 6 else "",
                                        "manager_name": _row[7].strip() if len(_row) > 7 else "",
                                        "course": _row[10].strip() if len(_row) > 10 else "",
                                    }
                except Exception as _e:
                    logger.warning(f"⚠️ Не удалось прочитать Student_Messages для /notactivated: {_e}")

                try:
                    if self.persistence and self.persistence.is_initialized():
                        # Chat_To_Student: chat_id(0),getcourse_id(1),student_name(2),invite_link(3)
                        _cts_ws = self.persistence.worksheets.get("Chat_To_Student")
                        if _cts_ws:
                            _cts_rows = await asyncio.to_thread(_cts_ws.get_all_values)
                            for _row in _cts_rows[1:]:
                                if len(_row) < 2 or not _row[0] or not _row[1]:
                                    continue
                                try:
                                    _cid = int(_row[0])
                                except ValueError:
                                    continue
                                chat_to_student_logs_idx[_cid] = {
                                    "gcid": _row[1].strip(),
                                    "student_name": _row[2].strip() if len(_row) > 2 else "",
                                    "invite_link": _row[3].strip() if len(_row) > 3 else "",
                                }
                except Exception as _e:
                    logger.warning(f"⚠️ Не удалось прочитать Chat_To_Student для /notactivated: {_e}")

                try:
                    if self.persistence and self.persistence.is_initialized():
                        # Students_Data: getcourse_id(0), name(1), ..., telegram_id(6)
                        _sd_ws = self.persistence.worksheets.get("Students_Data")
                        if _sd_ws:
                            _sd_rows = await asyncio.to_thread(_sd_ws.get_all_values)
                            for _row in _sd_rows[1:]:
                                if not _row or not _row[0]:
                                    continue
                                _gcid = _row[0].strip()
                                _name = _row[1].strip() if len(_row) > 1 else ""
                                if _gcid and _name:
                                    name_to_gcid[_name.lower()] = _gcid
                except Exception as _e:
                    logger.warning(f"⚠️ Не удалось прочитать Students_Data для /notactivated: {_e}")

                def _match_title_to_gcid(title: str) -> "str | None":
                    """Фолбэк: поиск gcid по заголовку чата через полное ФИО из Students_Data."""
                    import re as _re
                    parts = _re.split(r"[,.|:|\-–]", title)
                    if not parts:
                        return None
                    name_part = parts[0].strip().lower()
                    if not name_part or len(name_part) < 4:
                        return None
                    if name_part in name_to_gcid:
                        return name_to_gcid[name_part]
                    name_words = set(name_part.split())
                    for _sd_name_lower, _sd_gcid in name_to_gcid.items():
                        _sd_words = set(_sd_name_lower.split())
                        if len(name_words & _sd_words) >= 2 and len(name_words) >= 2:
                            return _sd_gcid
                    return None

                # Служебные чаты — пропускаем
                known_service_chats = set()
                try:
                    from config import VIP_DEPARTMENT_CHAT_ID, LUXURY_DEPARTMENT_CHAT_ID
                    known_service_chats.add(int(VIP_DEPARTMENT_CHAT_ID))
                    known_service_chats.add(int(LUXURY_DEPARTMENT_CHAT_ID))
                except Exception:
                    pass

                unactivated = []
                async for dialog in self.client.iter_dialogs():
                    if not dialog.is_group:
                        continue
                    entity = dialog.entity
                    cid = entity.id
                    # Супергруппы в Telegram хранятся как -100<id>
                    full_cid = int(f"-100{cid}") if cid > 0 else cid

                    if full_cid in known_service_chats or cid in known_service_chats:
                        continue
                    if full_cid in self.chat_to_student or cid in self.chat_to_student:
                        continue

                    chat_title = getattr(entity, "title", "") or str(full_cid)

                    # Поиск данных студента по chat_id:
                    # 1) Випалина-лист (col C)
                    vip_entry = vipalina_chat_to_data.get(full_cid) or vipalina_chat_to_data.get(cid)
                    gcid = vip_entry["getcourse_id"] if vip_entry else None

                    # 2) Student_Messages (Логи Випалина)
                    logs_msg = chat_msgs_idx.get(full_cid) or chat_msgs_idx.get(cid)
                    if not gcid and logs_msg:
                        gcid = logs_msg["gcid"]

                    # 3) Chat_To_Student (Логи Випалина)
                    logs_cts = chat_to_student_logs_idx.get(full_cid) or chat_to_student_logs_idx.get(cid)
                    if not gcid and logs_cts:
                        gcid = logs_cts["gcid"]

                    # 4) Фолбэк по имени из Students_Data
                    if not gcid:
                        gcid = _match_title_to_gcid(chat_title)

                    # Собираем финальные данные студента
                    kpi = kpi_data.get(gcid) if gcid else None

                    student_name = ""
                    manager_name = ""
                    course = ""
                    invite_link = ""

                    # Данные из Student_Messages (наиболее свежие)
                    if logs_msg:
                        student_name = logs_msg.get("student_name", "")
                        manager_name = logs_msg.get("manager_name", "")
                        course = logs_msg.get("course", "")

                    # Данные из KPI (invite_link, перебиваем course/manager если пустые)
                    if kpi:
                        invite_link = kpi.get("invite_link", "")
                        if not course:
                            course = kpi.get("course", "")
                        if not manager_name:
                            manager_name = kpi.get("manager_name", "")
                        if not student_name:
                            student_name = kpi.get("name", "")

                    # invite_link из Chat_To_Student если KPI не дал
                    if not invite_link and logs_cts:
                        invite_link = logs_cts.get("invite_link", "")
                    if not student_name and logs_cts:
                        student_name = logs_cts.get("student_name", "")

                    # Фильтр по менеджеру (не для руководителя)
                    if not is_head:
                        if not manager_name:
                            continue  # нет данных о менеджере — пропускаем
                        if manager_name.strip() != (sender_manager_name or "").strip():
                            continue

                    unactivated.append({
                        "chat_title": chat_title,
                        "chat_id": full_cid,
                        "getcourse_id": gcid,
                        "name": student_name,
                        "course": course,
                        "invite_link": invite_link,
                        "manager_name": manager_name,
                    })

                if not unactivated:
                    suffix = "" if is_head else " для вас"
                    await event.reply(f"✅ Нет неактивированных чатов{suffix}.")
                    return

                # Формируем блоки текста
                header = f"⚠️ **Неактивированные чаты: {len(unactivated)}**"
                blocks = []
                for item in unactivated:
                    display_name = item["name"] or item["chat_title"]
                    course = item["course"]
                    invite = item["invite_link"]
                    mgr = item["manager_name"]
                    gcid = item["getcourse_id"]

                    line = f"👤 **{display_name}**" + (f", {course}" if course else "")
                    if invite:
                        line += f"\n🔗 [Ссылка на чат]({invite})"
                    else:
                        line += f"\n💬 Chat ID: `{item['chat_id']}`"
                    if is_head and mgr:
                        line += f"\n👩‍💼 Менеджер: {mgr}"
                    if gcid:
                        line += f"\n→ `/activate {gcid}`"
                    else:
                        line += f"\n→ GetCourse ID неизвестен"
                    blocks.append(line)

                # Разбиваем на сообщения не разрывая блоки (макс 4000 символов)
                messages = []
                current = header
                for block in blocks:
                    addition = "\n\n" + block
                    if len(current) + len(addition) > 4000:
                        messages.append(current)
                        current = block
                    else:
                        current += addition
                if current:
                    messages.append(current)

                for msg in messages:
                    await event.reply(msg, parse_mode="md")
                    await asyncio.sleep(0.3)

            except Exception as e:
                logger.error(f"Ошибка при /notactivated: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")


        # ===== /inactive =====
        @self.client.on(events.NewMessage(pattern=r'/inactive'))
        async def handle_inactive_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                is_head = (sender_id in HEAD_IDS)
                sender_mgr = self._get_manager_name_by_id(sender_id)
                n_match = re.search(r'/inactive\s+(\d+)', event.message.text.strip())
                n_days = int(n_match.group(1)) if n_match else 14
                await event.reply(f"🔍 Ищу студентов без контакта >{n_days} дней...")
                # Загружаем Випалина (источник дат)
                rows = []
                if self.sheets_integration and self.sheets_integration.worksheet:
                    rows = await asyncio.to_thread(self.sheets_integration.worksheet.get_all_values)
                # Строим gcid → статус из "Общий список new" (текущий месяц)
                EXCL_STATUSES = {'Закончил', 'Не с нами', 'Окупился', 'Возврат'}
                excluded_gcids = set()
                try:
                    from report_generator import get_report_generator as _get_rg_ia
                    _students_ia = await _get_rg_ia()._get_kpi_data_for_month(None)
                    for _s in _students_ia:
                        if _s.get('status', '') in EXCL_STATUSES:
                            _g = _s.get('getcourse_id', '')
                            if _g:
                                excluded_gcids.add(_g)
                except Exception as _e_ia:
                    logger.warning(f"/inactive: не удалось загрузить статусы KPI: {_e_ia}")
                from datetime import date as _idate, datetime as _idtt
                today = _idate.today()
                def _ipd(s):
                    s = (s or '').strip()[:10]
                    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
                        try:
                            return _idtt.strptime(s, fmt).date()
                        except Exception:
                            pass
                    return None
                results = []
                for row in rows[1:]:
                    if not row or not row[0]:
                        continue
                    gcid = row[0].strip()
                    mgr = row[7].strip() if len(row) > 7 else ""
                    status = row[11].strip() if len(row) > 11 else ""
                    last_str = row[14].strip() if len(row) > 14 else ""
                    course = row[4].strip() if len(row) > 4 else ""
                    name = row[3].strip() if len(row) > 3 else ""
                    # Исключаем по статусу Випалины (базовые)
                    if any(s in status for s in ['Закончил', 'Завершил', 'Не с нами', 'Окупился', 'Возврат']):
                        continue
                    # Исключаем по статусу из Общий список new
                    if gcid in excluded_gcids:
                        continue
                    if not is_head and mgr != (sender_mgr or ""):
                        continue
                    last_d = _ipd(last_str)
                    # Пропускаем студентов без даты
                    if not last_d:
                        continue
                    days_ago = (today - last_d).days
                    if days_ago < n_days:
                        continue
                    label = last_d.strftime('%d.%m.%Y') + f" ({days_ago} дн. назад)"
                    results.append((days_ago, gcid, name, course, mgr, label))
                results.sort(key=lambda x: -x[0])
                if not results:
                    await event.reply(f"✅ Нет студентов без контакта более {n_days} дней.")
                    return
                NL, NL2 = chr(10), chr(10)*2
                header = f"📵 **Без контакта >{n_days} дней: {len(results)}**"
                blocks = []
                for days_ago, gcid, name, course, mgr, label in results:
                    parts = [f"👤 **{name or gcid}**" + (f", {course}" if course else "")]
                    parts.append(f"📅 Последний контакт: {label}")
                    if is_head and mgr:
                        parts.append(f"👩‍💼 {mgr}")
                    parts.append(f"→ `/report {gcid}`")
                    blocks.append(NL.join(parts))
                cur = header
                for b in blocks:
                    add = NL2 + b
                    if len(cur) + len(add) > 4000:
                        await event.reply(cur, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur = b
                    else:
                        cur += add
                if cur:
                    await event.reply(cur, parse_mode='md')
            except Exception as e:
                logger.error(f"Ошибка при /inactive: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        # ===== /notracker =====
        @self.client.on(events.NewMessage(pattern=r'/notracker'))
        async def handle_notracker_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                is_head = (sender_id in HEAD_IDS)
                sender_mgr = self._get_manager_name_by_id(sender_id)
                await event.reply("🔍 Загружаю данные...")
                from report_generator import get_report_generator
                report_gen = get_report_generator()
                students = await report_gen._get_kpi_data_for_month(None)
                results = []
                for s in students:
                    if s.get('is_archived'):
                        continue
                    status = s.get('status', '')
                    if status not in ('Новый', 'Учится'):
                        continue
                    tracker = s.get('tracker_url', '')
                    if tracker and tracker not in ('-', ''):
                        continue
                    mgr = s.get('manager_name', '')
                    if not is_head:
                        sm = (sender_mgr or '').lower()
                        if sm not in mgr.lower() and mgr.lower() not in sm:
                            continue
                    results.append(s)
                if not results:
                    suffix = '' if is_head else ' у вас'
                    await event.reply(f"✅ Нет студентов без трекера{suffix} (статус Новый/Учится).")
                    return
                NL, NL2 = chr(10), chr(10)*2
                header = f"📋 **Без трекера (Новый/Учится): {len(results)}**"
                blocks = []
                for s in results:
                    gcid = s.get('getcourse_id', '')
                    name = s.get('name', gcid)
                    course = s.get('course', '')
                    mgr = s.get('manager_name', '')
                    status = s.get('status', '')
                    parts = [f"👤 **{name}**" + (f", {course}" if course else "")]
                    parts.append(f"📌 Статус: {status}")
                    if is_head and mgr:
                        parts.append(f"👩\u200d💼 {mgr}")
                    if gcid:
                        parts.append(f"→ `/createtracker {gcid}`")
                    blocks.append(NL.join(parts))
                cur = header
                for b in blocks:
                    add = NL2 + b
                    if len(cur) + len(add) > 4000:
                        await event.reply(cur, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur = b
                    else:
                        cur += add
                if cur:
                    await event.reply(cur, parse_mode='md')
            except Exception as e:
                logger.error(f"Ошибка при /notracker: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        # ===== /nosla =====
        @self.client.on(events.NewMessage(pattern=r'/nosla'))
        async def handle_nosla_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                is_head = (sender_id in HEAD_IDS)
                sender_mgr = self._get_manager_name_by_id(sender_id)
                await event.reply("🔍 Загружаю активные SLA...")
                sla_rows = []
                if self.persistence and self.persistence.is_initialized():
                    _ws = self.persistence.worksheets.get("Active_SLA_Requests")
                    if _ws:
                        sla_rows = await asyncio.to_thread(_ws.get_all_values)
                if not sla_rows or len(sla_rows) <= 1:
                    await event.reply("✅ Нет открытых SLA-запросов.")
                    return
                # Определяем текущий месяц
                from datetime import datetime as _dtsla
                now_sla = _dtsla.now()
                cur_year_sla, cur_month_sla = now_sla.year, now_sla.month
                # Имена дежурных аккаунтов
                DUTY_NAMES = {'Черный Дежурный', 'Синий Дежурный', 'Изумрудный Дежурный'}
                # Строим gcid→менеджер
                gcid_to_mgr = {}
                if self.sheets_integration and self.sheets_integration.worksheet:
                    _vr = await asyncio.to_thread(self.sheets_integration.worksheet.get_all_values)
                    for row in _vr[1:]:
                        if row and row[0]:
                            _g = row[0].strip()
                            _m = row[7].strip() if len(row) > 7 else ""
                            if _g and _m:
                                gcid_to_mgr[_g] = _m
                results = []
                skipped_month = 0
                skipped_duty = 0
                skipped_offhours = 0
                for row in sla_rows[1:]:
                    if not row or not row[0]:
                        continue
                    cid_str = row[0].strip()
                    sname = row[2].strip() if len(row) > 2 else ""
                    req_text = row[3].strip() if len(row) > 3 else ""
                    req_time = row[4].strip() if len(row) > 4 else ""
                    is_work = row[5].strip().lower() if len(row) > 5 else ""
                    # Фильтр: только рабочее время
                    if is_work != 'true':
                        skipped_offhours += 1
                        continue
                    # Фильтр: только текущий месяц
                    if req_time:
                        try:
                            dt_sla = _dtsla.strptime(req_time[:19], '%Y-%m-%d %H:%M:%S')
                            if dt_sla.year != cur_year_sla or dt_sla.month != cur_month_sla:
                                skipped_month += 1
                                continue
                        except Exception:
                            skipped_month += 1
                            continue
                    else:
                        skipped_month += 1
                        continue
                    try:
                        cid = int(cid_str)
                    except ValueError:
                        continue
                    gcid = self.chat_to_student.get(cid)
                    if gcid is None:
                        cid2 = int(f"-100{abs(cid)}") if cid > 0 else cid
                        gcid = self.chat_to_student.get(cid2)
                    mgr = gcid_to_mgr.get(gcid or "", "")
                    # Фильтр: исключаем дежурные аккаунты
                    if mgr in DUTY_NAMES:
                        skipped_duty += 1
                        continue
                    if not is_head and mgr != (sender_mgr or ""):
                        continue
                    results.append((sname, req_text, req_time, cid_str, mgr))
                if not results:
                    suffix = '' if is_head else ' у вас'
                    note = f" (пропущено: {skipped_month} не тот мес., {skipped_offhours} нерабочее время, {skipped_duty} дежурные)"
                    await event.reply(f"✅ Нет открытых SLA-запросов{suffix} за текущий месяц{note}.")
                    return
                NL, NL2 = chr(10), chr(10)*2
                month_lbl = f"{cur_month_sla:02d}.{cur_year_sla}"
                header = f"⏰ **Открытые SLA ({month_lbl}, рабочее время): {len(results)}**"
                if is_head:
                    header += NL + f"(пропущено: {skipped_month} др. мес., {skipped_offhours} нерабоч. вр., {skipped_duty} дежурных)"
                blocks = []
                for sname, req_text, req_time, cid_str, mgr in results:
                    parts = [f"👤 **{sname or 'Неизвестный'}**"]
                    if req_text:
                        parts.append("💬 " + req_text[:80] + ('...' if len(req_text) > 80 else ''))
                    if req_time:
                        parts.append(f"🕐 {req_time}")
                    if is_head and mgr:
                        parts.append(f"👩‍💼 {mgr}")
                    parts.append(f"💬 Чат ID: `{cid_str}`")
                    blocks.append(NL.join(parts))
                cur = header
                for b in blocks:
                    add = NL2 + b
                    if len(cur) + len(add) > 4000:
                        await event.reply(cur, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur = b
                    else:
                        cur += add
                if cur:
                    await event.reply(cur, parse_mode='md')
            except Exception as e:
                logger.error(f"Ошибка при /nosla: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        # ===== /compare =====
        @self.client.on(events.NewMessage(pattern=r'/compare'))
        async def handle_compare_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Команда доступна только руководителю.")
                    return
                month_arg = event.message.text.strip()[len('/compare'):].strip()
                _cru = {'январь':1,'января':1,'февраль':2,'февраля':2,'март':3,'марта':3,'апрель':4,'апреля':4,'май':5,'мая':5,'июнь':6,'июня':6,'июль':7,'июля':7,'август':8,'августа':8,'сентябрь':9,'сентября':9,'октябрь':10,'октября':10,'ноябрь':11,'ноября':11,'декабрь':12,'декабря':12}
                import pytz as _cpz
                _cn = datetime.now(_cpz.timezone('Europe/Moscow'))
                ty, tm, mnd = _cn.year, _cn.month, ""
                if month_arg:
                    _cm = re.match(r'([а-яёА-ЯЁ]+)\s*(\d{2,4})?', month_arg.lower())
                    if _cm:
                        mw, yp = _cm.group(1), _cm.group(2)
                        _tm = _cru.get(mw)
                        if not _tm:
                            await event.reply(f"❌ Не распознан месяц: `{month_arg}`", parse_mode='md')
                            return
                        tm = _tm
                        mnd = mw.capitalize()
                        if yp:
                            yr = int(yp)
                            ty = 2000 + yr if yr < 100 else yr
                await event.reply("🔍 Формирую сравнение менеджеров...")
                from report_generator import get_report_generator
                rg = get_report_generator()
                mk = None
                for k, v in rg.MONTH_COLUMNS.items():
                    if v.get('year') == ty and v.get('month') == tm:
                        mk = k
                        mnd = v.get('name', mnd)
                        break
                students = await rg._get_kpi_data_for_month(mk)
                ms = {}
                for s in students:
                    if s.get('is_archived'):
                        continue
                    mgr = s.get('manager_name', '').strip() or 'Не назначен'
                    if mgr not in ms:
                        ms[mgr] = {'total': 0, 'active': 0, 'with_tracker': 0}
                    ms[mgr]['total'] += 1
                    try:
                        hw = int(s.get('hw_count', '0') or '0')
                    except Exception:
                        hw = 0
                    if hw > 0:
                        ms[mgr]['active'] += 1
                    t = s.get('tracker_url', '')
                    if t and t not in ('-', ''):
                        ms[mgr]['with_tracker'] += 1
                if not ms:
                    await event.reply("❌ Нет данных за указанный период.")
                    return
                NL, NL2 = chr(10), chr(10)*2
                period = mnd or f"{tm:02d}.{ty}"
                header = f"📊 **Сравнение менеджеров — {period}**"
                blocks = []
                for mgr, st in sorted(ms.items(), key=lambda x: -x[1]['total']):
                    pct = f"{100*st['active']//st['total']}%" if st['total'] else "0%"
                    parts = [f"👩\u200d💼 **{mgr}**", f"👥 Студентов: {st['total']}", f"✅ Активных: {st['active']} ({pct})", f"📁 С трекером: {st['with_tracker']}"]
                    blocks.append(NL.join(parts))
                cur = header
                for b in blocks:
                    add = NL2 + b
                    if len(cur) + len(add) > 4000:
                        await event.reply(cur, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur = b
                    else:
                        cur += add
                if cur:
                    await event.reply(cur, parse_mode='md')
            except Exception as e:
                logger.error(f"Ошибка при /compare: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        # ===== /courses =====
        @self.client.on(events.NewMessage(pattern=r'/courses'))
        async def handle_courses_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                is_head = (sender_id in HEAD_IDS)
                sender_mgr = self._get_manager_name_by_id(sender_id)
                await event.reply("🔍 Загружаю данные...")
                rows = []
                if self.sheets_integration and self.sheets_integration.worksheet:
                    rows = await asyncio.to_thread(self.sheets_integration.worksheet.get_all_values)
                cs = {}
                for row in rows[1:]:
                    if not row or not row[0]:
                        continue
                    mgr = row[7].strip() if len(row) > 7 else ""
                    status = row[11].strip() if len(row) > 11 else ""
                    course = (row[4].strip() if len(row) > 4 else "") or "Не указан"
                    tracker = row[8].strip() if len(row) > 8 else ""
                    if "Закончил" in status or "Завершил" in status:
                        continue
                    if not is_head and mgr != (sender_mgr or ""):
                        continue
                    if course not in cs:
                        cs[course] = {'total': 0, 'with_tracker': 0}
                    cs[course]['total'] += 1
                    if tracker and tracker not in ('-', ''):
                        cs[course]['with_tracker'] += 1
                if not cs:
                    suffix = '' if is_head else ' у вас'
                    await event.reply(f"ℹ️ Нет данных по курсам{suffix}.")
                    return
                total_all = sum(v['total'] for v in cs.values())
                title = "Все студенты" if is_head else (sender_mgr or "Ваши студенты")
                header = f"📚 **Распределение по курсам — {title} ({total_all} чел.)**"
                lines_c = [f"📚 **{c}**: {st['total']} чел. (трекер: {st['with_tracker']})" for c, st in sorted(cs.items(), key=lambda x: -x[1]['total'])]
                NL = chr(10)
                cur = header
                for line in lines_c:
                    add = NL + line
                    if len(cur) + len(add) > 4000:
                        await event.reply(cur, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur = line
                    else:
                        cur += add
                if cur:
                    await event.reply(cur, parse_mode='md')
            except Exception as e:
                logger.error(f"Ошибка при /courses: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        # ===== /retention =====
        @self.client.on(events.NewMessage(pattern=r'/retention'))
        async def handle_retention_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Команда доступна только руководителю.")
                    return
                course_arg = event.message.text.strip()[len('/retention'):].strip()
                from report_generator import get_report_generator
                rg = get_report_generator()
                NL = chr(10)
                if not course_arg:
                    await event.reply("🔍 Загружаю список курсов...")
                    if not self.kpi_sheets or not self.kpi_sheets.worksheet:
                        await event.reply("❌ KPI Ultra недоступен.")
                        return
                    kpi_rows = await asyncio.to_thread(self.kpi_sheets.worksheet.get_all_values)
                    courses = sorted(set(row[3].strip() for row in kpi_rows[20:] if len(row) > 3 and row[3].strip() and row[0].strip()))
                    if not courses:
                        await event.reply("❌ Список курсов пуст.")
                        return
                    msg_r = "📈 **Доступные курсы для /retention:**" + NL + NL + NL.join(f"{i+1}. {c}" for i, c in enumerate(courses))
                    msg_r += NL + NL + "Отправь: `/retention Название курса`"
                    if len(msg_r) <= 4000:
                        await event.reply(msg_r, parse_mode='md')
                    else:
                        for i in range(0, len(msg_r), 4000):
                            await event.reply(msg_r[i:i+4000], parse_mode='md')
                            await asyncio.sleep(0.3)
                    return
                await event.reply(f"🔍 Считаю ретеншн для «{course_arg}»...")
                import pytz as _rpz
                from datetime import date as _rd, datetime as _rdtt
                rnow = _rdtt.now(_rpz.timezone('Europe/Moscow'))
                hw_by_gcid = {}
                for delta in range(3):
                    m = (rnow.month - delta - 1) % 12 + 1
                    y = rnow.year if (rnow.month - delta) > 0 else rnow.year - 1
                    mk = next((k for k, v in rg.MONTH_COLUMNS.items() if v.get('year') == y and v.get('month') == m), None)
                    try:
                        for s in await rg._get_kpi_data_for_month(mk):
                            g = s.get('getcourse_id', '')
                            try:
                                hw = int(s.get('hw_count', '0') or '0')
                            except Exception:
                                hw = 0
                            if g and hw > 0:
                                hw_by_gcid[g] = True
                    except Exception:
                        pass
                if not self.kpi_sheets or not self.kpi_sheets.worksheet:
                    await event.reply("❌ KPI Ultra недоступен.")
                    return
                kpi_rows = await asyncio.to_thread(self.kpi_sheets.worksheet.get_all_values)
                today = _rd.today()
                buckets = {30: {'total': 0, 'active': 0}, 60: {'total': 0, 'active': 0}, 90: {'total': 0, 'active': 0}}
                def _rpd(s):
                    s = (s or '').strip()[:10]
                    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
                        try:
                            return _rdtt.strptime(s, fmt).date()
                        except Exception:
                            pass
                    return None
                matched = 0
                for row in kpi_rows[20:]:
                    if not row or not row[0]:
                        continue
                    course = row[3].strip() if len(row) > 3 else ''
                    if course_arg.lower() not in course.lower():
                        continue
                    matched += 1
                    gcid = row[0].strip()
                    ts = _rpd(row[7].strip() if len(row) > 7 else '')
                    if not ts:
                        continue
                    days_since = (today - ts).days
                    is_active = hw_by_gcid.get(gcid, False)
                    for thr in (30, 60, 90):
                        if days_since >= thr:
                            buckets[thr]['total'] += 1
                            if is_active:
                                buckets[thr]['active'] += 1
                if matched == 0:
                    await event.reply(f"❌ Студентов с курсом «{course_arg}» не найдено.")
                    return
                def _pct(a, t):
                    return f"{100*a//t}%" if t else "н/д"
                msg_r = f"📈 **Ретеншн — {course_arg}**" + NL + NL + f"Совпало: {matched} студентов" + NL + NL
                for thr in (30, 60, 90):
                    b = buckets[thr]
                    msg_r += f"**>{thr} дней:** {b['total']} чел., активных: {b['active']} ({_pct(b['active'], b['total'])})" + NL
                msg_r += NL + "_Активен = сдал ≥1 ДЗ за последние 3 месяца_"
                await event.reply(msg_r, parse_mode='md')
            except Exception as e:
                logger.error(f"Ошибка при /retention: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        # ===== /topactive =====
        @self.client.on(events.NewMessage(pattern=r'/topactive'))
        async def handle_topactive_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Команда доступна только руководителю.")
                    return
                await event.reply("🔍 Анализирую сообщения студентов...")
                sm_rows = []
                if self.persistence and self.persistence.is_initialized():
                    _wsm = self.persistence.worksheets.get("Student_Messages")
                    if _wsm:
                        sm_rows = await asyncio.to_thread(_wsm.get_all_values)
                from datetime import datetime as _tdtt, timedelta as _ttd, timezone as _ttz
                cutoff = _tdtt.now(_ttz.utc) - _ttd(days=30)
                stats = {}
                for row in sm_rows[1:]:
                    if len(row) < 6 or not row[5]:
                        continue
                    ts_str = row[0].strip()
                    gcid = row[5].strip()
                    name = row[6].strip() if len(row) > 6 else ""
                    mgr = row[7].strip() if len(row) > 7 else ""
                    course = row[10].strip() if len(row) > 10 else ""
                    try:
                        ts = _tdtt.strptime(ts_str[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=_ttz.utc)
                        if ts < cutoff:
                            continue
                    except Exception:
                        continue
                    if gcid not in stats:
                        stats[gcid] = {'count': 0, 'name': name, 'course': course, 'manager': mgr}
                    stats[gcid]['count'] += 1
                if not stats:
                    await event.reply("ℹ️ Нет сообщений за последние 30 дней.")
                    return
                top = sorted(stats.items(), key=lambda x: -x[1]['count'])[:20]
                NL, NL2 = chr(10), chr(10)*2
                lines_top = [f"🏆 **Топ-{len(top)} активных студентов (30 дней)**"]
                for i, (gcid, info) in enumerate(top, 1):
                    nm = info['name'] or gcid
                    crs = info['course']
                    mgr = info['manager']
                    cnt = info['count']
                    line = f"{i}. **{nm}**" + (f" ({crs})" if crs else "") + f" — {cnt} сообщ."
                    if mgr:
                        line += NL + "   👩\u200d💼 " + mgr
                    lines_top.append(line)
                msg_top = NL2.join(lines_top)
                if len(msg_top) <= 4000:
                    await event.reply(msg_top, parse_mode='md')
                else:
                    for i in range(0, len(msg_top), 4000):
                        await event.reply(msg_top[i:i+4000], parse_mode='md')
                        await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Ошибка при /topactive: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        # ===== /coursestats =====
        @self.client.on(events.NewMessage(pattern=r'/coursestats'))
        async def handle_coursestats_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Команда доступна только руководителю.")
                    return
                await event.reply("🔍 Формирую статистику по курсам...")
                from report_generator import get_report_generator
                students = await get_report_generator()._get_kpi_data_for_month(None)
                cs = {}
                for s in students:
                    if s.get('is_archived'):
                        continue
                    course = s.get('course', '').strip() or 'Не указан'
                    status = s.get('status', '').strip()
                    try:
                        hw = int(s.get('hw_count', '0') or '0')
                    except Exception:
                        hw = 0
                    if course not in cs:
                        cs[course] = {'total': 0, 'new': 0, 'learning': 0, 'done': 0, 'hw_sum': 0, 'hw_cnt': 0}
                    cs[course]['total'] += 1
                    if status == 'Новый':
                        cs[course]['new'] += 1
                    elif status == 'Учится':
                        cs[course]['learning'] += 1
                    elif 'Закончил' in status or status == 'Не с нами':
                        cs[course]['done'] += 1
                    if hw > 0:
                        cs[course]['hw_sum'] += hw
                        cs[course]['hw_cnt'] += 1
                if not cs:
                    await event.reply("❌ Нет данных за текущий месяц.")
                    return
                total_all = sum(v['total'] for v in cs.values())
                NL, NL2 = chr(10), chr(10)*2
                header = f"📊 **Статистика по курсам — текущий месяц ({total_all} студентов)**"
                blocks = []
                for course, st in sorted(cs.items(), key=lambda x: -x[1]['total']):
                    avg_hw = f"{st['hw_sum'] / st['hw_cnt']:.1f}" if st['hw_cnt'] else "0"
                    parts = [f"📚 **{course}** ({st['total']} чел.)", f"🟢 Учится: {st['learning']} | 🆕 Новый: {st['new']} | ✅ Завершил: {st['done']}", f"📝 Среднее ДЗ (у сдавших): {avg_hw}"]
                    blocks.append(NL.join(parts))
                cur = header
                for b in blocks:
                    add = NL2 + b
                    if len(cur) + len(add) > 4000:
                        await event.reply(cur, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur = b
                    else:
                        cur += add
                if cur:
                    await event.reply(cur, parse_mode='md')
            except Exception as e:
                logger.error(f"Ошибка при /coursestats: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

                # ===== /stuck =====
        @self.client.on(events.NewMessage(pattern=r'/stuck'))
        async def handle_stuck_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Команда доступна только руководителю.")
                    return
                raw = event.message.text.strip()[len('/stuck'):].strip()
                parts_split = raw.rsplit(None, 1)
                n_months = 3
                target_status = ''
                if parts_split:
                    if len(parts_split) == 2 and parts_split[1].isdigit():
                        n_months = int(parts_split[1])
                        target_status = parts_split[0].strip()
                    else:
                        target_status = raw.strip()
                VALID_STATUSES = ['Заморозка', 'Новый', 'Пропал', 'Выпускной', 'Модуль ОК', 'Учится', 'Закончил', 'Не с нами']
                NL = chr(10)
                NL2 = chr(10) * 2
                if not target_status:
                    status_list = NL.join('• ' + s for s in VALID_STATUSES)
                    help_msg = 'ℹ️ **Использование:** `/stuck [статус] [N]`' + NL2 + 'Показывает студентов с неизменным статусом N+ месяцев подряд (по умолчанию 3)' + NL2 + '**Доступные статусы:**' + NL + status_list
                    await event.reply(help_msg, parse_mode='md')
                    return
                matched_status = next((s for s in VALID_STATUSES if s.lower() == target_status.lower()), None)
                if not matched_status:
                    await event.reply('❌ Неизвестный статус: `' + target_status + '`' + NL + 'Доступные: ' + ', '.join(VALID_STATUSES), parse_mode='md')
                    return
                if n_months < 1 or n_months > 24:
                    await event.reply("❌ N должно быть от 1 до 24.")
                    return
                await event.reply('⏳ Ищу студентов со статусом **' + matched_status + '** ' + str(n_months) + '+ месяцев подряд...', parse_mode='md')
                from report_generator import get_report_generator
                rg = get_report_generator()
                sorted_months = sorted(rg.MONTH_COLUMNS.items(), key=lambda x: (x[1]['year'], x[1]['month']))
                from datetime import datetime as _dt
                now = _dt.now()
                cur_idx = None
                for i, (k, v) in enumerate(sorted_months):
                    if v['year'] == now.year and v['month'] == now.month:
                        cur_idx = i
                        break
                if cur_idx is None:
                    cur_idx = len(sorted_months) - 1
                if cur_idx < n_months - 1:
                    await event.reply('❌ Недостаточно данных: нужно ' + str(n_months) + ' мес., доступно только ' + str(cur_idx + 1) + '.')
                    return
                target_months = sorted_months[cur_idx - n_months + 1 : cur_idx + 1]
                def _read_sheet():
                    ws = rg.spreadsheet.worksheet('Общий список new')
                    return ws.get_all_values()
                all_data = await asyncio.to_thread(_read_sheet)
                results = []
                for row_idx, row in enumerate(all_data[20:], start=21):
                    if len(row) < 8 or not row[0]:
                        continue
                    name = row[2] if len(row) > 2 else ''
                    manager = row[10] if len(row) > 10 else ''
                    gcid = row[0].strip() if len(row) > 0 else ''
                    if not name:
                        continue
                    if manager == 'Не с нами':
                        continue
                    all_match = True
                    for _, mc in target_months:
                        si = mc['status']
                        s = row[si].strip() if len(row) > si else ''
                        if s != matched_status:
                            all_match = False
                            break
                    if all_match:
                        results.append({'name': name, 'manager': manager or 'Не указан', 'gcid': gcid})
                if not results:
                    await event.reply('✅ Нет студентов со статусом **' + matched_status + '** ' + str(n_months) + '+ месяцев подряд.', parse_mode='md')
                    return
                oldest_mc = target_months[0][1]
                newest_mc = target_months[-1][1]
                oldest_lbl = oldest_mc.get('name', '') + str(oldest_mc.get('year', ''))[-2:]
                newest_lbl = newest_mc.get('name', '') + str(newest_mc.get('year', ''))[-2:]
                month_range = oldest_lbl + '–' + newest_lbl
                by_manager = {}
                for r in results:
                    by_manager.setdefault(r['manager'], []).append(r)
                header = '🔒 **' + matched_status + ' — ' + str(n_months) + '+ мес. подряд** (' + month_range + ')' + NL + 'Всего: ' + str(len(results)) + ' студентов'
                blocks = []
                for mgr, students in sorted(by_manager.items()):
                    lines = ['👤 **' + mgr + '** (' + str(len(students)) + ' чел.):']
                    for s in sorted(students, key=lambda x: x['name']):
                        lines.append('  • ' + s['name'] + ' (GC: `' + s['gcid'] + '`)')
                    blocks.append(NL.join(lines))
                cur = header
                for b in blocks:
                    add = NL2 + b
                    if len(cur) + len(add) > 4000:
                        await event.reply(cur, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur = b
                    else:
                        cur += add
                if cur:
                    await event.reply(cur, parse_mode='md')
            except Exception as e:
                logger.error(f"Ошибка при /stuck: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

                # ===== /kpidrop =====
        @self.client.on(events.NewMessage(pattern=r'/kpidrop'))
        async def handle_kpidrop_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("❌ Команда доступна только руководителю.")
                    return
                await event.reply("⏳ Загружаю Прогресс менеджеров...")
                from report_generator import get_report_generator
                rg_kd = get_report_generator()
                sorted_kd = sorted(rg_kd.MONTH_COLUMNS.items(), key=lambda x: (x[1]['year'], x[1]['month']))
                from datetime import datetime as _dtkd
                now_kd = _dtkd.now()
                cidx_kd = None
                for i_kd, (k_kd, v_kd) in enumerate(sorted_kd):
                    if v_kd['year'] == now_kd.year and v_kd['month'] == now_kd.month:
                        cidx_kd = i_kd
                        break
                if cidx_kd is None:
                    cidx_kd = len(sorted_kd) - 1
                if cidx_kd < 1:
                    await event.reply("❌ Недостаточно данных: нужно минимум 2 месяца.")
                    return
                curr_mc_kd = sorted_kd[cidx_kd][1]
                prev_mc_kd = sorted_kd[cidx_kd - 1][1]
                curr_lbl_kd = curr_mc_kd.get('name', '') + str(curr_mc_kd.get('year', ''))[-2:]
                prev_lbl_kd = prev_mc_kd.get('name', '') + str(prev_mc_kd.get('year', ''))[-2:]
                def _read_progress_kd():
                    ws_kd = rg_kd.spreadsheet.worksheet('Прогресс менеджеров')
                    return ws_kd.get_all_values()
                all_rows_kd = await asyncio.to_thread(_read_progress_kd)
                curr_data_kd = {}
                prev_data_kd = {}
                for row_kd in all_rows_kd[1:]:
                    if len(row_kd) < 13:
                        continue
                    gcid_kd = row_kd[0].strip()
                    if not gcid_kd:
                        continue
                    name_kd = row_kd[1].strip()
                    mgr_kd = row_kd[2].strip()
                    j_kd = row_kd[9].strip()
                    month_kd = row_kd[12].strip()
                    if month_kd == curr_lbl_kd:
                        curr_data_kd[gcid_kd] = {'name': name_kd, 'manager': mgr_kd, 'j': j_kd}
                    elif month_kd == prev_lbl_kd:
                        prev_data_kd[gcid_kd] = {'name': name_kd, 'manager': mgr_kd, 'j': j_kd}
                results_kd = []
                for gcid_r, curr_r in curr_data_kd.items():
                    prev_r = prev_data_kd.get(gcid_r)
                    if not prev_r:
                        continue
                    if prev_r['j'] == '✅' and curr_r['j'] == '❌':
                        results_kd.append({'gcid': gcid_r, 'name': curr_r['name'], 'manager': curr_r['manager']})
                if not results_kd:
                    await event.reply(f"✅ Нет студентов с падением KPI (✅→❌) за {prev_lbl_kd}–{curr_lbl_kd}.")
                    return
                by_mgr_kd = {}
                for r_kd in results_kd:
                    by_mgr_kd.setdefault(r_kd['manager'] or 'Не указан', []).append(r_kd['name'])
                NL, NL2 = chr(10), chr(10)*2
                header_kd = f"📉 **KPI упал (✅→❌): {len(results_kd)} студ.**" + NL + f"Сравнение: {prev_lbl_kd} → {curr_lbl_kd}" + NL + f"Источник: Прогресс менеджеров (кол. J)"
                blocks_kd = []
                for mgr_k, names_k in sorted(by_mgr_kd.items()):
                    lines_k = [f"👤 **{mgr_k}** ({len(names_k)} чел.):"]
                    lines_k += [f"  • {n}" for n in sorted(names_k)]
                    blocks_kd.append(NL.join(lines_k))
                cur_kd = header_kd
                for b_kd in blocks_kd:
                    add_kd = NL2 + b_kd
                    if len(cur_kd) + len(add_kd) > 4000:
                        await event.reply(cur_kd, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur_kd = b_kd
                    else:
                        cur_kd += add_kd
                if cur_kd:
                    await event.reply(cur_kd, parse_mode='md')
            except Exception as e:
                logger.error(f"Ошибка при /kpidrop: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка: {e}")

        # ===== /nohw =====
        @self.client.on(events.NewMessage(pattern=r'/nohw'))
        async def handle_nohw_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("\u274c \u041a\u043e\u043c\u0430\u043d\u0434\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0442\u043e\u043b\u044c\u043a\u043e \u0440\u0443\u043a\u043e\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044e.")
                    return
                raw_nohw = event.message.text.strip()[len('/nohw'):].strip()
                try:
                    n_nohw = max(1, min(24, int(raw_nohw))) if raw_nohw.isdigit() else 3
                except Exception:
                    n_nohw = 3
                await event.reply(f"\u23f3 \u0418\u0449\u0443 \u0437\u043e\u043c\u0431\u0438-\u0441\u0442\u0443\u0434\u0435\u043d\u0442\u043e\u0432 (0 \u0414\u0417 \u0437\u0430 {n_nohw} \u043c\u0435\u0441. \u043f\u043e\u0434\u0440\u044f\u0434)...")
                from report_generator import get_report_generator
                rg_nohw = get_report_generator()
                sorted_nohw = sorted(rg_nohw.MONTH_COLUMNS.items(), key=lambda x: (x[1]['year'], x[1]['month']))
                from datetime import datetime as _dt3
                now3 = _dt3.now()
                cidx_nohw = None
                for i3, (k3, v3) in enumerate(sorted_nohw):
                    if v3['year'] == now3.year and v3['month'] == now3.month:
                        cidx_nohw = i3
                        break
                if cidx_nohw is None:
                    cidx_nohw = len(sorted_nohw) - 1
                if cidx_nohw < n_nohw - 1:
                    await event.reply(f"\u274c \u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0434\u0430\u043d\u043d\u044b\u0445: \u043d\u0443\u0436\u043d\u043e {n_nohw} \u043c\u0435\u0441., \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e {cidx_nohw + 1}.")
                    return
                target_nohw = sorted_nohw[cidx_nohw - n_nohw + 1 : cidx_nohw + 1]
                def _read_nohw():
                    ws_nh = rg_nohw.spreadsheet.worksheet('\u041e\u0431\u0449\u0438\u0439 \u0441\u043f\u0438\u0441\u043e\u043a new')
                    return ws_nh.get_all_values()
                all_nohw = await asyncio.to_thread(_read_nohw)
                EXCL_ST = {'\u0417\u0430\u043a\u043e\u043d\u0447\u0438\u043b', '\u041d\u0435 \u0441 \u043d\u0430\u043c\u0438'}
                results_nohw = []
                for row_nh in all_nohw[20:]:
                    if len(row_nh) < 8 or not row_nh[0]:
                        continue
                    name_nh = row_nh[2] if len(row_nh) > 2 else ''
                    mgr_nh = row_nh[10] if len(row_nh) > 10 else ''
                    if not name_nh or mgr_nh == '\u041d\u0435 \u0441 \u043d\u0430\u043c\u0438':
                        continue
                    cur_si = target_nohw[-1][1]['status']
                    cur_st = row_nh[cur_si].strip() if len(row_nh) > cur_si else ''
                    if cur_st in EXCL_ST:
                        continue
                    all_zero = True
                    for _, mc_nh in target_nohw:
                        ci_nh = mc_nh['count']
                        v_nh = row_nh[ci_nh].strip() if len(row_nh) > ci_nh else '0'
                        try:
                            hw_nh = int(v_nh or '0')
                        except Exception:
                            hw_nh = 0
                        if hw_nh != 0:
                            all_zero = False
                            break
                    if all_zero:
                        results_nohw.append({'name': name_nh, 'manager': mgr_nh or '\u041d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d', 'status': cur_st})
                if not results_nohw:
                    await event.reply(f"\u2705 \u041d\u0435\u0442 \u0441\u0442\u0443\u0434\u0435\u043d\u0442\u043e\u0432 \u0441 0 \u0414\u0417 \u0437\u0430 {n_nohw} \u043c\u0435\u0441. \u043f\u043e\u0434\u0440\u044f\u0434.")
                    return
                NL, NL2 = chr(10), chr(10)*2
                oldest_nh = target_nohw[0][1].get('name', '') + str(target_nohw[0][1].get('year', ''))[-2:]
                newest_nh = target_nohw[-1][1].get('name', '') + str(target_nohw[-1][1].get('year', ''))[-2:]
                by_mgr_nh = {}
                for r_nh in results_nohw:
                    by_mgr_nh.setdefault(r_nh['manager'], []).append(r_nh)
                header_nh = f"\U0001f9df **0 \u0414\u0417 \u0437\u0430 {n_nohw}+ \u043c\u0435\u0441.** ({oldest_nh}\u2013{newest_nh})" + NL + f"\u0412\u0441\u0435\u0433\u043e: {len(results_nohw)} \u0441\u0442\u0443\u0434\u0435\u043d\u0442\u043e\u0432"
                blocks_nh = []
                for mgr_k, stus_nh in sorted(by_mgr_nh.items()):
                    lines_nh = [f"\U0001f464 **{mgr_k}** ({len(stus_nh)} \u0447\u0435\u043b.):"]
                    for r2 in sorted(stus_nh, key=lambda x: x['name']):
                        lines_nh.append(f"  \u2022 {r2['name']} | {r2['status']}")
                    blocks_nh.append(NL.join(lines_nh))
                cur_nh = header_nh
                for b_nh in blocks_nh:
                    add_nh = NL2 + b_nh
                    if len(cur_nh) + len(add_nh) > 4000:
                        await event.reply(cur_nh, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur_nh = b_nh
                    else:
                        cur_nh += add_nh
                if cur_nh:
                    await event.reply(cur_nh, parse_mode='md')
            except Exception as e:
                logger.error(f"\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 /nohw: {e}", exc_info=True)
                await event.reply(f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {e}")

        # ===== /managerload =====
        @self.client.on(events.NewMessage(pattern=r'/managerload'))
        async def handle_managerload_command(event):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if sender_id != VIP_HEAD['telegram_id']:
                    await event.reply("\u274c \u041a\u043e\u043c\u0430\u043d\u0434\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0442\u043e\u043b\u044c\u043a\u043e \u0440\u0443\u043a\u043e\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044e.")
                    return
                await event.reply("\u23f3 \u0417\u0430\u0433\u0440\u0443\u0436\u0430\u044e \u0434\u0430\u043d\u043d\u044b\u0435 \u043f\u043e \u043c\u0435\u043d\u0435\u0434\u0436\u0435\u0440\u0430\u043c...")
                from report_generator import get_report_generator
                students_ml = await get_report_generator()._get_kpi_data_for_month(None)
                STATUS_ORDER = ['\u041d\u043e\u0432\u044b\u0439', '\u0423\u0447\u0438\u0442\u0441\u044f', '\u041c\u043e\u0434\u0443\u043b\u044c \u041e\u041a', '\u0412\u044b\u043f\u0443\u0441\u043a\u043d\u043e\u0439', '\u0417\u0430\u043c\u043e\u0440\u043e\u0437\u043a\u0430', '\u041f\u0440\u043e\u043f\u0430\u043b', '\u0417\u0430\u043a\u043e\u043d\u0447\u0438\u043b', '\u041e\u043a\u0443\u043f\u0438\u043b\u0441\u044f', '\u041e\u043a\u0443\u043f\u0430\u0435\u0442\u0441\u044f', '\u0421\u0442\u0430\u0436\u0438\u0440\u043e\u0432\u043a\u0430', '\u041d\u0435 \u0441 \u043d\u0430\u043c\u0438']
                table_ml = {}
                all_statuses_ml = set()
                for s_ml in students_ml:
                    if s_ml.get('is_archived'):
                        continue
                    mgr_ml = s_ml.get('manager_name', '') or '\u041d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d'
                    st_ml = s_ml.get('status', '') or '\u041f\u0443\u0441\u0442\u043e'
                    table_ml.setdefault(mgr_ml, {})
                    table_ml[mgr_ml][st_ml] = table_ml[mgr_ml].get(st_ml, 0) + 1
                    all_statuses_ml.add(st_ml)
                if not table_ml:
                    await event.reply("\u274c \u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445 \u0437\u0430 \u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u043c\u0435\u0441\u044f\u0446.")
                    return
                ordered_st = [s for s in STATUS_ORDER if s in all_statuses_ml]
                ordered_st += sorted(all_statuses_ml - set(STATUS_ORDER))
                NL, NL2 = chr(10), chr(10)*2
                header_ml = "\U0001f4ca **\u041d\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u043c\u0435\u043d\u0435\u0434\u0436\u0435\u0440\u043e\u0432 (\u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u043c\u0435\u0441\u044f\u0446)**"
                blocks_ml = []
                for mgr_ml2, counts_ml in sorted(table_ml.items()):
                    total_ml = sum(counts_ml.values())
                    lines_ml = [f"\U0001f464 **{mgr_ml2}** — {total_ml} \u0441\u0442\u0443\u0434."]
                    for st_o in ordered_st:
                        cnt = counts_ml.get(st_o, 0)
                        if cnt > 0:
                            lines_ml.append(f"  {st_o}: {cnt}")
                    blocks_ml.append(NL.join(lines_ml))
                cur_ml = header_ml
                for b_ml in blocks_ml:
                    add_ml = NL2 + b_ml
                    if len(cur_ml) + len(add_ml) > 4000:
                        await event.reply(cur_ml, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur_ml = b_ml
                    else:
                        cur_ml += add_ml
                if cur_ml:
                    await event.reply(cur_ml, parse_mode='md')
            except Exception as e:
                logger.error(f"\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 /managerload: {e}", exc_info=True)
                await event.reply(f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {e}")

        # ===== /hw0 и /hw1 (общий обработчик) =====
        async def _handle_hw_count_command(event, target_hw: int):
            try:
                if not event.is_private:
                    return
                sender_id = event.sender_id
                if not self._is_vip_manager(sender_id):
                    return
                is_head = (sender_id in HEAD_IDS)
                sender_mgr = self._get_manager_name_by_id(sender_id)
                lbl = str(target_hw)
                await event.reply(f"\u23f3 \u0418\u0449\u0443 \u0441\u0442\u0443\u0434\u0435\u043d\u0442\u043e\u0432 \u0441 {lbl} \u0414\u0417 \u0432 \u0442\u0435\u043a\u0443\u0449\u0435\u043c \u043c\u0435\u0441\u044f\u0446\u0435...")
                from report_generator import get_report_generator
                students_hw = await get_report_generator()._get_kpi_data_for_month(None)
                HW_STATUSES = {'\u041d\u043e\u0432\u044b\u0439', '\u0423\u0447\u0438\u0442\u0441\u044f', '\u041c\u043e\u0434\u0443\u043b\u044c \u041e\u041a'}
                results_hw = []
                for s_hw in students_hw:
                    if s_hw.get('is_archived'):
                        continue
                    if s_hw.get('status', '') not in HW_STATUSES:
                        continue
                    try:
                        hw_val = int(s_hw.get('hw_count', '0') or '0')
                    except Exception:
                        hw_val = 0
                    if hw_val != target_hw:
                        continue
                    mgr_hw = s_hw.get('manager_name', '')
                    if not is_head:
                        sm_hw = (sender_mgr or '').lower()
                        if sm_hw not in mgr_hw.lower() and mgr_hw.lower() not in sm_hw:
                            continue
                    results_hw.append(s_hw)
                NL, NL2 = chr(10), chr(10)*2
                if not results_hw:
                    suffix_hw = '' if is_head else ' у вас'
                    await event.reply(f"\u2705 \u041d\u0435\u0442 \u0441\u0442\u0443\u0434\u0435\u043d\u0442\u043e\u0432 \u0441 {lbl} \u0414\u0417{suffix_hw} (\u041d\u043e\u0432\u044b\u0439/\u0423\u0447\u0438\u0442\u0441\u044f/\u041c\u043e\u0434\u0443\u043b\u044c \u041e\u041a).")
                    return
                header_hw = f"\U0001f4dd **{lbl} \u0414\u0417 \u0432 \u0442\u0435\u043a\u0443\u0449\u0435\u043c \u043c\u0435\u0441\u044f\u0446\u0435: {len(results_hw)} \u0441\u0442\u0443\u0434.**"
                if not is_head:
                    header_hw += f" ({sender_mgr})"
                by_mgr_hw = {}
                for s_hw2 in results_hw:
                    mgr_k2 = s_hw2.get('manager_name', '\u041d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d')
                    by_mgr_hw.setdefault(mgr_k2, []).append(s_hw2)
                blocks_hw = []
                for mgr_hw2, stus_hw in sorted(by_mgr_hw.items()):
                    lines_hw = []
                    if is_head:
                        lines_hw.append(f"\U0001f464 **{mgr_hw2}** ({len(stus_hw)} \u0447\u0435\u043b.):")
                    for s_hw3 in sorted(stus_hw, key=lambda x: x.get('name', '')):
                        nm_hw = s_hw3.get('name', s_hw3.get('getcourse_id', ''))
                        course_hw = s_hw3.get('course', '')
                        st_hw = s_hw3.get('status', '')
                        line_hw = f"  \u2022 {nm_hw}"
                        if course_hw:
                            line_hw += f", {course_hw}"
                        line_hw += f" | {st_hw}"
                        lines_hw.append(line_hw)
                    blocks_hw.append(NL.join(lines_hw))
                cur_hw = header_hw
                for b_hw in blocks_hw:
                    add_hw = NL2 + b_hw
                    if len(cur_hw) + len(add_hw) > 4000:
                        await event.reply(cur_hw, parse_mode='md')
                        await asyncio.sleep(0.3)
                        cur_hw = b_hw
                    else:
                        cur_hw += add_hw
                if cur_hw:
                    await event.reply(cur_hw, parse_mode='md')
            except Exception as e:
                logger.error(f"\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 /hw{target_hw}: {e}", exc_info=True)
                await event.reply(f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {e}")

        @self.client.on(events.NewMessage(pattern=r'/hw0'))
        async def handle_hw0_command(event):
            await _handle_hw_count_command(event, 0)

        @self.client.on(events.NewMessage(pattern=r'/hw1'))
        async def handle_hw1_command(event):
            await _handle_hw_count_command(event, 1)

        logger.info("Настроены обработчики команд /start, /help, /report, /bigreport, /reportmonth, /reportweek, /sla, /принять, /пропустить, /tracker, /createtracker, /broadcast, /activate, /deactivate, /status, /oauth, /cleanprivchats, /notactivated, /inactive, /notracker, /nosla, /compare, /courses, /retention, /topactive, /coursestats, /stuck, /kpidrop, /nohw, /managerload, /hw0, /hw1")

    async def _handle_student_selection_for_activate(self, event):
        """
        Обрабатывает ответ менеджера с выбором студента при активации.
        """
        manager_id = event.sender_id
        
        # Проверяем, что есть активное состояние выбора
        if manager_id not in self.activate_student_selection_state:
            return False
        
        state = self.activate_student_selection_state[manager_id]
        
        # ВАЖНО: Проверяем, что ответ пришёл из ТОГО ЖЕ чата, где был /activate
        if event.chat_id != state['chat_id']:
            return False  # Это сообщение из другого чата - пропускаем
        
        candidates = state['candidates']
        message_text = event.message.text.strip() if event.message.text else ''
        
        # Игнорируем команды (кроме /cancel) - это не выбор студента
        if message_text.startswith('/') and not message_text.lower().startswith(('/cancel', '/отмена')):
            return False
        
        # Отмена
        if message_text.lower() in ['/cancel', '/отмена']:
            del self.activate_student_selection_state[manager_id]
            await event.reply("❌ Активация чата отменена.")
            return True
        
        # Очищаем сообщение от Markdown и лишних символов
        import re
        cleaned_text = re.sub(r'[*_~`\[\]]', '', message_text).strip()
        
        # Удаляем номер списка (1. , 2. и т.д.)
        cleaned_text = re.sub(r'^\d+\.\s*', '', cleaned_text).strip()
        
        # Удаляем юзернейм в скобках (@username)
        cleaned_text = re.sub(r'\s*\(@?\w+\)\s*$', '', cleaned_text).strip()
        
        logger.info(f"🔍 Выбор студента: оригинал='{message_text}' → очищено='{cleaned_text}'")
        
        # Пытаемся найти совпадение по имени
        selected_user = None
        for user in candidates:
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            
            # Точное совпадение
            if cleaned_text.lower() == full_name.lower():
                selected_user = user
                break
            
            # Имя студента содержится в сообщении (напр. "Ekaterina Dranko | SNOW SPORT")
            if full_name.lower() in cleaned_text.lower():
                selected_user = user
                break
            
            # Сообщение содержится в имени студента
            if cleaned_text.lower() in full_name.lower():
                selected_user = user
                break
        
        if not selected_user:
            await event.reply(
                "❌ Не удалось найти студента с таким именем.\n\n"
                "Пожалуйста, скопируйте имя точно из списка выше или отправьте `/cancel`."
            )
            return True
        
        # Завершаем активацию
        await self._complete_chat_activation(
            chat_id=state['chat_id'],
            getcourse_id=state['getcourse_id'],
            student_user=selected_user,
            manager_id=manager_id,
            invite_link=state['invite_link'],
            reply_event=event,
            student_kpi_data=state.get('student_kpi_data'),
            active_client=event.client
        )
        
        # Очищаем состояние
        del self.activate_student_selection_state[manager_id]
        return True
    
    async def _complete_chat_activation(
        self,
        chat_id: int,
        getcourse_id: str,
        student_user,
        manager_id: int,
        invite_link: str,
        reply_event,
        student_kpi_data=None,  # Данные студента из KPI Ultra для создания трекера
        active_client=None  # Клиент, который находится в чате (userbot или bot)
    ):
        """
        Завершает активацию чата с выбранным студентом.
        """
        # Клиент для операций с чатом (кто находится в чате)
        chat_client = active_client or self.client
        try:
            # Защита от повторной активации
            if chat_id in self.chat_to_student and self.chat_to_student[chat_id] == getcourse_id:
                logger.info(f"ℹ️ Чат {chat_id} уже активирован для студента {getcourse_id}, пропускаем")
                return
            
            # Извлекаем данные студента
            student_telegram_id = student_user.id
            student_username = student_user.username or ""
            student_name = f"{student_user.first_name or ''} {student_user.last_name or ''}".strip()
            
            # Получаем информацию о менеджере
            manager_info = self._get_manager_info(manager_id)
            manager_name = manager_info['name'] if manager_info else "Неизвестный менеджер"
            
            # Сохраняем в память chat_to_student
            self.chat_to_student[chat_id] = getcourse_id
            
            # Сохраняем данные студента
            if getcourse_id not in self.students_data:
                self.students_data[getcourse_id] = {
                    'name': student_name,
                    'telegram_id': student_telegram_id,
                    'telegram_username': student_username,
                    'getcourse_id': getcourse_id,
                    'course': '',  # Неизвестен при активации
                    'email': '',
                    'phone': ''
                }
            else:
                # Обновляем Telegram данные
                self.students_data[getcourse_id]['telegram_id'] = student_telegram_id
                self.students_data[getcourse_id]['telegram_username'] = student_username
            
            # КРИТИЧНО ДЛЯ SLA: Обновляем student_telegram_ids
            self.student_telegram_ids[getcourse_id] = student_telegram_id
            logger.info(f"✅ SLA: Студент {getcourse_id} добавлен в память (telegram_id={student_telegram_id})")
            
            # Сохраняем назначение менеджера
            self.manager_assignments[getcourse_id] = {
                'manager_id': manager_id,
                'manager_name': manager_name,
                'status': 'active'
            }
            
            # === ШАГ 1: Получаем курс из KPI Ultra ===
            student_course = ''
            existing_tracker_url = None
            if student_kpi_data:
                student_course = student_kpi_data.get('course', '')
                existing_tracker_url = student_kpi_data.get('tracker_url', '')
                if getcourse_id in self.students_data:
                    self.students_data[getcourse_id]['course'] = student_course
            
            # === ШАГ 2: Создаём трекер (ТОЛЬКО если нет существующего) ===
            tracker_url = "-"
            
            # Проверяем, есть ли уже трекер в KPI
            if existing_tracker_url and existing_tracker_url != '-' and 'docs.google.com' in existing_tracker_url:
                tracker_url = existing_tracker_url
                logger.info(f"ℹ️ Используем существующий трекер из KPI: {tracker_url}")
            elif self.tracker_creator and student_course:
                try:
                    logger.info(f"🔄 Создание трекера для студента {getcourse_id}...")
                    tracker_result = self.tracker_creator.create_tracker(
                        student_name=student_name,
                        course_tag=student_course,
                        manager_name=manager_name,
                        getcourse_id=getcourse_id
                    )
                    tracker_url = tracker_result['url']
                    logger.info(f"✅ Трекер создан: {tracker_url}")
                except Exception as e:
                    logger.error(f"❌ Ошибка создания трекера: {e}", exc_info=True)
            
            # === ШАГ 3: Обновляем KPI Sheets (Общий список new) ===
            if self.kpi_sheets:
                try:
                    kpi_row = await self.kpi_sheets._find_student_row_in_kpi(getcourse_id)
                    if kpi_row and tracker_url != "-":
                        await self.kpi_sheets.update_tracker_link(kpi_row, tracker_url)
                        logger.info(f"✅ Трекер обновлён в 'Общий список new'")
                    
                    if invite_link:
                        await self.kpi_sheets.update_or_sync_chat_link(getcourse_id, invite_link)
                        logger.info(f"✅ Chat link обновлён в 'Общий список new'")
                except Exception as e:
                    logger.error(f"❌ Ошибка обновления KPI Sheets: {e}", exc_info=True)
            
            # === ШАГ 4: Добавляем в Випалина ===
            if self.sheets_integration:
                try:
                    await self.sheets_integration.add_student_record(
                        getcourse_id=getcourse_id,
                        telegram_id=student_telegram_id,
                        chat_id=chat_id,
                        student_data=self.students_data[getcourse_id],
                        manager_id=manager_id,
                        manager_name=manager_name,
                        tracker_url=tracker_url,
                        invite_link=invite_link if invite_link else "-"
                    )
                    logger.info(f"✅ Студент {getcourse_id} добавлен в 'Випалина'")
                except Exception as e:
                    logger.error(f"❌ Ошибка добавления в 'Випалина': {e}", exc_info=True)
            
            # === ШАГ 5: Сохраняем в персистенцию (логи) ===
            if self.persistence and self.persistence.is_initialized():
                self.persistence.save_chat_to_student_mapping(chat_id, getcourse_id, student_name, invite_link)
                self.persistence.save_student_data(getcourse_id, self.students_data[getcourse_id])
                self.persistence.save_manager_assignment(getcourse_id, {
                    'manager_id': manager_id,
                    'manager_name': manager_name,
                    'course_tag': '',
                    'status': 'active',
                    'student_name': student_name,
                    'student_telegram': student_username,
                    'student_telegram_id': student_telegram_id
                })
            
            # === ШАГ 6: Удаляем технические сообщения активации ===
            messages_to_delete = []
            try:
                # Кешируем bot_user_id если ещё не установлен
                if self.bot_user_id is None:
                    try:
                        me = await chat_client.get_me()
                        self.bot_user_id = me.id
                    except Exception:
                        self.bot_user_id = -1
                
                # Собираем последние сообщения для удаления
                async for message in chat_client.iter_messages(chat_id, limit=15):
                    msg_text = message.text if message.text else ''
                    
                    # Сообщения от бота
                    if message.sender_id == self.bot_user_id:
                        # Удаляем: "⌛ Активирую чат...", "⚠️ НАЙДЕНО", "❌ Не удалось найти"
                        if 'Активирую чат' in msg_text or \
                           'НАЙДЕНО НЕСКОЛЬКО' in msg_text or \
                           'Не удалось найти студента' in msg_text or \
                           'Как ответить:' in msg_text:
                            messages_to_delete.append(message.id)
                    
                    # Сообщения от менеджера: /activate и выбор студента
                    elif message.sender_id == manager_id:
                        if msg_text.startswith('/activate'):
                            messages_to_delete.append(message.id)
                        # Выбор студента из списка (содержит имя студента)
                        elif student_name and student_name.lower() in msg_text.lower():
                            messages_to_delete.append(message.id)
                
                if messages_to_delete:
                    await chat_client.delete_messages(chat_id, messages_to_delete)
                    logger.info(f"🗑 Удалено {len(messages_to_delete)} технических сообщений активации")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить технические сообщения: {e}")
            
            # === ШАГ 7: Приветственное сообщение ===
            # Отправляем приветственное сообщение студенту
            try:
                # Импортируем CourseConfig для получения правильного названия курса
                from course_config_v2 import CourseConfig
                
                # Получаем название курса из классификатора
                tracker_course_name = CourseConfig.get_tracker_course_name(student_course) if student_course else "VIP-курс"
                
                # Формируем обращение к студенту
                if student_username:
                    student_greeting = f"@{student_username.lstrip('@')}"
                else:
                    student_greeting = student_name
                
                # Приветственное сообщение (аналогично онбордингу)
                welcome_message = f"""Здравствуйте, {student_greeting}!

Я Випалина, бот-помощник вашего персонального менеджера [{manager_name}](tg://user?id={manager_id}) в Zerocoder University! 🌟

Я создана для отслеживания вашего прогресса и сбора статистики, пока что общаться с вами я не смогу :)
Но иногда буду присылать важные сообщения!

Рада знакомству и успехов в обучении! 🚀"""
                
                await self.bot_client.send_message(chat_id, welcome_message)
                logger.info(f"✅ Приветственное сообщение отправлено студенту в чат {chat_id}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке приветственного сообщения: {e}", exc_info=True)
            
            logger.info(
                f"✅ Чат {chat_id} активирован для студента {getcourse_id} "
                f"({student_name}) менеджером {manager_name}"
            )
            
        except Exception as e:
            logger.error(f"Ошибка при завершении активации: {e}", exc_info=True)
            await reply_event.reply(f"❌ Ошибка при активации: {e}")
    
    async def _setup_bot_commands(self):
        """
        Устанавливает подсказки команд для User Client (@ultralina_zerocoder).
        Показываются при нажатии "/" в чате с ботом.
        """
        try:
            from telethon.tl.functions.bots import SetBotCommandsRequest
            from telethon.tl.types import BotCommand
            
            # Определяем команды для VIP-менеджеров
            commands = [
                BotCommand(
                    command='help',
                    description='Показать список всех команд'
                ),
                BotCommand(
                    command='bigreport',
                    description='Большой сводный отчёт (статусы, менеджеры, SLA)'
                ),
                BotCommand(
                    command='reportmonth',
                    description='Месячный отчёт по студентам'
                ),
                BotCommand(
                    command='reportweek',
                    description='Недельный отчёт по активности'
                ),
                BotCommand(
                    command='forecast',
                    description='Прогноз доходимости'
                ),
                BotCommand(
                    command='report',
                    description='Отчёт по студенту (/report ID)'
                ),
                BotCommand(
                    command='monthstats',
                    description='Статистика выполнения нормы за месяц'
                ),
                BotCommand(
                    command='syncprogress',
                    description='Обновить сводную таблицу прогресса'
                ),
                BotCommand(
                    command='broadcast',
                    description='Рассылка во все учебные чаты'
                ),
                BotCommand(
                    command='tracker',
                    description='Создать листы курсов в трекере'
                ),
                BotCommand(
                    command='addnew',
                    description='Добавить студента вручную'
                ),
                BotCommand(
                    command='activate',
                    description='Активировать чат (в группе)'
                ),
                BotCommand(
                    command='start',
                    description='Показать приветствие'
                ),
            ]
            
            # Устанавливаем команды через User Client
            # Примечание: SetBotCommandsRequest работает только для ботов,
            # но User Account может устанавливать команды для себя
            try:
                await self.client(SetBotCommandsRequest(
                    scope=types.BotCommandScopeDefault(),
                    lang_code='ru',
                    commands=commands
                ))
                logger.info("✅ Подсказки команд установлены для User Client")
            except Exception as e:
                # User Account не может устанавливать bot commands - это нормально
                logger.info("ℹ️ User Account не может устанавливать bot commands (это нормально)")
                logger.debug(f"Подробности: {e}")
                
        except Exception as e:
            logger.warning(f"⚠️ Не удалось установить подсказки команд: {e}")
    
    def _setup_sla_tracking(self):
        """
        Настраивает SLA-трекинг для групповых чатов студентов.
        Отслеживает первое сообщение студента за сутки и время ответа менеджера.
        """
        import pytz
        from datetime import datetime, timedelta
        
        # Кешируем ID бота чтобы не вызывать get_me() при каждом сообщении
        bot_user_id_cache = [None]  # Используем список для изменяемости в замыкании
        
        # Мониторинг групповых чатов через Classic Bot (@zerocoder_ultralina_bot)
        # Classic bot не имеет лимита на количество групп (в отличие от userbot)
        @self.bot_client.on(events.NewMessage(incoming=True, outgoing=False))
        async def handle_group_message(event):
            """
            Обрабатывает сообщения в групповых чатах для SLA-трекинга.
            Работает через bot_client (@zerocoder_ultralina_bot).
            """
            try:
                # ИГНОРИРУЕМ сообщения отправленные ДО запуска бота
                if event.message.date.replace(tzinfo=None) < self._startup_time:
                    return
                
                # Проверяем, что это групповой чат
                if not event.is_group:
                    return
                
                logger.info(f"🔔 Новое сообщение в группе: chat_id={event.chat_id}, sender_id={event.sender_id}")
                
                # Пропускаем сообщения от самого бота (кешируем ID classic bot)
                if bot_user_id_cache[0] is None:
                    try:
                        me = await self.bot_client.get_me()
                        bot_user_id_cache[0] = me.id
                        logger.info(f"🤖 ID classic бота закеширован: {bot_user_id_cache[0]}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось получить ID classic бота: {e}")
                        bot_user_id_cache[0] = -1  # Используем -1 чтобы не повторять ошибку
                
                if event.sender_id == bot_user_id_cache[0]:
                    return
                
                # ПРИОРИТЕТ 0: Проверяем, есть ли активный выбор студента при /activate
                if await self._handle_student_selection_for_activate(event):
                    return  # Обработано как выбор студента
                
                logger.info(f"✅ Проверка sender_id пройдена: {event.sender_id} != {bot_user_id_cache[0]}")
                
                chat_id = event.chat_id
                sender_id = event.sender_id
                message_text = event.message.text if event.message.text else ""
                
                logger.info(f"📝 Извлечены данные: chat_id={chat_id}, sender_id={sender_id}, text='{message_text[:50]}'")
                
                # Получаем время в МСК
                logger.info("⏰ Получаем время МСК...")
                moscow_tz = pytz.timezone(MOSCOW_TZ)
                message_time = datetime.now(moscow_tz)
                logger.info(f"✅ Время получено: {message_time}")
                
                # Проверяем, это студент или менеджер (только если SLA трекер инициализирован)
                is_manager = False
                if self.sla_tracker:
                    logger.info(f"🔍 Проверяем, является ли {sender_id} менеджером...")
                    is_manager = self.sla_tracker.is_manager(sender_id)
                    logger.info(f"✅ Результат проверки: is_manager={is_manager}")
                
                # Получаем getcourse_id студента для этого чата
                logger.info(f"🔍 Получаем getcourse_id для chat_id={chat_id}...")
                getcourse_id = self.chat_to_student.get(chat_id)
                logger.info(f"✅ getcourse_id = {getcourse_id}")
                
                logger.debug(f"SLA Debug: chat_id={chat_id}, getcourse_id={getcourse_id}, sender_id={sender_id}")
                
                if not getcourse_id:
                    # Чат не отслеживается (либо старый, либо не создан ботом)
                    logger.debug(f"SLA Debug: Чат {chat_id} не найден в chat_to_student. Всего чатов: {len(self.chat_to_student)}")
                    
                    # Уведомляем руководителя VIP-отдела о неактивированном чате
                    # НО НЕ для рабочего чата VIP-отдела
                    # И с rate-limiting (не чаще раза в 30 минут на чат)
                    if is_manager and chat_id != VIP_DEPARTMENT_CHAT_ID:
                        # Проверяем rate-limit
                        last_warning_time = self._unactivated_chat_warnings.get(chat_id)
                        now = datetime.now()
                        
                        # Отправляем уведомление только если прошло более 30 минут с последнего
                        if last_warning_time is None or (now - last_warning_time).total_seconds() > 1800:
                            try:
                                chat_entity = await self.bot_client.get_entity(chat_id)
                                chat_title = chat_entity.title if hasattr(chat_entity, 'title') else f"Chat {chat_id}"
                                
                                warning_message = (
                                    f"⚠️ **Чат не активирован**\n\n"
                                    f"Чат: **{chat_title}**\n"
                                    f"Chat ID: `{chat_id}`\n\n"
                                    f"Менеджер отправил сообщение в неактивированном чате.\n"
                                    f"SLA-трекинг и авто-обновление NocoDB не работают.\n\n"
                                    f"🔧 **Действие:**\n"
                                    f"Активируйте чат с помощью `/activate <getcourse_id>` в этом чате."
                                )
                                
                                await self.client.send_message(VIP_HEAD['telegram_id'], warning_message)
                                
                                # Сохраняем время отправки уведомления
                                self._unactivated_chat_warnings[chat_id] = now
                                
                                logger.info(f"✉️ Уведомление о неактивированном чате {chat_id} отправлено руководителю")
                            except Exception as notify_error:
                                logger.error(f"Ошибка при отправке уведомления о неактивированном чате: {notify_error}")
                        else:
                            # Rate-limit: пропускаем повторное уведомление
                            logger.debug(f"⚠️ Rate-limit: пропущено уведомление о неактивированном чате {chat_id}")
                    
                    return
                
                # Получаем данные студента для этого чата
                logger.info(f"🔍 Получаем данные студента для getcourse_id={getcourse_id}...")
                student_data = self.students_data.get(getcourse_id)
                
                # Если студента нет в students_data (например, старый чат активирован через /activate),
                # пытаемся получить Telegram ID из student_telegram_ids
                student_id = None
                student_name = None
                
                if student_data:
                    student_id = student_data.get('telegram_id')
                    student_name = student_data.get('name', 'Неизвестный студент')
                    logger.info(f"✅ Студент найден в students_data: {student_name}, telegram_id={student_id}")
                else:
                    # Fallback для старых чатов, активированных через /activate
                    student_id = self.student_telegram_ids.get(getcourse_id)
                    if student_id:
                        logger.info(f"✅ Студент найден в student_telegram_ids: telegram_id={student_id}")
                        # Пытаемся получить имя из KPI Sheets
                        try:
                            from report_generator import get_report_generator
                            report_gen = get_report_generator()
                            student_info = await report_gen.get_student_by_id(getcourse_id)
                            if student_info:
                                student_name = student_info.get('name', 'Неизвестный студент')
                                logger.info(f"✅ Имя студента из KPI: {student_name}")
                        except Exception as e:
                            logger.warning(f"Не удалось получить имя студента из KPI: {e}")
                            student_name = f"Студент {getcourse_id}"
                    else:
                        logger.warning(f"⚠️ Не найден telegram_id для студента {getcourse_id}")
                        
                        # Rate-limit для этого уведомления (используем тот же словарь)
                        last_warning_time = self._unactivated_chat_warnings.get(f"tg_{chat_id}")
                        now = datetime.now()
                        
                        if last_warning_time is None or (now - last_warning_time).total_seconds() > 1800:
                            # Уведомляем руководителя
                            try:
                                chat_entity = await self.bot_client.get_entity(chat_id)
                                chat_title = chat_entity.title if hasattr(chat_entity, 'title') else f"Chat {chat_id}"
                                
                                await self.client.send_message(
                                    VIP_HEAD['telegram_id'],
                                    f"⚠️ **Не удалось определить telegram_id студента**\n\n"
                                    f"Чат: **{chat_title}**\n"
                                    f"Chat ID: `{chat_id}`\n"
                                    f"GetCourse ID: `{getcourse_id}`\n\n"
                                    f"Студент отсутствует в students_data и student_telegram_ids.\n"
                                    f"SLA-трекинг не работает.\n\n"
                                    f"🔧 **Возможные причины:**\n"
                                    f"• Студент не прошёл онбординг через бота\n"
                                    f"• Данные не восстановились из Google Sheets\n"
                                    f"• Студент удалён из системы"
                                )
                                
                                self._unactivated_chat_warnings[f"tg_{chat_id}"] = now
                            except Exception as notify_error:
                                logger.error(f"Ошибка уведомления о telegram_id: {notify_error}")
                        return
                
                if not student_id:
                    logger.warning(f"⚠️ Не удалось определить telegram_id студента {getcourse_id}")
                    return
                
                # ВАЖНО: Если sender_id совпадает со student_id этого чата, это ВСЕГДА студент,
                # даже если он числится менеджером в других контекстах (например, VIP_HEAD для тестирования)
                is_student_message = (sender_id == student_id)
                
                logger.info(f"📊 Определение роли: sender_id={sender_id}, student_id={student_id}, is_manager={is_manager}, is_student_message={is_student_message}")
                
                if is_student_message:
                    # Это сообщение от студента - регистрируем запрос (только если SLA трекер инициализирован)
                    request_data = None
                    if self.sla_tracker:
                        request_data = self.sla_tracker.register_student_request(
                            chat_id=chat_id,
                            student_id=student_id,
                            student_name=student_name,
                            message_text=message_text,
                            timestamp=message_time
                        )
                    
                    if request_data:
                        logger.info(
                            f"SLA: Зарегистрирован запрос от {student_name} "
                            f"({'рабочее' if request_data['is_working_hours'] else 'нерабочее'} время)"
                        )
                    
                    # Логируем сообщение студента в таблицу
                    if self.persistence and self.persistence.is_initialized():
                        # Определяем тип сообщения
                        msg_type = "text"
                        if event.message.photo:
                            msg_type = "photo"
                        elif event.message.document:
                            msg_type = "document"
                        elif event.message.voice:
                            msg_type = "voice"
                        elif event.message.video:
                            msg_type = "video"
                        elif event.message.sticker:
                            msg_type = "sticker"
                        
                        # Получаем имя менеджера из данных студента или из назначений
                        manager_name_log = ""
                        assignment = self.manager_assignments.get(getcourse_id)
                        if assignment:
                            manager_name_log = assignment.get('manager_name', '')
                        
                        self.persistence.save_student_message(
                            chat_id=chat_id,
                            student_id=student_id,
                            getcourse_id=getcourse_id,
                            student_name=student_name,
                            manager_name=manager_name_log,
                            message_text=message_text,
                            message_type=msg_type,
                            course=student_data.get('course', '') if student_data else ''
                        )
                    
                    # Проверяем, это ответ на запрос месячного плана?
                    if self.monthly_plan_collector:
                        pending_plan = self.monthly_plan_collector.get_pending_plan(sender_id)
                        
                        if pending_plan:
                            # Студент отвечает на запрос плана
                            logger.info(f"📊 Обработка ответа на запрос плана от {student_name}")
                            
                            # Извлекаем число плана
                            plan_value = self.monthly_plan_collector.parse_plan_value(message_text)
                            
                            if plan_value:
                                logger.info(f"✅ План получен: {plan_value} ДЗ")
                                
                                # Отправляем подтверждение через classic bot (он в чате)
                                await self.bot_client.send_message(
                                    chat_id,
                                    "Благодарю, план на этот месяц определен! Ваш вип-менеджер будет следить за прогрессом :)"
                                )
                                
                                # Сохраняем в трекер
                                tracker_url = pending_plan.get('tracker_url', '')
                                start_date = pending_plan.get('start_date', '')
                                
                                if tracker_url:
                                    tracker_saved = await self.monthly_plan_collector.save_plan_to_tracker(
                                        tracker_url=tracker_url,
                                        plan_value=plan_value,
                                        start_date=start_date
                                    )
                                    if tracker_saved:
                                        logger.info(f"✅ План сохранен в трекер")
                                else:
                                    logger.warning(f"⚠️ Нет tracker_url для сохранения в трекер")
                                
                                # KPI Ultra заполняется автоматически через формулу из 'Прогресс менеджеров'

                                # Очищаем ожидание
                                self.monthly_plan_collector.clear_pending_plan(sender_id)
                            else:
                                logger.warning(f"⚠️ Не удалось извлечь число плана из: '{message_text}'")
                    
                    # Обновляем дату последнего контакта в листе "Випалина" (колонка O)
                    if self.sheets_integration:
                        try:
                            await self.sheets_integration.update_last_contact(chat_id)
                        except Exception as update_err:
                            logger.warning(f"Не удалось обновить Випалину для {getcourse_id}: {update_err}")
                
                elif is_manager:
                    # Это сообщение от менеджера - регистрируем ответ (только если SLA трекер инициализирован)
                    manager_name = None
                    if self.sla_tracker:
                        manager_name = self.sla_tracker.get_manager_name(sender_id)
                    
                    if manager_name and student_id:
                        sla_result = None
                        if self.sla_tracker:
                            sla_result = self.sla_tracker.register_manager_response(
                                chat_id=chat_id,
                                student_id=student_id,
                                manager_id=sender_id,
                                manager_name=manager_name,
                                response_time=message_time
                            )
                        
                        # Если ответ менеджера не привёл к записи SLA (нет активного запроса)
                        if not sla_result:
                            logger.debug(f"Ответ менеджера {manager_name} не создал SLA-запись (нет активного запроса студента)")
                        
                        if sla_result and self.sla_sheets:
                            # Получаем invite_link для чата
                            invite_link = None
                            if self.persistence and self.persistence.is_initialized():
                                invite_link = self.persistence.get_invite_link_by_chat_id(chat_id)
                            
                            # Сохраняем результат в Google Sheets
                            save_success = self.sla_sheets.save_sla_record(
                                sla_data=sla_result,
                                getcourse_id=getcourse_id,
                                invite_link=invite_link
                            )
                            
                            if save_success:
                                status_emoji = "✅" if sla_result['sla_met'] else "⚠️"
                                logger.info(
                                    f"{status_emoji} SLA: {manager_name} ответил на запрос "
                                    f"{student_name} за {sla_result['response_minutes']:.1f} мин"
                                )
                            else:
                                # Не удалось сохранить в Google Sheets
                                logger.error(f"❌ Не удалось сохранить SLA-запись в Google Sheets")
                                try:
                                    await self.client.send_message(
                                        VIP_HEAD['telegram_id'],
                                        f"⚠️ **Ответ менеджера не записан в SLA**\n\n"
                                        f"Менеджер: **{manager_name}**\n"
                                        f"Студент: **{student_name}**\n"
                                        f"GetCourse ID: `{getcourse_id}`\n"
                                        f"Время ответа: {sla_result['response_minutes']:.1f} мин\n\n"
                                        f"❌ Ошибка сохранения в Google Sheets SLA.\n"
                                        f"Проверьте подключение к таблице."
                                    )
                                except Exception as notify_error:
                                    logger.error(f"Ошибка уведомления о SLA: {notify_error}")
                        
                        # Авто-обновление касаний ("Следующее общение" + 14 дней)
                        if self.touch_updater and getcourse_id:
                            await self.touch_updater.on_manager_message(getcourse_id)
                
            except Exception as e:
                logger.error(f"Ошибка в SLA-трекинге: {e}", exc_info=True)
        
        logger.info("✅ Настроен SLA-трекинг для групповых чатов")
    
    def _is_vip_manager(self, user_id: int) -> bool:
        """Проверяет, имеет ли пользователь права менеджера (включая дежурных)"""
        return user_id in ALL_MANAGER_IDS
    
    def _get_manager_name_by_id(self, telegram_id: int) -> Optional[str]:
        """Получает имя менеджера по Telegram ID"""
        # Маппинг из report_generator
        manager_mapping = {
            5169675294: "Марина Иванова",
            6327692209: "Оля Антипанова",
            7089851957: "Кристина Махмудян",
            6467441345: "Лиза Виноградова",
            6468860203: "Катя Чайка",
            7814751891: "Оля Тихонова",
            8026625530: "Катя Пилипенко",
            268400185: "Ксюша Уланова"
        }
        return manager_mapping.get(telegram_id)
    
    def _get_manager_info(self, manager_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию о менеджере, дежурном или руководителе"""
        return self.role_manager.get_manager_info(manager_id)
        # Потом ищем в дежурных
        for account in ON_DUTY_ACCOUNTS:
            if account['telegram_id'] == manager_id:
                return account
        return None
    
    async def _notify_onboarding_success(self, student_name: str, manager_name: str, chat_id: int):
        """Отправляет уведомление об успешном онбординге"""
        try:
            message = f"""✅ **ОНБОРДИНГ ЗАВЕРШЕН**

👤 **Студент:** {student_name}
👩‍💼 **Менеджер:** {manager_name}
💬 **Чат создан:** {chat_id}

Студент получил приветственное сообщение и добавлен в учебный чат!
"""
            await self.client.send_message(VIP_DEPARTMENT_CHAT_ID, message)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления об успешном онбординге: {e}", exc_info=True)
    
    async def _notify_onboarding_error(self, manager_id: int, student_name: str):
        """Отправляет уведомление об ошибке онбординга"""
        try:
            message = f"""❌ **ОШИБКА ОНБОРДИНГА**

👤 **Студент:** {student_name}

Не удалось автоматически создать чат. Пожалуйста, создайте чат вручную.
"""
            await self.client.send_message(manager_id, message)
            await self.client.send_message(VIP_DEPARTMENT_CHAT_ID, message)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления об ошибке онбординга: {e}", exc_info=True)
    
    async def _notify_privacy_error(self, manager_id: int, student_name: str, student_username: str, getcourse_id: str):
        """Отправляет уведомление об ошибке приватности студента"""
        try:
            username_info = f"@{student_username}" if student_username and student_username != 'неизвестно' else 'не указан'
            
            message = f"""🔒 **ОШИБКА ПРИВАТНОСТИ**

👤 **Студент:** {student_name}
идент **GetCourse ID:** {getcourse_id}
💬 **Telegram:** {username_info}

⚠️ **Проблема:** Студент запретил добавлять себя в группы (настройки приватности Telegram).

🛠 **Что делать:**
1️⃣ Свяжитесь со студентом лично
2️⃣ Попросите изменить настройки приватности:
   Settings → Privacy and Security → Groups → выбрать "Everybody" или добавить в исключения
3️⃣ После изменения настроек создайте чат вручную
4️⃣ Добавьте бота @Vipalina_zerocoder_bot в чат

Либо создайте чат без добавления студента, а потом отправьте ему ссылку-приглашение.
"""
            await self.client.send_message(manager_id, message)
            await self.client.send_message(VIP_DEPARTMENT_CHAT_ID, message)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления об ошибке приватности: {e}", exc_info=True)
    
    async def _notify_nocodb_error(self, student_name: str, getcourse_id: str, manager_name: str, error: str):
        """Отправляет уведомление об ошибке синхронизации с NocoDB"""
        try:
            # Короткая версия ошибки (первые 200 символов)
            error_short = error[:200] + "..." if len(error) > 200 else error
            
            message = f"""⚠️ **ОШИБКА NOCODB (Фаза 1)**

👤 **Студент:** {student_name}
идент **GetCourse ID:** {getcourse_id}
👩‍💼 **Менеджер:** {manager_name}

❌ **Ошибка:** {error_short}

Онбординг завершен, но NocoDB не обновлен. 
🛠️ Проверьте таблицу 'Ученики все' (вьюшка 'Новенькие').
"""
            # Отправляем только в VIP-чат (руководитель увидит)
            await self.client.send_message(VIP_DEPARTMENT_CHAT_ID, message)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления об ошибке NocoDB: {e}", exc_info=True)
    
    async def _notify_kpi_sheets_error(self, student_name: str, getcourse_id: str, manager_name: str, error: str):
        """Отправляет уведомление об ошибке синхронизации с KPI Sheets"""
        try:
            # Короткая версия ошибки (первые 200 символов)
            error_short = error[:200] + "..." if len(error) > 200 else error
            
            message = f"""⚠️ **ОШИБКА KPI SHEETS (Фаза 2)**

👤 **Студент:** {student_name}
идент **GetCourse ID:** {getcourse_id}
👩‍💼 **Менеджер:** {manager_name}

❌ **Ошибка:** {error_short}

Онбординг завершен, но KPI Sheets не обновлен. 
Пожалуйста, добавьте студента в "Общий список new" вручную.
"""
            # Отправляем только в VIP-чат (руководитель увидит)
            await self.client.send_message(VIP_DEPARTMENT_CHAT_ID, message)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления об ошибке KPI Sheets: {e}", exc_info=True)
    
    async def _notify_manual_addition(self, student_data: Dict[str, Any], manager_name: str):
        """Отправляет уведомление о ручном добавлении студента"""
        try:
            student_name = student_data.get('name', 'Неизвестный студент')
            getcourse_id = student_data.get('getcourse_id', 'Неизвестный ID')
            course = student_data.get('course', 'Неизвестный курс')
            
            message = f"""➕ **СТУДЕНТ ДОБАВЛЕН ВРУЧНУЮ**

👤 **Студент:** {student_name}
🆔 **GetCourse ID:** {getcourse_id}
🎯 **Курс:** {course}
👩‍💼 **Менеджер:** {manager_name}

🚀 Онбординг запущен автоматически.
"""
            
            await self.client.send_message(VIP_DEPARTMENT_CHAT_ID, message)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о ручном добавлении студента: {e}", exc_info=True)
    
    async def _check_missing_students(self):
        """
        Проверяет "пропавших" студентов (>30 дней без контакта)
        и отправляет уведомления менеджерам.
        Уведомление отправляется при первом появлении статуса и повторно через 7 дней.
        """
        try:
            if not self.sheets_integration:
                return
            
            missing_students = await self.sheets_integration.get_missing_students(days_threshold=60)
            
            if not missing_students:
                logger.info("Нет пропавших студентов для уведомления")
                return
            
            # Группируем по менеджерам
            by_manager = {}
            for student in missing_students:
                manager_id = student.get('manager_id')
                if manager_id:
                    if manager_id not in by_manager:
                        by_manager[manager_id] = []
                    by_manager[manager_id].append(student)
            
            # Отправляем уведомления менеджерам
            for manager_id, students in by_manager.items():
                try:
                    message = "🔴 **ПРОПАВШИЕ СТУДЕНТЫ**\n\n"
                    message += "Студенты, которые не писали более 60 дней:\n\n"
                    
                    for s in students[:10]:  # Максимум 10 студентов в одном сообщении
                        message += f"👤 **{s['name']}**\n"
                        message += f"   📚 Курс: {s['course']}\n"
                        message += f"   ⌚ Последний контакт: {s['days_since']} дней назад\n"
                        if s.get('invite_link') and s['invite_link'] != '-':
                            message += f"   🔗 Чат: {s['invite_link']}\n"
                        message += "\n"
                    
                    if len(students) > 10:
                        message += f"\n... и ещё {len(students) - 10} студентов\n"
                    
                    message += "\n💡 Рекомендуется связаться с ними или деактивировать чаты (/deactivate)"
                    
                    await self.client.send_message(manager_id, message)
                    logger.info(f"Отправлено уведомление о {len(students)} пропавших студентах менеджеру {manager_id}")
                    
                    # Записываем дату уведомления для каждого студента
                    for s in students:
                        await self.sheets_integration.mark_notification_sent(s['row_idx'])
                    
                    await asyncio.sleep(1)  # Задержка между сообщениями
                    
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления менеджеру {manager_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке пропавших студентов: {e}", exc_info=True)
    
    async def _get_minireport_homework_stats(self, getcourse_id: str) -> tuple:
        """
        Получает статистику ДЗ из таблицы "Доходимость по ДЗ Випалина".
        
        Returns:
            (hw_week, hw_month): список ДЗ за неделю, кол-во ДЗ за месяц
        """
        try:
            from config import HOMEWORK_TRACKING_SPREADSHEET_ID, HOMEWORK_TRACKING_TAB
            from shared_gspread_client import get_shared_gspread_client
            import gspread
            
            gc = get_shared_gspread_client()
            spreadsheet = gc.open_by_key(HOMEWORK_TRACKING_SPREADSHEET_ID)
            worksheet = spreadsheet.worksheet(HOMEWORK_TRACKING_TAB)
            all_data = await asyncio.to_thread(worksheet.get_all_values)
            
            if len(all_data) <= 1:
                logger.info(f"Статистика ДЗ для {getcourse_id}: пустая таблица (нет данных)")
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
                    logger.warning(f"Парсинг даты ДЗ для {getcourse_id}, урок '{lesson_name}': дата='{submission_date_str}', ошибка={e}")
                    continue
            
            logger.info(f"Статистика ДЗ для {getcourse_id}: неделя={len(hw_week)}, месяц={hw_month_count}")
            return hw_week, hw_month_count
            
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Таблица ДЗ не найдена (HOMEWORK_TRACKING_SPREADSHEET_ID={HOMEWORK_TRACKING_SPREADSHEET_ID}) для студента {getcourse_id}")
            return [], 0
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Лист '{HOMEWORK_TRACKING_TAB}' не найден в таблице ДЗ для студента {getcourse_id}")
            return [], 0
        except Exception as e:
            logger.error(f"Критическая ошибка получения статистики ДЗ для {getcourse_id}: {type(e).__name__} - {e}", exc_info=True)
            return [], 0
    
    async def _get_minireport_chat_link(self, getcourse_id: str, vipalina_info: Dict) -> str:
        """
        Получает ссылку на чат из Випалины, если нет - из KPI Ultra.
        """
        chat_link = vipalina_info.get('chat_link', '')
        if chat_link and chat_link != '-':
            return chat_link
        
        # Fallback: ищем в KPI Ultra, лист "Общий список new", столбец G
        try:
            from config import GOOGLE_SHEETS_ID, GOOGLE_SHEETS_KPI_TAB
            from shared_gspread_client import get_shared_gspread_client
            import gspread
            
            gc = get_shared_gspread_client()
            spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
            worksheet = spreadsheet.worksheet(GOOGLE_SHEETS_KPI_TAB)
            all_data = await asyncio.to_thread(worksheet.get_all_values)
            
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
    
    async def _missing_students_check_loop(self):
        """
        Периодическая проверка пропавших студентов (раз в день в 10:00 МСК).
        """
        import pytz
        
        moscow_tz = pytz.timezone('Europe/Moscow')
        
        while True:
            try:
                now = datetime.now(moscow_tz)
                
                # Проверяем в 10:00 МСК
                if now.hour == 10 and now.minute < 5:
                    logger.info("🔍 Запуск ежедневной проверки пропавших студентов")
                    await self._check_missing_students()
                    # Ждём 1 час чтобы не отправить повторно
                    await asyncio.sleep(3600)
                else:
                    # Проверяем каждые 5 минут
                    await asyncio.sleep(300)
                    
            except Exception as e:
                logger.error(f"Ошибка в цикле проверки пропавших: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def run(self):
        """Запускает основной цикл бота"""
        try:
            # Авторизация User Client как пользовательский аккаунт через номер телефона
            # Используется сессия ultralina_session.session созданная через ultralina_telethon.py
            # Для фонового режима используем force_sms=True чтобы не запрашивать интерактивный ввод
            try:
                await self.client.start()
                logger.info("✅ User Client запущен (@ultralina_zerocoder)")
                
                # КРИТИЧНО: Прогреваем диалоги для получения сообщений из групп
                # Без этого клиент не получает события из групповых чатов
                logger.info("🔄 Прогрев диалогов для получения групповых сообщений...")
                dialog_count = 0
                group_count = 0
                try:
                    async for dialog in self.client.iter_dialogs(limit=100):
                        dialog_count += 1
                        if dialog.is_group:
                            group_count += 1
                except Exception as dialog_err:
                    logger.warning(f"⚠️ Ошибка при прогреве диалогов: {dialog_err}")
                
                logger.info(f"✅ Прогрето {dialog_count} диалогов, из них {group_count} групповых")
                
                # catch_up ОТКЛЮЧЕН: вызывает TypeNotFoundError при новых TL-объектах Telegram API
                # и потенциально дублирует доставку событий
                logger.info("✅ catch_up пропущен — клиент готов к получению новых событий")
                    
            except Exception as e:
                # Если сессия недействительна, пытаемся авторизоваться с номером
                logger.warning(f"⚠️ Не удалось запустить с существующей сессией: {e}")
                logger.error(
                    "❌ Для первого запуска необходимо выполнить авторизацию:\n"
                    "python3 ultralina_telethon.py"
                )
                raise
            
            # Авторизация Bot Client через токен бота (для inline-кнопок)
            # Повторные попытки при нестабильном соединении через Tor
            bot_started = False
            for attempt in range(1, 6):
                try:
                    await self.bot_client.start(bot_token=TELETHON_BOT_TOKEN)
                    bot_started = True
                    logger.info(f"✅ Bot Client запущен (@zerocoder_ultralina_bot) с попытки {attempt}")
                    break
                except Exception as bot_err:
                    logger.warning(f"⚠️ Попытка {attempt}/5 запуска Bot Client не удалась: {bot_err}")
                    if attempt < 5:
                        await asyncio.sleep(5 * attempt)
                    else:
                        raise
            
            if not bot_started:
                raise RuntimeError("❌ Не удалось запустить Bot Client после 5 попыток")
            
            logger.info("Запущен клиент Telethon для автоматизации VIP-отдела")
            
            # Запускаем оркестратор
            await self.start()
            
            # Запускаем периодическую проверку пропавших студентов
            asyncio.create_task(self._missing_students_check_loop())
            logger.info("✅ Запущена ежедневная проверка пропавших студентов (10:00 МСК)")
            
            # Запускаем планировщик рассылки месячных планов
            # АВТОМАТИЧЕСКАЯ РАССЫЛКА ОТКЛЮЧЕНА - только ручной запуск через /sendmonthlyplans
            if self.monthly_plan_scheduler:
                logger.info("ℹ️ Автоматическая рассылка месячных планов отключена (используйте /sendmonthlyplans)")
            
            # Проверяем статус соединения перед входом в run_until_disconnected
            user_connected = self.client.is_connected()
            bot_connected = self.bot_client.is_connected()
            logger.info(f"🔌 Статус соединений: User Client={user_connected}, Bot Client={bot_connected}")
            
            if not user_connected or not bot_connected:
                logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Клиент не подключен! User={user_connected}, Bot={bot_connected}")
                raise RuntimeError("Клиенты не подключены перед run_until_disconnected()")
            
            logger.info("🔄 Входим в режим ожидания событий (run_until_disconnected)...")
            logger.info("⏳ Бот готов к работе и будет работать до отключения вручную")
            
            # Ожидаем завершения работы (ОБА клиента) ИЛИ сигнала shutdown
            # Используем asyncio.gather чтобы ждать оба клиента одновременно
            # Создаём задачи для обоих клиентов
            user_task = asyncio.create_task(self.client.run_until_disconnected())
            bot_task = asyncio.create_task(self.bot_client.run_until_disconnected())
            
            # Ждём сигнала shutdown или отключения клиентов
            if _shutdown_event:
                shutdown_task = asyncio.create_task(_shutdown_event.wait())
                
                done, pending = await asyncio.wait(
                    {user_task, bot_task, shutdown_task},
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Если получен сигнал shutdown
                if shutdown_task in done:
                    logger.info("📡 Получен сигнал shutdown - отключаю клиентов")
                    
                    # Отменяем оставшиеся задачи
                    for task in pending:
                        task.cancel()
                    
                    # Вызываем graceful shutdown
                    await _graceful_shutdown(self)
                else:
                    # Клиенты отключились сами
                    logger.warning("⚠️ run_until_disconnected() завершён - оба клиента отключились")
            else:
                # Signal handlers не установлены - просто ждём клиентов
                logger.warning("⚠️ Signal handlers не установлены - ждём только отключения клиентов")
                await asyncio.gather(user_task, bot_task)
            
        except Exception as e:
            logger.error(f"Критическая ошибка в работе бота: {e}", exc_info=True)
            raise


    async def _send_course_clarification_for_createtracker(
        self, 
        manager_id: int,
        student_data: Dict[str, Any],
        candidates: list[Dict[str, Any]],
        kpi_row: Dict[str, Any]
    ):
        """
        Отправляет запрос уточнения курса менеджеру в личные сообщения.
        Используется для команды /createtracker при неоднозначном курсе.
        """
        try:
            course_tag = student_data.get('course', '')
            student_name = student_data.get('name', 'Неизвестный студент')
            getcourse_id = student_data.get('getcourse_id', 'unknown')
            
            # Формируем список вариантов
            variants_text = "\n".join([
                f"{i+1}. {c.get('internal_name', c.get('kpi_name', 'Unknown'))} (лист: {c.get('gant_sheet', 'N/A')})"
                for i, c in enumerate(candidates)
            ])
            
            message = f"""⚠️ **Неоднозначное определение курса**

👤 Студент: {student_name}
🆔 GetCourse ID: `{getcourse_id}`
🏷 Тег из GetCourse:
`{course_tag}`

Найдено несколько подходящих вариантов:
{variants_text}

**Что делать:**
Ответьте на это сообщение номером нужного варианта (1, 2, 3...) или полным названием курса из списка выше.
"""
            
            # Отправляем сообщение менеджеру в личные сообщения
            sent_message = await self.client.send_message(
                manager_id,
                message,
                parse_mode='Markdown'
            )
            
            # Сохраняем информацию для последующей обработки ответа
            import time
            self.pending_createtracker_clarifications[sent_message.id] = {
                'type': 'ambiguous_course_createtracker',
                'getcourse_id': getcourse_id,
                'student_name': student_name,
                'student_data': student_data,
                'original_tag': course_tag,
                'candidates': candidates,
                'kpi_row': kpi_row,
                'manager_id': manager_id,
                'timestamp': time.time()
            }
            
            logger.info(f"✅ Отправлен запрос уточнения курса менеджеру {manager_id} для /createtracker")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке запроса уточнения для /createtracker: {e}", exc_info=True)
    
    async def _send_unknown_course_clarification_for_createtracker(
        self,
        manager_id: int,
        student_data: Dict[str, Any],
        candidates: list[str],
        kpi_row: Dict[str, Any]
    ):
        """
        Отправляет запрос уточнения неизвестного курса менеджеру в личные сообщения.
        Используется для команды /createtracker при полностью неизвестном курсе.
        """
        try:
            course_tag = student_data.get('course', '')
            student_name = student_data.get('name', 'Неизвестный студент')
            getcourse_id = student_data.get('getcourse_id', 'unknown')
            
            message = f"""❓ **Курс не найден в системе**

👤 Студент: {student_name}
🆔 GetCourse ID: `{getcourse_id}`
🏷 Тег из GetCourse:
`{course_tag}`
"""
            
            # Если есть похожие кандидаты, показываем их
            if candidates:
                variants_text = "\n".join([
                    f"{i+1}. {name}"
                    for i, name in enumerate(candidates)
                ])
                message += f"\nВозможные похожие курсы:\n{variants_text}\n"
            
            message += "\n**Что делать:**\nОтветьте на это сообщение с названием курса из списка выше или укажите точное внутреннее название.\n"
            
            # Отправляем сообщение менеджеру в личные сообщения
            sent_message = await self.client.send_message(
                manager_id,
                message,
                parse_mode='Markdown'
            )
            
            # Сохраняем информацию для последующей обработки ответа
            import time
            self.pending_createtracker_clarifications[sent_message.id] = {
                'type': 'unknown_course_createtracker',
                'getcourse_id': getcourse_id,
                'student_name': student_name,
                'student_data': student_data,
                'original_tag': course_tag,
                'candidates': candidates,
                'kpi_row': kpi_row,
                'manager_id': manager_id,
                'timestamp': time.time()
            }
            
            logger.info(f"✅ Отправлен запрос уточнения неизвестного курса менеджеру {manager_id} для /createtracker")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке запроса уточнения неизвестного курса: {e}", exc_info=True)
    
    async def _handle_activate_course_clarification_response(self, message) -> bool:
        """
        Обрабатывает ответ менеджера на уточнение курса при /activate.
        
        Returns:
            True если ответ успешно обработан
        """
        try:
            sender_id = message.sender_id
            
            # Проверяем, есть ли ожидающее уточнение для этого менеджера
            if sender_id not in self.pending_activate_course_clarifications:
                return False
            
            clarification_data = self.pending_activate_course_clarifications[sender_id]
            
            # Парсим ответ менеджера
            user_input = message.text.strip() if hasattr(message, 'text') and message.text else ""
            
            if not user_input:
                return False
            
            from course_config_v2 import CourseConfig
            selected_course_tag = None
            
            if clarification_data['type'] == 'ambiguous_course':
                # Обрабатываем выбор из вариантов
                candidates = clarification_data['candidates']
                selected_course = None
                
                # Пытаемся распознать номер
                if user_input.isdigit():
                    idx = int(user_input) - 1
                    if 0 <= idx < len(candidates):
                        selected_course = candidates[idx]
                        logger.info(f"🔢 Выбран курс по номеру {idx+1}: {selected_course.get('internal_name')}")
                
                # Или поиск по названию
                if not selected_course:
                    normalized_input = user_input.lower()
                    for candidate in candidates:
                        internal_name = candidate.get('internal_name', candidate.get('kpi_name', ''))
                        if normalized_input in internal_name.lower():
                            selected_course = candidate
                            logger.info(f"🅰️ Выбран курс по названию: {internal_name}")
                            break
                
                if not selected_course:
                    await self.client.send_message(
                        sender_id,
                        "❌ Не удалось определить выбранный курс. "
                        "Пожалуйста, укажите номер варианта (1, 2, 3...) или точное название."
                    )
                    return True
                
                # Добавляем временное соответствие
                original_course = clarification_data['original_course']
                CourseConfig.COURSE_MAPPING[original_course] = selected_course
                selected_course_tag = original_course
                logger.info(f"📌 Добавлено временное соответствие: {original_course} -> {selected_course.get('internal_name')}")
                
            elif clarification_data['type'] == 'unknown_course':
                # Просто используем указанное название
                selected_course_tag = user_input
                logger.info(f"➕ Используем введённое название курса: {selected_course_tag}")
            
            # Подтверждаем менеджеру
            await self.client.send_message(
                sender_id,
                f"✅ Курс уточнён, создаю трекер для студента **{clarification_data['student_name']}**..."
            )
            
            # Удаляем из pending
            del self.pending_activate_course_clarifications[sender_id]
            
            # Создаём трекер с уточнённым курсом
            await self._create_tracker_for_activate(
                getcourse_id=clarification_data['getcourse_id'],
                student_name=clarification_data['student_name'],
                manager_id=sender_id,
                manager_name=clarification_data['manager_name'],
                course_tag=selected_course_tag
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки ответа на уточнение /activate: {e}", exc_info=True)
            return False
    
    async def _run_createtracker_flow(
        self,
        manager_id: int,
        getcourse_id: str,
        student_name: str,
        course_tag: str,
        manager_name: str,
        row_number: int,
    ):
        """Создаёт трекер и обновляет KPI/Випалину. Вызывается из /createtracker и подтверждения да/нет."""
        import asyncio as _asyncio
        if not self.tracker_creator:
            await self.client.send_message(manager_id, "❌ TrackerCreator не инициализирован.")
            return
        try:
            tracker_result = await _asyncio.to_thread(
                self.tracker_creator.create_tracker,
                student_name=student_name,
                course_tag=course_tag,
                manager_name=manager_name,
                getcourse_id=getcourse_id
            )
            tracker_url = tracker_result['url']
            logger.info(f"✅ Трекер создан для {getcourse_id}: {tracker_url}")
            # Обновляем KPI Sheets
            try:
                await self.kpi_sheets.update_tracker_link(row_number, tracker_url)
            except Exception as e:
                logger.error(f"❌ Ошибка обновления KPI для {getcourse_id}: {e}")
            # Обновляем Випалину
            if self.sheets_integration:
                try:
                    await self.sheets_integration.update_tracker_url_by_getcourse_id(getcourse_id, tracker_url)
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось обновить Випалину: {e}")
            await self.client.send_message(
                manager_id,
                f"✅ **Трекер успешно создан!**\n\n"
                f"👤 Студент: **{student_name}**\n"
                f"🆔 GetCourse ID: `{getcourse_id}`\n"
                f"🔗 [Открыть трекер]({tracker_url})",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"❌ Ошибка создания трекера {getcourse_id}: {e}", exc_info=True)
            await self.bot_client.send_message(
                manager_id,
                f"❌ Не удалось создать трекер (команда /createtracker)\n\n"
                f"Студент: {student_name}\n"
                f"GetCourse ID: `{getcourse_id}`\n\n"
                f"Ошибка: {str(e)[:200]}\n\n"
                f"🔧 Проверьте квоту Google Drive.",
                parse_mode='Markdown'
            )

    async def _create_tracker_for_activate(
        self,
        getcourse_id: str,
        student_name: str,
        manager_id: int,
        manager_name: str,
        course_tag: str
    ):
        """
        Создаёт трекер после уточнения курса при /activate.
        """
        try:
            # Создаём трекер
            tracker_result = await asyncio.to_thread(
                self.tracker_creator.create_tracker,
                student_name=student_name,
                course_tag=course_tag,
                manager_name=manager_name,
                getcourse_id=getcourse_id
            )
            
            tracker_url = tracker_result['url']
            logger.info(f"✅ Трекер создан для студента {getcourse_id}: {tracker_url}")
            
            # Обновляем ссылку на трекер в KPI Sheets
            if self.kpi_sheets:
                try:
                    kpi_row = await self.kpi_sheets._find_student_row_in_kpi(getcourse_id)
                    if kpi_row:
                        await self.kpi_sheets.update_tracker_link(kpi_row, tracker_url)
                        logger.info(f"✅ Ссылка на трекер обновлена в KPI Sheets для студента {getcourse_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка обновления ссылки на трекер в KPI Sheets: {e}", exc_info=True)
            
            # Обновляем в листе Випалина
            if self.sheets_integration:
                try:
                    vipalina_updated = await self.sheets_integration.update_tracker_url_by_getcourse_id(
                        getcourse_id=getcourse_id,
                        tracker_url=tracker_url
                    )
                    if vipalina_updated:
                        logger.info(f"✅ Трекер обновлён в листе Випалина для {getcourse_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось обновить трекер в Випалина: {e}")
            
            # Отправляем успешное сообщение
            await self.client.send_message(
                manager_id,
                f"✅ **Трекер успешно создан!**\n\n"
                f"👤 Студент: **{student_name}**\n"
                f"🆔 GetCourse ID: `{getcourse_id}`\n"
                f"📚 Курс: {course_tag}\n"
                f"👩‍💼 Менеджер: {manager_name}\n\n"
                f"🔗 [Открыть трекер]({tracker_url})",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания трекера после уточнения: {e}", exc_info=True)
            await self.bot_client.send_message(
                manager_id,
                f"❌ **Ошибка создания трекера**\n\n"
                f"Студент: {student_name}\n"
                f"GetCourse ID: `{getcourse_id}`\n\n"
                f"Ошибка: {str(e)[:200]}\n\n"
                f"🔧 Проверьте квоту Google Drive.",
                parse_mode='Markdown'
            )
    
    async def _handle_createtracker_clarification_response(self, message) -> bool:
        """
        Обрабатывает ответ менеджера на уточнение курса для команды /createtracker.
        
        Returns:
            True если ответ успешно обработан
        """
        try:
            # Проверяем, что это ответ на сообщение
            if not hasattr(message, 'reply_to_msg_id') or not message.reply_to_msg_id:
                return False
            
            replied_msg_id = message.reply_to_msg_id
            
            # Проверяем, есть ли это сообщение в наших уточнениях
            if replied_msg_id not in self.pending_createtracker_clarifications:
                return False
            
            clarification_data = self.pending_createtracker_clarifications[replied_msg_id]
            
            # Парсим ответ менеджера
            user_input = message.text.strip() if hasattr(message, 'text') and message.text else ""
            
            if clarification_data['type'] == 'ambiguous_course_createtracker':
                # Обрабатываем выбор из вариантов
                candidates = clarification_data['candidates']
                selected_course = None
                
                # Пытаемся распознать номер
                if user_input.isdigit():
                    idx = int(user_input) - 1
                    if 0 <= idx < len(candidates):
                        selected_course = candidates[idx]
                        logger.info(f"🔢 Выбран курс по номеру {idx+1}: {selected_course.get('internal_name')}")
                
                # Или поиск по названию
                if not selected_course:
                    normalized_input = user_input.lower()
                    for candidate in candidates:
                        internal_name = candidate.get('internal_name', candidate.get('kpi_name', ''))
                        if normalized_input in internal_name.lower():
                            selected_course = candidate
                            logger.info(f"🅰️ Выбран курс по названию: {internal_name}")
                            break
                
                if not selected_course:
                    await self.client.send_message(
                        clarification_data['manager_id'],
                        "❌ Не удалось определить выбранный курс. "
                        "Пожалуйста, укажите номер варианта (1, 2, 3...) или точное название.",
                        reply_to=message.id
                    )
                    return False
                
                # Обновляем курс в CourseConfig временно
                from course_config_v2 import CourseConfig
                original_tag = clarification_data['original_tag']
                CourseConfig.COURSE_MAPPING[original_tag] = selected_course
                logger.info(f"📌 Добавлено временное соответствие: {original_tag} -> {selected_course.get('internal_name')}")
                
            elif clarification_data['type'] == 'unknown_course_createtracker':
                # Обрабатываем ответ с названием курса
                # Проверяем, есть ли курс среди кандидатов
                candidates = clarification_data.get('candidates', [])
                matched_course_name = None
                
                if candidates:
                    normalized_input = user_input.lower()
                    for candidate_name in candidates:
                        if normalized_input in candidate_name.lower():
                            matched_course_name = candidate_name
                            logger.info(f"✅ Найден курс из кандидатов: {matched_course_name}")
                            break
                
                # Если не нашли, используем как есть
                if not matched_course_name:
                    matched_course_name = user_input
                    logger.info(f"➕ Используем введённое название: {matched_course_name}")
                
                # Запускаем регистрацию нового курса через unknown_course_handler
                if self.unknown_course_handler:
                    from course_config_v2 import CourseConfig
                    request_id = CourseConfig.register_unknown_course(
                        getcourse_tag=clarification_data['original_tag'],
                        student_data=clarification_data['student_data']
                    )
                    logger.info(f"📝 Зарегистрирован неизвестный курс: {clarification_data['original_tag']}")
            
            # Подтверждаем менеджеру
            await self.client.send_message(
                clarification_data['manager_id'],
                f"✅ Курс уточнён, создаю трекер для студента {clarification_data['student_name']}...",
                reply_to=message.id
            )
            
            # Удаляем из pending
            del self.pending_createtracker_clarifications[replied_msg_id]
            
            # Запускаем создание трекера с уточнённым курсом
            await self._create_tracker_after_clarification(
                clarification_data['student_data'],
                clarification_data['kpi_row'],
                clarification_data['manager_id']
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки ответа на уточнение /createtracker: {e}", exc_info=True)
            return False
    
    async def _create_tracker_after_clarification(
        self,
        student_data: Dict[str, Any],
        kpi_row: Dict[str, Any],
        manager_id: int
    ):
        """
        Создаёт трекер после уточнения курса менеджером.
        """
        try:
            student_name = student_data.get('name')
            course_tag = student_data.get('course')
            getcourse_id = student_data.get('getcourse_id')
            
            manager_info = self._get_manager_info(manager_id)
            if not manager_info:
                await self.client.send_message(manager_id, "❌ Не удалось определить данные менеджера.")
                return
            
            manager_name = manager_info['name']
            
            # Создаём трекер
            tracker_result = await asyncio.to_thread(
                self.tracker_creator.create_tracker,
                student_name=student_name,
                course_tag=course_tag,
                manager_name=manager_name,
                getcourse_id=getcourse_id
            )
            
            tracker_url = tracker_result['url']
            logger.info(f"✅ Трекер создан для студента {getcourse_id}: {tracker_url}")
            
            # Обновляем ссылку на трекер в KPI Sheets
            try:
                await self.kpi_sheets.update_tracker_link(kpi_row, tracker_url)
                logger.info(f"✅ Ссылка на трекер обновлена в KPI Sheets для студента {getcourse_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка обновления ссылки на трекер в KPI Sheets: {e}", exc_info=True)
            
            # Обновляем в листе Випалина (если студент там есть)
            try:
                if self.sheets_integration:
                    vipalina_updated = await self.sheets_integration.update_tracker_url_by_getcourse_id(
                        getcourse_id=getcourse_id,
                        tracker_url=tracker_url
                    )
                    if vipalina_updated:
                        logger.info(f"✅ Трекер обновлён в листе Випалина для {getcourse_id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось обновить трекер в Випалина: {e}")
            
            # Отправляем успешное сообщение
            await self.client.send_message(
                manager_id,
                f"✅ **Трекер успешно создан!**\n\n"
                f"👤 Студент: **{student_name}**\n"
                f"🆔 GetCourse ID: `{getcourse_id}`\n"
                f"📚 Курс: {course_tag}\n"
                f"👩‍💼 Менеджер: {manager_name}\n\n"
                f"🔗 [Открыть трекер]({tracker_url})",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания трекера после уточнения: {e}", exc_info=True)
            await self.client.send_message(
                manager_id,
                f"❌ **Ошибка создания трекера**\n\n"
                f"Студент: {student_data.get('name')}\n"
                f"GetCourse ID: `{student_data.get('getcourse_id')}`\n\n"
                f"Ошибка: {str(e)[:200]}\n\n"
                f"🔧 Проверьте квоту Google Drive.",
                parse_mode='Markdown'
            )


# Глобальные переменные для graceful shutdown
_orchestrator_instance = None
_shutdown_event = None

async def setup_signal_handlers_async():
    """Устанавливает асинхронные обработчики сигналов для graceful shutdown"""
    import signal
    global _shutdown_event
    
    _shutdown_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        """Обработчик сигналов SIGTERM и SIGINT"""
        logger = logging.getLogger('vipalina_telethon')
        logger.info("📡 Получен сигнал остановки - запускаю graceful shutdown")
        if _shutdown_event:
            _shutdown_event.set()
    
    # Регистрируем signal handlers через asyncio loop
    loop.add_signal_handler(signal.SIGTERM, signal_handler)
    loop.add_signal_handler(signal.SIGINT, signal_handler)
    
    logging.getLogger('vipalina_telethon').info("✅ Async signal handlers установлены (SIGTERM, SIGINT)")

async def main():
    """Основная функция для запуска автоматизации VIP-отдела"""
    global _orchestrator_instance
    
    # PID-lock: гарантируем что работает только ОДИН экземпляр бота
    import os
    pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.vipalina.pid')
    my_pid = os.getpid()
    
    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                old_pid = int(f.read().strip())
            if old_pid != my_pid:
                os.kill(old_pid, 0)  # signal 0 = проверка существования
                print(f"⚠️ Обнаружен запущенный экземпляр (PID {old_pid}), убиваю...")
                os.kill(old_pid, 9)
                import time
                time.sleep(1)
        except (ProcessLookupError, ValueError, PermissionError, OSError):
            pass  # Процесс мёртв или PID невалиден — продолжаем
    
    with open(pid_file, 'w') as f:
        f.write(str(my_pid))
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler('vipalina_logs/vip_automation.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger('vipalina_telethon')
    logger.info("🚀 Запуск автоматизации VIP-отдела Zerocoder University")
    
    # Устанавливаем async signal handlers
    await setup_signal_handlers_async()
    
    # Глобальный обработчик необработанных исключений asyncio
    def global_exception_handler(loop, context):
        """Обработчик критических исключений asyncio"""
        exception = context.get('exception')
        message = context.get('message', 'Неизвестная ошибка')
        
        if exception:
            logger.error(f"🚨 КРИТИЧЕСКОЕ ИСКЛЮЧЕНИЕ: {exception}", exc_info=exception)
            
            # Формируем сообщение с трейсбэком
            import traceback
            error_text = ''.join(traceback.format_exception(
                type(exception), exception, exception.__traceback__
            ))[:500]
            
            # Пытаемся отправить уведомление руководителю
            try:
                # Получаем клиент из контекста если есть
                from config import VIP_HEAD
                from telethon import TelegramClient
                
                # Создаем асинхронную задачу для отправки уведомления
                async def send_critical_error_notification():
                    try:
                        # Пытаемся найти активный клиент
                        # Для этого используем глобальную переменную orchestrator если она доступна
                        pass  # Уведомление будет отправлено через orchestrator если он доступен
                    except:
                        pass
                
                asyncio.create_task(send_critical_error_notification())
            except:
                pass
        else:
            logger.error(f"🚨 КРИТИЧЕСКАЯ ОШИБКА ASYNCIO: {message}")
    
    # Устанавливаем глобальный обработчик
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(global_exception_handler)
    logger.info("✅ Глобальный обработчик исключений установлен")
    
    try:
        # Создаем и запускаем оркестратор
        orchestrator = VipAutomationOrchestrator()
        _orchestrator_instance = orchestrator
        
        # Оборачиваем критические исключения для отправки уведомлений
        async def run_with_error_notification():
            try:
                await orchestrator.run()
            except Exception as e:
                # Отправляем уведомление руководителю о критической ошибке
                try:
                    import traceback
                    error_text = ''.join(traceback.format_exception(
                        type(e), e, e.__traceback__
                    ))[:500]
                    
                    if hasattr(orchestrator, 'client') and orchestrator.client:
                        await orchestrator.client.send_message(
                            VIP_HEAD['telegram_id'],
                            f"🚨 **КРИТИЧЕСКАЯ ОШИБКА БОТА**\n\n"
                            f"Бот остановлен из-за необработанного исключения:\n\n"
                            f"```\n{error_text}\n```\n\n"
                            f"🔧 **Действие:**\n"
                            f"Проверьте логи и перезапустите бота."
                        )
                        logger.info("✉️ Уведомление о критической ошибке отправлено руководителю")
                except Exception as notify_error:
                    logger.error(f"Не удалось отправить уведомление о критической ошибке: {notify_error}")
                
                # Пробрасываем исключение дальше
                raise
        
        await run_with_error_notification()
        
    except KeyboardInterrupt:
        logger.info("🛑 Автоматизация остановлена пользователем (Ctrl+C)")
        await _graceful_shutdown(orchestrator)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в работе автоматизации: {e}", exc_info=True)
        await _graceful_shutdown(orchestrator)
        sys.exit(1)


async def _graceful_shutdown(orchestrator):
    """Graceful shutdown: корректно отключает ОБА клиента"""
    logger = logging.getLogger('vipalina_telethon')
    logger.info("🔄 Начинаю graceful shutdown...")
    
    try:
        # 1. Останавливаем Bot Client
        if hasattr(orchestrator, 'bot_client') and orchestrator.bot_client.is_connected():
            logger.info("🔌 Отключаю Bot Client (@zerocoder_ultralina_bot)...")
            await orchestrator.bot_client.disconnect()
            logger.info("✅ Bot Client отключён")
        
        # 2. Останавливаем User Client
        if hasattr(orchestrator, 'client') and orchestrator.client.is_connected():
            logger.info("🔌 Отключаю User Client (@ultralina_zerocoder)...")
            await orchestrator.client.disconnect()
            logger.info("✅ User Client отключён")
        
        # 3. Сохраняем состояние в персистенцию
        if hasattr(orchestrator, 'persistence') and orchestrator.persistence:
            logger.info("💾 Сохраняю финальное состояние в Google Sheets...")
            orchestrator.persistence.log_event('shutdown', 'Graceful shutdown завершён', {})
            logger.info("✅ Состояние сохранено")
        
        logger.info("✅ Graceful shutdown завершён успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при graceful shutdown: {e}", exc_info=True)


async def setup_ai_message_handler(orchestrator):
    """Настраивает обработчик сообщений от студентов с AI-анализом"""
    try:
        from ai_analyzer import get_ai_analyzer
        
        # Обработчик сообщений от студентов в групповых чатах
        # Убрали chats=... фильтр, чтобы работало с чатами, активированными после запуска
        @orchestrator.client.on(events.NewMessage(incoming=True))
        async def handle_student_group_message(event):
            """Обработчик сообщений студентов в групповых чатах с AI-анализом"""
            try:
                # Проверяем, что это групповой чат
                if not event.is_group:
                    return
                
                # Получаем ID чата и студента
                chat_id = event.chat_id
                getcourse_id = orchestrator.chat_to_student.get(chat_id)
                
                if not getcourse_id:
                    return  # Чат не отслеживается
                
                # Проверяем, что сообщение не от менеджера
                user_id = event.sender_id
                if orchestrator._is_vip_manager(user_id):
                    return  # Пропускаем сообщения от менеджеров
                
                # Получаем текст сообщения
                message_text = event.message.text if event.message.text else "[медиа/стикер]"
                if not message_text or message_text.startswith('/'):
                    return  # Пропускаем команды и пустые сообщения
                
                # Получаем информацию о студенте
                user = await event.get_sender()
                user_id = user.id
                username = user.username or "Неизвестно"
                
                logger.info(f"🤖 Получено сообщение от студента {username} ({getcourse_id}): {message_text[:50]}...")
                
                # Выполняем AI-анализ
                analyzer = await get_ai_analyzer()
                analysis_result = await analyzer.analyze_student_message(message_text, getcourse_id)
                
                # Отправляем рекомендации менеджеру
                await send_ai_recommendations_to_managers(orchestrator, analysis_result, getcourse_id, chat_id)
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения студента с AI: {e}", exc_info=True)
        
        logger.info("✅ AI-обработчик сообщений студентов настроен (динамический режим)")
        
    except Exception as e:
        logger.error(f"❌ Ошибка настройки AI-обработчика: {e}")


async def send_ai_recommendations_to_managers(orchestrator, analysis_result: Dict[str, Any], getcourse_id: str, chat_id: int):
    """Отправляет AI-рекомендации менеджерам"""
    try:
        # Получаем данные студента для формирования сообщения
        student_name = analysis_result.get("student_context", {}).get("name", "Неизвестно")
        manager_name = analysis_result.get("student_context", {}).get("manager", "Не назначен")
        
        # Формируем сообщение для менеджера
        message = f"🤖 **AI АНАЛИЗ СООБЩЕНИЯ**\n\n"
        message += f"👤 Студент: **{student_name}** (ID: {getcourse_id})\n"
        message += f"👨‍💼 Менеджер: {manager_name}\n"
        message += f"💬 Сообщение: \"{analysis_result.get('original_message', '')[:100]}...\"\n\n"
        
        # Добавляем классификацию
        classification = analysis_result.get("classification", {})
        message += f"🏷 Категория: **{classification.get('category', 'Не определена')}**\n"
        message += f"📊 Уверенность: {classification.get('confidence', 0):.2f}\n"
        message += f"🔍 Причина: {classification.get('reasoning', 'Не указано')}\n\n"
        
        # Добавляем контекст
        context = analysis_result.get("context_analysis", {})
        message += f"⚠️ Риск отсева: **{context.get('risk_level', 'Неизвестно')}**\n"
        message += f"📈 Активность: {context.get('activity_score', 0)}%\n\n"
        
        # Добавляем рекомендации
        recommendations = analysis_result.get("recommendations", "Рекомендации не сгенерированы")
        message += f"💡 **РЕКОМЕНДАЦИИ**:\n{recommendations}\n\n"
        
        # Добавляем приоритет
        priority = analysis_result.get("priority", "обычный")
        priority_emoji = {"высокий": "🚨", "средний": "⚠️", "обычный": "ℹ️"}.get(priority, "ℹ️")
        message += f"{priority_emoji} Приоритет: **{priority}**\n\n"
        
        # Добавляем ссылку на чат
        student_context = analysis_result.get("student_context", {})
        chat_link = student_context.get("chat_link", "")
        if chat_link:
            message += f"🔗 [Открыть чат]({chat_link})\n"
        
        # Отправляем сообщение менеджеру студента
        manager_telegram_id = get_manager_telegram_id_by_name(manager_name)
        if manager_telegram_id:
            try:
                await orchestrator.client.send_message(manager_telegram_id, message, parse_mode='md')
                logger.info(f"✅ AI-рекомендации отправлены менеджеру {manager_name}")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки AI-рекомендаций менеджеру {manager_name}: {e}")
        else:
            # Если не нашли конкретного менеджера, отправляем всем VIP-менеджерам
            logger.warning(f"⚠️ Не найден Telegram ID менеджера {manager_name}, отправляем всем")
            for manager_id in ALL_MANAGER_IDS:
                try:
                    await orchestrator.client.send_message(manager_id, message, parse_mode='md')
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки AI-рекомендаций менеджеру {manager_id}: {e}")
                    
    except Exception as e:
        logger.error(f"❌ Ошибка отправки AI-рекомендаций: {e}", exc_info=True)


def get_manager_telegram_id_by_name(manager_name: str) -> Optional[int]:
    """Получает Telegram ID менеджера по имени"""
    try:
        from config import VIP_MANAGERS_VIP, VIP_MANAGERS_LUXURY, VIP_HEAD
        
        # Ищем в VIP менеджерах
        for manager in VIP_MANAGERS_VIP:
            if manager['name'] == manager_name:
                return manager['telegram_id']
        
        # Ищем в Luxury менеджерах
        for manager in VIP_MANAGERS_LUXURY:
            if manager['name'] == manager_name:
                return manager['telegram_id']
        
        # Проверяем руководителя
        if VIP_HEAD['name'] == manager_name:
            return VIP_HEAD['telegram_id']
            
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка получения Telegram ID менеджера {manager_name}: {e}")
        return None

if __name__ == "__main__":
    # Запускаем асинхронную функцию
    asyncio.run(main())
    asyncio.run(main())
