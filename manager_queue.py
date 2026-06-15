"""
Модуль управления очередью VIP-менеджеров и обработки inline-кнопок
"""

import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from telethon import Button, TelegramClient
from telethon import events
from telethon.tl.types import Message

# Импортируем конфигурационные параметры
try:
    from config import (
        VIP_DEPARTMENT_CHAT_ID,
        VIP_HEAD,
        HEAD_IDS,
        ON_DUTY_ACCOUNTS,
        ALL_MANAGER_IDS,
        VIP_MANAGERS_VIP,
        VIP_MANAGERS_LUXURY
    )
except ImportError:
    # Для тестов
    VIP_DEPARTMENT_CHAT_ID = -1001755644531
    VIP_HEAD = {"telegram_id": 268400185}
    ON_DUTY_ACCOUNTS = []
    ALL_MANAGER_IDS = []
    VIP_MANAGERS_VIP = []
    VIP_MANAGERS_LUXURY = []

from course_config_v2 import CourseConfig
from datetime_utils import get_moscow_now

# Модуль персистенции
try:
    from vipalina_persistence import get_persistence
except ImportError:
    get_persistence = None

# Настройка логирования
logger = logging.getLogger('manager_queue')


@dataclass
class ManagerAssignment:
    """Информация о назначении менеджера студенту"""
    student_getcourse_id: str
    manager_id: int
    manager_name: str
    course_tag: str
    timestamp: datetime
    status: str  # "pending", "accepted", "skipped"
    # Данные студента для переназначения
    student_name: str = 'Unknown'
    student_telegram: str = ''
    student_telegram_id: Optional[int] = None
    dm_message_id: Optional[int] = None  # ID личного DM менеджеру (для удаления при skip)


