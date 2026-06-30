"""
Скрипт для обновления заголовков в листе 'Випалина'
Добавляет новые колонки R, S, T для дат из трекера
"""

import asyncio
import logging
from vipalina_sheets import VipalinaSheetIntegration

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('update_headers')


async def update_headers():
    """Обновляет заголовки в листе Випалина"""
    try:
        logger.info("🔄 Начинаем обновление заголовков в листе 'Випалина'...")
        
        # Создаем экземпляр интеграции
        sheets = VipalinaSheetIntegration()
        
        # Новые заголовки с колонками R, S, T
        headers = [
            'GetCourse ID',           # A
            'Telegram ID',            # B
            'Chat ID',                # C
            'Имя студента',           # D
            'Курс',                   # E
            'Username',               # F
            'Менеджер ID',            # G
            'Менеджер Имя',           # H
            'Трекер',                 # I
            'Ссылка на чат',          # J
            'Дата создания чата',     # K
            'Статус',                 # L
            'Последнее обновление',   # M
            'Сегмент рассылок',       # N
            'Дата последнего контакта', # O
            'Выходит на связь?',      # P
            'Уведомление о пропаже',  # Q
            'Дата начала обучения',   # R (из трекера "📈 Статистика" C4)
            'Дата начала окупаемости', # S (из трекера "📈 Статистика" C10)
            'Окупить до'              # T (из трекера "📈 Статистика" C11)
        ]
        
        logger.info(f"📝 Обновляем заголовки (всего {len(headers)} колонок)...")
        
        # Обновляем заголовки
        from async_sheets_wrapper import AsyncSheetsWrapper
        await AsyncSheetsWrapper.run_sync(
            sheets.worksheet.update,
            'A1:T1',
            [headers]
        )
        
        # Форматируем заголовки (жирный шрифт и серый фон)
        await AsyncSheetsWrapper.run_sync(
            sheets.worksheet.format,
            'A1:T1',
            {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            }
        )
        
        logger.info("✅ Заголовки успешно обновлены!")
        logger.info("📊 Добавлены новые колонки:")
        logger.info("   R - Дата начала обучения (из трекера C4)")
        logger.info("   S - Дата начала окупаемости (из трекера C10)")
        logger.info("   T - Окупить до (из трекера C11)")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении заголовков: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(update_headers())
