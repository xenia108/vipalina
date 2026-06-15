"""
Модуль управления пользователями и их ролями.
Централизованная логика для определения прав доступа и ролей пользователей.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from config import (
    VIP_HEAD,
    VIP_DEVELOPER,
    HEAD_IDS,
    ON_DUTY_ACCOUNTS,
    VIP_MANAGERS_VIP,
    VIP_MANAGERS_LUXURY,
    ALL_MANAGER_IDS,
    AUTHORIZED_VIP_USERS
)

logger = logging.getLogger('user_management')


class UserRoleManager:
    """Менеджер для управления ролями пользователей с кэшированием"""
    
    # Время жизни кэша (в секундах)
    CACHE_TTL = 300  # 5 минут
    
    def __init__(self, sheets_integration=None):
        """
        Инициализация менеджера ролей.
        
        Args:
            sheets_integration: Опциональная интеграция с Google Sheets для проверки студентов
        """
        self.sheets_integration = sheets_integration
        self.vip_head_id = VIP_HEAD['telegram_id']
        self.head_ids = HEAD_IDS  # Все IDs с правами руководителя (включая разработчика)
        self.on_duty_ids = [acc['telegram_id'] for acc in ON_DUTY_ACCOUNTS]
        self.vip_manager_ids = [mgr['telegram_id'] for mgr in VIP_MANAGERS_VIP + VIP_MANAGERS_LUXURY]
        self.all_manager_ids = ALL_MANAGER_IDS
        self.authorized_vip_users = AUTHORIZED_VIP_USERS
        
        # Кэш ролей: user_id -> {'role': str, 'cached_at': datetime}
        self._role_cache: Dict[int, Dict[str, Any]] = {}
        
        logger.info("UserRoleManager инициализирован с кэшированием ролей")
    
    def _is_cache_valid(self, user_id: int) -> bool:
        """
        Проверяет, актуален ли кэш для пользователя.
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            True если кэш актуален
        """
        if user_id not in self._role_cache:
            return False
        
        cached_at = self._role_cache[user_id]['cached_at']
        age = (datetime.now() - cached_at).total_seconds()
        
        return age < self.CACHE_TTL
    
    def _get_cached_role(self, user_id: int) -> Optional[str]:
        """
        Получает роль из кэша, если он актуален.
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            Роль из кэша или None
        """
        if self._is_cache_valid(user_id):
            logger.debug(f"Используется кэшированная роль для пользователя {user_id}")
            return self._role_cache[user_id]['role']
        return None
    
    def _cache_role(self, user_id: int, role: str):
        """
        Сохраняет роль в кэш.
        
        Args:
            user_id: Telegram ID пользователя
            role: Роль пользователя
        """
        self._role_cache[user_id] = {
            'role': role,
            'cached_at': datetime.now()
        }
        logger.debug(f"Роль {role} для пользователя {user_id} сохранена в кэш")
    
    def invalidate_cache(self, user_id: Optional[int] = None):
        """
        Инвалидирует кэш для пользователя или всего кэша.
        
        Args:
            user_id: Telegram ID пользователя или None для очистки всего кэша
        """
        if user_id is None:
            self._role_cache.clear()
            logger.info("Кэш ролей полностью очищен")
        elif user_id in self._role_cache:
            del self._role_cache[user_id]
            logger.debug(f"Кэш для пользователя {user_id} инвалидирован")
    
    def get_user_role(self, user_id: int) -> str:
        """
        Определяет роль пользователя по его ID с кэшированием.
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            Роль: "head", "on_duty", "vip_manager", "vip_student", "unauthorized"
        """
        # Проверяем кэш
        cached_role = self._get_cached_role(user_id)
        if cached_role:
            return cached_role
        
        logger.debug(f"Определение роли для пользователя {user_id}")
        
        # Проверяем руководителей (включая разработчика)
        if user_id in self.head_ids:
            role = "head"
            self._cache_role(user_id, role)
            logger.debug(f"Пользователь {user_id} является руководителем/разработчиком")
            return role
        
        # Проверяем дежурных
        if user_id in self.on_duty_ids:
            role = "on_duty"
            self._cache_role(user_id, role)
            logger.debug(f"Пользователь {user_id} является дежурным")
            return role
        
        # Проверяем VIP-менеджеров
        if user_id in self.vip_manager_ids:
            role = "vip_manager"
            self._cache_role(user_id, role)
            logger.debug(f"Пользователь {user_id} является VIP-менеджером")
            return role
        
        # Проверяем в списке авторизованных VIP-пользователей
        if user_id in self.authorized_vip_users or str(user_id) in self.authorized_vip_users:
            role = "vip_student"
            self._cache_role(user_id, role)
            logger.debug(f"Пользователь {user_id} в списке авторизованных VIP-пользователей")
            return role
        
        # Проверяем в Google Sheets (только если интеграция доступна)
        if self.sheets_integration:
            logger.debug(f"Проверка пользователя {user_id} в Google Sheets")
            try:
                student_info = self.sheets_integration.get_student_info_by_telegram_id(user_id)
                if student_info:
                    role = "vip_student"
                    self._cache_role(user_id, role)
                    logger.debug(f"Пользователь {user_id} найден в Google Sheets как студент")
                    return role
            except Exception as e:
                logger.error(f"Ошибка при проверке студента в Google Sheets: {e}")
        
        # Не авторизован
        role = "unauthorized"
        self._cache_role(user_id, role)
        logger.debug(f"Пользователь {user_id} не авторизован")
        return role
    
    def is_authorized_vip_user(self, user_id: int) -> bool:
        """
        Проверяет, является ли пользователь авторизованным VIP-пользователем.
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            True если пользователь авторизован
        """
        return user_id in self.authorized_vip_users or str(user_id) in self.authorized_vip_users
    
    def is_vip_manager(self, user_id: int) -> bool:
        """
        Проверяет, является ли пользователь VIP-менеджером.
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            True если пользователь является VIP-менеджером
        """
        return user_id in self.vip_manager_ids
    
    def is_manager_or_head(self, user_id: int) -> bool:
        """
        Проверяет, имеет ли пользователь права менеджера (включая дежурных и руководителя).
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            True если пользователь имеет права менеджера
        """
        return user_id in self.all_manager_ids
    
    def get_manager_info(self, manager_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о менеджере по его ID.
        
        Args:
            manager_id: Telegram ID менеджера
            
        Returns:
            Dict с информацией о менеджере или None
        """
        # Ищем в VIP-менеджерах
        for manager in VIP_MANAGERS_VIP:
            if manager['telegram_id'] == manager_id:
                return manager
        
        # Ищем в Luxury-менеджерах
        for manager in VIP_MANAGERS_LUXURY:
            if manager['telegram_id'] == manager_id:
                return manager
        
        # Проверяем руководителя
        if VIP_HEAD['telegram_id'] == manager_id:
            return VIP_HEAD
        
        # Проверяем дежурных
        for duty_account in ON_DUTY_ACCOUNTS:
            if duty_account['telegram_id'] == manager_id:
                return duty_account
        
        return None
    
    def get_manager_name(self, manager_id: int) -> Optional[str]:
        """
        Получает имя менеджера по его ID.
        
        Args:
            manager_id: Telegram ID менеджера
            
        Returns:
            Имя менеджера или None
        """
        manager_info = self.get_manager_info(manager_id)
        return manager_info['name'] if manager_info else None


