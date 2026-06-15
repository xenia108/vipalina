"""
Модуль ручного добавления студентов VIP-менеджерами.
Позволяет менеджерам добавлять студентов через команду /добавить_студента.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.tl.types import KeyboardButtonCallback
import re

from config import VIP_MANAGERS_VIP, VIP_MANAGERS_LUXURY, VIP_HEAD, ON_DUTY_ACCOUNTS, ALL_MANAGER_IDS
from vip_chat_monitor import StudentData

logger = logging.getLogger('vipalina_telethon')


class ManualStudentAddition:
    """
    Класс для ручного добавления студентов VIP-менеджерами.
    Поддерживает интерактивный диалог для сбора информации о студенте.
    """
    
    def __init__(self, client: TelegramClient):
        self.client = client
        # Хранилище состояний диалогов: user_id -> dialog_state
        self.dialog_states: Dict[int, Dict[str, Any]] = {}
        
        logger.info("Инициализирован модуль ручного добавления студентов")
    
    def _is_vip_manager(self, user_id: int) -> bool:
        """Проверяет, имеет ли пользователь права менеджера (включая дежурных)"""
        return user_id in ALL_MANAGER_IDS
    
    def _get_manager_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию о менеджере, дежурном или руководителе"""
        # Сначала ищем в VIP-менеджерах
        for manager in VIP_MANAGERS_VIP:
            if manager['telegram_id'] == user_id:
                return manager
        # Потом ищем в Luxury-менеджерах
        for manager in VIP_MANAGERS_LUXURY:
            if manager['telegram_id'] == user_id:
                return manager
        # Проверяем руководителя
        if VIP_HEAD['telegram_id'] == user_id:
            return VIP_HEAD
        # Потом ищем в дежурных
        for on_duty in ON_DUTY_ACCOUNTS:
            if on_duty['telegram_id'] == user_id:
                return on_duty
        return None
    
    async def start_manual_addition(self, event, manager_id: int) -> bool:
        """
        Начинает процесс ручного добавления студента.
        
        Args:
            event: Событие Telegram
            manager_id: ID менеджера, инициировавшего добавление
            
        Returns:
            True если процесс начат успешно
        """
        try:
            # Проверяем права
            if not self._is_vip_manager(manager_id):
                await event.reply("❌ У вас нет прав для добавления студентов.")
                return False
            
            manager_info = self._get_manager_info(manager_id)
            if not manager_info:
                await event.reply("❌ Не удалось получить информацию о менеджере.")
                return False
            
            # Инициализируем состояние диалога
            self.dialog_states[manager_id] = {
                'step': 'awaiting_name',
                'student_data': {},
                'manager_name': manager_info['name'],
                'started_at': datetime.now()
            }
            
            # Отправляем приветственное сообщение с кнопкой отмены
            message = """📝 **ДОБАВЛЕНИЕ СТУДЕНТА ВРУЧНУЮ**

Привет! Давай добавим нового VIP-студента в систему.

Я буду задавать вопросы шаг за шагом. Ты можешь в любой момент отменить процесс.

**Шаг 1/5:** Как зовут студента?
💡 _Введи имя и фамилию (например: Иван Петров)_
"""
            
            buttons = [[Button.inline("❌ Отменить", b"cancel_add")]]
            await event.reply(message, buttons=buttons)
            logger.info(f"Менеджер {manager_info['name']} начала процесс ручного добавления студента")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при начале ручного добавления студента: {e}", exc_info=True)
            return False
    
    async def cancel_addition(self, event, manager_id: int) -> bool:
        """
        Отменяет процесс добавления студента.
        
        Args:
            event: Событие Telegram
            manager_id: ID менеджера
            
        Returns:
            True если процесс отменён
        """
        if manager_id in self.dialog_states:
            del self.dialog_states[manager_id]
            await event.reply("❌ Добавление студента отменено.")
            logger.info(f"Менеджер {manager_id} отменила добавление студента")
            return True
        else:
            await event.reply("⚠️ Нет активного процесса добавления студента.")
            return False
    
    async def process_dialog_message(self, event, manager_id: int, message_text: str) -> Optional[StudentData]:
        """
        Обрабатывает сообщение в диалоге добавления студента.
        
        Args:
            event: Событие Telegram
            manager_id: ID менеджера
            message_text: Текст сообщения
            
        Returns:
            StudentData если все данные собраны, иначе None
        """
        if manager_id not in self.dialog_states:
            return None
        
        try:
            state = self.dialog_states[manager_id]
            current_step = state['step']
            student_data = state['student_data']
            
            # Обрабатываем шаги диалога
            if current_step == 'awaiting_name':
                student_data['name'] = message_text.strip()
                state['step'] = 'awaiting_getcourse_id'
                
                message = """✅ Имя сохранено!

**Шаг 2/5:** Какой GetCourse ID у студента?
💡 _Введи числовой ID или ссылку на профиль студента в GetCourse_
💡 _Например: 432950986 или https://university.zerocoder.ru/user/control/user/update/id/432950986_
"""
                buttons = [[Button.inline("❌ Отменить", b"cancel_add")]]
                await event.reply(message, buttons=buttons)
                
            elif current_step == 'awaiting_getcourse_id':
                # Извлекаем ID из ссылки или используем как есть
                id_match = re.search(r'(?:id/)?(\d+)', message_text)
                if id_match:
                    student_data['getcourse_id'] = id_match.group(1)
                    student_data['getcourse_url'] = f"https://university.zerocoder.ru/user/control/user/update/id/{student_data['getcourse_id']}"
                    state['step'] = 'awaiting_phone'
                    
                    message = """✅ GetCourse ID сохранён!

**Шаг 3/5:** Какой номер телефона у студента?
💡 _Введи номер в любом формате (например: +79289755499 или 79289755499)_
💡 _Если не знаешь, нажми кнопку "Пропустить" или напиши "нет"_
"""
                    buttons = [
                        [Button.inline("⏭️ Пропустить", b"skip_phone")],
                        [Button.inline("❌ Отменить", b"cancel_add")]
                    ]
                    await event.reply(message, buttons=buttons)
                else:
                    await event.reply("❌ Неверный формат. Введи числовой ID или ссылку.")
                
            elif current_step == 'awaiting_phone':
                if message_text.lower() == 'нет':
                    student_data['phone'] = None
                else:
                    # Убираем все нецифровые символы
                    phone = ''.join(filter(str.isdigit, message_text))
                    student_data['phone'] = phone
                
                state['step'] = 'awaiting_course'
                
                message = """✅ Телефон сохранён!

**Шаг 4/5:** На какой курс записан студент?
💡 _Введи название курса или тарифа_
💡 _Например: [luxury][ai-studio] Тариф "Своя AI-студия"_
"""
                buttons = [[Button.inline("❌ Отменить", b"cancel_add")]]
                await event.reply(message, buttons=buttons)
                
            elif current_step == 'awaiting_course':
                student_data['course'] = message_text.strip()
                state['step'] = 'awaiting_telegram'
                
                message = """✅ Курс сохранён!

**Шаг 5/5:** Какой Telegram username у студента?
💡 _Введи @username (например: @ivanov)_
💡 _Или введи Telegram ID если знаешь (например: 123456789)_
💡 _Если не знаешь, нажми кнопку "Пропустить" или напиши "нет"_
"""
                buttons = [
                    [Button.inline("⏭️ Пропустить", b"skip_telegram")],
                    [Button.inline("❌ Отменить", b"cancel_add")]
                ]
                await event.reply(message, buttons=buttons)
                
            elif current_step == 'awaiting_telegram':
                # Пытаемся определить, что ввели: username или ID
                if message_text.lower() == 'нет':
                    student_data['telegram_username'] = None
                    student_data['telegram_id'] = None
                elif message_text.startswith('@'):
                    student_data['telegram_username'] = message_text.strip()
                    student_data['telegram_id'] = None
                elif message_text.isdigit():
                    student_data['telegram_id'] = int(message_text)
                    student_data['telegram_username'] = None
                else:
                    student_data['telegram_username'] = f"@{message_text.strip().lstrip('@')}"
                    student_data['telegram_id'] = None
                
                # Завершаем диалог и создаём StudentData
                student = await self._create_student_data(student_data)
                
                # Показываем сводку
                summary = self._format_student_summary(student)
                await event.reply(summary)
                
                # Очищаем состояние
                del self.dialog_states[manager_id]
                
                logger.info(f"Менеджер {state['manager_name']} успешно добавила студента {student.name} вручную")
                return student
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при обработке диалога добавления студента: {e}", exc_info=True)
            await event.reply(f"❌ Произошла ошибка: {e}\nПопробуйте снова или используйте /отмена")
            return None
    
    async def _create_student_data(self, data: Dict[str, Any]) -> StudentData:
        """
        Создаёт объект StudentData из собранных данных.
        
        Args:
            data: Словарь с данными студента
            
        Returns:
            StudentData объект
        """
        student = StudentData()
        student.name = data.get('name')
        student.getcourse_id = data.get('getcourse_id')
        student.getcourse_url = data.get('getcourse_url')
        student.email = None  # Email больше не запрашивается
        student.phone = data.get('phone')
        student.course = data.get('course')
        student.telegram_username = data.get('telegram_username')
        student.telegram_id = data.get('telegram_id')
        student.date_received = datetime.now()
        
        # Пытаемся получить telegram_id если есть username
        if student.telegram_username and not student.telegram_id:
            try:
                user = await self.client.get_entity(student.telegram_username)
                # Handle case where get_entity returns a list
                if isinstance(user, list) and len(user) > 0:
                    user = user[0]
                user_id = getattr(user, 'id', None)
                if user_id:
                    student.telegram_id = user_id
                    logger.info(f"Получен Telegram ID {user_id} для @{student.telegram_username}")
            except Exception as e:
                logger.warning(f"Не удалось получить Telegram ID для {student.telegram_username}: {e}")
        
        # Пытаемся получить username если есть telegram_id
        if student.telegram_id and not student.telegram_username:
            try:
                user = await self.client.get_entity(student.telegram_id)
                # Handle case where get_entity returns a list
                if isinstance(user, list) and len(user) > 0:
                    user = user[0]
                username = getattr(user, 'username', None)
                if username:
                    student.telegram_username = f"@{username}"
                    logger.info(f"Получен username @{username} для ID {student.telegram_id}")
            except Exception as e:
                logger.warning(f"Не удалось получить username для ID {student.telegram_id}: {e}")
        
        # Пытаемся получить данные по телефону если не удалось по username/id
        if not student.telegram_id and student.phone:
            try:
                phone = student.phone if student.phone.startswith('+') else f"+{student.phone}"
                user = await self.client.get_entity(phone)
                # Handle case where get_entity returns a list
                if isinstance(user, list) and len(user) > 0:
                    user = user[0]
                user_id = getattr(user, 'id', None)
                if user_id:
                    student.telegram_id = user_id
                    username = getattr(user, 'username', None)
                    if username:
                        student.telegram_username = f"@{username}"
                    logger.info(f"Получены данные по телефону: ID {user_id}, username @{username or 'N/A'}")
            except Exception as e:
                logger.warning(f"Не удалось получить данные по телефону {student.phone}: {e}")
        
        return student
    
    def _format_student_summary(self, student: StudentData) -> str:
        """
        Форматирует сводку о добавленном студенте.
        
        Args:
            student: Данные студента
            
        Returns:
            Отформатированное сообщение
        """
        summary = """✅ **СТУДЕНТ ДОБАВЛЕН В СИСТЕМУ**

📋 **Сводка:**
"""
        summary += f"👤 **Имя:** {student.name}\n"
        summary += f"🔗 **GetCourse ID:** {student.getcourse_id}\n"
        summary += f"📱 **Телефон:** {student.phone or 'Не указан'}\n"
        summary += f"🎯 **Курс:** {student.course}\n"
        summary += f"💬 **Telegram:** {student.telegram_username or 'Не указан'}\n"
        summary += f"🆔 **Telegram ID:** {student.telegram_id or 'Не удалось получить'}\n"
        
        summary += "\n🚀 Онбординг запущен автоматически!"
        
        return summary
    
    def is_in_dialog(self, manager_id: int) -> bool:
        """
        Проверяет, находится ли менеджер в процессе добавления студента.
        
        Args:
            manager_id: ID менеджера
            
        Returns:
            True если менеджер в диалоге
        """
        return manager_id in self.dialog_states
    
    def setup_handlers(self, on_student_added_callback):
        """
        Настраивает обработчики команд для ручного добавления студентов.
        
        Args:
            on_student_added_callback: Callback функция, вызываемая при добавлении студента
        """
        
        @self.client.on(events.NewMessage(pattern=r'/addnew'))
        async def handle_add_student_command(event):
            """Обработчик команды /addnew"""
            manager_id = event.sender_id
            await self.start_manual_addition(event, manager_id)
        
        @self.client.on(events.NewMessage(pattern=r'/cancel'))
        async def handle_cancel_command(event):
            """Обработчик команды /cancel"""
            manager_id = event.sender_id
            await self.cancel_addition(event, manager_id)
        
        @self.client.on(events.CallbackQuery())
        async def handle_button_callback(event):
            """Обработчик нажатий на кнопки"""
            manager_id = event.sender_id
            data = event.data
            
            if data == b"cancel_add":
                await self.cancel_addition(event, manager_id)
                await event.answer()
            elif data == b"skip_phone":
                if manager_id in self.dialog_states and self.dialog_states[manager_id]['step'] == 'awaiting_phone':
                    await self.process_dialog_message(event, manager_id, "нет")
                    await event.answer("Телефон пропущен")
            elif data == b"skip_telegram":
                if manager_id in self.dialog_states and self.dialog_states[manager_id]['step'] == 'awaiting_telegram':
                    await self.process_dialog_message(event, manager_id, "нет")
                    await event.answer("Telegram пропущен")
        
        @self.client.on(events.NewMessage(incoming=True))
        async def handle_dialog_messages(event):
            """Обработчик сообщений в диалоге добавления студента"""
            manager_id = event.sender_id
            
            # Пропускаем, если это команда
            if event.message.text and event.message.text.startswith('/'):
                return
            
            # Проверяем, находится ли менеджер в диалоге
            if not self.is_in_dialog(manager_id):
                return
            
            # Обрабатываем сообщение
            message_text = event.message.text
            student = await self.process_dialog_message(event, manager_id, message_text)
            
            # Если студент добавлен полностью, вызываем callback
            if student and on_student_added_callback:
                try:
                    await on_student_added_callback(student, manager_id)
                except Exception as e:
                    logger.error(f"Ошибка при вызове callback on_student_added: {e}", exc_info=True)
        
        logger.info("Настроены обработчики команд для ручного добавления студентов")
