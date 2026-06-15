"""
Кеширование Telegram entities для снижения количества запросов к API.
Решает проблему множественных запросов к Telegram API для получения одних и тех же entities.
"""

import logging
from typing import Optional, Union, Dict, Any
from datetime import datetime, timedelta
from telethon.tl.types import User, Chat, Channel
from telethon import TelegramClient

logger = logging.getLogger('vipalina_telethon')


Entity = Union[User, Chat, Channel]


class EntityCache:
    """
    Кеш для Telegram entities с поддержкой TTL и пакетной загрузки.
    """
    
    # Время жизни кеша: 1 час
    TTL = timedelta(hours=1)
    
    def __init__(self, client: TelegramClient):
        """
        Args:
            client: Экземпляр TelegramClient
        """
        self.client = client
        # Кеш: key -> {'entity': Entity, 'cached_at': datetime}
        self._cache: Dict[Any, Dict[str, Any]] = {}
    
    def _get_cache_key(self, identifier: Union[int, str]) -> str:
        """
        Создает ключ кеша из идентификатора.
        
        Args:
            identifier: ID, username или номер телефона
            
        Returns:
            Строковый ключ для кеша
        """
        if isinstance(identifier, int):
            return f"id_{identifier}"
        elif isinstance(identifier, str):
            # Убираем @ из username и + из телефона для единообразия
            clean_id = identifier.lstrip('@+')
            return f"str_{clean_id}"
        else:
            return str(identifier)
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        Проверяет, актуален ли кеш для данного ключа.
        
        Args:
            cache_key: Ключ кеша
            
        Returns:
            True если кеш актуален
        """
        if cache_key not in self._cache:
            return False
        
        cached_at = self._cache[cache_key]['cached_at']
        age = datetime.now() - cached_at
        return age < self.TTL
    
    def get_from_cache(self, identifier: Union[int, str]) -> Optional[Entity]:
        """
        Получает entity из кеша, если он актуален.
        
        Args:
            identifier: ID, username или номер телефона
            
        Returns:
            Entity или None если не найдено/устарело
        """
        cache_key = self._get_cache_key(identifier)
        
        if not self._is_cache_valid(cache_key):
            return None
        
        entity = self._cache[cache_key]['entity']
        logger.debug(f"Entity найден в кеше: {identifier}")
        return entity
    
    def put_to_cache(self, identifier: Union[int, str], entity: Entity) -> None:
        """
        Сохраняет entity в кеш.
        
        Args:
            identifier: ID, username или номер телефона
            entity: Telegram entity
        """
        cache_key = self._get_cache_key(identifier)
        
        self._cache[cache_key] = {
            'entity': entity,
            'cached_at': datetime.now()
        }
        
        logger.debug(f"Entity добавлен в кеш: {identifier}")
    
    async def get_entity(self, identifier: Union[int, str]) -> Optional[Entity]:
        """
        Получает entity с использованием кеша.
        Если в кеше нет или устарело - загружает через API и кеширует.
        
        Args:
            identifier: ID, username или номер телефона
            
        Returns:
            Entity или None при ошибке
        """
        # Пробуем получить из кеша
        cached_entity = self.get_from_cache(identifier)
        if cached_entity:
            return cached_entity
        
        # Загружаем через API
        try:
            entity = await self.client.get_entity(identifier)
            self.put_to_cache(identifier, entity)
            logger.info(f"Entity загружен из API и закеширован: {identifier}")
            return entity
        except Exception as e:
            logger.error(f"Ошибка при получении entity {identifier}: {e}")
            return None
    
    async def get_entities_batch(self, identifiers: list) -> Dict[Any, Optional[Entity]]:
        """
        Получает несколько entities одновременно с использованием кеша.
        Оптимизирует запросы: сначала проверяет кеш, затем загружает недостающие.
        
        Args:
            identifiers: Список ID, usernames или номеров
            
        Returns:
            Dict: identifier -> Entity (или None при ошибке)
        """
        results = {}
        to_load = []
        
        # Проверяем кеш для всех identifiers
        for identifier in identifiers:
            cached = self.get_from_cache(identifier)
            if cached:
                results[identifier] = cached
            else:
                to_load.append(identifier)
        
        # Загружаем недостающие entities
        if to_load:
            logger.info(f"Загрузка {len(to_load)} entities из {len(identifiers)} (остальные из кеша)")
            
            for identifier in to_load:
                try:
                    entity = await self.client.get_entity(identifier)
                    self.put_to_cache(identifier, entity)
                    results[identifier] = entity
                except Exception as e:
                    logger.error(f"Ошибка при загрузке entity {identifier}: {e}")
                    results[identifier] = None
        else:
            logger.info(f"Все {len(identifiers)} entities получены из кеша")
        
        return results
    
    def clear_cache(self) -> None:
        """Очищает весь кеш."""
        self._cache.clear()
        logger.info("Кеш entities очищен")
    
    def invalidate(self, identifier: Union[int, str]) -> None:
        """
        Инвалидирует кеш для конкретного entity.
        
        Args:
            identifier: ID, username или номер телефона
        """
        cache_key = self._get_cache_key(identifier)
        if cache_key in self._cache:
            del self._cache[cache_key]
            logger.debug(f"Entity удален из кеша: {identifier}")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Возвращает статистику кеша.
        
        Returns:
            Dict со статистикой (total, valid, expired)
        """
        total = len(self._cache)
        valid = sum(1 for key in self._cache if self._is_cache_valid(key))
        expired = total - valid
        
        return {
            'total': total,
            'valid': valid,
            'expired': expired
        }
