#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль мониторинга чата VIP-отдела для автоматической обработки новых студентов
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from telethon import TelegramClient, events
from telethon.tl.types import Message
import pytz

# Настройка логирования
logger = logging.getLogger('vip_chat_monitor')

# ID чата VIP-отдела
VIP_DEPARTMENT_CHAT_ID = -1001755644531

# Username бота, который присылает новых студентов
ZEROCODER_NEWS_BOT = "zerocoder_news_bot"
TEST_USER = "xenia108"  # Для тестирования онбординга

# Часовой пояс Москвы (из конфигурации)
MOSCOW_TZ = "Europe/Moscow"


class StudentData:
    """Класс для хранения данных студента"""
    
    def __init__(self):
        self.name: Optional[str] = None
        self.getcourse_id: Optional[str] = None
        self.getcourse_url: Optional[str] = None
        self.email: Optional[str] = None
        self.phone: Optional[str] = None
        self.course: Optional[str] = None
        self.telegram_username: Optional[str] = None
        self.telegram_id: Optional[int] = None
        self.raw_message: Optional[str] = None
        self.message_id: Optional[int] = None
        self.date_received: datetime = datetime.now()
    
    def __str__(self):
        return f"StudentData(name={self.name}, getcourse_id={self.getcourse_id}, telegram={self.telegram_username})"
    
    def is_valid(self) -> bool:
        """Проверяет, что получены минимально необходимые данные"""
        return bool(self.name and self.getcourse_id)
    
    def to_dict(self) -> Dict:
        """Конвертирует в словарь для удобной работы"""
        return {
            'name': self.name,
            'getcourse_id': self.getcourse_id,
            'getcourse_url': self.getcourse_url,
            'email': self.email,
            'phone': self.phone,
            'course': self.course,
            'telegram_username': self.telegram_username,
            'telegram_id': self.telegram_id,
            'message_id': self.message_id,
            'date_received': self.date_received.isoformat()
        }


