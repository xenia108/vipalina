"""
Модуль авто-обновления "Следующее общение" при сообщениях менеджера.

Отслеживает сообщения менеджеров в чатах студентов и автоматически
сдвигает дату "Следующее общение" на +14 дней.
"""

import logging
from datetime import datetime, timedelta
from config import (
    VIP_MANAGERS_VIP,
    VIP_MANAGERS_LUXURY,
    VIP_HEAD,
    ON_DUTY_ACCOUNTS,
    NOCODB_FIELD_NEXT_CONTACT,
    NOCODB_FIELD_LAST_CONTACT
)

logger = logging.getLogger(__name__)


class TouchAutoUpdater:
    """
    Автоматическое обновление дат касаний при сообщениях менеджеров.
    """
    
    def __init__(self, nocodb_integration, vipalina_sheets=None):
        """
        Args:
            nocodb_integration: VipalinaNocoDBIntegration
            vipalina_sheets: VipalinaSheetIntegration (опционально)
        """
        self.nocodb = nocodb_integration
        self.vipalina_sheets = vipalina_sheets
        self.manager_ids = self._collect_manager_ids()
        
    def _collect_manager_ids(self) -> set:
        """Собирает все Telegram ID менеджеров"""
        ids = set()
        
        for manager in VIP_MANAGERS_VIP:
            ids.add(manager['telegram_id'])
        
        for manager in VIP_MANAGERS_LUXURY:
            ids.add(manager['telegram_id'])
        
        ids.add(VIP_HEAD['telegram_id'])
        
        for duty in ON_DUTY_ACCOUNTS:
            ids.add(duty['telegram_id'])
        
        return ids
    
    def is_manager(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь менеджером"""
        return user_id in self.manager_ids
    
    async def on_manager_message(self, getcourse_id: str):
        """
        Обрабатывает исходящее сообщение менеджера студенту.
        Обновляет "Следующее общение" = сегодня + 14 дней.
        
        Args:
            getcourse_id: ID студента из GetCourse
        """
        try:
            today = datetime.now()
            next_date = (today + timedelta(days=14)).date()
            next_date_str = next_date.strftime('%Y-%m-%d')
            
            # Обновляем только "Следующее общение" (менеджер написал)
            fields_to_update = {
                NOCODB_FIELD_NEXT_CONTACT: next_date_str
            }
            
            success = await self.nocodb.update_fields_by_getcourse_id(
                getcourse_id,
                fields_to_update
            )
            
            if success:
                logger.info(
                    f"✅ Авто-обновление для {getcourse_id}: "
                    f"следующее общение={next_date_str}"
                )
            else:
                logger.warning(f"Не удалось обновить даты для {getcourse_id}")
                
        except Exception as e:
            logger.error(f"Ошибка авто-обновления дат для {getcourse_id}: {e}", exc_info=True)
            
            # Уведомляем руководителя (если есть Telethon клиент)
            try:
                if hasattr(self, 'telethon_client') and self.telethon_client:
                    from config import VIP_HEAD
                    await self.telethon_client.send_message(
                        VIP_HEAD['telegram_id'],
                        f"⚠️ **Не удалось обновить дату касания**\n\n"
                        f"GetCourse ID: `{getcourse_id}`\n\n"
                        f"Менеджер написал, но NocoDB не обновился.\n"
                        f"Ошибка: {str(e)[:150]}"
                    )
            except:
                pass
