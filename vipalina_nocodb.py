"""
Модуль интеграции VipAlina с NocoDB.
Управляет таблицей "Ученики все" (вьюшка "Новенькие") - обновление поля "Менеджер" после принятия.

Заменяет интеграцию с Airtable.
"""

import logging
import httpx
from typing import Optional, Dict, Any, List
from api_utils import retry_async, AirtableAPIError

logger = logging.getLogger('vipalina_nocodb')


class VipalinaNocoDBIntegration:
    """
    Интеграция VipAlina с NocoDB.
    Управляет таблицей "Ученики все" - автоматическое обновление менеджера.
    """
    
    def __init__(
        self,
        api_url: str,
        api_token: str,
        base_id: str,
        table_id: str,
        view_id: Optional[str] = None
    ):
        """
        Инициализация интеграции с NocoDB.
        
        Args:
            api_url: URL NocoDB инстанса (без trailing slash)
            api_token: API токен для доступа
            base_id: ID базы данных (workspace)
            table_id: ID таблицы "Ученики все"
            view_id: ID вьюшки "Новенькие" (опционально)
        """
        self.api_url = api_url.rstrip('/')
        self.api_token = api_token
        self.base_id = base_id
        self.table_id = table_id
        self.view_id = view_id
        
        self.headers = {
            'xc-token': api_token,
            'Content-Type': 'application/json'
        }
        
        logger.info(f"✅ Инициализирована интеграция с NocoDB: {api_url}")
        logger.info(f"   База: {base_id}, Таблица: {table_id}")
        if view_id:
            logger.info(f"   Вьюшка: {view_id}")
    
    def _get_base_url(self) -> str:
        """Возвращает базовый URL для API запросов к таблице"""
        return f"{self.api_url}/api/v2/tables/{self.table_id}/records"
    
    def _get_update_url(self, record_id: int) -> str:
        """
        Возвращает URL для обновления записи.
        Использует API v1 для PATCH запросов.
        """
        return f"{self.api_url}/api/v1/db/data/noco/{self.base_id}/{self.table_id}/{record_id}"
    
    @retry_async(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(AirtableAPIError, Exception))
    async def find_student_by_getcourse_id(
        self,
        getcourse_id: str,
        getcourse_field: str = "ID пользователя",
        use_view: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Находит студента в таблице "Ученики все" по GetCourse ID.
        
        Args:
            getcourse_id: ID студента из GetCourse
            getcourse_field: Название поля в NocoDB с GetCourse ID
            use_view: Использовать ли view_id для фильтрации (для /testreminder нужно False)
            
        Returns:
            Dict с данными записи или None если не найдено
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = self._get_base_url()
                
                # NocoDB фильтр: where=(field,eq,value)
                params = {
                    'where': f"({getcourse_field},eq,{getcourse_id})",
                    'limit': 1
                }
                
                # Используем view_id только если use_view=True
                if use_view and self.view_id:
                    params['viewId'] = self.view_id
                
                logger.info(f"🔍 Поиск студента в NocoDB по GetCourse ID: {getcourse_id}")
                
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                records = data.get('list', [])
                
                if not records:
                    logger.warning(f"⚠️ Студент с GetCourse ID {getcourse_id} не найден в NocoDB")
                    return None
                
                if len(records) > 1:
                    logger.warning(f"⚠️ Найдено несколько записей для GetCourse ID {getcourse_id}, используем первую")
                
                record = records[0]
                record_id = record.get('Id') or record.get('id')
                
                logger.info(f"✅ Студент найден в NocoDB: record_id={record_id}")
                
                return {
                    'id': record_id,
                    'fields': record,
                    'record_url': f"{self.api_url}/dashboard/#/nc/{self.base_id}/{self.table_id}/{record_id}"
                }
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP ошибка при поиске студента {getcourse_id}: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске студента {getcourse_id} в NocoDB: {e}", exc_info=True)
            return None
    
    @retry_async(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(AirtableAPIError, Exception))
    async def update_manager_field(
        self,
        record_id: int,
        manager_name: str,
        manager_field: str = "Менеджер"
    ) -> bool:
        """
        Обновляет поле "Менеджер" для записи студента.
        
        Args:
            record_id: ID записи в NocoDB
            manager_name: Имя менеджера для записи
            manager_field: Название поля менеджера в NocoDB
            
        Returns:
            True если обновление успешно
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = self._get_update_url(record_id)
                
                # Payload для обновления
                payload = {
                    manager_field: manager_name
                }
                
                logger.info(f"🔄 Обновление менеджера в NocoDB: record_id={record_id}, manager={manager_name}")
                
                response = await client.patch(url, headers=self.headers, json=payload)
                response.raise_for_status()
                
                logger.info(f"✅ Менеджер успешно обновлен в NocoDB для записи {record_id}")
                return True
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP ошибка при обновлении менеджера: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении менеджера в NocoDB для записи {record_id}: {e}", exc_info=True)
            return False
    
    @retry_async(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(AirtableAPIError, Exception))
    async def update_student_dates(
        self,
        record_id: int,
        date_fields: Dict[str, str]
    ) -> bool:
        """
        Обновляет поля с датами для записи студента.
        
        Args:
            record_id: ID записи в NocoDB
            date_fields: Словарь {название_поля: дата} для обновления
            
        Returns:
            True если обновление успешно
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = self._get_update_url(record_id)
                
                logger.info(f"🔄 Обновление дат в NocoDB: record_id={record_id}, поля={list(date_fields.keys())}")
                
                response = await client.patch(url, headers=self.headers, json=date_fields)
                response.raise_for_status()
                
                logger.info(f"✅ Даты успешно обновлены в NocoDB для записи {record_id}")
                return True
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP ошибка при обновлении дат: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении дат в NocoDB для записи {record_id}: {e}", exc_info=True)
            return False
    
    @retry_async(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(AirtableAPIError, Exception))
    async def update_fields_by_getcourse_id(
        self,
        getcourse_id: str,
        fields: Dict[str, Any],
        getcourse_field: str = "ID пользователя",
        use_view: bool = False
    ) -> bool:
        """
        Универсальное обновление полей студента по GetCourse ID.
        
        Args:
            getcourse_id: ID студента из GetCourse
            fields: Словарь {название_поля: значение} для обновления
            getcourse_field: Название поля в NocoDB с GetCourse ID
            use_view: Использовать ли view фильтр (по умолчанию False - по всей таблице)
            
        Returns:
            True если обновление успешно
        """
        try:
            # Сначала находим студента (без view фильтра для кнопок)
            record = await self.find_student_by_getcourse_id(getcourse_id, getcourse_field, use_view=use_view)
            if not record:
                logger.warning(f"⚠️ Студент {getcourse_id} не найден в NocoDB для обновления")
                return False
            
            record_id = record['id']
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = self._get_update_url(record_id)
                
                logger.info(f"🔄 Обновление полей в NocoDB: getcourse_id={getcourse_id}, поля={list(fields.keys())}")
                
                response = await client.patch(url, headers=self.headers, json=fields)
                response.raise_for_status()
                
                logger.info(f"✅ Поля успешно обновлены в NocoDB для студента {getcourse_id}")
                return True
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP ошибка при обновлении полей: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении полей в NocoDB для студента {getcourse_id}: {e}", exc_info=True)
            return False
    
    async def get_student_data(
        self,
        getcourse_id: str,
        getcourse_field: str = "ID пользователя"
    ) -> Optional[Dict[str, Any]]:
        """
        Получает полные данные студента из NocoDB.
        
        Args:
            getcourse_id: ID студента из GetCourse
            getcourse_field: Название поля в NocoDB с GetCourse ID
            
        Returns:
            Dict с данными студента или None
        """
        record = await self.find_student_by_getcourse_id(getcourse_id, getcourse_field)
        
        if not record:
            return None
        
        fields = record['fields']
        
        # Формируем стандартизированный объект данных (совместимый с Airtable API)
        student_data = {
            'record_id': record['id'],
            'getcourse_id': getcourse_id,
            'name': fields.get('Студент', '') or fields.get('Имя', ''),
            'course': fields.get('Курс', ''),
            'email': fields.get('Email', ''),
            'phone': fields.get('Телефон', ''),
            'telegram': fields.get('Telegram', ''),
            'manager': fields.get('Менеджер', ''),
            'record_url': record['record_url'],
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
            manager_name: Имя менеджера для NocoDB
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
                    'error': f"Студент {getcourse_id} не найден в NocoDB",
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
            logger.info(f"✅ NocoDB синхронизирован: студент {getcourse_id} → менеджер {manager_name}")
            
            return {
                'success': True,
                'student_data': student,
                'manager_name': manager_name,
                'bot_manager_name': bot_manager_name,
                'record_id': student['id'],
                'record_url': student['record_url']
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при синхронизации студента {getcourse_id} с NocoDB: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'step': 'unknown'
            }
    
    def get_manager_nocodb_name(self, bot_manager_name: str) -> str:
        """
        Преобразует имя менеджера из бота в формат NocoDB.
        
        Args:
            bot_manager_name: Имя менеджера в боте
            
        Returns:
            Имя менеджера для NocoDB
        """
        # Имена синхронизированы между системами
        return bot_manager_name
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Тестирует подключение к NocoDB.
        
        Returns:
            Dict с результатами теста
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = self._get_base_url()
                params = {'limit': 1}
                
                logger.info("🧪 Тестирование подключения к NocoDB...")
                
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                logger.info(f"✅ Подключение к NocoDB успешно! Найдено записей: {data.get('pageInfo', {}).get('totalRows', 0)}")
                
                return {
                    'success': True,
                    'total_rows': data.get('pageInfo', {}).get('totalRows', 0),
                    'message': 'Подключение успешно'
                }
                
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"❌ Ошибка подключения к NocoDB: {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }
        except Exception as e:
            logger.error(f"❌ Ошибка при тестировании подключения: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }


# Функция для быстрой инициализации из конфига
def create_nocodb_integration(
    api_url: str,
    api_token: str,
    base_id: str,
    table_id: str,
    view_id: Optional[str] = None
) -> VipalinaNocoDBIntegration:
    """
    Создает и возвращает экземпляр интеграции с NocoDB.
    
    Args:
        api_url: URL NocoDB инстанса
        api_token: API токен
        base_id: ID базы данных
        table_id: ID таблицы
        view_id: ID вьюшки (опционально)
        
    Returns:
        VipalinaNocoDBIntegration: Готовый к работе объект интеграции
    """
    return VipalinaNocoDBIntegration(
        api_url=api_url,
        api_token=api_token,
        base_id=base_id,
        table_id=table_id,
        view_id=view_id
    )