# Singleton instance для удобного использования
_role_manager_instance: Optional[UserRoleManager] = None


def get_role_manager(sheets_integration=None) -> UserRoleManager:
    """
    Получает singleton instance UserRoleManager.
    
    Args:
        sheets_integration: Опциональная интеграция с Google Sheets
        
    Returns:
        UserRoleManager instance
    """
    global _role_manager_instance
    
    if _role_manager_instance is None:
        _role_manager_instance = UserRoleManager(sheets_integration)
    elif sheets_integration and _role_manager_instance.sheets_integration is None:
        # Обновляем sheets_integration если он не был установлен ранее
        _role_manager_instance.sheets_integration = sheets_integration
    
    return _role_manager_instance


# Convenience functions для обратной совместимости
def get_user_role(user_id: int, sheets_integration=None) -> str:
    """Определяет роль пользователя"""
    return get_role_manager(sheets_integration).get_user_role(user_id)


def is_authorized_vip_user(user_id: int) -> bool:
    """Проверяет, является ли пользователь авторизованным"""
    return get_role_manager().is_authorized_vip_user(user_id)


def is_vip_manager(user_id: int) -> bool:
    """Проверяет, является ли пользователь VIP-менеджером"""
    return get_role_manager().is_vip_manager(user_id)


def is_manager_or_head(user_id: int) -> bool:
    """Проверяет, имеет ли пользователь права менеджера"""
    return get_role_manager().is_manager_or_head(user_id)


def get_manager_info(manager_id: int) -> Optional[Dict[str, Any]]:
    """Получает информацию о менеджере"""
    return get_role_manager().get_manager_info(manager_id)


def get_manager_name(manager_id: int) -> Optional[str]:
    """Получает имя менеджера"""
    return get_role_manager().get_manager_name(manager_id)
