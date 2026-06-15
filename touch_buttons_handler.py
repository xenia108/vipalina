"""
Обработчик inline-кнопок для касаний студентов (weekly_reminders).

Обрабатывает нажатия кнопок:
- ✅ Написал → обновляет "Следующее общение" = сегодня + 14 дней
- ⏰ +7 дней → сдвигает "Следующее общение" на 7 дней вперёд
- ⏰ +14 дней → сдвигает "Следующее общение" на 14 дней вперёд
"""

import logging
from datetime import datetime, timedelta
from telethon import events
from config import NOCODB_FIELD_NEXT_CONTACT

logger = logging.getLogger(__name__)


def setup_touch_buttons_handler(client, nocodb_integration):
    """
    Регистрирует обработчик callback-кнопок касаний.
    
    Args:
        client: Telethon TelegramClient
        nocodb_integration: VipalinaNocoDBIntegration для обновления полей
    """
    
    @client.on(events.CallbackQuery(pattern=b'touch_'))
    async def handle_touch_buttons(event):
        """Обработчик inline-кнопок касаний"""
        try:
            data = event.data.decode('utf-8')
            
            # Парсим данные кнопки: touch_done:123456 или touch_delay_7:123456
            if ':' not in data:
                return
            
            parts = data.split(':', 1)
            action = parts[0]
            getcourse_id = parts[1]
            
            today = datetime.now().date()
            
            # Определяем новую дату следующего общения
            if action == 'touch_done':
                # Менеджер написал → +14 дней
                next_date = today + timedelta(days=14)
                message = f"✅ Касание зафиксировано. Следующее — {next_date.strftime('%d.%m.%Y')}"
            elif action == 'touch_delay_7':
                # Отложить на 7 дней
                next_date = today + timedelta(days=7)
                message = f"⏰ Касание отложено на 7 дней. Следующее — {next_date.strftime('%d.%m.%Y')}"
            elif action == 'touch_delay_14':
                # Отложить на 14 дней
                next_date = today + timedelta(days=14)
                message = f"⏰ Касание отложено на 14 дней. Следующее — {next_date.strftime('%d.%m.%Y')}"
            else:
                logger.warning(f"Неизвестное действие кнопки: {action}")
                return
            
            # Обновляем дату в NocoDB
            next_date_str = next_date.strftime('%Y-%m-%d')
            success = await nocodb_integration.update_fields_by_getcourse_id(
                getcourse_id,
                {NOCODB_FIELD_NEXT_CONTACT: next_date_str}
            )
            
            if success:
                await event.answer(message, alert=False)
                logger.info(f"✅ Обновлено 'Следующее общение' для {getcourse_id}: {next_date_str}")
            else:
                await event.answer("❌ Ошибка обновления даты", alert=True)
                logger.error(f"Не удалось обновить 'Следующее общение' для {getcourse_id}")
                
        except Exception as e:
            logger.error(f"Ошибка обработки кнопки касания: {e}", exc_info=True)
            try:
                await event.answer("❌ Произошла ошибка", alert=True)
            except:
                pass
    
    logger.info("✅ Обработчик кнопок касаний зарегистрирован")
