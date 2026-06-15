"""
System Monitor для VipAlina.
Мониторинг здоровья системы, обработка конфликтов и rollback при ошибках.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import threading
from collections import deque

logger = logging.getLogger(__name__)


class ConflictResolver:
    """
    Обработчик конфликтов при одновременных действиях.
    Использует блокировки для синхронизации операций.
    """
    
    def __init__(self):
        """Инициализация Conflict Resolver."""
        # Блокировки для операций с конкретными студентами
        self._student_locks: Dict[str, asyncio.Lock] = {}
        # Глобальная блокировка для критических операций
        self._global_lock = asyncio.Lock()
        logger.info("Conflict Resolver инициализирован")
    
    async def acquire_student_lock(self, student_id: str) -> asyncio.Lock:
        """
        Получает блокировку для операций с конкретным студентом.
        
        Args:
            student_id: ID студента (getcourse_id или telegram_id)
            
        Returns:
            Lock для использования в async with
        """
        if student_id not in self._student_locks:
            self._student_locks[student_id] = asyncio.Lock()
        
        lock = self._student_locks[student_id]
        logger.debug(f"Запрос блокировки для студента {student_id}")
        return lock
    
    async def execute_with_lock(self, student_id: str, operation, *args, **kwargs):
        """
        Выполняет операцию с блокировкой для студента.
        
        Args:
            student_id: ID студента
            operation: Async функция для выполнения
            *args, **kwargs: Аргументы функции
            
        Returns:
            Результат операции
        """
        lock = await self.acquire_student_lock(student_id)
        
        async with lock:
            logger.debug(f"Блокировка получена для студента {student_id}")
            try:
                result = await operation(*args, **kwargs)
                logger.debug(f"Операция для студента {student_id} выполнена успешно")
                return result
            except Exception as e:
                logger.error(f"Ошибка при выполнении операции для студента {student_id}: {e}")
                raise
            finally:
                logger.debug(f"Блокировка освобождена для студента {student_id}")
    
    def cleanup_locks(self):
        """Очищает неиспользуемые блокировки."""
        # Удаляем блокировки, которые не заняты
        to_remove = [
            student_id for student_id, lock in self._student_locks.items()
            if not lock.locked()
        ]
        
        for student_id in to_remove:
            del self._student_locks[student_id]
        
        if to_remove:
            logger.debug(f"Очищено {len(to_remove)} неиспользуемых блокировок")


class RollbackManager:
    """
    Менеджер отката изменений при ошибках.
    Сохраняет шаги операции и откатывает при ошибке.
    """
    
    def __init__(self, state_manager):
        """
        Args:
            state_manager: Экземпляр StateManager
        """
        self.state_manager = state_manager
        # Стек операций для отката
        self._rollback_stacks: Dict[str, List[Dict[str, Any]]] = {}
        logger.info("Rollback Manager инициализирован")
    
    async def start_transaction(self, transaction_id: str):
        """
        Начинает транзакцию с возможностью отката.
        
        Args:
            transaction_id: Уникальный ID транзакции
        """
        self._rollback_stacks[transaction_id] = []
        logger.info(f"Начата транзакция {transaction_id}")
    
    async def add_rollback_step(
        self,
        transaction_id: str,
        rollback_func,
        *args,
        **kwargs
    ):
        """
        Добавляет шаг для отката.
        
        Args:
            transaction_id: ID транзакции
            rollback_func: Функция отката (async)
            *args, **kwargs: Аргументы функции отката
        """
        if transaction_id not in self._rollback_stacks:
            logger.warning(f"Транзакция {transaction_id} не найдена")
            return
        
        step = {
            'func': rollback_func,
            'args': args,
            'kwargs': kwargs,
            'timestamp': datetime.now()
        }
        
        self._rollback_stacks[transaction_id].append(step)
        logger.debug(f"Добавлен шаг отката для транзакции {transaction_id}")
    
    async def commit_transaction(self, transaction_id: str):
        """
        Фиксирует транзакцию (успешное завершение).
        
        Args:
            transaction_id: ID транзакции
        """
        if transaction_id in self._rollback_stacks:
            del self._rollback_stacks[transaction_id]
            logger.info(f"✅ Транзакция {transaction_id} зафиксирована")
    
    async def rollback_transaction(self, transaction_id: str, error: Optional[Exception] = None):
        """
        Откатывает транзакцию (при ошибке).
        
        Args:
            transaction_id: ID транзакции
            error: Ошибка, которая вызвала откат
        """
        if transaction_id not in self._rollback_stacks:
            logger.warning(f"Транзакция {transaction_id} не найдена для отката")
            return
        
        logger.error(f"🔄 Начало отката транзакции {transaction_id}")
        if error:
            logger.error(f"Причина отката: {error}")
        
        # Откатываем шаги в обратном порядке
        steps = self._rollback_stacks[transaction_id]
        steps.reverse()
        
        rollback_errors = []
        
        for i, step in enumerate(steps, 1):
            try:
                logger.info(f"Откат шага {i}/{len(steps)}")
                await step['func'](*step['args'], **step['kwargs'])
                logger.info(f"✅ Шаг {i} откачен")
            except Exception as e:
                logger.error(f"❌ Ошибка при откате шага {i}: {e}", exc_info=True)
                rollback_errors.append(str(e))
        
        # Обновляем состояние операции
        await self.state_manager.update_operation_status(
            transaction_id,
            'rolled_back',
            error=f"Rollback completed. Errors: {'; '.join(rollback_errors) if rollback_errors else 'None'}"
        )
        
        # Удаляем стек отката
        del self._rollback_stacks[transaction_id]
        
        if rollback_errors:
            logger.error(f"⚠️ Откат транзакции {transaction_id} завершен с ошибками")
        else:
            logger.info(f"✅ Откат транзакции {transaction_id} выполнен успешно")


class SystemMonitor:
    """
    Мониторинг здоровья системы.
    Отслеживает метрики, ошибки и производительность.
    """
    
    def __init__(self, state_manager):
        """
        Args:
            state_manager: Экземпляр StateManager
        """
        self.state_manager = state_manager
        self.conflict_resolver = ConflictResolver()
        self.rollback_manager = RollbackManager(state_manager)
        
        # Метрики системы
        self.metrics = {
            'uptime_start': datetime.now(),
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'rolled_back_operations': 0,
            'average_response_time': 0.0,
            'errors_last_hour': deque(maxlen=100),
            'active_operations': 0
        }
        
        self.running = False
        logger.info("System Monitor инициализирован")
    
    async def start(self):
        """Запускает мониторинг."""
        self.running = True
        logger.info("✅ System Monitor запущен")
    
    async def monitor_loop(self):
        """Основной цикл мониторинга."""
        logger.info("Запуск цикла мониторинга...")
        
        while self.running:
            try:
                await asyncio.sleep(60)  # Каждую минуту
                
                # Логируем метрики
                await self._log_metrics()
                
                # Очищаем старые блокировки
                self.conflict_resolver.cleanup_locks()
                
                # Проверяем здоровье системы
                await self._health_check()
                
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)
    
    async def _log_metrics(self):
        """Логирует текущие метрики системы."""
        uptime = datetime.now() - self.metrics['uptime_start']
        
        success_rate = 0
        if self.metrics['total_operations'] > 0:
            success_rate = (self.metrics['successful_operations'] / 
                          self.metrics['total_operations'] * 100)
        
        logger.info("=" * 80)
        logger.info("SYSTEM METRICS")
        logger.info(f"Uptime: {uptime}")
        logger.info(f"Total Operations: {self.metrics['total_operations']}")
        logger.info(f"Success Rate: {success_rate:.1f}%")
        logger.info(f"Active Operations: {self.metrics['active_operations']}")
        logger.info(f"Errors (last hour): {len(self.metrics['errors_last_hour'])}")
        logger.info("=" * 80)
    
    async def _health_check(self):
        """Проверяет здоровье системы."""
        issues = []
        
        # Проверка: слишком много ошибок
        if len(self.metrics['errors_last_hour']) > 50:
            issues.append(f"High error rate: {len(self.metrics['errors_last_hour'])} errors in last hour")
        
        # Проверка: низкий success rate
        if self.metrics['total_operations'] > 10:
            success_rate = (self.metrics['successful_operations'] / 
                          self.metrics['total_operations'] * 100)
            if success_rate < 80:
                issues.append(f"Low success rate: {success_rate:.1f}%")
        
        if issues:
            logger.warning("⚠️ HEALTH CHECK ISSUES:")
            for issue in issues:
                logger.warning(f"  - {issue}")
        else:
            logger.debug("✅ Health check passed")
    
    async def record_operation_start(self, operation_id: str):
        """Регистрирует начало операции."""
        self.metrics['total_operations'] += 1
        self.metrics['active_operations'] += 1
        logger.debug(f"Операция {operation_id} начата")
    
    async def record_operation_success(self, operation_id: str):
        """Регистрирует успешное завершение операции."""
        self.metrics['successful_operations'] += 1
        self.metrics['active_operations'] -= 1
        logger.debug(f"Операция {operation_id} завершена успешно")
    
    async def record_operation_failure(self, operation_id: str, error: Exception):
        """Регистрирует ошибку операции."""
        self.metrics['failed_operations'] += 1
        self.metrics['active_operations'] -= 1
        self.metrics['errors_last_hour'].append({
            'operation_id': operation_id,
            'error': str(error),
            'timestamp': datetime.now()
        })
        logger.error(f"Операция {operation_id} завершена с ошибкой: {error}")
    
    async def record_operation_rollback(self, operation_id: str):
        """Регистрирует откат операции."""
        self.metrics['rolled_back_operations'] += 1
        logger.info(f"Операция {operation_id} откачена")
    
    async def stop(self):
        """Останавливает мониторинг."""
        self.running = False
        logger.info("System Monitor остановлен")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Возвращает текущие метрики."""
        return self.metrics.copy()