class VIPChatMonitor:
    """Класс для мониторинга чата VIP-отдела и парсинга новых студентов"""
    
    def __init__(self, client: TelegramClient):
        self.client = client
        self.logger = logging.getLogger('vip_chat_monitor')
        # Инициализируем часовой пояс Москвы
        self.moscow_tz = pytz.timezone(MOSCOW_TZ)
    
    def parse_student_message(self, message_text: str, message_id: Optional[int] = None) -> Optional[StudentData]:
        """
        Парсит сообщение от @zerocoder_news_bot (или @xenia108 для тестирования) и извлекает данные студента
        
        Формат сообщения:
        Эй, смотрите все! Новый VIP!
        
        Имя: Виктория
        Ссылка: https://university.zerocoder.ru/user/control/user/update/id/476965397
        Почта: vikulya_klenina@mail.ru
        Телефон: 79035437005
        Курс: [vibe-market] Тариф "VIP"
        Телеграм: @Viktoria37
        Телеграм ID: 745948821
        
        Хорошей работы!
        """
        
        if not message_text or "Новый VIP!" not in message_text:
            return None
        
        student = StudentData()
        student.raw_message = message_text
        student.message_id = message_id
        
        # Парсинг имени
        name_match = re.search(r'Имя:\s*(.+?)(?:\n|$)', message_text)
        if name_match:
            student.name = name_match.group(1).strip()
        
        # Парсинг ссылки на GetCourse и извлечение ID
        url_match = re.search(r'Ссылка:\s*(https://university\.zerocoder\.ru/user/control/user/update/id/(\d+))', message_text)
        if url_match:
            student.getcourse_url = url_match.group(1).strip()
            student.getcourse_id = url_match.group(2).strip()
        
        # Парсинг email
        email_match = re.search(r'Почта:\s*(.+?)(?:\n|$)', message_text)
        if email_match:
            student.email = email_match.group(1).strip()
        
        # Парсинг телефона
        phone_match = re.search(r'Телефон:\s*(\d+)', message_text)
        if phone_match:
            student.phone = phone_match.group(1).strip()
        
        # Парсинг курса
        course_match = re.search(r'Курс:\s*(.+?)(?:\n|$)', message_text)
        if course_match:
            student.course = course_match.group(1).strip()
        
        # Парсинг Telegram username
        telegram_match = re.search(r'Телеграм:\s*(@\w+)', message_text)
        if telegram_match:
            student.telegram_username = telegram_match.group(1).strip()
        
        # Парсинг Telegram ID (если есть в сообщении)
        telegram_id_match = re.search(r'Телеграм ID:\s*(\d+)', message_text)
        if telegram_id_match:
            student.telegram_id = int(telegram_id_match.group(1).strip())
            self.logger.info(f"Извлечен Telegram ID из сообщения: {student.telegram_id}")
        
        if student.is_valid():
            self.logger.info(f"Успешно распарсен новый студент: {student}")
            return student
        else:
            self.logger.warning(f"Не удалось распарсить все необходимые данные студента из сообщения")
            return None
    
    async def get_telegram_id_by_username(self, username: str) -> Optional[int]:
        """
        Получает Telegram ID пользователя по username
        
        Args:
            username: Username пользователя (с @ или без)
        
        Returns:
            Telegram ID или None если не удалось получить
        """
        try:
            # Убираем @ если есть
            clean_username = username.lstrip('@')
            
            self.logger.info(f"Получение Telegram ID для username: {clean_username}")
            
            # Получаем сущность пользователя
            user = await self.client.get_entity(clean_username)
            
            self.logger.info(f"Успешно получен Telegram ID: {user.id} для @{clean_username}")
            return user.id
            
        except Exception as e:
            self.logger.warning(f"Не удалось получить Telegram ID для @{clean_username}: {e}")
            return None
    
    async def get_telegram_id_by_phone(self, phone: str) -> Optional[int]:
        """
        Получает Telegram ID пользователя по номеру телефона
        
        Args:
            phone: Номер телефона
        
        Returns:
            Telegram ID или None если не удалось получить
        """
        try:
            # Форматируем номер телефона (добавляем + если нет)
            if not phone.startswith('+'):
                phone = '+' + phone
            
            self.logger.info(f"Получение Telegram ID для телефона: {phone}")
            
            # Получаем контакты по номеру телефона
            contacts = await self.client.get_contacts()
            
            for contact in contacts:
                if hasattr(contact, 'phone') and contact.phone == phone.lstrip('+'):
                    self.logger.info(f"Найден контакт с ID: {contact.id}")
                    return contact.id
            
            # Если не нашли в контактах, пробуем через get_entity
            try:
                user = await self.client.get_entity(phone)
                self.logger.info(f"Успешно получен Telegram ID: {user.id} для телефона {phone}")
                return user.id
            except:
                pass
            
            self.logger.warning(f"Не удалось найти пользователя с телефоном {phone}")
            return None
            
        except Exception as e:
            self.logger.warning(f"Не удалось получить Telegram ID для телефона {phone}: {e}")
            return None
    
    async def enrich_student_data(self, student: StudentData) -> StudentData:
        """
        Обогащает данные студента, получая Telegram ID
        
        Args:
            student: Объект StudentData
        
        Returns:
            Обогащенный объект StudentData
        """
        # Если Telegram ID уже есть (извлечен из сообщения), пропускаем API-запросы
        if student.telegram_id:
            self.logger.info(f"Telegram ID уже есть в данных: {student.telegram_id}, пропускаем API-запросы")
            return student
        
        # Сначала пробуем получить ID по username
        if student.telegram_username:
            telegram_id = await self.get_telegram_id_by_username(student.telegram_username)
            if telegram_id:
                student.telegram_id = telegram_id
                return student
        
        # Если username не указан или не удалось получить ID, пробуем по телефону
        if student.phone and not student.telegram_id:
            self.logger.info(f"Username не указан или ID не получен, пробуем по телефону: {student.phone}")
            telegram_id = await self.get_telegram_id_by_phone(student.phone)
            if telegram_id:
                student.telegram_id = telegram_id
                # Получаем username если его не было
                if not student.telegram_username:
                    try:
                        user = await self.client.get_entity(telegram_id)
                        if user.username:
                            student.telegram_username = f"@{user.username}"
                    except:
                        pass
        
        return student
    
    async def analyze_chat_history(self, since_date: datetime) -> List[StudentData]:
        """
        Анализирует историю чата VIP-отдела и возвращает список новых студентов,
        которые появились с указанной даты.
        
        Args:
            since_date: Дата, начиная с которой нужно анализировать историю чата
            
        Returns:
            Список StudentData новых студентов
        """
        new_students = []
        
        try:
            # Преобразуем since_date в aware datetime если она naive
            if since_date.tzinfo is None:
                # Если дата naive, преобразуем её в aware с московским временем
                since_date = self.moscow_tz.localize(since_date)
            
            self.logger.info(f"Анализ истории чата VIP-отдела с {since_date}")
            
            # Получаем историю сообщений из чата VIP-отдела
            # Ограничиваем количество сообщений для оптимизации (последние 100 сообщений)
            async for message in self.client.iter_messages(
                VIP_DEPARTMENT_CHAT_ID, 
                limit=100,
                reverse=False  # Получаем от новых к старым
            ):
                # Проверяем, что сообщение имеет дату
                if hasattr(message, 'date') and message.date:
                    # Преобразуем дату сообщения в aware datetime если она naive
                    message_date = message.date
                    if message_date.tzinfo is None:
                        # Если дата сообщения naive, преобразуем её в aware с московским временем
                        message_date = self.moscow_tz.localize(message_date)
                    
                    # Проверяем, что сообщение после указанной даты
                    if message_date >= since_date:
                        # Проверяем, что сообщение от @zerocoder_news_bot
                        sender = await message.get_sender()
                        if sender and hasattr(sender, 'username') and sender.username:
                            if sender.username.lower() == ZEROCODER_NEWS_BOT.lower():
                                # Парсим данные студента из сообщения
                                student = self.parse_student_message(message.text, message.id)
                                if student:
                                    # Обогащаем данные студента
                                    student = await self.enrich_student_data(student)
                                    # Устанавливаем дату получения из сообщения
                                    student.date_received = message_date
                                    new_students.append(student)
                                    self.logger.info(f"Найден новый студент из истории: {student.name}")
                    elif message_date < since_date:
                        # Если мы дошли до сообщений старше указанной даты, прекращаем анализ
                        break
            
            self.logger.info(f"Анализ завершен. Найдено новых студентов: {len(new_students)}")
            
        except Exception as e:
            self.logger.error(f"Ошибка при анализе истории чата: {e}", exc_info=True)
        
        return new_students
    
    def setup_monitor(self, on_new_student_callback):
        """
        Настраивает мониторинг чата VIP-отдела
        
        Args:
            on_new_student_callback: Callback функция, вызываемая при получении нового студента
                                    Должна принимать StudentData как аргумент
        """
        # Сохраняем callback для использования в _handle_course_mapping_response
        self._on_new_student_callback = on_new_student_callback
        
        @self.client.on(events.NewMessage(chats=VIP_DEPARTMENT_CHAT_ID))
        async def handler(event):
            """Обработчик новых сообщений в чате VIP-отдела"""
            
            # Проверяем, что сообщение от @zerocoder_news_bot или @xenia108 (для тестирования)
            sender = await event.get_sender()
            
            if not sender or not hasattr(sender, 'username'):
                return
            
            # ИГНОРИРУЕМ сообщения от ботов @zerocoder_ultralina_bot и @Vipalina_zerocoder_bot
            if sender.username and sender.username.lower() in ['zerocoder_ultralina_bot', 'vipalina_zerocoder_bot']:
                return
            
            is_news_bot = sender.username and sender.username.lower() == ZEROCODER_NEWS_BOT.lower()
            is_test_user = sender.username and sender.username.lower() == TEST_USER.lower()
            
            if is_news_bot or is_test_user:
                self.logger.info(f"Получено сообщение от @{sender.username} {'(тестирование)' if is_test_user else ''}")
                
                message_text = event.message.text
                message_id = event.message.id
                
                # Парсим данные студента
                student = self.parse_student_message(message_text, message_id)
                
                if student:
                    # Обогащаем данные (получаем Telegram ID)
                    student = await self.enrich_student_data(student)
                    
                    # Вызываем callback - он сам определит, известен ли курс
                    await on_new_student_callback(student)
                else:
                    self.logger.warning(f"Не удалось распарсить данные студента из сообщения")
        
        self.logger.info(f"Мониторинг чата VIP-отдела ({VIP_DEPARTMENT_CHAT_ID}) настроен")
    
    async def _request_internal_course_name(self, event, student):
        """
        Запрашивает внутреннее название курса в чате.
        
        Args:
            event: Событие Telegram
            student: Данные студента
        """
        try:
            message = f"""🎓 **НЕИЗВЕСТНЫЙ КУРС**

Обнаружен новый студент с неизвестным курсом:

👤 **Студент:** {student.name}
🎯 **Курс с GetCourse:** {student.course}

Пожалуйста, укажите внутреннее название курса в формате:
`#этокурс Название курса`

Например: `#этокурс Чат-боты`
"""
            
            await event.reply(message)
            self.logger.info(f"Запрошено внутреннее название для курса: {student.course}")
            
        except Exception as e:
            self.logger.error(f"Ошибка при запросе внутреннего названия курса: {e}", exc_info=True)
    
    async def _handle_course_mapping_response(self, event):
        """
        Обрабатывает ответ с внутренним названием курса.
        
        Args:
            event: Событие Telegram
        """
        try:
            message_text = event.message.text
            
            # Извлекаем название курса из сообщения
            match = re.search(r'#этокурс\s+(.+)', message_text, re.IGNORECASE)
            if not match:
                return
            
            internal_name = match.group(1).strip()
            
            # Ищем последнее сообщение от @zerocoder_news_bot с неизвестным курсом
            # В реальной реализации лучше хранить это в базе данных или кэше
            messages = await self.client.get_messages(VIP_DEPARTMENT_CHAT_ID, limit=20)
            
            for msg in messages:
                if msg.sender and hasattr(msg.sender, 'username') and \
                   msg.sender.username and msg.sender.username.lower() == ZEROCODER_NEWS_BOT.lower():
                    
                    student = self.parse_student_message(msg.text, msg.id)
                    if student:
                        from course_config_v2 import CourseConfig
                        course_config = CourseConfig.get_course_by_tag(student.course)
                        
                        if not course_config:
                            # Найдено сообщение с неизвестным курсом
                            # Добавляем курс в маппинг
                            course_data = {
                                "internal_name": internal_name,
                                "airtable_name": internal_name,
                                "kpi_name": internal_name,
                                "tracker_name": internal_name,
                                "lesson_count": 50,  # Дефолтные значения
                                "access_days": 180,
                                "support_days": 90,
                                "monthly_target": 7,
                                "monthly_minimum": 7
                            }
                            
                            CourseConfig.add_custom_course(student.course, course_data)
                            
                            # Уведомляем о добавлении курса
                            response_msg = f"✅ Курс '{student.course}' добавлен в классификатор с внутренним названием '{internal_name}'"
                            await event.reply(response_msg)
                            
                            self.logger.info(f"Добавлен новый курс в классификатор: {student.course} -> {internal_name}")
                            
                            # Теперь можем обработать студента
                            student = await self.enrich_student_data(student)
                            
                            # Вызываем callback для обработки студента с новым курсом
                            if hasattr(self, '_on_new_student_callback') and self._on_new_student_callback:
                                await self._on_new_student_callback(student)
                            
                            break
            
        except Exception as e:
            self.logger.error(f"Ошибка при обработке ответа с внутренним названием курса: {e}", exc_info=True)


# Пример использования
if __name__ == "__main__":
    # Это только для демонстрации, в реальной работе будет интегрировано в vipalina_telethon.py
    
    async def on_new_student(student: StudentData):
        """Callback функция для обработки нового студента"""
        print(f"\n{'='*50}")
        print(f"Новый VIP-студент обнаружен!")
        print(f"{'='*50}")
        print(f"Имя: {student.name}")
        print(f"GetCourse ID: {student.getcourse_id}")
        print(f"GetCourse URL: {student.getcourse_url}")
        print(f"Email: {student.email}")
        print(f"Телефон: {student.phone}")
        print(f"Курс: {student.course}")
        print(f"Telegram username: {student.telegram_username}")
        print(f"Telegram ID: {student.telegram_id}")
        print(f"{'='*50}\n")
    
    print("Модуль мониторинга VIP чата готов к использованию")