class ManagerQueue:
    """
    Управление очередями VIP-менеджеров.
    Реализует две круговые очереди для справедливого распределения студентов:
    - VIP очередь: для студентов без [luxury] и [mini-luxury] в теге курса
    - Luxury очередь: для студентов с [luxury] или [mini-luxury] в теге курса
    
    Thread-safe с использованием threading.Lock для предотвращения race conditions.
    """
    
    def __init__(self, client: TelegramClient):
        self.client = client
        self.vip_managers = VIP_MANAGERS_VIP.copy()
        self.luxury_managers = VIP_MANAGERS_LUXURY.copy()
        self.current_vip_index = 0
        self.current_luxury_index = 0
        self.assignments: Dict[str, ManagerAssignment] = {}  # getcourse_id -> ManagerAssignment
        self.on_student_accepted: Optional[Callable] = None
        
        # Lock для thread-safe операций с очередями и назначениями
        self._vip_lock = threading.Lock()
        self._luxury_lock = threading.Lock()
        self._assignments_lock = threading.Lock()
        
        logger.info(f"Инициализированы очереди менеджеров:")
        logger.info(f"  VIP очередь: {len(self.vip_managers)} менеджеров")
        logger.info(f"  Luxury очередь: {len(self.luxury_managers)} менеджеров")
    
    def _save_queue_indices(self):
        """Сохраняет индексы очередей в персистенцию."""
        try:
            if get_persistence:
                persistence = get_persistence()
                if persistence and persistence.is_initialized():
                    persistence.save_queue_indices(self.current_vip_index, self.current_luxury_index)
        except Exception as e:
            logger.error(f"Ошибка сохранения индексов очередей: {e}")
    
    def _save_assignment(self, getcourse_id: str, assignment: 'ManagerAssignment'):
        """Сохраняет назначение в персистенцию."""
        try:
            if get_persistence:
                persistence = get_persistence()
                if persistence and persistence.is_initialized():
                    persistence.save_manager_assignment(getcourse_id, {
                        'manager_id': assignment.manager_id,
                        'manager_name': assignment.manager_name,
                        'course_tag': assignment.course_tag,
                        'status': assignment.status,
                        'student_name': assignment.student_name,
                        'student_telegram': assignment.student_telegram,
                        'student_telegram_id': assignment.student_telegram_id
                    })
        except Exception as e:
            logger.error(f"Ошибка сохранения назначения: {e}")
    
    def _delete_assignment(self, getcourse_id: str):
        """Удаляет назначение из персистенции."""
        try:
            if get_persistence:
                persistence = get_persistence()
                if persistence and persistence.is_initialized():
                    persistence.delete_manager_assignment(getcourse_id)
        except Exception as e:
            logger.error(f"Ошибка удаления назначения: {e}")
    
    def _is_luxury_student(self, course_tag: str) -> bool:
        """
        Проверяет, является ли студент Luxury студентом.
        
        Args:
            course_tag: Тег курса из GetCourse
            
        Returns:
            True если это Luxury или Mini-Luxury студент
        """
        return '[luxury]' in course_tag.lower() or '[mini-luxury]' in course_tag.lower()
    
    def get_next_manager(self, course_tag: str) -> Optional[Dict[str, Any]]:
        """
        Получает следующего менеджера в очереди в зависимости от типа курса.
        Thread-safe операция.
        
        Args:
            course_tag: Тег курса из GetCourse
            
        Returns:
            Dict с информацией о менеджере
        """
        # Определяем тип студента по тегу курса
        is_luxury = self._is_luxury_student(course_tag)
        
        if is_luxury:
            # Luxury студенты - используем Luxury очередь
            with self._luxury_lock:
                if not self.luxury_managers:
                    logger.error("Список Luxury менеджеров пуст!")
                    return None
                
                manager = self.luxury_managers[self.current_luxury_index]
                self.current_luxury_index = (self.current_luxury_index + 1) % len(self.luxury_managers)
                self._save_queue_indices()  # Сохраняем индексы
                logger.info(f"Следующий Luxury менеджер в очереди: {manager['name']} (ID: {manager['telegram_id']})")
                return manager
        else:
            # VIP студенты - используем VIP очередь
            with self._vip_lock:
                if not self.vip_managers:
                    logger.error("Список VIP менеджеров пуст!")
                    return None
                
                manager = self.vip_managers[self.current_vip_index]
                self.current_vip_index = (self.current_vip_index + 1) % len(self.vip_managers)
                self._save_queue_indices()  # Сохраняем индексы
                logger.info(f"Следующий VIP менеджер в очереди: {manager['name']} (ID: {manager['telegram_id']})")
                return manager
    
    def skip_to_next_manager(self, getcourse_id: str, course_tag: str) -> Optional[Dict[str, Any]]:
        """
        Пропускает текущего менеджера и назначает следующего.
        Thread-safe операция.
        
        Args:
            getcourse_id: ID студента в GetCourse
            course_tag: Тег курса из GetCourse
            
        Returns:
            Dict с информацией о следующем менеджере или None
        """
        with self._assignments_lock:
            if getcourse_id not in self.assignments:
                logger.warning(f"Нет активного назначения для студента {getcourse_id}")
                return None
            
            # Защита: если студент уже принят — игнорируем пропуск со старых кнопок
            if self.assignments[getcourse_id].status == "accepted":
                logger.warning(f"Студент {getcourse_id} уже принят, пропуск игнорируется")
                return None
            
            # Отмечаем как пропущенный
            self.assignments[getcourse_id].status = "skipped"
            
            # Получаем следующего менеджера
            next_manager = self.get_next_manager(course_tag)
            
            # Сохраняем данные студента для переназначения
            old_assignment = self.assignments[getcourse_id]
            
            # Создаем новое назначение
            self.assignments[getcourse_id] = ManagerAssignment(
                student_getcourse_id=getcourse_id,
                manager_id=next_manager['telegram_id'] if next_manager else 0,
                manager_name=next_manager['name'] if next_manager else 'Unknown',
                course_tag=old_assignment.course_tag,  # Сохраняем тот же курс
                timestamp=get_moscow_now(),
                status="pending",
                student_name=old_assignment.student_name,
                student_telegram=old_assignment.student_telegram,
                student_telegram_id=old_assignment.student_telegram_id
            )
            
            logger.info(f"Студент {getcourse_id} переназначен на {next_manager['name'] if next_manager else 'Unknown'}")
            # Сохраняем обновлённое назначение в персистенцию
            self._save_assignment(getcourse_id, self.assignments[getcourse_id])
            return next_manager
    
    def _format_student_notification(self, student_data: Dict[str, Any], manager: Dict[str, Any]) -> str:
        """
        Форматирует уведомление о новом студенте.
        """
        name = student_data.get('name', 'Не указано')
        course_tag = student_data.get('course', 'Не указан')
        telegram = student_data.get('telegram_username', 'Не указан')
        telegram_id = student_data.get('telegram_id')
        getcourse_id = student_data.get('getcourse_id', 'unknown')
        
        if telegram and telegram != 'Не указан' and not telegram.startswith('@'):
            telegram = f"@{telegram}"
        
        course_display = CourseConfig.get_tracker_course_name(course_tag)
        telegram_id_display = str(telegram_id) if telegram_id else 'Не найден'
        manager_mention = f"[{manager['name']}](tg://user?id={manager['telegram_id']})"
        
        # Строим очередь после текущего
        # current_idx уже указывает на СЛЕДУЮЩЕГО после назначенного (индекс сдвинут в get_next_manager)
        is_luxury = self._is_luxury_student(course_tag)
        queue_list = self.luxury_managers if is_luxury else self.vip_managers
        current_idx = self.current_luxury_index if is_luxury else self.current_vip_index
        # Показываем следующих 3, начиная с current_idx (он уже указывает на следующего)
        next_names = []
        for i in range(0, 3):
            idx = (current_idx + i) % len(queue_list) if queue_list else None
            if idx is not None and queue_list[idx]['name'] != manager['name']:
                parts = queue_list[idx]['name'].split()
                # Буква фамилии только для имён с дублями (Катя, Оля)
                NAMES_WITH_DUPLICATES = {'Катя', 'Оля'}
                if parts[0] in NAMES_WITH_DUPLICATES and len(parts) > 1:
                    short = parts[0] + ' ' + parts[1][0] + '.'
                else:
                    short = parts[0]
                next_names.append(short)  # Имя (+ буква фамилии только для Катя/Оля)
        next_line = " → ".join(next_names) if next_names else "—"
        
        message = f"""🎓 **НОВЫЙ VIP-СТУДЕНТ**

👤 **Студент:** {name}
🎯 **Курс:** {course_display}
💬 **Telegram:** {telegram}
🆔 **Telegram ID:** {telegram_id_display}

👩‍💼 **Назначена:** {manager_mention}
📋 **Следующие:** {next_line}
"""
        return message

    async def post_student_notification(self, student_data: Dict[str, Any]) -> bool:
        """
        Отправляет уведомление о новом студенте в VIP-отдел чат.
        Thread-safe операция.
        
        Args:
            student_data: Данные о студенте (name, getcourse_id, email, phone, course, telegram_username, etc.)
            
        Returns:
            True если уведомление отправлено успешно
        """
        try:
            # Получаем следующего менеджера в зависимости от типа курса
            course_tag = student_data.get('course', '')
            manager = self.get_next_manager(course_tag)
            
            if not manager:
                logger.error("Не удалось получить менеджера из очереди")
                return False
            
            # Создаем назначение (thread-safe)
            getcourse_id = student_data.get('getcourse_id', 'unknown')
            course_tag = student_data.get('course', '')
            
            with self._assignments_lock:
                self.assignments[getcourse_id] = ManagerAssignment(
                    student_getcourse_id=getcourse_id,
                    manager_id=manager['telegram_id'],
                    manager_name=manager['name'],
                    course_tag=course_tag,
                    timestamp=get_moscow_now(),
                    status="pending",
                    student_name=student_data.get('name', 'Unknown'),
                    student_telegram=student_data.get('telegram_username', ''),
                    student_telegram_id=student_data.get('telegram_id')
                )
                # Сохраняем в персистенцию
                self._save_assignment(getcourse_id, self.assignments[getcourse_id])
            
            # Формируем сообщение с информацией о студенте
            message = self._format_student_notification(student_data, manager)
            
            # Создаем inline-кнопки
            buttons = [
                [
                    Button.inline("✅ Принять", data=f"accept_{getcourse_id}"),
                    Button.inline("⏭ Пропустить", data=f"skip_{getcourse_id}"),
                    Button.inline("❌ Не заводим", data=f"reject_{getcourse_id}")
                ]
            ]
            
            # Отправляем в чат VIP-отдела с кнопками
            await self.client.send_message(
                VIP_DEPARTMENT_CHAT_ID,
                message,
                buttons=buttons
            )
            
            # Личное уведомление назначенному менеджеру
            try:
                student_name = student_data.get('name', 'Неизвестно')
                course_display = CourseConfig.get_tracker_course_name(course_tag)
                dm_text = (
                    f"🔔 **Тебе новый студент!**\n\n"
                    f"👤 {student_name}\n"
                    f"🎯 {course_display}\n\n"
                    f"Найди уведомление в чате отдела и нажми **Принять**."
                )
                dm_msg = await self.client.send_message(manager['telegram_id'], dm_text)
                # Сохраняем ID DM для возможного удаления при skip
                with self._assignments_lock:
                    if getcourse_id in self.assignments:
                        self.assignments[getcourse_id].dm_message_id = dm_msg.id
                logger.info(f"📩 Личное уведомление отправлено менеджеру {manager['name']}")
            except Exception as dm_err:
                logger.warning(f"⚠️ Не удалось отправить DM менеджеру {manager['name']}: {dm_err}")
            
            logger.info(f"Уведомление о студенте {student_data.get('name')} отправлено в чат {VIP_DEPARTMENT_CHAT_ID}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о студенте: {e}", exc_info=True)
            return False
    
    async def handle_accept_command(self, getcourse_id: str, manager_id: int) -> bool:
        """
        Обрабатывает команду /принять от менеджера.
        
        Args:
            getcourse_id: ID студента в GetCourse
            manager_id: Telegram ID менеджера
            
        Returns:
            True если команда обработана успешно
        """
        if getcourse_id not in self.assignments:
            logger.warning(f"Нет активного назначения для студента {getcourse_id}")
            return False
        
        assignment = self.assignments[getcourse_id]
        
        # Проверяем права менеджера:
        # 1. Назначенный менеджер
        # 2. Руководитель VIP-отдела (Ксюша Уланова)
        # 3. Дежурные аккаунты
        is_assigned = assignment.manager_id == manager_id
        is_head = manager_id in HEAD_IDS
        is_on_duty = manager_id in [acc['telegram_id'] for acc in ON_DUTY_ACCOUNTS]
        
        if not (is_assigned or is_head or is_on_duty):
            logger.warning(f"Менеджер {manager_id} пытается принять студента {getcourse_id}, но назначен {assignment.manager_id}")
            return False
        
        # Отмечаем как принятый
        assignment.status = "accepted"
        
        logger.info(f"Менеджер {assignment.manager_name} (ID: {manager_id}) приняла студента {getcourse_id}")
        
        # Вызываем callback если установлен
        if self.on_student_accepted:
            try:
                await self.on_student_accepted(getcourse_id, manager_id)
            except Exception as e:
                logger.error(f"Ошибка при вызове callback on_student_accepted: {e}", exc_info=True)
        
        return True
    
    async def handle_skip_command(self, getcourse_id: str, manager_id: int) -> bool:
        """
        Обрабатывает команду /пропустить от менеджера.
        
        Args:
            getcourse_id: ID студента в GetCourse
            manager_id: Telegram ID менеджера
            
        Returns:
            True если команда обработана успешно
        """
        if getcourse_id not in self.assignments:
            logger.warning(f"Нет активного назначения для студента {getcourse_id}")
            return False
        
        assignment = self.assignments[getcourse_id]
        
        # Проверяем права менеджера:
        # 1. Назначенный менеджер
        # 2. Руководитель VIP-отдела (Ксюша Уланова)
        # 3. Дежурные аккаунты
        is_assigned = assignment.manager_id == manager_id
        is_head = manager_id in HEAD_IDS
        is_on_duty = manager_id in [acc['telegram_id'] for acc in ON_DUTY_ACCOUNTS]
        
        if not (is_assigned or is_head or is_on_duty):
            logger.warning(f"Менеджер {manager_id} пытается пропустить студента {getcourse_id}, но назначен {assignment.manager_id}")
            return False
        
        # Получаем следующего менеджера
        next_manager = self.skip_to_next_manager(getcourse_id, assignment.course_tag)
        
        if not next_manager:
            logger.error(f"Не удалось получить следующего менеджера для студента {getcourse_id}")
            return False
        
        # Отправляем уведомление о переназначении
        try:
            # Формируем упоминание нового менеджера
            next_manager_mention = f"[{next_manager['name']}](tg://user?id={next_manager['telegram_id']})"
            
            message = f"""♻️ **СТУДЕНТ ПЕРАССТАНОВЛЕН**

📋 **GetCourse ID:** {getcourse_id}
👩‍💼 **Пропустила:** {assignment.manager_name}
👩‍💼 **Следующая в очереди:** {next_manager_mention}

Для принятия студента: `/принять_{getcourse_id}`
Для пропуска: `/пропустить_{getcourse_id}`
"""
            await self.client.send_message(VIP_DEPARTMENT_CHAT_ID, message)
            
            logger.info(f"Менеджер {assignment.manager_name} пропустила студента {getcourse_id}, переназначен на {next_manager['name']}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о переназначении: {e}", exc_info=True)
            return False
    
    def get_assignment(self, getcourse_id: str) -> Optional[ManagerAssignment]:
        """
        Получает информацию о назначении менеджера для студента.
        
        Args:
            getcourse_id: ID студента в GetCourse
            
        Returns:
            ManagerAssignment или None
        """
        return self.assignments.get(getcourse_id)
    
    def set_student_accepted_callback(self, callback: Callable):
        """
        Устанавливает callback функцию, которая вызывается когда менеджер принимает студента.
        
        Args:
            callback: Async функция с параметрами (getcourse_id: str, manager_id: int)
        """
        self.on_student_accepted = callback
        logger.info("Установлен callback для события принятия студента")
    
    def setup_callback_handler(self, client: TelegramClient):
        """
        Настраивает обработчик callback-запросов для inline-кнопок.
        
        Args:
            client: TelegramClient для регистрации обработчиков
        """
        @client.on(events.CallbackQuery())
        async def handle_callback_query(event):
            """Обработчик inline-кнопок"""
            try:
                data = event.data.decode('utf-8')
                
                # Проверяем, что это кнопка для управления студентами
                if not (data.startswith('accept_') or data.startswith('skip_') or data.startswith('reject_') or 
                        data.startswith('confirm_accept_') or data.startswith('confirm_reject_') or data.startswith('cancel_action_')):
                    return
                
                # Обработка подтверждений
                if data.startswith('confirm_accept_'):
                    action = 'accept'
                    getcourse_id = data[15:]  # Убираем 'confirm_accept_'
                elif data.startswith('confirm_reject_'):
                    action = 'reject'
                    getcourse_id = data[15:]  # Убираем 'confirm_reject_'
                elif data.startswith('cancel_action_'):
                    # Отмена действия - возвращаем исходные кнопки
                    getcourse_id = data[13:]  # Убираем 'cancel_action_'
                    if getcourse_id in self.assignments:
                        assignment = self.assignments[getcourse_id]
                        manager = None
                        # Находим менеджера по ID
                        for m in self.vip_managers + self.luxury_managers:
                            if m['telegram_id'] == assignment.manager_id:
                                manager = m
                                break
                        
                        if manager:
                            # Восстанавливаем исходное сообщение
                            original_message = self._format_student_notification(
                                {"name": "Unknown", "course": assignment.course_tag, "telegram_username": "", "telegram_id": None, "getcourse_id": getcourse_id},
                                manager
                            )
                            
                            # Создаем исходные кнопки
                            buttons = [
                                [
                                    Button.inline("✅ Принять", data=f"accept_{getcourse_id}"),
                                    Button.inline("⏭ Пропустить", data=f"skip_{getcourse_id}"),
                                    Button.inline("❌ Не заводим", data=f"reject_{getcourse_id}")
                                ]
                            ]
                            
                            await event.edit(original_message, buttons=buttons)
                            await event.answer("↩️ Действие отменено", alert=True)
                    return
                
                # Получаем getcourse_id и тип действия
                elif data.startswith('accept_'):
                    action = 'accept'
                    getcourse_id = data[7:]  # Убираем 'accept_'
                elif data.startswith('skip_'):
                    action = 'skip'
                    getcourse_id = data[5:]  # Убираем 'skip_'
                else:  # reject
                    action = 'reject'
                    getcourse_id = data[7:]  # Убираем 'reject_'
                
                # Получаем ID менеджера
                manager_id = event.sender_id
                
                # Проверяем права доступа
                if getcourse_id not in self.assignments:
                    await event.answer("❌ Нет активного назначения для этого студента", alert=True)
                    return
                
                assignment = self.assignments[getcourse_id]
                
                # Проверяем права менеджера:
                # 1. Назначенный менеджер
                # 2. Руководитель VIP-отдела (Ксюша Уланова)
                # 3. Дежурные аккаунты
                is_assigned = assignment.manager_id == manager_id
                is_head = manager_id in HEAD_IDS
                is_on_duty = manager_id in [acc['telegram_id'] for acc in ON_DUTY_ACCOUNTS]
                
                # Добавляем возможность для всех менеджеров взаимодействовать с кнопками
                # (но с предупреждением, если это не их студент)
                is_authorized_manager = manager_id in ALL_MANAGER_IDS
                
                if not (is_assigned or is_head or is_on_duty or is_authorized_manager):
                    await event.answer("❌ У вас нет прав для выполнения этого действия", alert=True)
                    return
                
                # Если пользователь является менеджером, но не назначенным, показываем предупреждение
                # Только для кнопок accept и reject, skip разрешен для всех
                if is_authorized_manager and not (is_assigned or is_head or is_on_duty) and action in ['accept', 'reject']:
                    # Для кнопки "Принять" требуем подтверждение
                    if action == 'accept':
                        confirmation_message = f"""⚠️ **ПОДТВЕРЖДЕНИЕ ПРИНЯТИЯ**

Вы пытаетесь принять студента, назначенного менеджеру {assignment.manager_name}.

Если вы уверены, что хотите принять этого студента, нажмите кнопку еще раз."""
                        
                        # Создаем кнопку подтверждения
                        confirm_buttons = [
                            [
                                Button.inline("✅ Подтвердить принятие", data=f"confirm_accept_{getcourse_id}"),
                                Button.inline("❌ Отмена", data=f"cancel_action_{getcourse_id}")
                            ]
                        ]
                        
                        await event.edit(event.message.text + "\n\n" + confirmation_message, buttons=confirm_buttons)
                        await event.answer("⚠️ Требуется подтверждение", alert=True)
                        return
                    elif action == 'reject':
                        # Для кнопки "Отклонить" требуем подтверждение
                        confirmation_message = f"""⚠️ **ПОДТВЕРЖДЕНИЕ ОТКЛОНЕНИЯ**

Вы пытаетесь отклонить студента, назначенного менеджеру {assignment.manager_name}.

Если вы уверены, что хотите отклонить этого студента, нажмите кнопку еще раз."""
                        
                        # Создаем кнопку подтверждения
                        confirm_buttons = [
                            [
                                Button.inline("❌ Подтвердить отклонение", data=f"confirm_reject_{getcourse_id}"),
                                Button.inline("↩️ Отмена", data=f"cancel_action_{getcourse_id}")
                            ]
                        ]
                        
                        await event.edit(event.message.text + "\n\n" + confirmation_message, buttons=confirm_buttons)
                        await event.answer("⚠️ Требуется подтверждение", alert=True)
                        return
                # Для кнопки "Пропустить" разрешаем действие всем менеджерам без подтверждения
                elif is_authorized_manager and not (is_assigned or is_head or is_on_duty) and action == 'skip':
                    pass  # Разрешаем пропустить без подтверждения
                
                # Обрабатываем действие
                if action == 'accept':
                    # Защита от старых кнопок: если уведомление было для другого менеджера,
                    # а assignment уже переключился (через skip) — блокируем
                    try:
                        msg_text = event.message.text or event.message.message or ''
                        current_manager_name = assignment.manager_name
                        if current_manager_name and current_manager_name not in msg_text:
                            await event.answer(
                                f"⚠️ Это устаревшая кнопка. Студент уже переназначен менеджеру {current_manager_name}.",
                                alert=True
                            )
                            await event.edit(buttons=None)
                            return
                    except Exception:
                        pass  # Если не удалось прочитать текст — не блокируем
                    
                    # Отмечаем как принятый
                    assignment.status = "accepted"
                    
                    # Убираем кнопки, оставляя сообщение
                    await event.edit(buttons=None)
                    
                    # Отправляем уведомление
                    await event.answer("✅ Студент принят! Начинаю онбординг...", alert=True)
                    
                    # Удаляем назначение из персистенции (завершено)
                    self._delete_assignment(getcourse_id)
                    
                    # Вызываем callback если установлен
                    # ВАЖНО: передаём НАЗНАЧЕННОГО менеджера из очереди, а не того, кто нажал кнопку
                    if self.on_student_accepted:
                        try:
                            await self.on_student_accepted(getcourse_id, assignment.manager_id)
                        except Exception as e:
                            logger.error(f"Ошибка при вызове callback on_student_accepted: {e}", exc_info=True)
                    
                elif action == 'skip':
                    # Защита: если студент уже принят — игнорируем нажатие старой кнопки
                    if assignment.status == "accepted" or getcourse_id not in self.assignments:
                        await event.answer("✅ Студент уже принят другим менеджером", alert=True)
                        await event.edit(buttons=None)
                        return
                    
                    # Получаем следующего менеджера
                    next_manager = self.skip_to_next_manager(getcourse_id, assignment.course_tag)
                    
                    if not next_manager:
                        await event.answer("❌ Не удалось получить следующего менеджера", alert=True)
                        return
                    
                    # Формируем упоминание нового менеджера
                    next_manager_mention = f"[{next_manager['name']}](tg://user?id={next_manager['telegram_id']})"
                    
                    # Обновляем сообщение БЕЗ кнопок
                    message = f"""♻️ **СТУДЕНТ ПЕРЕНАЗНАЧЕН**

📋 **GetCourse ID:** {getcourse_id}
👩‍💼 **Пропустила:** {assignment.manager_name}
👩‍💼 **Следующая в очереди:** {next_manager_mention}

✅ Новый менеджер получит отдельное уведомление с кнопками.
"""
                    
                    await event.edit(message, buttons=None)
                    await event.answer("⏭ Студент пропущен, назначен следующему менеджеру", alert=True)
                    
                    # Отправляем НОВОЕ уведомление следующему менеджеру с кнопками
                    try:
                        # Удаляем DM у пропустившего менеджера
                        if assignment.dm_message_id:
                            try:
                                await self.client.delete_messages(assignment.manager_id, [assignment.dm_message_id])
                                logger.info(f"🗑 DM удалён у менеджера {assignment.manager_name}")
                            except Exception:
                                pass
                        
                        # Получаем данные студента из обновленного assignment
                        updated_assignment = self.assignments[getcourse_id]
                        student_data = {
                            'name': updated_assignment.student_name,
                            'getcourse_id': getcourse_id,
                            'course': updated_assignment.course_tag,
                            'telegram_username': updated_assignment.student_telegram,
                            'telegram_id': updated_assignment.student_telegram_id
                        }
                        
                        notification_message = self._format_student_notification(student_data, next_manager)
                        
                        buttons = [
                            [
                                Button.inline("✅ Принять", data=f"accept_{getcourse_id}"),
                                Button.inline("⏭ Пропустить", data=f"skip_{getcourse_id}"),
                                Button.inline("❌ Не заводим", data=f"reject_{getcourse_id}")
                            ]
                        ]
                        
                        await self.client.send_message(
                            VIP_DEPARTMENT_CHAT_ID,
                            notification_message,
                            buttons=buttons
                        )
                        
                        logger.info(f"Отправлено новое уведомление для {next_manager['name']} о студенте {getcourse_id}")
                        
                        # DM новому менеджеру после skip
                        try:
                            course_display = CourseConfig.get_tracker_course_name(updated_assignment.course_tag)
                            dm_text = (
                                f"🔔 **Тебе назначен студент!**\n\n"
                                f"👤 {updated_assignment.student_name}\n"
                                f"🎯 {course_display}\n\n"
                                f"Предыдущий менеджер пропустил. Найди уведомление в чате отдела и нажми **Принять**."
                            )
                            new_dm = await self.client.send_message(next_manager['telegram_id'], dm_text)
                            # Сохраняем ID нового DM
                            if getcourse_id in self.assignments:
                                self.assignments[getcourse_id].dm_message_id = new_dm.id
                            logger.info(f"📩 DM при skip отправлен менеджеру {next_manager['name']}")
                        except Exception as dm_err:
                            logger.warning(f"⚠️ Не удалось отправить DM при skip: {dm_err}")
                        
                    except Exception as notify_error:
                        logger.error(f"Ошибка при отправке уведомления новому менеджеру: {notify_error}", exc_info=True)
                    
                elif action == 'reject':
                    # Отмечаем как отклоненный
                    assignment.status = "rejected"
                    
                    # Удаляем назначение из персистенции (завершено)
                    self._delete_assignment(getcourse_id)
                    
                    # Убираем кнопки, оставляя сообщение
                    rejection_message = f"""❌ **СТУДЕНТ ОТКЛОНЕН**

📋 **GetCourse ID:** {getcourse_id}
👩‍💼 **Отклонил:** {assignment.manager_name}

Этот студент не будет обработан системой.
"""
                    await event.edit(rejection_message, buttons=None)
                    await event.answer("❌ Студент отклонен и не будет обработан", alert=True)
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке inline-кнопки: {e}", exc_info=True)
                # Отправляем сообщение об ошибке пользователю
                try:
                    await event.answer("❌ Произошла ошибка при обработке запроса. Проверьте логи.", alert=True)
                except:
                    pass  # Игнорируем ошибки при отправке уведомления об ошибке
