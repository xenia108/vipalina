"""
Скрипт для добавления формул IMPORTRANGE в таблицу "Випалина"
для всех существующих студентов с трекерами.

Формулы подтягивают даты из трекеров в колонки R, S, T:
- R: Дата начала обучения (из "📈 Статистика" C4)
- S: Дата начала окупаемости (из "📈 Статистика" C10)  
- T: Окупить до (из "📈 Статистика" C11)
"""

import asyncio
import logging
from vipalina_sheets import VipalinaSheetIntegration
from async_sheets_wrapper import AsyncSheetsWrapper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def add_formulas_to_existing_students():
    """
    Добавляет формулы IMPORTRANGE для всех студентов, у которых есть трекер.
    """
    try:
        logger.info("🚀 Начинаем добавление формул IMPORTRANGE для существующих студентов...")
        
        # Инициализируем интеграцию с таблицей
        sheets_integration = VipalinaSheetIntegration()
        worksheet = sheets_integration.worksheet
        
        # Получаем все данные из таблицы
        logger.info("📊 Загружаем данные из таблицы 'Випалина'...")
        all_data = await AsyncSheetsWrapper.run_sync(
            worksheet.get_all_values
        )
        
        if len(all_data) <= 1:
            logger.warning("⚠️ В таблице нет данных о студентах")
            return
        
        # Подсчитываем статистику
        total_students = len(all_data) - 1  # Минус заголовок
        students_with_tracker = 0
        students_updated = 0
        students_skipped = 0
        
        logger.info(f"📋 Найдено студентов в таблице: {total_students}")
        
        # Обрабатываем каждого студента
        for row_idx, row in enumerate(all_data[1:], start=2):  # Начинаем со строки 2
            if len(row) < 9:  # Проверяем, что есть колонка I (трекер)
                continue
            
            getcourse_id = row[0] if len(row) > 0 else ''
            student_name = row[3] if len(row) > 3 else 'Неизвестный'
            tracker_url = row[8] if len(row) > 8 else ''
            
            # Пропускаем студентов без трекера
            if not tracker_url or tracker_url == '-':
                logger.debug(f"⏭️ Пропускаем студента {student_name} (нет трекера)")
                students_skipped += 1
                continue
            
            students_with_tracker += 1
            
            # Создаём формулы IMPORTRANGE
            formula_start_date = f'=IFERROR(IMPORTRANGE("{tracker_url}"; "📈 Статистика!C4"); "-")'
            formula_breakeven_start = f'=IFERROR(IMPORTRANGE("{tracker_url}"; "📈 Статистика!C10"); "-")'
            formula_breakeven_deadline = f'=IFERROR(IMPORTRANGE("{tracker_url}"; "📈 Статистика!C11"); "-")'
            
            try:
                # Добавляем формулы в ячейки R, S, T
                await AsyncSheetsWrapper.run_sync(
                    worksheet.update,
                    f'R{row_idx}:T{row_idx}',
                    [[formula_start_date, formula_breakeven_start, formula_breakeven_deadline]],
                    value_input_option='USER_ENTERED'
                )
                
                students_updated += 1
                logger.info(f"✅ [{students_updated}/{students_with_tracker}] {student_name} (строка {row_idx})")
                
                # Небольшая пауза, чтобы не перегружать API
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ Ошибка для студента {student_name} (строка {row_idx}): {e}")
        
        # Итоговая статистика
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 ИТОГОВАЯ СТАТИСТИКА:")
        logger.info(f"   Всего студентов:           {total_students}")
        logger.info(f"   Студентов с трекером:      {students_with_tracker}")
        logger.info(f"   Успешно обновлено:         {students_updated} ✅")
        logger.info(f"   Пропущено (нет трекера):   {students_skipped} ⏭️")
        logger.info("=" * 60)
        logger.info("")
        
        if students_updated > 0:
            logger.info("🎉 Формулы IMPORTRANGE успешно добавлены!")
            logger.info("💡 Теперь даты будут обновляться автоматически в реальном времени")
        else:
            logger.warning("⚠️ Не найдено студентов для обновления")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(add_formulas_to_existing_students())
