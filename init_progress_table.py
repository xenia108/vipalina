#!/usr/bin/env python3
"""
Скрипт для первичной инициализации сводной таблицы "Прогресс менеджеров".
Создает лист и настраивает формулы IMPORTRANGE.
"""

import asyncio
import logging
from progress_aggregator import get_progress_aggregator

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """
    Инициализирует сводную таблицу прогресса.
    """
    print("=" * 80)
    print("ИНИЦИАЛИЗАЦИЯ СВОДНОЙ ТАБЛИЦЫ 'ПРОГРЕСС МЕНЕДЖЕРОВ'")
    print("=" * 80)
    print()
    
    try:
        # Получаем aggregator
        aggregator = get_progress_aggregator()
        
        print("📋 Создаю лист 'Прогресс менеджеров' в KPI Ultra...")
        
        # Создаем или получаем лист
        progress_sheet = aggregator._get_or_create_sheet()
        
        print(f"✅ Лист успешно инициализирован!")
        print()
        
        print("🔄 Синхронизирую данные студентов из 'Випалина'...")
        
        # Синхронизируем студентов
        await aggregator.sync_students_from_vipalina()
        
        print()
        print("=" * 80)
        print("✅ ИНИЦИАЛИЗАЦИЯ ЗАВЕРШЕНА!")
        print("=" * 80)
        print()
        print("📊 Сводная таблица 'Прогресс менеджеров' готова к использованию.")
        print()
        print("📝 Следующие шаги:")
        print("1. Откройте Google Sheets и найдите лист 'Прогресс менеджеров'")
        print("2. Разрешите доступ к IMPORTRANGE для всех трекеров")
        print("3. Используйте команду /monthstats в боте для просмотра статистики")
        print()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации: {e}", exc_info=True)
        print()
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())
