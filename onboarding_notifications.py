"""
Модуль для уведомлений и обработки проблем во время онбординга студентов.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.functions.messages import CreateChatRequest

from config import VIP_ZEROCODER_BOT_USERNAME, VIP_DEPARTMENT_CHAT_ID

logger = logging.getLogger('vipalina_telethon')


class OnboardingNotifications:
    """
    Модуль для отправки уведомлений о прогрессе онбординга и обработки проблем.
    """
    
    def __init__(self, client: TelegramClient):
        self.client = client
    
    async def notify_onboarding_progress(self, stage: str, student_name: str, manager_name: str, details: str):
        """
        Отправляет уведомление о прогрессе онбординга в VIP-чат.
        
        Args:
            stage: Этап онбординга
            student_name: Имя студента
            manager_name: Имя менеджера
            details: Детали этапа
        """
        try:
            message = f"""🔄 **ОНБОРДИНГ: {stage}**

👤 **Студент:** {student_name}
👩‍💼 **Менеджер:** {manager_name}

📋 **Детали:** {details}
"""
            await self.client.send_message(VIP_DEPARTMENT_CHAT_ID, message)
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о прогрессе онбординга: {e}", exc_info=True)
    
    async def handle_student_privacy_issue(
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
            
            # Отправляем уведомление о проблеме приватности
            await self.notify_onboarding_progress(
                "Проблема приватности", 
                student_name, 
                manager_name, 
                "Невозможно добавить студента в группу из-за настроек приватности"
            )
            
            # Создаем приватный чат с менеджером и ботом для решения проблемы
            private_chat_info = await self._create_private_support_chat(
                manager_id=manager_id,
                manager_name=manager_name,
                student_name=student_name,
                student_telegram_id=student_telegram_id
            )
            
            if private_chat_info:
                private_chat_id = private_chat_info['chat_id']
                # Отправляем инструкции менеджеру в приватный чат
                instruction_message = f"""⚠️ **НЕВОЗМОЖНО СОЗДАТЬ УЧЕБНУЮ ГРУППУ**

👤 **Студент:** {student_name}
🆔 **Telegram ID:** {student_telegram_id or 'Не указан'}

**Причина:** Студент ограничил возможность добавления в группы.

**Что нужно сделать:**
1. Свяжитесь со студентом по email/телефону
2. Попросите его изменить настройки приватности:
   - Настройки → Конфиденциальность → Группы и каналы → Все пользователи
3. Или попросите студента написать боту первым: @{VIP_ZEROCODER_BOT_USERNAME}
4. После этого повторите попытку принятия студента

**Альтернатива:**
Создайте группу вручную:
1. Создайте новую группу в Telegram
2. Добавьте: студента, себя и @{VIP_ZEROCODER_BOT_USERNAME}
3. Назовите: "🎓 {student_name} | VIP"
4. Отправьте приветственное сообщение
"""
                await self.client.send_message(private_chat_id, instruction_message)
                
                # Отправляем уведомление об успешном создании приватного чата
                await self.notify_onboarding_progress(
                    "Создание приватного чата", 
                    student_name, 
                    manager_name, 
                    f"Создан приватный чат с инструкциями для менеджера (ID: {private_chat_id})"
                )
            
            # Отправляем сообщение студенту, если возможно
            if student_telegram_id:
                try:
                    welcome_message = f"""🎓 Здравствуйте, {student_name}!

Поздравляем с началом обучения в Zerocoder University! 🎉

Мы хотим создать для вас личный учебный чат, но не можем этого сделать из-за настроек приватности вашего аккаунта.

Пожалуйста, измените настройки приватности:
- Настройки → Конфиденциальность → Группы и каналы → Разрешить всем пользователям добавлять вас в группы

После этого ваш персональный менеджер сможет создать для вас учебный чат.

Если у вас возникнут вопросы, вы можете написать мне напрямую!

С уважением,
Команда Zerocoder University 🚀"""
                    await self.client.send_message(student_telegram_id, welcome_message)
                    logger.info(f"Отправлено сообщение студенту {student_name} с просьбой изменить настройки приватности")
                    
                    # Отправляем уведомление об отправке сообщения студенту
                    await self.notify_onboarding_progress(
                        "Сообщение студенту", 
                        student_name, 
                        manager_name, 
                        "Отправлено сообщение студенту с просьбой изменить настройки приватности"
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение студенту {student_name}: {e}")
                    # Отправляем уведомление об ошибке отправки сообщения студенту
                    await self.notify_onboarding_progress(
                        "Ошибка сообщения студенту", 
                        student_name, 
                        manager_name, 
                        f"Не удалось отправить сообщение студенту: {str(e)}"
                    )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке проблемы приватности для студента {student_data.get('name', 'Неизвестный студент')}: {e}", exc_info=True)
            # Отправляем уведомление об ошибке обработки проблемы приватности
            await self.notify_onboarding_progress(
                "Ошибка обработки приватности", 
                student_data.get('name', 'Неизвестный студент'), 
                manager_name, 
                f"Произошла ошибка при обработке проблемы приватности: {str(e)}"
            )
    
    async def _create_private_support_chat(
        self,
        manager_id: int,
        manager_name: str,
        student_name: str,
        student_telegram_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """
        Создает приватный чат с менеджером и ботом для решения проблемы приватности.
        
        Args:
            manager_id: Telegram ID менеджера
            manager_name: Имя менеджера
            student_name: Имя студента
            student_telegram_id: Telegram ID студента (если известен)
            
        Returns:
            Dict с информацией о чате (chat_id, chat_title) или None
        """
        try:
            # Получаем entity менеджера
            manager_entity = await self.client.get_entity(manager_id)
            
            # Получаем entity бота @vip_zerocode_bot
            bot_entity = await self.client.get_entity(VIP_ZEROCODER_BOT_USERNAME)
            
            # Создаем чат (обычная группа) с менеджером и ботом
            chat_title = f"⚠️ Проблема с {student_name}"
            # Используем тот же подход, что и в основном методе создания чата
            result = await self.client(CreateChatRequest(
                users=[manager_entity, bot_entity],
                title=chat_title
            ))
            
            # Получаем ID созданного чата
            chat_id = None
            if hasattr(result, 'chats') and result.chats:
                chat_id = result.chats[0].id
                if chat_id > 0:
                    chat_id = -chat_id
            
            if chat_id:
                logger.info(f"Создан приватный чат '{chat_title}' с ID: {chat_id}")
                return {
                    'chat_id': chat_id,
                    'chat_title': chat_title
                }
            else:
                logger.error("Не удалось получить ID созданного приватного чата")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при создании приватного чата с менеджером {manager_name}: {e}", exc_info=True)
            return None