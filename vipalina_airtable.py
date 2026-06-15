"""
Модуль интеграции VipAlina с Airtable.
Управляет таблицей "Новые" студенты - обновление поля "Менеджер" после принятия.

Фаза 1 автоматизации: Базовая интеграция с Airtable
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from api_utils import retry_async, AirtableAPIError

logger = logging.getLogger('vipalina_telethon')

# TODO: Установить библиотеку pyairtable
# pip install pyairtable

try:
    from pyairtable import Api
    AIRTABLE_AVAILABLE = True
except ImportError:
    AIRTABLE_AVAILABLE = False
    logger.warning("pyairtable не установлен. Установите: pip install pyairtable")


class VipalinaAirtableIntegration:
    """
    Интеграция VipAlina с Airtable.
    Управляет таблицей "Новые" - автоматическое обновление менеджера.
    """
    
    def __init__(
        self,
        api_key: str,
        base_id: str,
        table_id: str
    ):
        """
        Инициализация интеграции с Airtable.
        
        Args:
            api_key: API ключ Airtable
            base_id: ID базы данных
            table_id: ID таблицы (вместо названия)
        """
        if not AIRTABLE_AVAILABLE:
            raise ImportError("Библиотека pyairtable не установлена")
        
        self.api_key = api_key
        self.base_id = base_id
        self.table_id = table_id
        
        # Инициализация API
        self.api = Api(api_key)
        self.table = self.api.table(base_id, table_id)
        
        logger.info(f"Инициализирована интеграция с Airtable: база {base_id}, таблица {table_id}")
    
    @retry_async(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(AirtableAPIError, Exception))
    async def find_student_by_getcourse_id(
        self,
        getcourse_id: str,
        getcourse_field: str = "ID пользователя"
    ) -> Optional[Dict[str, Any]]:
        """
        Находит студента в таблице "Новые" по GetCourse ID.
        
        Args:
            getcourse_id: ID студента из GetCourse
            getcourse_field: Название поля в Airtable с GetCourse ID
            
        Returns:
            Dict с данными записи или None если не найдено
        """
        try:
            # Формируем фильтр для поиска
            formula = f"{{{getcourse_field}}} = '{getcourse_id}'"
            
            logger.info(f"Поиск студента в Airtable по GetCourse ID: {getcourse_id}")
            
            # Выполняем поиск
            records = self.table.all(formula=formula)
            
            if not records:
                logger.warning(f"Студент с GetCourse ID {getcourse_id} не найден в Airtable")
                return None
            
            if len(records) > 1:
                logger.warning(f"Найдено несколько записей для GetCourse ID {getcourse_id}, используем первую")
            
            record = records[0]
            
            logger.info(f"Студент найден в Airtable: record_id={record['id']}")
            
            return {
                'id': record['id'],
                'fields': record['fields'],
                'created_time': record.get('createdTime'),
                'record_url': f"https://airtable.com/{self.base_id}/{self.table_id}/{record['id']}"
            }
            
        except Exception as e:
            logger.error(f"Ошибка при поиске студента {getcourse_id} в Airtable: {e}", exc_info=True)
            return None
    
    @retry_async(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(AirtableAPIError, Exception))
    async def update_manager_field(
        self,
        record_id: str,
        manager_name: str,
        manager_field: str = "Менеджер"
    ) -> bool:
        """
        Обновляет поле "Менеджер" для записи студента.
        
        Args:
            record_id: ID записи в Airtable
            manager_name: Имя менеджера для записи
            manager_field: Название поля менеджера в Airtable
            
        Returns:
            True если обновление успешно
        """
        try:
            logger.info(f"Обновление менеджера в Airtable: record_id={record_id}, manager={manager_name}")
            
            # ВАЖНО: Поле "Менеджер" в Airtable - это MULTIPLE SELECT
            # Требуется формат: массив строк ['Имя Менеджера']
            updated_record = self.table.update(
                record_id,
                {manager_field: [manager_name]}  # Массив строк!
            )
            
            logger.info(f"Менеджер успешно обновлен в Airtable для записи {record_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении менеджера в Airtable для записи {record_id}: {e}", exc_info=True)
            return False
    
    async def get_student_data(
        self,
        getcourse_id: str,
        getcourse_field: str = "ID пользователя"
    ) -> Optional[Dict[str, Any]]:
        """
        Получает полные данные студента из Airtable.
        
        Args:
            getcourse_id: ID студента из GetCourse
            getcourse_field: Название поля в Airtable с GetCourse ID
            
        Returns:
            Dict с данными студента или None
        """
        record = await self.find_student_by_getcourse_id(getcourse_id, getcourse_field)
        
        if not record:
            return None
        
        fields = record['fields']
        
        # Формируем стандартизированный объект данных
        student_data = {
            'record_id': record['id'],
            'getcourse_id': getcourse_id,
            'name': fields.get('Имя', ''),
            'course': fields.get('Курс', ''),
            'email': fields.get('Email', ''),
            'phone': fields.get('Телефон', ''),
            'telegram': fields.get('Telegram', ''),
            'manager': fields.get('Менеджер', ''),
            'record_url': record['record_url'],
            'created_time': record.get('created_time'),
            # Сохраняем все остальные поля как есть
            'raw_fields': fields
        }
        
        return student_data
    
    async def sync_after_manager_acceptance(
        self,
        getcourse_id: str,
        manager_name: str,
        bot_manager_name: str,
        getcourse_field: str = "ID пользователя",
        manager_field: str = "Менеджер"
    ) -> Dict[str, Any]:
        """
        Полная синхронизация после того, как менеджер принял студента.
        
        Args:
            getcourse_id: ID студента из GetCourse
            manager_name: Имя менеджера для Airtable
            bot_manager_name: Имя менеджера из бота (для логирования)
            getcourse_field: Название поля GetCourse ID
            manager_field: Название поля менеджера
            
        Returns:
            Dict с результатами синхронизации
        """
        try:
            # 1. Поиск студента
            student = await self.find_student_by_getcourse_id(getcourse_id, getcourse_field)
            
            if not student:
                return {
                    'success': False,
                    'error': f"Студент {getcourse_id} не найден в Airtable",
                    'step': 'find_student'
                }
            
            # 2. Обновление менеджера
            update_success = await self.update_manager_field(
                record_id=student['id'],
                manager_name=manager_name,
                manager_field=manager_field
            )
            
            if not update_success:
                return {
                    'success': False,
                    'error': f"Не удалось обновить менеджера для записи {student['id']}",
                    'step': 'update_manager',
                    'student_data': student
                }
            
            # 3. Успех
            logger.info(f"✅ Airtable синхронизирован: студент {getcourse_id} → менеджер {manager_name}")
            
            return {
                'success': True,
                'student_data': student,
                'manager_name': manager_name,
                'bot_manager_name': bot_manager_name,
                'record_id': student['id'],
                'record_url': student['record_url']
            }
            
        except Exception as e:
            logger.error(f"Ошибка при синхронизации студента {getcourse_id} с Airtable: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'step': 'unknown'
            }
    
    def get_manager_airtable_name(self, bot_manager_name: str) -> str:
        """
        Преобразует имя менеджера из бота в формат Airtable.
        
        Маппинг имен (бот → Airtable):
        - Все имена теперь одинаковые в боте и Airtable
        - Марина Иванова заменила Марину Ермолову
        
        Args:
            bot_manager_name: Имя менеджера в боте
            
        Returns:
            Имя менеджера для Airtable
        """
        # Все имена теперь синхронизированы
        # Марина Иванова - это новое имя, которое используется везде
        return bot_manager_name


# Функция для быстрой инициализации из конфига
def create_airtable_integration(
    api_key: str,
    base_id: str,
    table_id: str
) -> VipalinaAirtableIntegration:
    """
    Создает и возвращает экземпляр интеграции с Airtable.
    
    Args:
        api_key: API ключ Airtable
        base_id: ID базы данных
        table_id: ID таблицы
        
    Returns:
        VipalinaAirtableIntegration: Готовый к работе объект интеграции
    """
    return VipalinaAirtableIntegration(
        api_key=api_key,
        base_id=base_id,
        table_id=table_id
    )
