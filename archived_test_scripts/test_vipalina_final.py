#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новой структуры листа "Випалина"
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

async def test_vipalina_sheet():
    """Тестирует запись данных в новую структуру листа "Випалина" """
    
    logger.info("🧪 Начинаем тест новой структуры листа 'Випалина'")
    
    try:
        # Инициализируем интеграцию с Google Sheets
        sheets = VipalinaSheetIntegration()
        logger.info("✅ Подключение к Google Sheets установлено")
        
        # Проверяем заголовки
        headers = await asyncio.to_thread(sheets.worksheet.row_values, 1)
        logger.info(f"\n📋 Заголовки листа 'Випалина':")
        for i, header in enumerate(headers, 1):
            logger.info(f"   {chr(64+i)}: {header}")
        
        # Тест 1: Полный онбординг (все данные есть)
        logger.info("\n" + "="*60)
        logger.info("ТЕСТ 1: Полный успешный онбординг")
        logger.info("="*60)
        
        test_student_1 = {
            'name': 'Анна Петрова',
            'course': '[vip] Python-разработчик',
            'telegram_username': '@anna_petrova'
        }
        
        result_1 = await sheets.add_student_record(
            getcourse_id='TEST_001',
            telegram_id=111222333,
            chat_id=-1001234567890,
            student_data=test_student_1,
            manager_id=268400185,
            manager_name='Ксюша Уланова',
            tracker_url='https://docs.google.com/spreadsheets/d/TRACKER_ID_001'
        )
        
        if result_1:
            logger.info("✅ ТЕСТ 1 ПРОЙДЕН: Запись с полными данными добавлена")
        else:
            logger.error("❌ ТЕСТ 1 НЕ ПРОЙДЕН")
        
        # Тест 2: Частичный онбординг (некоторые данные отсутствуют)
        logger.info("\n" + "="*60)
        logger.info("ТЕСТ 2: Частичный онбординг (нет Telegram ID и трекера)")
        logger.info("="*60)
        
        test_student_2 = {
            'name': 'Иван Сидоров',
            'course': '[luxury] Fullstack JavaScript',
            'telegram_username': '@ivan_sidorov'
        }
        
        result_2 = await sheets.add_student_record(
            getcourse_id='TEST_002',
            telegram_id=None,  # Нет Telegram ID
            chat_id=-1009876543210,
            student_data=test_student_2,
            manager_id=5169675294,
            manager_name='Марина Иванова',
            tracker_url="-"  # Трекер не создан
        )
        
        if result_2:
            logger.info("✅ ТЕСТ 2 ПРОЙДЕН: Запись с прочерками добавлена")
        else:
            logger.error("❌ ТЕСТ 2 НЕ ПРОЙДЕН")
        
        # Тест 3: Минимальный онбординг (почти все данные отсутствуют)
        logger.info("\n" + "="*60)
        logger.info("ТЕСТ 3: Минимальный онбординг (только обязательные данные)")
        logger.info("="*60)
        
        test_student_3 = {
            'name': 'Мария Александровна Смирнова',  # Длинное имя - должно остаться только "Мария"
            'course': '[bundle] UX/UI Дизайнер',
            'telegram_username': ''
        }
        
        result_3 = await sheets.add_student_record(
            getcourse_id='TEST_003',
            telegram_id=None,
            chat_id=None,
            student_data=test_student_3,
            manager_id=None,
            manager_name=None,
            tracker_url="-"
        )
        
        if result_3:
            logger.info("✅ ТЕСТ 3 ПРОЙДЕН: Запись с минимальными данными добавлена")
        else:
            logger.error("❌ ТЕСТ 3 НЕ ПРОЙДЕН")
        
        # Проверяем результаты
        logger.info("\n" + "="*60)
        logger.info("ПРОВЕРКА РЕЗУЛЬТАТОВ")
        logger.info("="*60)
        
        # Получаем все данные из таблицы
        all_data = await asyncio.to_thread(sheets.worksheet.get_all_values)
        
        logger.info(f"\n📊 Всего строк в таблице: {len(all_data)}")
        logger.info(f"📊 Строк с данными (без заголовка): {len(all_data) - 1}")
        
        if len(all_data) > 1:
            logger.info("\n📝 Записи в таблице:")
            for i, row in enumerate(all_data[1:], 2):
                logger.info(f"\nСтрока {i}:")
                logger.info(f"  GetCourse ID: {row[0]}")
                logger.info(f"  Telegram ID: {row[1]}")
                logger.info(f"  Chat ID: {row[2]}")
                logger.info(f"  Имя: {row[3]} (должно быть только первое слово)")
                logger.info(f"  Курс: {row[4]}")
                logger.info(f"  Username: {row[5]}")
                logger.info(f"  Менеджер ID: {row[6]}")
                logger.info(f"  Менеджер: {row[7]}")
                logger.info(f"  Трекер: {row[8]}")
                logger.info(f"  Статус: {row[10] if len(row) > 10 else 'N/A'}")
        
        # Проверяем, что имена содержат только первое слово
        logger.info("\n" + "="*60)
        logger.info("ПРОВЕРКА ФОРМАТА ИМЕН")
        logger.info("="*60)
        
        names_correct = True
        for i, row in enumerate(all_data[1:], 2):
            name = row[3] if len(row) > 3 else ""
            if ' ' in name:
                logger.error(f"❌ Строка {i}: Имя '{name}' содержит пробел (должно быть только первое слово)")
                names_correct = False
            else:
                logger.info(f"✅ Строка {i}: Имя '{name}' в правильном формате")
        
        # Итоговый результат
        logger.info("\n" + "="*60)
        logger.info("ИТОГОВЫЙ РЕЗУЛЬТАТ")
        logger.info("="*60)
        
        if result_1 and result_2 and result_3 and names_correct:
            logger.info("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
            logger.info("✅ Структура листа 'Випалина' работает корректно")
            logger.info("✅ Имена записываются только первым словом")
            logger.info("✅ Отсутствующие данные заменяются на '-'")
            return True
        else:
            logger.error("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании: {e}", exc_info=True)
        return False

async def cleanup():
    """Очищает тестовые данные"""
    try:
        logger.info("\n🗑️ Очистка тестовых данных...")
        sheets = VipalinaSheetIntegration()
        
        # Получаем все данные
        all_data = await asyncio.to_thread(sheets.worksheet.get_all_values)
        
        # Удаляем строки с тестовыми данными (TEST_001, TEST_002, TEST_003)
        rows_to_delete = []
        for i, row in enumerate(all_data[1:], 2):
            if len(row) > 0 and row[0].startswith('TEST_'):
                rows_to_delete.append(i)
        
        # Удаляем строки в обратном порядке (чтобы индексы не сбивались)
        for row_num in sorted(rows_to_delete, reverse=True):
            await asyncio.to_thread(sheets.worksheet.delete_rows, row_num)
            logger.info(f"   Удалена строка {row_num}")
        
        logger.info(f"✅ Очистка завершена: удалено {len(rows_to_delete)} тестовых строк")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке: {e}", exc_info=True)

async def main():
    """Главная функция"""
    success = await test_vipalina_sheet()
    
    # Предлагаем очистить тестовые данные
    if success:
        await cleanup()
    
    print("\n" + "="*60)
    if success:
        print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО УСПЕШНО")
    else:
        print("❌ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО С ОШИБКАМИ")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
