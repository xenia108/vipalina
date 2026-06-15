#!/usr/bin/env python3
"""
Тестовый скрипт для проверки записи данных в лист "Випалина"
"""

import asyncio
import logging
from vipalina_sheets import VipalinaSheetIntegration

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_add_student():
    """Тестирует добавление студента в лист "Випалина" """
    
    logger.info("🧪 Начинаем тест записи в лист 'Випалина'")
    
    try:
        # Инициализируем интеграцию с Google Sheets
        sheets = VipalinaSheetIntegration()
        logger.info("✅ Подключение к Google Sheets установлено")
        
        # Тестовые данные студента
        test_student_data = {
            'name': 'Тестовый Студент',
            'email': 'test@example.com',
            'phone': '79999999999',
            'course': '[test] Тестовый Курс',
            'telegram_username': '@test_user'
        }
        
        test_getcourse_id = 'TEST_' + str(asyncio.get_event_loop().time()).replace('.', '_')
        test_telegram_id = 123456789
        test_chat_id = -1001234567890
        test_manager_id = 268400185  # Ксюша Уланова
        test_manager_name = 'Ксюша Уланова'
        
        logger.info(f"📝 Тестовые данные:")
        logger.info(f"   GetCourse ID: {test_getcourse_id}")
        logger.info(f"   Telegram ID: {test_telegram_id}")
        logger.info(f"   Chat ID: {test_chat_id}")
        logger.info(f"   Имя: {test_student_data['name']}")
        logger.info(f"   Курс: {test_student_data['course']}")
        logger.info(f"   Менеджер: {test_manager_name}")
        
        # Пытаемся добавить запись
        logger.info("\n🔄 Вызываем add_student_record()...")
        
        result = await sheets.add_student_record(
            getcourse_id=test_getcourse_id,
            telegram_id=test_telegram_id,
            chat_id=test_chat_id,
            student_data=test_student_data,
            manager_id=test_manager_id,
            manager_name=test_manager_name
        )
        
        if result:
            logger.info("✅ Запись успешно добавлена в Google Sheets!")
            
            # Проверяем, что запись действительно появилась
            logger.info("\n🔍 Проверяем, что запись появилась в таблице...")
            student_info = await sheets.get_student_info(test_getcourse_id)
            
            if student_info:
                logger.info("✅ Запись найдена в таблице!")
                logger.info(f"\n📊 Данные из таблицы:")
                logger.info(f"   GetCourse ID: {student_info['getcourse_id']}")
                logger.info(f"   Telegram ID: {student_info['telegram_id']}")
                logger.info(f"   Chat ID: {student_info['chat_id']}")
                logger.info(f"   Имя: {student_info['name']}")
                logger.info(f"   Email: {student_info['email']}")
                logger.info(f"   Телефон: {student_info['phone']}")
                logger.info(f"   Курс: {student_info['course']}")
                logger.info(f"   Username: {student_info['username']}")
                logger.info(f"   Менеджер: {student_info['manager_name']}")
                logger.info(f"   Статус: {student_info['status']}")
                logger.info(f"   Создан: {student_info['created_at']}")
                
                logger.info("\n✅ ТЕСТ ПРОЙДЕН УСПЕШНО!")
                return True
            else:
                logger.error("❌ Запись не найдена в таблице после добавления")
                return False
        else:
            logger.error("❌ Не удалось добавить запись в Google Sheets")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании: {e}", exc_info=True)
        return False

async def main():
    """Главная функция"""
    success = await test_add_student()
    
    if success:
        print("\n" + "="*60)
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("❌ ТЕСТЫ НЕ ПРОЙДЕНЫ")
        print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
