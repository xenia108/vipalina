"""
Модуль автоматического онбординга VIP-студентов.
Создает учебный чат, отправляет приветственное сообщение, добавляет участников.
"""

import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.functions.messages import CreateChatRequest, EditChatAdminRequest, ExportChatInviteRequest
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import ChatAdminRights, InputPhoneContact
from telethon.errors import (
    UserPrivacyRestrictedError, 
    UserNotMutualContactError,
    FloodWaitError,
    ChatWriteForbiddenError,
    PeerFloodError
)

from config import VIP_ZEROCODER_BOT_USERNAME, ULTRALINA_BOT_USERNAME, VIP_MANAGERS_VIP, VIP_DEPARTMENT_CHAT_ID, ON_DUTY_ACCOUNTS, VIP_HEAD

# Импортируем модуль конфигурации курсов
from course_config_v2 import CourseConfig

# Импортируем модуль уведомлений
from onboarding_notifications import OnboardingNotifications

# Импортируем утилиты для работы с API
from api_utils import retry_async, TelegramAPIError

# Импортируем кеш entities для оптимизации
from entity_cache import EntityCache

logger = logging.getLogger('vipalina_telethon')


class StudentDataValidationError(Exception):
    """Исключение для ошибок валидации данных студента"""
    pass


def validate_student_data(student_data: Dict[str, Any]) -> None:
    """
    Валидирует данные студента перед онбордингом.
    
    Проверяет обязательные поля:
    - getcourse_id: ID студента в GetCourse (непустая строка)
    - telegram_id: Telegram ID студента (целое число)
    - course: Тег курса (непустая строка)
    - name: Имя студента (непустая строка, минимум 2 символа)
    
    Args:
        student_data: Словарь с данными студента
        
    Raises:
        StudentDataValidationError: Если данные невалидны
    """
    errors = []
    
    # 1. Проверка getcourse_id
    getcourse_id = student_data.get('getcourse_id')
    if not getcourse_id:
        errors.append("Отсутствует обязательное поле 'getcourse_id'")
    elif not isinstance(getcourse_id, str) or not getcourse_id.strip():
        errors.append("Поле 'getcourse_id' должно быть непустой строкой")
    elif not re.match(r'^[0-9]+$', getcourse_id.strip()):
        errors.append(f"Поле 'getcourse_id' должно содержать только цифры, получено: '{getcourse_id}'")
    
    # 2. Проверка telegram_id (ОБЯЗАТЕЛЬНОЕ)
    telegram_id = student_data.get('telegram_id')
    
    if not telegram_id:
        errors.append("Отсутствует обязательное поле 'telegram_id'")
    elif not isinstance(telegram_id, int):
        # Пытаемся конвертировать строку в число
        if isinstance(telegram_id, str) and telegram_id.isdigit():
            student_data['telegram_id'] = int(telegram_id)
            logger.info(f"telegram_id сконвертирован из строки в int: {telegram_id}")
        else:
            errors.append(f"Поле 'telegram_id' должно быть целым числом, получено: {type(telegram_id).__name__}")
    elif telegram_id <= 0:
        errors.append(f"Поле 'telegram_id' должно быть положительным числом, получено: {telegram_id}")
    
    # 3. Проверка course
    course = student_data.get('course')
    if not course:
        errors.append("Отсутствует обязательное поле 'course'")
    elif not isinstance(course, str) or not course.strip():
        errors.append("Поле 'course' должно быть непустой строкой")
    elif len(course.strip()) < 3:
        errors.append(f"Поле 'course' слишком короткое (минимум 3 символа), получено: '{course}'")
    
    # 4. Проверка name
    name = student_data.get('name')
    if not name:
        errors.append("Отсутствует обязательное поле 'name'")
    elif not isinstance(name, str) or not name.strip():
        errors.append("Поле 'name' должно быть непустой строкой")
    elif len(name.strip()) < 2:
        errors.append(f"Поле 'name' слишком короткое (минимум 2 символа), получено: '{name}'")
    
    # Если есть ошибки, выбрасываем исключение
    if errors:
        error_message = "Ошибки валидации данных студента:\n" + "\n".join(f"  - {err}" for err in errors)
        logger.error(error_message)
        logger.error(f"Полученные данные студента: {student_data}")
        raise StudentDataValidationError(error_message)
    
    logger.info(f"Валидация данных студента успешна: getcourse_id={getcourse_id}, telegram_id={telegram_id}, course={course}, name={name}")


class ContactManager:
    """
    Менеджер для добавления/удаления студентов в контакты Telethon-аккаунта.
    Это позволяет обходить ограничения Telegram Privacy Settings.
    """
    
    def __init__(self, client: TelegramClient):
        self.client = client
        logger.info("✅ ContactManager инициализирован")
    
    async def add_student_to_contacts(
        self, 
        phone: str, 
        first_name: str, 
        last_name: str = ""
    ) -> Optional[int]:
        """
        Добавляет студента в контакты Telethon-аккаунта.
        После этого можно отправлять ЛС и добавлять в группы.
        
        Args:
            phone: Номер телефона в формате +79991234567
            first_name: Имя студента
            last_name: Фамилия студента (опционально)
        
        Returns:
            user_id студента если успешно, None если ошибка
        """
        try:
            # Создаем контакт
            contact = InputPhoneContact(
                client_id=0,  # Уникальный ID для этого запроса
                phone=phone,
                first_name=first_name,
                last_name=last_name or ""
            )
            
            logger.info(f"📞 Добавление студента в контакты: {first_name} {last_name} ({phone})")
            
            # Импортируем контакт
            result = await self.client(ImportContactsRequest([contact]))
            
            if result.users:
                user = result.users[0]
                logger.info(f"✅ Студент добавлен в контакты: {first_name} {last_name}")
                logger.info(f"   User ID: {user.id}")
                logger.info(f"   Username: @{user.username or 'нет'}")
                logger.info(f"   Phone: {phone}")
                logger.info(f"   Contact: {user.contact}")
                logger.info(f"   Mutual Contact: {user.mutual_contact}")
                
                return user.id
            else:
                logger.warning(f"⚠️ Контакт не найден в Telegram: {phone}")
                logger.warning(f"   Возможные причины:")
                logger.warning(f"   - Номер телефона не зарегистрирован в Telegram")
                logger.warning(f"   - Неверный формат номера")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления в контакты: {e}", exc_info=True)
            return None
    
    async def remove_student_from_contacts(self, user_id: int) -> bool:
        """
        Удаляет студента из контактов после завершения онбординга.
        Это очищает список контактов и скрывает факт добавления.
        
        Args:
            user_id: ID пользователя
        
        Returns:
            True если успешно удален, False если ошибка
        """
        try:
            # Получаем entity пользователя
            user_entity = await self.client.get_entity(user_id)
            
            # Удаляем из контактов
            await self.client(DeleteContactsRequest([user_entity]))
            
            logger.info(f"🧹 Студент удален из контактов: User ID {user_id}")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка удаления из контактов (User ID {user_id}): {e}")
            return False


