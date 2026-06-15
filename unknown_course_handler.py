#!/usr/bin/env python3
"""
Модуль для обработки неизвестных курсов и запроса их маппинга у менеджеров
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from telethon import TelegramClient

from config import VIP_DEPARTMENT_CHAT_ID, VIP_HEAD
from course_config_v2 import CourseConfig

logger = logging.getLogger('vipalina_telethon')


class UnknownCourseHandler:
    """
    Модуль для обработки неизвестных курсов.
    Запрашивает маппинг у менеджеров и добавляет новые курсы в систему.
    """
    
    def __init__(self, client: TelegramClient, onboarding_callback=None, tracker_creator=None):
        self.client = client
        self.onboarding_callback = onboarding_callback  # Колбэк для запуска онбординга
        self.tracker_creator = tracker_creator  # Для записи в классификатор
        self.pending_clarifications = {}  # {message_id: clarification_data} для хранения уточнений
        self.vip_department_chat_id = VIP_DEPARTMENT_CHAT_ID
        logger.info("Инициализирован обработчик неизвестных курсов")
    
    async def handle_unknown_course(
        self,
        student_data: Dict[str, Any],
        manager_id: int,
        candidates: Optional[list[str]] = None,
    ) -> bool:
        """
        Обрабатывает неизвестный курс, отправляя запрос на маппинг в чат VIP-отдела.
        
        Args:
            student_data: Данные о студенте
            manager_id: ID менеджера, который будет обрабатывать запрос
            
        Returns:
            True если запрос отправлен успешно
        """
        try:
            course_tag = student_data.get('course', '')
            student_name = student_data.get('name', 'Неизвестный студент')
            getcourse_id = student_data.get('getcourse_id', 'unknown')
            
            # Регистрируем неизвестный курс с данными студента
            request_id = CourseConfig.register_unknown_course(
                getcourse_tag=course_tag,
                student_data=student_data  # Передаём данные студента
            )
            
            # Формируем сообщение с запросом маппинга
            message = self._format_mapping_request(
                request_id=request_id,
                course_tag=course_tag,
                student_name=student_name,
                getcourse_id=getcourse_id,
                manager_id=manager_id,
                candidates=candidates,
            )
            
            # Отправляем сообщение в чат VIP-отдела
            await self.client.send_message(
                VIP_DEPARTMENT_CHAT_ID,
                message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Запрос маппинга для неизвестного курса '{course_tag}' отправлен в чат {VIP_DEPARTMENT_CHAT_ID}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса маппинга: {e}", exc_info=True)
            return False
    
    async def handle_ambiguous_course(
        self,
        student_data: Dict[str, Any],
        manager_id: int,
        candidates: list[Dict[str, Any]],
    ) -> bool:
        """
        Обрабатывает ситуацию, когда найдено несколько подходящих курсов.
        Отправляет запрос уточнения в чат VIP-отдела.
        
        Args:
            student_data: Данные о студенте
            manager_id: ID менеджера
            candidates: Список кандидатов (dict с getcourse_tag, internal_name, gant_sheet)
            
        Returns:
            True если запрос отправлен успешно
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
            
            # Отправляем сообщение
            sent_message = await self.client.send_message(
                self.vip_department_chat_id,
                message,
                parse_mode='Markdown'
            )
            
            # Сохраняем информацию для последующей обработки ответа
            import time
            self.pending_clarifications[sent_message.id] = {
                'type': 'ambiguous_course',
                'getcourse_id': getcourse_id,
                'student_name': student_name,
                'student_data': student_data,
                'original_tag': course_tag,
                'candidates': candidates,
                'timestamp': time.time()
            }
            
            logger.info(f"✅ Отправлен запрос уточнения курса для студента {getcourse_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке запроса уточнения: {e}", exc_info=True)
            return False
    
    async def handle_clarification_response(self, message) -> bool:
        """
        Обрабатывает ответ менеджера на уточнение курса.
        Формат: ответ на сообщение бота с номером варианта или названием курса.
        
        Args:
            message: Сообщение от менеджера
            
        Returns:
            True если ответ успешно обработан
        """
        try:
            # Проверяем, что это ответ на сообщение
            if not hasattr(message, 'reply_to_msg_id') or not message.reply_to_msg_id:
                return False
            
            replied_msg_id = message.reply_to_msg_id
            
            # Проверяем, есть ли это сообщение в наших подтверждениях
            if replied_msg_id not in self.pending_clarifications:
                return False
            
            clarification_data = self.pending_clarifications[replied_msg_id]
            
            # Проверяем тип уточнения
            if clarification_data['type'] != 'ambiguous_course':
                return False
            
            # Парсим ответ менеджера
            user_input = message.text.strip() if hasattr(message, 'text') and message.text else ""
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
                    self.vip_department_chat_id,
                    "❌ Не удалось определить выбранный курс. "
                    "Пожалуйста, укажите номер варианта (1, 2, 3...) или точное название.",
                    reply_to=message.id
                )
                return False
            
            # Подтверждение
            selected_name = selected_course.get('internal_name', selected_course.get('kpi_name', 'Unknown'))
            await self.client.send_message(
                self.vip_department_chat_id,
                f"✅ Выбран курс: **{selected_name}**\n"
                f"Запускаю онбординг студента...",
                parse_mode='Markdown',
                reply_to=message.id
            )
            
            # Удаляем из pending
            del self.pending_clarifications[replied_msg_id]
            
            # Обновляем курс в CourseConfig (временно, для этого студента)
            from course_config_v2 import CourseConfig
            original_tag = clarification_data['original_tag']
            selected_tag = selected_course.get('getcourse_tag', original_tag)
            
            # Добавляем временное соответствие для этого тега
            CourseConfig.COURSE_MAPPING[original_tag] = selected_course
            logger.info(f"📌 Добавлено временное соответствие: {original_tag} -> {selected_name}")
            
            # Запускаем онбординг с выбранным курсом
            if self.onboarding_callback:
                try:
                    student_data = clarification_data['student_data']
                    # Обновляем курс в student_data на ВЫБРАННОЕ НАЗВАНИЕ (internal_name/kpi_name)
                    # selected_course содержит данные курса из COURSE_MAPPING
                    selected_name = selected_course.get('internal_name') or selected_course.get('kpi_name', selected_tag)
                    student_data['course'] = selected_name
                    
                    logger.info(f"🚀 Запуск онбординга для студента {student_data.get('name')} с курсом {selected_name}...")
                    await self.onboarding_callback(student_data)
                    logger.info(f"✅ Онбординг запущен для студента {student_data.get('name')}")
                except Exception as e:
                    logger.error(f"❌ Ошибка при запуске онбординга: {e}", exc_info=True)
            else:
                logger.warning("⚠️ Нет onboarding_callback, онбординг не запущен")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке ответа на уточнение: {e}", exc_info=True)
            return False
    
    def _format_mapping_request(
        self,
        request_id: str,
        course_tag: str,
        student_name: str,
        getcourse_id: str,
        manager_id: int,
        candidates: Optional[list[str]] = None,
    ) -> str:
        """
        Форматирует сообщение с запросом маппинга курса.
        
        Args:
            request_id: ID запроса
            course_tag: Тег курса из GetCourse
            student_name: Имя студента
            getcourse_id: ID студента в GetCourse
            manager_id: ID менеджера
            candidates: Необязательный список возможных внутренних названий курса
        
        Returns:
            Отформатированное сообщение
        """
        message = f"""🚨 **Новый курс, требующий уточнения!**

Нужно определить внутреннее название для курса:

**Тег курса из GetCourse:** `{course_tag}`

**Студент:**
{student_name} (ID: {getcourse_id})
"""

        # Если есть кандидаты, показываем их как подсказку
        if candidates:
            message += "\nВозможные варианты по данным системы:\n\n"
            for idx, name in enumerate(candidates, start=1):
                message += f"{idx}) {name}\n"
            message += "\n**Инструкция:**\n" \
                       "1. Выберите корректный вариант из списка выше или укажите своё название.\n" \
                       "2. Ответьте на это сообщение с тегом `#этокурс` и НУЖНЫМ внутренним названием курса.\n" \
                       "3. Например: `#этокурс Промпт-инженер 3.0, VIP Плюс`\n"
        else:
            message += "\n**Инструкция:**\n" \
                       "1. Определите внутреннее название курса.\n" \
                       "2. Ответьте на это сообщение с тегом `#этокурс` и внутренним названием курса.\n" \
                       "3. Например: `#этокурс Новый курс 2025, VIP`\n"

        message += f"""\n**Request ID:** `{request_id[:8]}...`
"""
        
        return message
    
    async def process_mapping_response(self, message) -> bool:
        """
        Обрабатывает ответ с маппингом курса.
        
        Args:
            message: Сообщение с маппингом курса
            
        Returns:
            True если маппинг успешно обработан
        """
        try:
            logger.info(f"📥 Получено сообщение: {message.text if hasattr(message, 'text') else 'NO TEXT'}")
            
            # Проверяем, что сообщение содержит тег #этокурс
            if not hasattr(message, 'text') or not message.text or '#этокурс' not in message.text.lower():
                logger.debug("Сообщение не содержит #этокурс")
                return False
            
            # Извлекаем внутреннее название курса из ответа
            internal_name = self._extract_internal_name(message.text)
            if not internal_name:
                logger.warning("Не удалось извлечь внутреннее название курса из сообщения с #этокурс")
                return False
            
            # Ищем оригинальное сообщение с запросом маппинга
            original_message = None
            course_tag = None
            request_id = None
            
            # Вариант 1: Пользователь ответил на сообщение (reply_to)
            if hasattr(message, 'reply_to_msg_id') and message.reply_to_msg_id:
                logger.info("Обнаружен ответ на сообщение, получаем оригинальное сообщение...")
                original_message = await self.client.get_messages(
                    VIP_DEPARTMENT_CHAT_ID,
                    ids=message.reply_to_msg_id
                )
                
                if original_message:
                    original_text = original_message[0].text if isinstance(original_message, list) and len(original_message) > 0 else getattr(original_message, 'text', None)
                    if original_text:
                        request_id = self._extract_request_id(original_text)
                        course_tag = self._extract_course_tag(original_text)
                        if course_tag:
                            # Очищаем от кавычек
                            course_tag = course_tag.strip('`').strip()
                            logger.info(f"Из ответа извлечен тег курса: {course_tag}")
            
            # Вариант 2: Пользователь просто написал #этокурс в чате (без ответа)
            # Ищем последнее сообщение с запросом маппинга в чате
            if not course_tag:
                logger.info("Нет ответа на сообщение, ищем последний запрос маппинга в чате...")
                recent_messages = await self.client.get_messages(
                    VIP_DEPARTMENT_CHAT_ID,
                    limit=30  # Проверяем последние 30 сообщений
                )
                
                # Получаем ID бота (самого себя)
                bot_id = (await self.client.get_me()).id
                logger.info(f"🤖 ID бота: {bot_id}")
                
                # Сначала пытаемся найти request_id из сообщений бота с "Request ID"
                temp_request_id = None
                for msg in recent_messages:
                    # Проверяем, что сообщение от бота и содержит Request ID
                    if not msg.text or msg.sender_id != bot_id or "Request ID" not in msg.text:
                        continue
                    temp_request_id = self._extract_request_id(msg.text)
                    if temp_request_id:
                        logger.info(f"🔍 Найден request_id в сообщении бота: {temp_request_id}")
                        break
                
                # Если нашли request_id, получаем course_tag из UNKNOWN_COURSES
                if temp_request_id and temp_request_id in CourseConfig.UNKNOWN_COURSES:
                    unknown_course_data = CourseConfig.UNKNOWN_COURSES[temp_request_id]
                    course_tag = unknown_course_data.get('getcourse_tag')
                    request_id = temp_request_id
                    logger.info(f"✅ Из UNKNOWN_COURSES получен тег курса: {course_tag}")
                else:
                    if temp_request_id:
                        logger.warning(f"⚠️ Request ID {temp_request_id} не найден в UNKNOWN_COURSES")
                
                # Если не нашли через request_id, пробуем старый способ (поиск по маркерам)
                if not course_tag:
                    logger.info("Ищем курс по маркерам в сообщениях...")
                    for msg in recent_messages:
                        if not msg.text:
                            continue
                        
                        # Ищем сообщение с запросом маппинга (содержит "🎓" или "НЕИЗВЕСТНЫЙ КУРС" или "Тег курса из GetCourse")
                        if any(marker in msg.text for marker in ["🎓", "НЕИЗВЕСТНЫЙ КУРС", "Курс с GetCourse:"]):
                            # Пробуем извлечь тег курса из разных форматов
                            course_tag = self._extract_course_tag(msg.text)
                            if not course_tag:
                                # Альтернативный формат: "🎯 Курс с GetCourse: [tag] Name"
                                course_tag = self._extract_course_tag_alternative(msg.text)
                            
                            if course_tag:
                                request_id = self._extract_request_id(msg.text) if "Request ID" in msg.text else None
                                logger.info(f"Найден запрос маппинга в последних сообщениях (по маркерам), тег: {course_tag}")
                                break
            
            if not course_tag:
                logger.warning("Не удалось найти запрос маппинга курса")
                await self.client.send_message(
                    VIP_DEPARTMENT_CHAT_ID,
                    "⚠️ Не найден запрос маппинга курса. Пожалуйста, ответьте на сообщение с запросом или напишите тег курса в формате:\n`#этокурс [tag] Название курса, VIP`",
                    parse_mode='Markdown',
                    reply_to=message.id
                )
                return False
            
            # Получаем данные студента из UNKNOWN_COURSES
            student_data = None
            if request_id and request_id in CourseConfig.UNKNOWN_COURSES:
                student_data = CourseConfig.UNKNOWN_COURSES[request_id].get('student_data')
                # Удаляем из списка ожидания
                del CourseConfig.UNKNOWN_COURSES[request_id]
            
            # Добавляем курс в маппинг
            course_mapping = self._create_course_mapping(internal_name)
            CourseConfig.add_custom_course(course_tag, course_mapping)
            
            # Пишем в классификатор курсов (трекер), если есть tracker_creator
            if self.tracker_creator:
                try:
                    await asyncio.to_thread(
                        self.tracker_creator.add_course_to_classifier,
                        getcourse_tag=course_tag,
                        internal_name=internal_name
                    )
                    logger.info(f"✅ Курс '{course_tag}' добавлен в классификатор")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось добавить курс в классификатор: {e}")
            
            # Формируем подтверждение
            confirmation_message = f"""✅ **Курс добавлен!**

**Тег GetCourse:** `{course_tag}`
**Внутреннее название:** {internal_name}

"""
            confirmation_message += "Теперь этот курс будет распознаваться автоматически для новых студентов."
            
            await self.client.send_message(
                VIP_DEPARTMENT_CHAT_ID,
                confirmation_message,
                parse_mode='Markdown',
                reply_to=message.id
            )
            
            logger.info(f"✅ Курс '{course_tag}' успешно добавлен в систему с внутренним названием '{internal_name}'")
            
            # Запускаем онбординг для студента, если есть его данные
            if student_data and self.onboarding_callback:
                try:
                    logger.info(f"🚀 Запуск онбординга для студента {student_data.get('name')}...")
                    
                    # Обновляем курс в student_data с новым маппингом
                    student_data['course'] = course_tag
                    
                    # Запускаем онбординг
                    await self.onboarding_callback(student_data)
                    
                    logger.info(f"✅ Онбординг запущен для студента {student_data.get('name')}")
                except Exception as e:
                    logger.error(f"❌ Ошибка при запуске онбординга: {e}", exc_info=True)
            elif student_data and not self.onboarding_callback:
                logger.warning("⚠️ Нет onboarding_callback, онбординг не запущен")
            else:
                logger.info("ℹ️ Нет данных студента, онбординг не требуется")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обработке ответа с маппингом: {e}", exc_info=True)
            return False
    
    @staticmethod
    def _extract_request_id(message_text: str) -> Optional[str]:
        """
        Извлекает Request ID из текста сообщения.
        
        Args:
            message_text: Текст сообщения
            
        Returns:
            Request ID или None
        """
        import re
        # Ищем Request ID в формате UUID (полный или сокращённый с ...)
        # Полный: Request ID: 9ac2f80d-e018-4b89-a4c3-fddef6c0a54c
        # Сокращённый: Request ID: `9ac2f80d...`
        match = re.search(r'Request\s+ID[:\s*`\'"]*([a-f0-9]{8})', message_text, re.IGNORECASE)
        if match:
            short_id = match.group(1)
            # Ищем полный UUID в UNKNOWN_COURSES по первым 8 символам
            from course_config_v2 import CourseConfig
            for full_id in CourseConfig.UNKNOWN_COURSES.keys():
                if full_id.startswith(short_id):
                    logger.info(f"✅ Найден полный request_id: {full_id} по сокращённому: {short_id}")
                    return full_id
        logger.debug(f"⚠️ Request ID не найден в тексте: {message_text[:200]}")
        return None
    
    @staticmethod
    def _extract_internal_name(message_text: str) -> Optional[str]:
        """
        Извлекает внутреннее название курса из текста сообщения.
        
        Args:
            message_text: Текст сообщения
            
        Returns:
            Внутреннее название курса или None
        """
        import re
        logger.debug(f"Попытка извлечь внутреннее название из текста: '{message_text}'")
        
        # Основной паттерн: #этокурс Название курса
        # Поддерживаем варианты: #этокурс, `#этокурс`, **#этокурс**
        match = re.search(r'[`*]*#этокурс[`*]*\s+(.+)', message_text, re.IGNORECASE)
        if match:
            result = match.group(1).strip()
            logger.info(f"✅ Извлечено внутреннее название: '{result}'")
            return result
        
        logger.warning(f"❌ Не удалось извлечь название из текста: '{message_text[:100]}'")
        return None
    
    @staticmethod
    def _extract_course_tag(message_text: str) -> Optional[str]:
        """
        Извлекает тег курса из текста сообщения.
        
        Args:
            message_text: Текст сообщения
            
        Returns:
            Тег курса или None
        """
        import re
        # Новый формат: Тег курса из GetCourse: `[buba] Как быть Бубой`
        match = re.search(r'Тег курса из GetCourse:\s*`(.+?)`', message_text, re.DOTALL)
        if match:
            course_tag = match.group(1).strip()
            # Убираем возможные кавычки внутри
            course_tag = course_tag.strip('`').strip()
            return course_tag
        
        # Старый формат с блоком кода (для совместимости)
        match = re.search(r'Тег курса из GetCourse:\s*```\s*(.+?)\s*```', message_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Формат с жирным шрифтом
        match = re.search(r'Тег курса из GetCourse:\s*\*\*\s*(.+?)\s*\*\*', message_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Простой текст
        match = re.search(r'Тег курса из GetCourse:\s*\n(.+?)\n', message_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        return None
    
    @staticmethod
    def _extract_course_tag_alternative(message_text: str) -> Optional[str]:
        """
        Извлекает тег курса из альтернативного формата (🎯 Курс с GetCourse: [tag] Name).
        
        Args:
            message_text: Текст сообщения
            
        Returns:
            Тег курса или None
        """
        import re
        # 🎯 Курс с GetCourse: [tili] Тилимилитрямдия
        # или 🎯 **Курс с GetCourse:** [tili] Тилимилитрямдия (с Markdown форматированием)
        match = re.search(r'🎯\s*\*{0,2}Курс с GetCourse:\*{0,2}\s*(.+?)\s*(?:\n|$)', message_text, re.IGNORECASE)
        if match:
            course_tag = match.group(1).strip()
            # Убираем Markdown форматирование (* и **)
            course_tag = course_tag.strip('*').strip()
            return course_tag
        
        # Пробуем без emoji
        match = re.search(r'\*{0,2}Курс с GetCourse:\*{0,2}\s*(.+?)\s*(?:\n|$)', message_text, re.IGNORECASE)
        if match:
            course_tag = match.group(1).strip()
            # Убираем Markdown форматирование
            course_tag = course_tag.strip('*').strip()
            return course_tag
        
        return None
    
    @staticmethod
    def _create_course_mapping(internal_name: str) -> Dict[str, Any]:
        """
        Создает маппинг курса на основе внутреннего названия.
        
        Args:
            internal_name: Внутреннее название курса
            
        Returns:
            Данные курса для маппинга
        """
        # Создаем базовый маппинг на основе внутреннего названия
        return {
            'internal_name': internal_name,
            'airtable_name': internal_name,
            'kpi_name': internal_name,
            'tracker_name': internal_name.split(',')[0].strip(),  # Берем первую часть до запятой
            'gant_sheet': '',  # Пустой лист ГАНТ по умолчанию
            'lesson_count': 50,  # Дефолтное значение
            'access_days': 360,  # Дефолтное значение (12 месяцев)
            'curator_support_days': 180,  # Дефолтное значение (6 месяцев)
            'vip_support_days': 360,  # Дефолтное значение (12 месяцев)
            'monthly_target': 7,  # Дефолтное значение
            'monthly_minimum': 7,  # Дефолтное значение
        }