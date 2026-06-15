#!/usr/bin/env python3
"""
Диагностический скрипт для проверки работы с таблицей SLA Випалина (SLA_Data).
Проверяет инициализацию, структуру листа и наличие данных.
"""

import logging
from sla_sheets import SLASheetsIntegration
from config import SLA_GOOGLE_SHEETS_ID, SLA_GOOGLE_SHEETS_TAB

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('sla_diagnostics')


def main():
    """Главная функция диагностики"""
    logger.info("=" * 80)
    logger.info("🔍 ДИАГНОСТИКА ТАБЛИЦЫ SLA ВИПАЛИНА")
    logger.info("=" * 80)
    
    logger.info(f"\n📋 Конфигурация:")
    logger.info(f"   Таблица ID: {SLA_GOOGLE_SHEETS_ID}")
    logger.info(f"   Лист: {SLA_GOOGLE_SHEETS_TAB}")
    logger.info(f"   Ссылка: https://docs.google.com/spreadsheets/d/{SLA_GOOGLE_SHEETS_ID}")
    
    # Шаг 1: Инициализация
    logger.info(f"\n🔌 Шаг 1: Инициализация SLASheetsIntegration...")
    try:
        sla_sheets = SLASheetsIntegration()
        logger.info("   ✅ Успешно инициализирован")
    except Exception as e:
        logger.error(f"   ❌ ОШИБКА при инициализации: {e}")
        logger.error("\n🔧 Возможные причины:")
        logger.error("   1. Файл vipalina_google_service_account.json отсутствует")
        logger.error("   2. Нет доступа к таблице для сервисного аккаунта")
        logger.error("   3. Неправильный ID таблицы в config.py")
        return 1
    
    # Шаг 2: Проверка структуры
    logger.info(f"\n📊 Шаг 2: Проверка структуры листа '{SLA_GOOGLE_SHEETS_TAB}'...")
    try:
        # Получаем все значения
        all_values = sla_sheets.worksheet.get_all_values()
        
        if not all_values:
            logger.warning("   ⚠️  Лист полностью пустой (даже заголовков нет)")
            logger.info("\n💡 Заголовки будут созданы автоматически при первой записи")
            return 0
        
        # Проверяем заголовки
        headers = all_values[0]
        expected_headers = [
            'Дата', 'Время запроса', 'Студент', 'GetCourse ID', 'Менеджер',
            'Время ответа', 'Время реакции (мин)', 'Рабочее время?', 'SLA ≤15 мин?',
            'Chat ID', 'Student ID', 'Manager ID', 'Текст запроса (фрагмент)',
            'Месяц', 'Год', 'Ссылка на чат'
        ]
        
        logger.info(f"   Ожидается столбцов: {len(expected_headers)}")
        logger.info(f"   Фактически столбцов: {len(headers)}")
        
        if headers == expected_headers:
            logger.info("   ✅ Заголовки совпадают полностью")
        else:
            logger.warning("   ⚠️  Заголовки отличаются!")
            logger.info("\n   Ожидаемые заголовки:")
            for i, h in enumerate(expected_headers, 1):
                logger.info(f"      {i}. {h}")
            logger.info("\n   Фактические заголовки:")
            for i, h in enumerate(headers, 1):
                match = "✅" if i <= len(expected_headers) and h == expected_headers[i-1] else "❌"
                logger.info(f"      {i}. {h} {match}")
        
        # Шаг 3: Проверка данных
        logger.info(f"\n📈 Шаг 3: Проверка данных...")
        data_rows = all_values[1:] if len(all_values) > 1 else []
        logger.info(f"   Строк с данными: {len(data_rows)}")
        
        if len(data_rows) == 0:
            logger.warning("   ⚠️  НЕТ ДАННЫХ (только заголовки)")
            logger.info("\n❓ ПОЧЕМУ ДАННЫХ НЕТ?")
            logger.info("   1. Бот не запущен или не работает")
            logger.info("   2. Студенты не писали сообщения")
            logger.info("   3. Менеджеры не отвечали на сообщения студентов")
            logger.info("   4. Ошибка при инициализации sla_sheets в боте")
            logger.info("\n💡 ЛОГИКА ЗАПИСИ:")
            logger.info("   • Студент пишет ПЕРВОЕ сообщение за сутки → создаётся SLA-запрос")
            logger.info("   • Менеджер отвечает → SLA-запрос закрывается → ЗАПИСЬ в SLA_Data")
            logger.info("   • Если менеджер НЕ ответил → данные НЕ попадают в SLA_Data")
        else:
            logger.info("   ✅ Данные есть!")
            logger.info(f"\n   Статистика по месяцам:")
            
            # Подсчитываем по месяцам
            from collections import defaultdict
            by_month = defaultdict(int)
            
            for row in data_rows:
                if len(row) >= 15:
                    month = row[13] if len(row) > 13 else ''
                    year = row[14] if len(row) > 14 else ''
                    if month and year:
                        by_month[f"{month} {year}"] += 1
            
            for period, count in sorted(by_month.items(), key=lambda x: x[0]):
                logger.info(f"      {period}: {count} записей")
            
            # Показываем последние 3 записи
            logger.info(f"\n   📝 Последние 3 записи:")
            for i, row in enumerate(data_rows[-3:], 1):
                logger.info(f"\n      Запись {len(data_rows) - 3 + i}:")
                if len(row) >= 7:
                    logger.info(f"         Дата: {row[0]}")
                    logger.info(f"         Студент: {row[2]}")
                    logger.info(f"         Менеджер: {row[4]}")
                    logger.info(f"         Время реакции: {row[6]} мин")
                    logger.info(f"         SLA соблюдён: {row[8]}")
        
    except Exception as e:
        logger.error(f"   ❌ ОШИБКА при проверке структуры: {e}", exc_info=True)
        return 1
    
    # Итоговая информация
    logger.info("\n" + "=" * 80)
    logger.info("✅ ДИАГНОСТИКА ЗАВЕРШЕНА")
    logger.info("=" * 80)
    
    if len(data_rows) == 0:
        logger.info("\n🔧 ЧТО ДЕЛАТЬ:")
        logger.info("   1. Проверить, запущен ли бот: ps aux | grep vip_automation")
        logger.info("   2. Проверить логи бота на наличие ошибок инициализации SLA")
        logger.info("   3. Убедиться, что студенты пишут сообщения")
        logger.info("   4. Убедиться, что менеджеры отвечают на сообщения")
        logger.info("\n💡 ТЕСТИРОВАНИЕ:")
        logger.info("   Для теста попросите студента написать в чат,")
        logger.info("   а менеджера ответить. Запись должна появиться.")
    
    return 0


if __name__ == "__main__":
    exit(main())