class StudentOnboardingModule:
    """
    Модуль для автоматизированного онбординга VIP-студентов.
    Создает учебный чат, добавляет участников, назначает администраторов.
    """
    
    def __init__(self, client: TelegramClient, system_monitor=None, state_manager=None, bot_client=None):
        self.client = client
        self.bot_client = bot_client
        self.notifications = OnboardingNotifications(client)
        # Инициализируем кеш entities для оптимизации
        self.entity_cache = EntityCache(client)
        
        # Инициализируем Contact Manager для добавления в контакты
        self.contact_manager = ContactManager(client)
        
        # Интеграция с мониторингом и state management
        self.system_monitor = system_monitor
        self.state_manager = state_manager
        
        # Получаем rollback_manager и conflict_resolver из system_monitor
        self.rollback_manager = system_monitor.rollback_manager if system_monitor else None
        self.conflict_resolver = system_monitor.conflict_resolver if system_monitor else None
        
        # Хранилище ожидающих коррекций: message_id -> (student_data, manager_id, manager_name)
        self.pending_corrections = {}
        
        # Персистентное хранилище
        from vipalina_persistence import get_persistence
        self.persistence = get_persistence()
        
        # Загружаем ожидающие коррекции из БД
        if self.persistence and self.persistence.is_initialized():
            self.pending_corrections = self.persistence.get_all_pending_corrections()
            logger.info(f"Загружено {len(self.pending_corrections)} ожидающих коррекций")
        
        logger.info("Инициализирован модуль онбординга студентов")
        if system_monitor:
            logger.info("✅ Интеграция с System Monitor и State Manager активна")
    
    async def onboard_student(
        self,
        student_data: Dict[str, Any],
        manager_id: int,
        manager_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Выполняет полный процесс онбординга студента с rollback и conflict resolution.
        
        Args:
            student_data: Данные о студенте (name, telegram_id, phone, email, course, getcourse_id, etc.)
            manager_id: Telegram ID менеджера
            manager_name: Имя менеджера
            
        Returns:
            Dict с результатами онбординга (chat_id, welcome_message_sent, etc.) или None при ошибке
            
        Raises:
            StudentDataValidationError: Если данные студента невалидны
        """
        student_id = student_data.get('getcourse_id', student_data.get('telegram_id', 'unknown'))
        
        # Используем ConflictResolver для предотвращения одновременных операций
        if self.conflict_resolver:
            return await self.conflict_resolver.execute_with_lock(
                student_id,
                self._onboard_student_with_rollback,
                student_data,
                manager_id,
                manager_name
            )
        else:
            # Если ConflictResolver нет, выполняем напрямую
            return await self._onboard_student_with_rollback(
                student_data,
                manager_id,
                manager_name
            )
    
    async def _onboard_student_with_rollback(
        self,
        student_data: Dict[str, Any],
        manager_id: int,
        manager_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Внутренний метод онбординга с поддержкой rollback.
        """
        transaction_id = f"onboard_{student_data.get('getcourse_id', 'unknown')}_{datetime.now().timestamp()}"
        
        # Регистрируем операцию в System Monitor
        if self.system_monitor:
            await self.system_monitor.record_operation_start(transaction_id)
        
        # Сохраняем операцию в State Manager
        if self.state_manager:
            await self.state_manager.save_operation(
                operation_id=transaction_id,
                operation_type="onboarding",
                data=student_data,
                status="in_progress"
            )
        
        # Начинаем транзакцию для rollback
        if self.rollback_manager:
            await self.rollback_manager.start_transaction(transaction_id)
        
        try:
            # ВАЛИДАЦИЯ ДАННЫХ СТУДЕНТА
            try:
                validate_student_data(student_data)
            except StudentDataValidationError as ve:
                logger.error(f"Ошибка валидации данных студента: {ve}")
                
                # Запрашиваем у менеджера недостающие данные
                corrected_data = await self._request_data_correction(
                    student_data=student_data,
                    validation_error=ve,
                    manager_id=manager_id,
                    manager_name=manager_name
                )
                
                if corrected_data:
                    # Данные исправлены, продолжаем онбординг с исправленными данными
                    student_data = corrected_data
                    logger.info(f"Данные студента исправлены менеджером: {student_data.get('name')}")
                else:
                    # Менеджер не предоставил данные или произошла ошибка
                    if self.state_manager:
                        await self.state_manager.update_operation_status(
                            transaction_id, "failed", error="Validation failed, no correction provided"
                        )
                    if self.system_monitor:
                        await self.system_monitor.record_operation_failure(transaction_id, ve)
                    return None
            
            student_name = student_data.get('name', 'Студент')
            student_telegram_id = student_data.get('telegram_id')
            student_telegram_username = student_data.get('telegram_username')
            student_phone = student_data.get('phone')
            course_tag = student_data.get('course', '')
            
            logger.info(f"Начат онбординг студента: {student_name} (getcourse_id: {student_data.get('getcourse_id')})")
            # Уведомления отправляются через OnboardingTracker в vip_automation_main.py
            
            # ШАГ 1: Создаем учебный чат
            chat_info = await self._create_study_chat(
                student_name=student_name,
                student_telegram_id=student_telegram_id,
                student_telegram_username=student_telegram_username,
                student_phone=student_phone,
                manager_id=manager_id,
                manager_name=manager_name,
                course_tag=course_tag
            )
            
            if not chat_info:
                logger.error(f"Не удалось создать чат для студента {student_name}")
                raise Exception("Не удалось создать чат")
            
            chat_id = chat_info['chat_id']
            
            # Регистрируем rollback: удаление чата
            if self.rollback_manager:
                await self.rollback_manager.add_rollback_step(
                    transaction_id,
                    self._delete_chat,
                    chat_id=chat_id
                )
            
            # Уведомление об успешном создании чата отправляется через OnboardingTracker
            
            # ШАГ 2: Отправляем приветственное сообщение
            welcome_sent = await self._send_welcome_message(
                chat_id=chat_id,
                student_name=student_name,
                student_telegram_username=student_telegram_username,
                manager_name=manager_name,
                manager_id=manager_id,
                course=course_tag
            )

            # 🚪 Userbot покидает чат ТОЛЬКО если владение успешно передано
            # Иначе через 7 дней Telegram назначит владельцем следующего админа (студента!)
            ownership_transferred = chat_info.get('ownership_transferred', False)
            if not ownership_transferred:
                logger.warning(f"⛔ НЕ покидаем чат {chat_id} — владение не передано (FloodWait/ошибка). Userbot остаётся владельцем.")
            else:
                try:
                    from telethon.tl.functions.channels import LeaveChannelRequest
                    import asyncio as _asyncio
                    
                    # Запоминаем ID последнего сообщения для удаления "покинул" позже
                    last_msg = (await self.client.get_messages(chat_id, limit=1))[0]
                    last_msg_id = last_msg.id if last_msg else 0
                    
                    await self.client(LeaveChannelRequest(channel=chat_id))
                    logger.info(f"🚪 Userbot покинул чат {chat_id} (слот освобожден)")
                    
                    # Удаляем системное сообщение "покинул группу" через bot_client
                    if last_msg_id and hasattr(self, 'bot_client') and self.bot_client:
                        try:
                            await _asyncio.sleep(1)
                            leave_msg_id = last_msg_id + 1
                            await self.bot_client.delete_messages(chat_id, [leave_msg_id])
                            logger.info(f"🗑 Удалено системное сообщение о выходе из чата {chat_id}")
                        except Exception as del_e:
                            logger.warning(f"⚠️ Не удалось удалить сообщение о выходе: {del_e}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось покинуть чат {chat_id}: {e}")
            
            result = {
                'chat_id': chat_info['chat_id'],
                'chat_title': chat_info['chat_title'],
                'invite_link': chat_info.get('invite_link'),
                'welcome_message_sent': welcome_sent,
                'manager_id': manager_id,
                'manager_name': manager_name,
                'timestamp': datetime.now()
            }
            
            # ВСЕ УСПЕШНО - фиксируем транзакцию
            if self.rollback_manager:
                await self.rollback_manager.commit_transaction(transaction_id)
            
            if self.state_manager:
                await self.state_manager.update_operation_status(transaction_id, "completed")
            
            if self.system_monitor:
                await self.system_monitor.record_operation_success(transaction_id)
            
            logger.info(f"Онбординг студента {student_name} завершен успешно. Chat ID: {chat_id}")
            # Уведомление о завершении отправляется через OnboardingTracker
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при онбординге студента {student_data.get('name', 'Неизвестный студент')}: {e}", exc_info=True)
            
            # ОТКАТЫВАЕМ ВСЕ ИЗМЕНЕНИЯ
            if self.rollback_manager:
                await self.rollback_manager.rollback_transaction(transaction_id, error=e)
                if self.system_monitor:
                    await self.system_monitor.record_operation_rollback(transaction_id)
            
            if self.state_manager:
                await self.state_manager.update_operation_status(
                    transaction_id, "failed", error=str(e)
                )
            
            if self.system_monitor:
                await self.system_monitor.record_operation_failure(transaction_id, e)
            
            # Уведомление об ошибке отправляется через OnboardingTracker
            return None
    
    async def _delete_chat(self, chat_id: int):
        """
        Удаляет чат (для rollback).
        """
        try:
            from telethon.tl.functions.messages import DeleteChatRequest
            await self.client(DeleteChatRequest(chat_id=chat_id))
            logger.info(f"Чат {chat_id} удален (откат изменений)")
        except Exception as e:
            logger.error(f"Ошибка при удалении чата {chat_id}: {e}")
    
    async def _delete_channel(self, chat_id: int):
        """
        Удаляет канал/супергруппу (для rollback).
        """
        try:
            from telethon.tl.functions.channels import DeleteChannelRequest
            await self.client(DeleteChannelRequest(channel=chat_id))
            logger.info(f"Супергруппа {chat_id} удалена (откат изменений)")
        except Exception as e:
            logger.error(f"Ошибка при удалении супергруппы {chat_id}: {e}")
    
    async def _request_data_correction(
        self,
        student_data: Dict[str, Any],
        validation_error: StudentDataValidationError,
        manager_id: int,
        manager_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Запрашивает у менеджера исправление недостающих данных.
        Ждет ответ 15 минут, затем переходит в спящий режим.
        Через 48 часов автоматически пропускает студента.
        
        Args:
            student_data: Исходные данные студента
            validation_error: Ошибка валидации
            manager_id: Telegram ID менеджера
            manager_name: Имя менеджера
            
        Returns:
            Исправленные данные или None
        """
        try:
            from telethon import events
            import asyncio
            
            # Формируем сообщение с запросом данных
            request_message = f"""❌ **НЕВАЛИДНЫЕ ДАННЫЕ СТУДЕНТА**

{str(validation_error)}

🔄 **МОЖНО ИСПРАВИТЬ ПРЯМО ЗДЕСЬ!**

Ответьте на это сообщение в формате:
```
gc_id: 309200567
tg_id: 268400185
course: AI Консалтинг [vip]
name: Ксения Уланова
```

💡 **Telegram ID можно указать как:**
• Числовой ID: `268400185`
• Username: `@VOL_D_E_MAR` или `VOL_D_E_MAR`

**Полученные данные:**
gc_id: {student_data.get('getcourse_id') or '❌ Отсутствует'}
tg_id: {student_data.get('telegram_id') or '❌ Отсутствует'}
course: {student_data.get('course') or '❌ Отсутствует'}
name: {student_data.get('name') or '❌ Отсутствует'}

⏱ Жду вашего ответа...
"""
            
            # Отправляем сообщение в VIP-чат
            sent_message = await self.client.send_message(VIP_DEPARTMENT_CHAT_ID, request_message)
            logger.info(f"Отправлен запрос на исправление данных менеджеру {manager_name}")
            
            # Сохраняем в хранилище ожидающих коррекций
            self.pending_corrections[sent_message.id] = {
                'student_data': student_data.copy(),
                'manager_id': manager_id,
                'manager_name': manager_name
            }
            logger.info(f"Сохранён контекст коррекции для message_id={sent_message.id}")
            
            # Сохраняем в персистентное хранилище
            if self.persistence and self.persistence.is_initialized():
                self.persistence.save_pending_correction(
                    message_id=sent_message.id,
                    student_data=student_data.copy(),
                    manager_id=manager_id,
                    manager_name=manager_name
                )
            
            # Создаем Future для ожидания ответа
            response_future = asyncio.Future()
            
            # Обработчик ответов
            @self.client.on(events.NewMessage(chats=VIP_DEPARTMENT_CHAT_ID, from_users=[manager_id]))
            async def handle_correction_response(event):
                # Проверяем, что это ответ на наше сообщение
                if event.message.is_reply and event.message.reply_to_msg_id == sent_message.id:
                    if not response_future.done():
                        response_future.set_result(event.message.text)
            
            try:
                # Ждем ответ 15 минут (900 секунд)
                response_text = await asyncio.wait_for(response_future, timeout=900.0)
                
                # Парсим ответ
                corrected_data = self._parse_correction_response(response_text, student_data)
                
                if corrected_data:
                    # Если указан username вместо ID, пытаемся разрешить его
                    telegram_username = corrected_data.get('telegram_username')
                    telegram_id = corrected_data.get('telegram_id')
                    
                    if telegram_username and not telegram_id:
                        username = telegram_username
                        resolved_id = await self._resolve_username_to_id(username)
                        if resolved_id:
                            corrected_data['telegram_id'] = resolved_id
                            logger.info(f"✅ Username @{username} разрешён в ID: {resolved_id}")
                        else:
                            logger.warning(f"⚠️ Не удалось разрешить username @{username}, продолжаю с username")
                    
                    # Проверяем исправленные данные
                    try:
                        validate_student_data(corrected_data)
                        # Данные валидны!
                        await self.client.send_message(
                            VIP_DEPARTMENT_CHAT_ID,
                            f"✅ **ДАННЫЕ ИСПРАВЛЕНЫ!**\n\nПродолжаю онбординг студента {corrected_data.get('name')}...",
                            reply_to=sent_message.id
                        )
                        logger.info(f"Данные успешно исправлены менеджером: {corrected_data}")
                        return corrected_data
                    except StudentDataValidationError as ve:
                        # Данные все еще невалидны
                        await self.client.send_message(
                            VIP_DEPARTMENT_CHAT_ID,
                            f"❌ **ДАННЫЕ ВСЕ ЕЩЕ НЕВАЛИДНЫ:**\n\n{str(ve)}\n\nОтветьте на это сообщение с правильными данными.",
                            reply_to=sent_message.id
                        )
                        # Продолжаем ждать в спящем режиме
                        return await self._wait_in_sleep_mode(sent_message, student_data, manager_id, handle_correction_response)
                else:
                    await self.client.send_message(
                        VIP_DEPARTMENT_CHAT_ID,
                        "❌ Не удалось распознать формат ответа. Ответьте на это сообщение с данными в правильном формате.",
                        reply_to=sent_message.id
                    )
                    # Продолжаем ждать в спящем режиме
                    return await self._wait_in_sleep_mode(sent_message, student_data, manager_id, handle_correction_response)
                    
            except asyncio.TimeoutError:
                # 15 минут истекло - переход в спящий режим
                logger.info(f"Первый таймаут (15 минут) истек, переход в спящий режим")
                
                await self.client.send_message(
                    VIP_DEPARTMENT_CHAT_ID,
                    f"😴 **УХОЖУ В СПЯЩИЙ РЕЖИМ**\n\nОтветьте на это сообщение с недостающими данными, чтобы я продолжила онбординг студента {student_data.get('name', 'Неизвестный студент')}.\n\n⚠️ Если не ответите в течение 48 часов, студент будет автоматически пропущен.",
                    reply_to=sent_message.id
                )
                
                # Переход в спящий режим с ожиданием 48 часов
                return await self._wait_in_sleep_mode(sent_message, student_data, manager_id, handle_correction_response)
                
        except Exception as e:
            logger.error(f"Ошибка при запросе исправления данных: {e}", exc_info=True)
            return None
    
    async def _wait_in_sleep_mode(
        self,
        original_message,
        student_data: Dict[str, Any],
        manager_id: int,
        existing_handler
    ) -> Optional[Dict[str, Any]]:
        """
        Спящий режим: ожидание ответа до 48 часов.
        После 48 часов студент автоматически пропускается.
        
        Args:
            original_message: Исходное сообщение с запросом
            student_data: Данные студента
            manager_id: ID менеджера
            existing_handler: Существующий обработчик событий
            
        Returns:
            Исправленные данные или None (если студент пропущен)
        """
        try:
            import asyncio
            
            # Создаем новый Future для ожидания ответа
            sleep_future = asyncio.Future()
            
            # Обновляем обработчик для спящего режима
            @self.client.on(events.NewMessage(chats=VIP_DEPARTMENT_CHAT_ID, from_users=[manager_id]))
            async def handle_sleep_response(event):
                if event.message.is_reply and event.message.reply_to_msg_id == original_message.id:
                    if not sleep_future.done():
                        sleep_future.set_result(event.message.text)
            
            try:
                # Ждем ответ 48 часов (172800 секунд)
                response_text = await asyncio.wait_for(sleep_future, timeout=172800.0)
                
                # Парсим ответ
                corrected_data = self._parse_correction_response(response_text, student_data)
                
                if corrected_data:
                    # Если указан username вместо ID, пытаемся разрешить его
                    telegram_username = corrected_data.get('telegram_username')
                    telegram_id = corrected_data.get('telegram_id')
                    
                    if telegram_username and not telegram_id:
                        username = telegram_username
                        resolved_id = await self._resolve_username_to_id(username)
                        if resolved_id:
                            corrected_data['telegram_id'] = resolved_id
                            logger.info(f"✅ Username @{username} разрешён в ID: {resolved_id}")
                        else:
                            logger.warning(f"⚠️ Не удалось разрешить username @{username}, продолжаю с username")
                    
                    try:
                        validate_student_data(corrected_data)
                        # Данные валидны!
                        await self.client.send_message(
                            VIP_DEPARTMENT_CHAT_ID,
                            f"✅ **ДАННЫЕ ИСПРАВЛЕНЫ!**\n\nПродолжаю онбординг студента {corrected_data.get('name')}...",
                            reply_to=original_message.id
                        )
                        logger.info(f"Данные исправлены после спящего режима: {corrected_data}")
                        return corrected_data
                    except StudentDataValidationError as ve:
                        # Данные все еще невалидны
                        await self.client.send_message(
                            VIP_DEPARTMENT_CHAT_ID,
                            f"❌ **ДАННЫЕ ВСЕ ЕЩЕ НЕВАЛИДНЫ:**\n\n{str(ve)}\n\nОтветьте на это сообщение с правильными данными.",
                            reply_to=original_message.id
                        )
                        # Рекурсивно продолжаем ждать
                        return await self._wait_in_sleep_mode(original_message, student_data, manager_id, handle_sleep_response)
                else:
                    await self.client.send_message(
                        VIP_DEPARTMENT_CHAT_ID,
                        "❌ Не удалось распознать формат ответа. Ответьте на это сообщение с данными в правильном формате.",
                        reply_to=original_message.id
                    )
                    return await self._wait_in_sleep_mode(original_message, student_data, manager_id, handle_sleep_response)
                    
            except asyncio.TimeoutError:
                # 48 часов истекло - автоматический пропуск студента
                logger.warning(f"48 часов истекло, студент {student_data.get('name')} автоматически пропущен")
                
                await self.client.send_message(
                    VIP_DEPARTMENT_CHAT_ID,
                    f"⏰ **ВРЕМЯ ОЖИДАНИЯ ИСТЕКЛО (48 ЧАСОВ)**\n\nСтудент **{student_data.get('name', 'Неизвестный студент')}** автоматически пропущен.\n\n❌ Онбординг не выполнен.",
                    reply_to=original_message.id
                )
                
                return None
                
        except Exception as e:
            logger.error(f"Ошибка в спящем режиме: {e}", exc_info=True)
            return None
    
    def _parse_correction_response(self, response_text: str, original_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Парсит ответ менеджера с исправленными данными.
        
        Args:
            response_text: Текст ответа менеджера
            original_data: Исходные данные
            
        Returns:
            Исправленные данные или None
        """
        try:
            # Копируем исходные данные
            corrected_data = original_data.copy()
            
            # Парсим поля
            lines = response_text.strip().split('\n')
            for line in lines:
                line = line.strip()
                # Убираем маркеры списка (•, -, *)
                line = line.lstrip('•').lstrip('-').lstrip('*').strip()
                # Убираем markdown форматирование (**жирный**, __курсив__)
                line = line.replace('**', '').replace('__', '').strip()
                
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    # Поддержка различных вариантов ключей
                    if key in ['gc_id', 'getcourse_id', 'gk_id', 'getcourse id', 'id getcourse']:
                        corrected_data['getcourse_id'] = value
                    elif key in ['tg_id', 'telegram_id', 'telegram id', 'id telegram']:
                        # Поддержка numeric ID, username (@username или username)
                        value_clean = value.strip()
                        if value_clean.isdigit():
                            # Это числовой ID
                            corrected_data['telegram_id'] = int(value_clean)
                            logger.info(f"Распознан telegram_id: {value_clean}")
                        elif value_clean.startswith('@') or (value_clean and not value_clean.isdigit()):
                            # Это username
                            username = value_clean.lstrip('@')
                            corrected_data['telegram_username'] = username
                            # НЕ устанавливаем telegram_id = None, оставляем как есть
                            logger.info(f"Распознан telegram_username: {username}")
                        else:
                            # Неизвестный формат, сохраняем как есть
                            corrected_data['telegram_id'] = value
                    elif key in ['course', 'курс']:
                        corrected_data['course'] = value
                    elif key in ['name', 'имя', 'student_name', 'имя студента']:
                        corrected_data['name'] = value
            
            logger.debug(f"Распознанные данные: {corrected_data}")
            return corrected_data
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге ответа: {e}")
            return None
    
    async def handle_correction_reply(self, reply_to_msg_id: int, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает ответ на запрос коррекции.
        Может быть вызван из глобального обработчика сообщений.
        
        Args:
            reply_to_msg_id: ID сообщения, на которое ответили
            response_text: Текст ответа
            
        Returns:
            Исправленные данные или None
        """
        if reply_to_msg_id not in self.pending_corrections:
            logger.debug(f"Нет ожидающей коррекции для message_id={reply_to_msg_id}")
            return None
        
        try:
            context = self.pending_corrections[reply_to_msg_id]
            student_data = context['student_data']
            manager_id = context['manager_id']
            manager_name = context['manager_name']
            
            logger.info(f"🔍 Найден контекст коррекции для {student_data.get('name')} (message_id={reply_to_msg_id})")
            
            # Парсим ответ
            corrected_data = self._parse_correction_response(response_text, student_data)
            
            if not corrected_data:
                logger.warning("Не удалось распознать формат ответа")
                await self.client.send_message(
                    VIP_DEPARTMENT_CHAT_ID,
                    "❌ Не удалось распознать формат ответа. Ответьте на это сообщение с данными в правильном формате.",
                    reply_to=reply_to_msg_id
                )
                return None
            
            # Если указан username вместо ID, пытаемся разрешить его
            if corrected_data.get('telegram_username') and not corrected_data.get('telegram_id'):
                username = corrected_data['telegram_username']
                resolved_id = await self._resolve_username_to_id(username)
                if resolved_id:
                    corrected_data['telegram_id'] = resolved_id
                    logger.info(f"✅ Username @{username} разрешён в ID: {resolved_id}")
                else:
                    logger.warning(f"⚠️ Не удалось разрешить username @{username}, продолжаю с username")
            
            # Проверяем исправленные данные
            try:
                validate_student_data(corrected_data)
                # Данные валидны!
                await self.client.send_message(
                    VIP_DEPARTMENT_CHAT_ID,
                    f"✅ **ДАННЫЕ ИСПРАВЛЕНЫ!**\n\nПродолжаю онбординг студента {corrected_data.get('name')}...",
                    reply_to=reply_to_msg_id
                )
                logger.info(f"✅ Данные успешно исправлены: {corrected_data}")
                
                # Удаляем из хранилища
                del self.pending_corrections[reply_to_msg_id]
                
                # Удаляем из персистентного хранилища
                if self.persistence and self.persistence.is_initialized():
                    self.persistence.delete_pending_correction(reply_to_msg_id)
                
                return corrected_data
                
            except StudentDataValidationError as ve:
                # Данные все еще невалидны
                await self.client.send_message(
                    VIP_DEPARTMENT_CHAT_ID,
                    f"❌ **ДАННЫЕ ВСЕ ЕЩЕ НЕВАЛИДНЫ:**\n\n{str(ve)}\n\nОтветьте на это сообщение с правильными данными.",
                    reply_to=reply_to_msg_id
                )
                logger.warning(f"Данные все еще невалидны: {ve}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при обработке ответа на коррекцию: {e}", exc_info=True)
            return None
    
    async def _resolve_username_to_id(self, username: str) -> Optional[int]:
        """
        Разрешает telegram username в numeric user ID.
        
        Args:
            username: Telegram username (без @)
            
        Returns:
            User ID или None если не удалось разрешить
        """
        try:
            logger.info(f"🔍 Разрешение username в ID: @{username}")
            entity = await self.client.get_entity(username)
            if entity:
                user_id = entity.id
                logger.info(f"✅ Username @{username} разрешён в ID: {user_id}")
                return user_id
            else:
                logger.warning(f"⚠️ Не удалось найти пользователя с username: @{username}")
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка при разрешении username @{username}: {e}")
            return None
    
    @retry_async(
        max_attempts=3,
        delay=2.0,
        backoff=2.0,
        exceptions=(FloodWaitError, ChatWriteForbiddenError, PeerFloodError, TelegramAPIError, Exception)
    )
    async def _create_study_chat(
        self,
        student_name: str,
        student_telegram_id: Optional[int],
        student_telegram_username: Optional[str],
        student_phone: Optional[str],
        manager_id: int,
        manager_name: str,
        course_tag: str
    ) -> Optional[Dict[str, Any]]:
        """
        Создает учебный чат для студента.
        
        Args:
            student_name: Имя студента
            student_telegram_id: Telegram ID студента (если известен)
            student_telegram_username: Telegram username студента (если есть)
            student_phone: Номер телефона студента (если telegram_id неизвестен)
            manager_id: Telegram ID менеджера
            manager_name: Имя менеджера
            course_tag: Тег курса из GetCourse
            
        Returns:
            Dict с информацией о чате (chat_id, chat_title) или None
        """
        try:
            # Получаем внутреннее название курса для названия чата
            course_info = CourseConfig.get_course_by_tag(course_tag)
            course_display_name = course_info['tracker_name'] if course_info else "VIP"
            
            # Формируем название чата с внутренним названием курса
            chat_title = f"🎓 {student_name} | {course_display_name}"
            
            # 📞 ШАГ 0: ДОБАВЛЯЕМ СТУДЕНТА В КОНТАКТЫ (если есть телефон)
            # Это позволяет обойти ограничения Telegram Privacy Settings
            student_user_id_from_contacts = None
            
            if student_phone:
                logger.info(f"🔑 Попытка добавить студента в контакты...")
                
                # Разделяем имя на first_name и last_name
                name_parts = student_name.split(' ', 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ""
                
                # Добавляем в контакты
                student_user_id_from_contacts = await self.contact_manager.add_student_to_contacts(
                    phone=student_phone,
                    first_name=first_name,
                    last_name=last_name
                )
                
                if student_user_id_from_contacts:
                    logger.info(f"✅ Студент УСПЕШНО добавлен в контакты!")
                    logger.info(f"   Теперь можно:")
                    logger.info(f"   - Отправлять ЛС студенту")
                    logger.info(f"   - Добавлять в супергруппы")
                    
                    # Перезаписываем telegram_id если он не был известен
                    if not student_telegram_id:
                        student_telegram_id = student_user_id_from_contacts
                        logger.info(f"🎯 Telegram ID студента получен из контактов: {student_telegram_id}")
                else:
                    logger.warning(f"⚠️ Не удалось добавить в контакты. Пробуем стандартный путь...")
            else:
                logger.info(f"🚨 Номер телефона не указан - пропускаем добавление в контакты")
            
            # Получаем entities студента, менеджера и бота ОДНИМ пакетным запросом
            # Для менеджера используем InputUser напрямую (не требует контакта)
            from telethon.tl.types import InputUser
            
            entities_to_get = [VIP_ZEROCODER_BOT_USERNAME]
            
            # Добавляем студента: СНАЧАЛА по телефону (приоритет), затем по ID
            # Телефон надежнее, так как не требует предварительного контакта
            if student_phone:
                # Очищаем номер телефона
                clean_phone = ''.join(filter(str.isdigit, student_phone))
                if not clean_phone.startswith('+'):
                    clean_phone = '+' + clean_phone
                entities_to_get.insert(0, clean_phone)
                logger.info(f"Попытка найти студента по телефону: {clean_phone}")
            elif student_telegram_id:
                entities_to_get.insert(0, student_telegram_id)
                logger.info(f"Попытка найти студента по ID: {student_telegram_id}")
            
            # Пакетная загрузка entities с кешированием
            entities = await self.entity_cache.get_entities_batch(entities_to_get)
            
            # Извлекаем конкретные entities
            student_entity = None
            
            # СНАЧАЛА пробуем по телефону (если есть)
            if student_phone:
                clean_phone = ''.join(filter(str.isdigit, student_phone))
                if not clean_phone.startswith('+'):
                    clean_phone = '+' + clean_phone
                student_entity = entities.get(clean_phone)
                if student_entity:
                    logger.info(f"✅ Студент {student_name} найден по телефону {clean_phone}")
            
            # Если не нашли по телефону, пробуем по ID
            if not student_entity and student_telegram_id:
                student_entity = entities.get(student_telegram_id)
                if student_entity:
                    logger.info(f"✅ Студент {student_name} найден по ID {student_telegram_id}")
            
            # Получаем entity менеджера через entity_cache (предзагружен при старте)
            # Если нет в кеше - пробуем get_entity
            try:
                # Сначала проверяем кеш
                manager_entity = self.entity_cache.get_from_cache(manager_id)
                if manager_entity:
                    logger.info(f"✅ Entity менеджера {manager_name} получен из кеша (ID: {manager_id})")
                else:
                    # Если нет в кеше - загружаем через API
                    manager_entity = await self.client.get_entity(manager_id)
                    self.entity_cache.put_to_cache(manager_id, manager_entity)
                    logger.info(f"✅ Entity менеджера {manager_name} загружен через API (ID: {manager_id})")
            except Exception as e:
                logger.error(f"❌ Не удалось получить entity менеджера {manager_name}: {e}")
                # Fallback: используем InputUser с access_hash=0 (может не работать!)
                manager_entity = InputUser(user_id=manager_id, access_hash=0)
                logger.warning(f"⚠️ Используем InputUser с access_hash=0 для {manager_name} - менеджер МОЖЕТ НЕ ДОБАВИТЬСЯ!")
            
            # Для студента тоже создаем InputUser с access_hash=0
            # Это работает для супергрупп даже без предварительного контакта
            if not student_entity and student_telegram_id:
                logger.info(f"⚠️ Студент не найден через get_entity, используем InputUser с ID={student_telegram_id}")
                student_entity = InputUser(user_id=student_telegram_id, access_hash=0)
            
            bot_entity = entities.get(VIP_ZEROCODER_BOT_USERNAME)
            
            # ПРОВЕРКА: студент и бот должны быть найдены
            if not student_entity:
                logger.error(f"Не удалось найти entity студента {student_name} (ID: {student_telegram_id}, phone: {student_phone})")
                await self.notifications.notify_onboarding_progress(
                    "Ошибка поиска студента", 
                    student_name, 
                    manager_name, 
                    f"Не удалось найти студента в Telegram. Проверьте Telegram ID ({student_telegram_id}) или номер телефона."
                )
                return None
            
            if not bot_entity:
                logger.error(f"Не удалось найти entity бота @{VIP_ZEROCODER_BOT_USERNAME}")
                await self.notifications.notify_onboarding_progress(
                    "Ошибка поиска бота", 
                    student_name, 
                    manager_name, 
                    f"Не удалось найти бота @{VIP_ZEROCODER_BOT_USERNAME} в Telegram."
                )
                return None
            
            # СОЗДАЁМ СУПЕРГРУППУ (не требует взаимного контакта)
            # Шаг 1: Создаём канал с Випалиной
            from telethon.tl.functions.channels import CreateChannelRequest, InviteToChannelRequest, EditAdminRequest, EditCreatorRequest
            from telethon.tl.functions.account import GetPasswordRequest
            from telethon import password as telethon_password_utils
            from telethon.tl.types import ChatAdminRights
            
            result = await self.client(CreateChannelRequest(
                title=chat_title,
                about="🎓 Учебный чат Zerocoder University",
                megagroup=True  # Супергруппа (не канал)
            ))
            
            # Логируем тип результата для диагностики
            logger.info(f"Тип результата CreateChannelRequest: {type(result).__name__}")
            
            # Получаем ID созданного чата
            chat_id = None
            
            # CreateChannelRequest возвращает Updates объект
            if hasattr(result, 'chats') and result.chats:
                chat = result.chats[0]
                chat_id = chat.id
                # Для супергрупп chat_id нужно преобразовать в -100XXXXXXXXXX
                chat_id = -1000000000000 - chat_id
                logger.info(f"Chat ID из result.chats: {chat.id} -> супергруппа ID: {chat_id}")
            
            # Если нашли chat_id
            if not chat_id:
                logger.error(f"Не удалось получить ID созданного чата. Result: {result}")
                return None
            
            logger.info(f"Создана супергруппа '{chat_title}' с ID: {chat_id}")
            
            # Шаг 1.3: Экспортируем invite-ссылку для чата (первая попытка)
            invite_link = None
            try:
                invite_result = await self.client(ExportChatInviteRequest(
                    peer=chat_id
                ))
                if invite_result and hasattr(invite_result, 'link'):
                    invite_link = invite_result.link
                    logger.info(f"✅ Получена invite-ссылка: {invite_link}")
                else:
                    logger.warning("⚠️ Не удалось получить invite-ссылку (нет атрибута link)")
            except Exception as e:
                logger.warning(f"⚠️ Первая попытка экспорта invite-ссылки не удалась: {e}. Повторим после назначения прав.")
            
            # (ЛС студенту отправляется ПОСЛЕ получения invite-ссылки — см. ниже)
            
            # Шаг 2: Добавляем участников (студент, менеджер, бот)
            student_added = False
            
            # Получаем entity для Черного Дежурного
            black_duty_account = None
            black_duty_entity = None
            
            # Ищем Черного Дежурного в конфигурации
            for account in ON_DUTY_ACCOUNTS:
                if account.get('name') == 'Изумрудный Дежурный':
                    black_duty_account = account
                    break
            
            if black_duty_account:
                try:
                    # Сначала проверяем кеш
                    black_duty_entity = self.entity_cache.get_from_cache(black_duty_account['telegram_id'])
                    if not black_duty_entity:
                        black_duty_entity = await self.client.get_entity(black_duty_account['telegram_id'])
                        self.entity_cache.put_to_cache(black_duty_account['telegram_id'], black_duty_entity)
                    logger.info(f"✅ Entity Изумрудного Дежурного получен: {black_duty_account['name']}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить entity Изумрудного Дежурного: {e}")
            else:
                logger.warning("⚠️ Изумрудный Дежурный не найден в конфигурации")
            
            # Получаем entity для Руководителя VIP-отдела (только для Luxury студентов)
            vip_head_entity = None
            is_luxury_student = '[luxury]' in course_tag.lower() or '[mini-luxury]' in course_tag.lower()
            
            if is_luxury_student:
                try:
                    # Сначала проверяем кеш
                    vip_head_entity = self.entity_cache.get_from_cache(VIP_HEAD['telegram_id'])
                    if not vip_head_entity:
                        vip_head_entity = await self.client.get_entity(VIP_HEAD['telegram_id'])
                        self.entity_cache.put_to_cache(VIP_HEAD['telegram_id'], vip_head_entity)
                    logger.info(f"✅ Entity Руководителя VIP-отдела получен: {VIP_HEAD['name']}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить entity Руководителя VIP-отдела: {e}")
            else:
                logger.info("ℹ️ Студент не Luxury - Руководитель VIP-отдела не добавляется")
            
            # Формируем список участников для добавления
            users_to_invite = [student_entity, manager_entity, bot_entity]
            users_names = [f"Студент: {student_name}", f"Менеджер: {manager_name}", f"Бот: @{VIP_ZEROCODER_BOT_USERNAME}"]
            
            if black_duty_entity:
                users_to_invite.append(black_duty_entity)
                users_names.append(f"Изумрудный Дежурный: {black_duty_account['name']}")
            if vip_head_entity:
                users_to_invite.append(vip_head_entity)
                users_names.append(f"Руководитель VIP: {VIP_HEAD['name']}")
            
            logger.info(f"👥 Добавляем {len(users_to_invite)} участников: {', '.join(users_names)}")
            
            try:
                result = await self.client(InviteToChannelRequest(
                    channel=chat_id,
                    users=users_to_invite
                ))
                logger.info(f"Участники добавлены в супергруппу {chat_id}")
                
                # Проверяем кто РЕАЛЬНО добавлен
                if hasattr(result, 'missing_invitees') and result.missing_invitees:
                    logger.warning(f"⚠️ Некоторые участники НЕ БЫЛИ ДОБАВЛЕНЫ:")
                    for missing in result.missing_invitees:
                        if hasattr(missing, 'user_id'):
                            missing_id = missing.user_id
                            # Определяем кто именно не добавлен
                            if missing_id == student_telegram_id:
                                logger.warning(f"⚠️ Студент {student_name} (ID: {missing_id}) НЕ ДОБАВЛЕН (настройки приватности)")
                                student_added = False
                            elif missing_id == manager_id:
                                logger.error(f"❌ МЕНЕДЖЕР {manager_name} (ID: {missing_id}) НЕ БЫЛ ДОБАВЛЕН!")
                            else:
                                logger.warning(f"⚠️ Участник ID {missing_id} НЕ ДОБАВЛЕН")
                else:
                    student_added = True
                    logger.info(f"✅ ВСЕ участники УСПЕШНО добавлены в чат")
                    
            except Exception as e:
                logger.error(f"Ошибка при добавлении участников: {e}", exc_info=True)
                # НЕ удаляем чат - продолжаем онбординг
                logger.warning(f"⚠️ Чат создан, но студент не добавлен. Менеджер добавит вручную.")
                student_added = False
                # Продолжаем без raise - чат остается
            
            # Назначаем менеджера администратором с полными правами
            try:
                manager_admin_rights = ChatAdminRights(
                    change_info=True,
                    post_messages=True,
                    edit_messages=True,
                    delete_messages=True,
                    ban_users=True,
                    invite_users=True,
                    pin_messages=True,
                    add_admins=True,
                    manage_call=True
                )
                
                # Для супергрупп используем EditAdminRequest из channels
                # ВАЖНО: используем manager_id (int), а не manager_entity (InputUser)
                await self.client(EditAdminRequest(
                    channel=chat_id,
                    user_id=manager_id,
                    admin_rights=manager_admin_rights,
                    rank="VIP-менеджер"
                ))
                
                logger.info(f"Менеджер {manager_name} назначен администратором чата {chat_id}")
            except Exception as e:
                logger.warning(f"Не удалось назначить менеджера администратором: {e}")
            
            # Назначаем бота администратором
            try:
                bot_admin_rights = ChatAdminRights(
                    change_info=False,
                    post_messages=True,
                    edit_messages=False,
                    delete_messages=True,
                    ban_users=False,
                    invite_users=True,
                    pin_messages=True,
                    add_admins=False,
                    manage_call=False
                )
                
                await self.client(EditAdminRequest(
                    channel=chat_id,
                    user_id=bot_entity,
                    admin_rights=bot_admin_rights,
                    rank="Bot"
                ))
                
                logger.info(f"Бот @{VIP_ZEROCODER_BOT_USERNAME} назначен администратором чата {chat_id}")
            except Exception as e:
                logger.warning(f"Не удалось назначить бота администратором: {e}")
            
            # Добавляем и назначаем @zerocoder_ultralina_bot (classic bot для мониторинга)
            ultralina_bot_entity = None
            try:
                ultralina_bot_entity = await self.entity_cache.get_entities_batch([ULTRALINA_BOT_USERNAME])
                ultralina_bot_entity = ultralina_bot_entity.get(ULTRALINA_BOT_USERNAME)
                
                if ultralina_bot_entity:
                    # Добавляем в чат
                    await self.client(InviteToChannelRequest(
                        channel=chat_id,
                        users=[ultralina_bot_entity]
                    ))
                    logger.info(f"✅ @{ULTRALINA_BOT_USERNAME} добавлен в чат {chat_id}")
                    
                    # Назначаем администратором (нужно для чтения всех сообщений)
                    ultralina_admin_rights = ChatAdminRights(
                        change_info=False,
                        post_messages=True,
                        edit_messages=False,
                        delete_messages=True,
                        ban_users=False,
                        invite_users=False,
                        pin_messages=True,
                        add_admins=False,
                        manage_call=False
                    )
                    
                    await self.client(EditAdminRequest(
                        channel=chat_id,
                        user_id=ultralina_bot_entity,
                        admin_rights=ultralina_admin_rights,
                        rank="Випалина"
                    ))
                    logger.info(f"✅ @{ULTRALINA_BOT_USERNAME} назначен администратором чата {chat_id}")
                else:
                    logger.warning(f"⚠️ Не удалось найти entity @{ULTRALINA_BOT_USERNAME}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось добавить @{ULTRALINA_BOT_USERNAME} в чат: {e}")
            
            # Назначаем Черного Дежурного администратором (если он был добавлен)
            if black_duty_entity:
                try:
                    # Те же права что и у менеджера
                    duty_admin_rights = ChatAdminRights(
                        change_info=True,
                        post_messages=True,
                        edit_messages=True,
                        delete_messages=True,
                        ban_users=True,
                        invite_users=True,
                        pin_messages=True,
                        add_admins=True,
                        manage_call=True
                    )
                    
                    await self.client(EditAdminRequest(
                        channel=chat_id,
                        user_id=black_duty_entity,
                        admin_rights=duty_admin_rights,
                        rank="Дежурный"
                    ))
                    
                    logger.info(f"Черный Дежурный ({black_duty_account['name']}) назначен администратором чата {chat_id}")
                except Exception as e:
                    logger.warning(f"Не удалось назначить Черного Дежурного администратором: {e}")
            
            # Назначаем Руководителя VIP-отдела администратором (если он был добавлен для Luxury студентов)
            if vip_head_entity:
                try:
                    # Те же права что и у менеджера
                    head_admin_rights = ChatAdminRights(
                        change_info=True,
                        post_messages=True,
                        edit_messages=True,
                        delete_messages=True,
                        ban_users=True,
                        invite_users=True,
                        pin_messages=True,
                        add_admins=True,
                        manage_call=True
                    )
                    
                    await self.client(EditAdminRequest(
                        channel=chat_id,
                        user_id=vip_head_entity,
                        admin_rights=head_admin_rights,
                        rank="Руководитель VIP-отдела"
                    ))
                    
                    logger.info(f"Руководитель VIP-отдела ({VIP_HEAD['name']}) назначен администратором чата {chat_id}")
                except Exception as e:
                    logger.warning(f"Не удалось назначить Руководителя VIP-отдела администратором: {e}")
            
            # === ПЕРЕДАЧА ВЛАДЕНИЯ ЧАТОМ (с fallback) ===
            async def _try_transfer_ownership(target_id, label):
                """Попытка передать владение чатом. Возвращает True при успехе."""
                try:
                    from config import VIPALINA_2FA_PASSWORD
                    pwd_settings = await self.client(GetPasswordRequest())
                    srp = telethon_password_utils.compute_check(pwd_settings, VIPALINA_2FA_PASSWORD)
                    await self.client(EditCreatorRequest(
                        channel=chat_id,
                        user_id=target_id,
                        password=srp
                    ))
                    logger.info(f"✅ Владение чатом {chat_id} передано: {label}")
                    return True
                except Exception as ex:
                    logger.warning(f"⚠️ Не удалось передать владение → {label}: {ex}")
                    return False

            ownership_transferred = False
            # Попытка 1: передать менеджеру
            ownership_transferred = await _try_transfer_ownership(manager_id, f"менеджер {manager_name}")
            # Попытка 2: передать Изумрудному Дежурному
            if not ownership_transferred and black_duty_entity:
                ownership_transferred = await _try_transfer_ownership(
                    black_duty_account['telegram_id'],
                    f"Изумрудный Дежурный ({black_duty_account['name']})"
                )
            if not ownership_transferred:
                logger.info(f"ℹ️ Владелец чата {chat_id}: Випалина (передача не удалась)")

            # Итоговые роли в супергруппе:
            # - Владелец: Менеджер (при успехе) → Изумрудный Дежурный → Випалина (fallback)
            # - Администратор с полными правами: Менеджер
            # - Администратор: Бот @vip_zerocode_bot
            # - Участник: Студент
            
            # ВТОРОЙ ШАНС: Если invite_link не был получен ранее, повторяем попытку
            # После назначения всех прав у нас больше шансов получить ссылку
            if not invite_link:
                logger.info("🔄 Вторая попытка получить invite-ссылку после назначения прав...")
                try:
                    import asyncio
                    await asyncio.sleep(1)  # Небольшая задержка для применения прав
                    
                    invite_result = await self.client(ExportChatInviteRequest(
                        peer=chat_id
                    ))
                    if invite_result and hasattr(invite_result, 'link'):
                        invite_link = invite_result.link
                        logger.info(f"✅ Invite-ссылка получена со второй попытки: {invite_link}")
                    else:
                        logger.warning("⚠️ Не удалось получить invite-ссылку даже со второй попытки")
                except Exception as e:
                    logger.error(f"❌ Ошибка при второй попытке экспорта invite-ссылки: {e}")
            
            # 📩 Отправляем ЛС студенту ВСЕГДА
            # Если есть invite_link и студент не добавлен — шлём ссылку на чат
            # Если invite_link нет или студент уже добавлен — шлём контакт менеджера
            try:
                dm_entity = None
                
                if student_phone:
                    try:
                        dm_entity = await self.client.get_entity(student_phone)
                        logger.info(f"✅ Entity для ЛС получен по телефону: {student_phone}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось получить entity по телефону: {e}")
                
                if not dm_entity and student_telegram_username:
                    try:
                        dm_entity = await self.client.get_entity(student_telegram_username)
                        logger.info(f"✅ Entity для ЛС получен по username: {student_telegram_username}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось получить entity по username: {e}")
                
                if dm_entity:
                    manager_link = f"tg://user?id={manager_id}"
                    
                    if invite_link:
                        # Есть ссылка — шлём invite + контакт менеджера
                        invite_message = f"""🎓 Здравствуйте, {student_name}!

Поздравляем с началом обучения в Zerocoder University! 🎉

Для вас создан учебный чат с вашим персональным менеджером: {invite_link}

Ваш VIP-менеджер — [{manager_name}]({manager_link}) 💚
Пожалуйста, принимайте приглашение в чат!"""
                    else:
                        # Нет ссылки — шлём только контакт менеджера
                        invite_message = f"""🎓 Здравствуйте, {student_name}!

Поздравляем с началом обучения в Zerocoder University! 🎉

Ваш персональный VIP-менеджер — [{manager_name}]({manager_link}).
Напишите ей — вас добавят в учебный чат! 💚"""
                    
                    await self.client.send_message(dm_entity, invite_message)
                    logger.info(f"✅ Личное сообщение отправлено студенту {student_name} (invite_link={'да' if invite_link else 'нет'})")
                    
                    import asyncio
                    await asyncio.sleep(2)
                else:
                    logger.warning(f"⚠️ Не удалось получить entity для ЛС студенту {student_name}")
                    
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить ЛС студенту: {e}")
            
            # 🧹 ШАГ FINAL: Удаляем студента из контактов (опционально)
            # Это очищает список контактов и скрывает факт добавления
            if student_user_id_from_contacts and student_added:
                logger.info(f"🧹 Онбординг завершен - удаляем студента из контактов...")
                await self.contact_manager.remove_student_from_contacts(student_user_id_from_contacts)
            elif student_user_id_from_contacts and not student_added:
                logger.info(f"⚠️ Студент НЕ добавлен в чат - ОСТАВЛЯЕМ в контактах для повторной попытки")
            
            return {
                'chat_id': chat_id,
                'chat_title': chat_title,
                'invite_link': invite_link,
                'ownership_transferred': ownership_transferred
            }
            
        except UserPrivacyRestrictedError:
            logger.error(f"Студент {student_name} ограничил возможность добавления в группы")
            # ВАЖНО: Чат создан, но студент не добавлен
            # Возвращаем информацию о чате, чтобы продолжить онбординг
            if chat_id:
                logger.info(f"Чат создан успешно, но студент не добавлен из-за приватности. Chat ID: {chat_id}")
                return {
                    'chat_id': chat_id,
                    'chat_title': chat_title,
                    'invite_link': invite_link if 'invite_link' in dir() else None
                }
            else:
                # Отправляем уведомление об ошибке приватности
                await self.notifications.notify_onboarding_progress("Ошибка приватности", student_name, manager_name, "Студент ограничил возможность добавления в группы")
                return None
        except UserNotMutualContactError:
            logger.error(f"Студент {student_name} не является взаимным контактом")
            # ВАЖНО: Чат создан, но студент не добавлен
            # Возвращаем информацию о чате, чтобы продолжить онбординг
            if chat_id:
                logger.info(f"Чат создан успешно, но студент не добавлен из-за отсутствия контакта. Chat ID: {chat_id}")
                return {
                    'chat_id': chat_id,
                    'chat_title': chat_title,
                    'invite_link': invite_link if 'invite_link' in dir() else None
                }
            else:
                # Отправляем уведомление об ошибке контакта
                await self.notifications.notify_onboarding_progress("Ошибка контакта", student_name, manager_name, "Студент не является взаимным контактом")
                return None
        except Exception as e:
            logger.error(f"Ошибка при создании чата для студента {student_name}: {e}", exc_info=True)
            # Отправляем уведомление об общей ошибке
            await self.notifications.notify_onboarding_progress("Ошибка создания чата", student_name, manager_name, f"Произошла ошибка при создании чата: {str(e)}")
            return None
    
    async def _send_welcome_message(
        self,
        chat_id: int,
        student_name: str,
        student_telegram_username: Optional[str],
        manager_name: str,
        manager_id: int,
        course: str
    ) -> bool:
        """
        Отправляет приветственное сообщение в учебный чат.
        Вариант Б: Сообщение от имени бота с упоминанием менеджера.
        
        Args:
            chat_id: ID чата
            student_name: Имя студента
            student_telegram_username: Telegram username студента (если есть)
            manager_name: Имя менеджера
            manager_id: Telegram ID менеджера
            course: Название курса
            
        Returns:
            True если сообщение отправлено успешно
        """
        try:
            # Формируем обращение к студенту
            if student_telegram_username:
                # Если есть username - тегаем
                student_greeting = f"@{student_telegram_username.lstrip('@')}"
            else:
                # Если нет username - используем полное имя из карточки
                student_greeting = student_name
            
            # Импортируем CourseConfig для получения правильного названия курса
            from course_config_v2 import CourseConfig
            
            # Получаем название курса из классификатора для отображения в трекере
            tracker_course_name = CourseConfig.get_tracker_course_name(course)
            
            # Формируем приветственное сообщение
            message = f"""Здравствуйте, {student_greeting}!

Добро пожаловать в Zerocoder University! 🌟

Поздравляем с началом обучения на курсе 📚

Знакомьтесь — ваш персональный менеджер [{manager_name}](tg://user?id={manager_id})!
Она будет сопровождать вас на протяжении всего обучения и поможет с любыми вопросами 💚

Также в чате присутствует ботик вип-отдела @zerocoder_ultralina_bot — бот-помощник, который отслеживает ваш прогресс и собирает статистику!
Общаться с ним не нужно, но иногда он будет присылать важные сообщения :)

В ближайшее время вы получите подробную информацию о вашем курсе и тарифе.

Успехов в обучении! 🚀"""
            
            await self.client.send_message(chat_id, message)
            logger.info(f"Приветственное сообщение отправлено в чат {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке приветственного сообщения в чат {chat_id}: {e}", exc_info=True)
            return False
    
    async def _handle_student_privacy_issue(
        self,
        student_data: Dict[str, Any],
        manager_id: int,
        manager_name: str
    ):
        """
        Обрабатывает случай, когда студента нельзя добавить в группу из-за настроек приватности.
        
        Args:
            student_data: Данные о студенте
            manager_id: Telegram ID менеджера
            manager_name: Имя менеджера
        """
        try:
            student_name = student_data.get('name', 'Студент')
            student_telegram_id = student_data.get('telegram_id')
            
            logger.info(f"Обработка проблемы приватности для студента {student_name}")
            
            # Используем метод из модуля уведомлений для обработки проблемы приватности
            await self.notifications.handle_student_privacy_issue(
                student_data=student_data,
                manager_id=manager_id,
                manager_name=manager_name
            )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке проблемы приватности для студента {student_data.get('name', 'Неизвестный студент')}: {e}", exc_info=True)
            # Отправляем уведомление об ошибке обработки проблемы приватности
            await self.notifications.notify_onboarding_progress(
                "Ошибка обработки приватности", 
                student_data.get('name', 'Неизвестный студент'), 
                manager_name, 
                f"Произошла ошибка при обработке проблемы приватности: {str(e)}"
            )
    
    async def add_curator_to_chat(
        self,
        chat_id: int,
        curator_username: str
    ) -> bool:
        """
        Добавляет куратора в учебный чат.
        
        Args:
            chat_id: ID чата
            curator_username: Username или ID куратора
            
        Returns:
            True если куратор добавлен успешно
        """
        try:
            # Получаем entity куратора
            curator_entity = await self.client.get_entity(curator_username)
            
            # Добавляем в чат
            await self.client.edit_permissions(
                chat_id,
                curator_entity,
                view_messages=True,
                send_messages=True
            )
            
            logger.info(f"Куратор {curator_username} добавлен в чат {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении куратора {curator_username} в чат {chat_id}: {e}", exc_info=True)
            return False