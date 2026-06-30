#!/usr/bin/env python3
"""
Скрипт для обновления формул IMPORTRANGE в листе Vipalina.
Заменяет динамические формулы на формулы с прямыми ссылками на трекеры.
"""

import asyncio
import sys
import logging
from vipalina_sheets import VipalinaSheetIntegration
from async_sheets_wrapper import AsyncSheetsWrapper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fix_formulas')


async def fix_importrange_formulas():
    """Обновляет формулы IMPORTRANGE для всех студентов с трекерами"""
    try:
        logger.info("Начинаем обновление формул IMPORTRANGE...")
        
        # Инициализируем интеграцию с Google Sheets
        vipalina = VipalinaSheetIntegration()
        
        # Получаем все данные из таблицы
        all_data = await AsyncSheetsWrapper.run_sync(
            vipalina.worksheet.get_all_values
        )
        
        if len(all_data) <= 1:
            logger.warning("В таблице нет данных о студентах")
            return
        
        headers = all_data[0]
        data_rows = all_data[1:]
        
        # Находим индекс колонки с трекером (I)
        tracker_col_idx = 8  # Колонка I (нумерация с 0)
        
        updated_count = 0
        skipped_count = 0
        
        for row_idx, row in enumerate(data_rows, start=2):  # Начинаем с 2 (строка 1 - заголовки)
            if len(row) <= tracker_col_idx:
                continue
            
            tracker_url = row[tracker_col_idx]
            
            # Проверяем, есть ли трекер
            if not tracker_url or tracker_url == '-':
                logger.debug(f"Строка {row_idx}: нет трекера, пропускаем")
                skipped_count += 1
                continue
            
            # Обновляем формулы для этой строки
            try:
                formula_start_date = f'=IMPORTRANGE("{tracker_url}"; "📈 Статистика!C4")'
                formula_breakeven_start = f'=IMPORTRANGE("{tracker_url}"; "📈 Статистика!C10")'
                formula_breakeven_deadline = f'=IMPORTRANGE("{tracker_url}"; "📈 Статистика!C11")'
                
                await AsyncSheetsWrapper.run_sync(
                    vipalina.worksheet.update,
                    f'R{row_idx}:T{row_idx}',
                    [[formula_start_date, formula_breakeven_start, formula_breakeven_deadline]],
                    value_input_option='USER_ENTERED'
                )
                
                getcourse_id = row[0] if len(row) > 0 else 'unknown'
                logger.info(f"✅ Строка {row_idx} (GetCourse ID: {getcourse_id}): формулы обновлены")
                updated_count += 1
                
                # Небольшая задержка, чтобы не превысить квоту API
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Ошибка при обновлении формул для строки {row_idx}: {e}")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Обновление завершено!")
        logger.info(f"Обновлено строк: {updated_count}")
        logger.info(f"Пропущено строк (нет трекера): {skipped_count}")
        logger.info(f"{'='*60}\n")
        
        logger.info("ВАЖНО: После обновления формул вам нужно:")
        logger.info("1. Открыть лист Vipalina в браузере")
        logger.info("2. Кликнуть на каждую ячейку R12, R13, R14, R15, R16, R17")
        logger.info("3. Предоставить доступ к трекерам через появившееся окно")
        logger.info("4. После предоставления доступа формулы начнут работать")
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(fix_importrange_formulas())
    sys.exit(exit_code)
