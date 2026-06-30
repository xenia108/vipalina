#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Единая точка входа для VipAlina Bot.
Запускает все компоненты системы одновременно с интеграцией мониторинга.
"""

import asyncio
import signal
import sys
from typing import Optional
from datetime import datetime

# Импорты компонентов системы
from config import API_ID, API_HASH, LOG_LEVEL
from centralized_logger import setup_centralized_logging, get_logger
from system_monitor import SystemMonitor
from state_manager import StateManager

# Создаем централизованный логгер
logger = get_logger(__name__)


class VipAlinaApplication:
    """
    Главное приложение VipAlina.
    Управляет жизненным циклом всех компонентов с интеграцией мониторинга.
    """
    
    def __init__(self):
        """Инициализация приложения."""
        self.user_client = None  # Telethon user
        self.system_monitor = None
        self.state_manager = None
        self.orchestrator = None  # VipAutomationOrchestrator
        self.running = False
        
        logger.info("=" * 80)
        logger.info("VipAlina Application инициализирован")
        logger.info("=" * 80)
    
    async def initialize(self):
        """Инициализирует все компоненты системы."""
        try:
            logger.info("🚀 Начало инициализации компонентов...")
            
            # 1. Инициализация State Manager (для offline/restart)
            logger.info("📊 Инициализация State Manager...")
            self.state_manager = StateManager()
            await self.state_manager.initialize()
            logger.info("✅ State Manager инициализирован")
            
            # 2. Инициализация System Monitor
            logger.info("📈 Инициализация System Monitor...")
            self.system_monitor = SystemMonitor(self.state_manager)
            await self.system_monitor.start()
            logger.info("✅ System Monitor запущен")
            
            # 3. Восстановление состояния после restart
            logger.info("🔄 Восстановление состояния после restart...")
            await self.state_manager.restore_pending_operations()
            logger.info("✅ Состояние восстановлено")
            
            # 4. Инициализация Telethon UserClient
            logger.info("👤 Инициализация Telethon UserClient...")
            from telethon import TelegramClient
            
            self.user_client = TelegramClient(
                'vipalina_session',
                API_ID,
                API_HASH
            )
            logger.info("✅ Telethon UserClient инициализирован")
            
            # 5. Инициализация VipAutomationOrchestrator (с интеграцией мониторинга)
            logger.info("🎼 Инициализация VipAutomationOrchestrator...")
            from vip_automation_main import VipAutomationOrchestrator
            
            # Создаем оркестратор
            self.orchestrator = VipAutomationOrchestrator()
            # Заменяем его клиент на наш (с мониторингом)
            self.orchestrator.client = self.user_client
            # Интегрируем System Monitor и State Manager
            self.orchestrator.system_monitor = self.system_monitor
            self.orchestrator.state_manager = self.state_manager
            
            # ВАЖНО: Пересоздаем onboarding_module с правильными параметрами
            from student_onboarding import StudentOnboardingModule
            self.orchestrator.onboarding_module = StudentOnboardingModule(
                self.user_client,
                system_monitor=self.system_monitor,
                state_manager=self.state_manager
            )
            
            logger.info("✅ VipAutomationOrchestrator инициализирован")
            
            logger.info("=" * 80)
            logger.info("✅ ВСЕ КОМПОНЕНТЫ ИНИЦИАЛИЗИРОВАНЫ")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при инициализации: {e}", exc_info=True)
            raise
    
    async def start(self):
        """Запускает все компоненты системы."""
        try:
            self.running = True
            logger.info("🚀 Запуск всех компонентов системы...")
            
            # Запускаем компоненты параллельно
            tasks = []
            
            # 1. Запуск Telethon UserClient с оркестратором
            logger.info("👤 Запуск Telethon UserClient с VipAutomationOrchestrator...")
            tasks.append(asyncio.create_task(self._run_user_client()))
            
            # 2. Запуск мониторинга
            logger.info("📈 Запуск мониторинга...")
            tasks.append(asyncio.create_task(self.system_monitor.monitor_loop()))
            
            # 3. Запуск @Vipalina_zerocoder_bot для учебных чатов
            logger.info("🤖 Запуск @Vipalina_zerocoder_bot...")
            tasks.append(asyncio.create_task(self._run_telegram_bot()))
            
            logger.info("=" * 80)
            logger.info("✅ ВСЕ СИСТЕМЫ ЗАПУЩЕНЫ")
            logger.info("=" * 80)
            logger.info("Бот работает. Нажмите Ctrl+C для остановки.")
            logger.info("ℹ️  Telethon: личные сообщения + группы + создание чатов")
            logger.info("ℹ️  Bot: ответы в учебных чатах студентам")
            
            # Ждем завершения всех задач
            await asyncio.gather(*tasks)
            
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске системы: {e}", exc_info=True)
            raise
    
    async def _run_user_client(self):
        """Запускает Telethon UserClient с полной автоматизацией."""
        try:
            # Сначала подключаем клиент
            await self.user_client.start()
            logger.info("✅ Telethon UserClient запущен и работает")
            
            # ВАЖНО: Только после подключения регистрируем handlers через orchestrator.start()
            logger.info("📝 Регистрация event handlers через VipAutomationOrchestrator...")
            await self.orchestrator.start()
            logger.info("✅ Event handlers зарегистрированы")
            
            # Держим клиента активным
            await self.user_client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"❌ Ошибка в Telethon UserClient: {e}", exc_info=True)
            raise
    
    async def _run_telegram_bot(self):
        """⛔ ЗАБЛОКИРОВАНО: @Vipalina_zerocoder_bot больше не используется."""
        logger.warning("⛔ @Vipalina_zerocoder_bot ЗАБЛОКИРОВАН")
        logger.info("   Используется только Telethon-система (User Account + Bot Client)")
        logger.info("   @Vipalina_zerocoder_bot НЕ ЗАПУСКАЕТСЯ")
        return
        
        # ЗАБЛОКИРОВАННЫЙ КОД - НЕ ВЫПОЛНЯЕТСЯ
        # try:
        #     import vipalina_bot
        #     logger.info("✅ @Vipalina_zerocoder_bot запущен")
        #     
        #     # Запускаем бота в асинхронном режиме
        #     def run_bot():
        #         vipalina_bot.bot.infinity_polling()
        #     
        #     loop = asyncio.get_event_loop()
        #     await loop.run_in_executor(None, run_bot)
        #     
        # except Exception as e:
        #     logger.error(f"❌ Ошибка в @Vipalina_zerocoder_bot: {e}", exc_info=True)
        #     raise
    
    async def stop(self):
        """Останавливает все компоненты системы."""
        try:
            logger.info("=" * 80)
            logger.info("🛑 Начало остановки системы...")
            logger.info("=" * 80)
            
            self.running = False
            
            # 1. Сохранение состояния
            if self.state_manager:
                logger.info("💾 Сохранение текущего состояния...")
                await self.state_manager.save_state()
                logger.info("✅ Состояние сохранено")
            
            # 2. Остановка мониторинга
            if self.system_monitor:
                logger.info("📈 Остановка System Monitor...")
                await self.system_monitor.stop()
                logger.info("✅ System Monitor остановлен")
            
            # 3. Остановка Telethon UserClient
            if self.user_client and self.user_client.is_connected():
                logger.info("👤 Остановка Telethon UserClient...")
                await self.user_client.disconnect()
                logger.info("✅ Telethon UserClient остановлен")
            
            logger.info("=" * 80)
            logger.info("✅ ВСЕ КОМПОНЕНТЫ ОСТАНОВЛЕНЫ")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"❌ Ошибка при остановке системы: {e}", exc_info=True)


# Глобальный экземпляр приложения
app: Optional[VipAlinaApplication] = None


def signal_handler(signum, frame):
    """Обработчик сигналов завершения (Ctrl+C)."""
    logger.info(f"Получен сигнал {signum}, начинаем graceful shutdown...")
    if app:
        asyncio.create_task(app.stop())
        sys.exit(0)


async def main():
    """Главная функция запуска приложения."""
    global app
    
    try:
        # Настройка централизованного логирования
        setup_centralized_logging()
        
        logger.info("=" * 80)
        logger.info("VIPALINA BOT - ЗАПУСК СИСТЕМЫ")
        logger.info(f"Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)
        
        # Создание приложения
        app = VipAlinaApplication()
        
        # Регистрация обработчиков сигналов
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Инициализация и запуск
        await app.initialize()
        await app.start()
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания (Ctrl+C)")
        if app:
            await app.stop()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        if app:
            await app.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
