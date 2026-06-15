"""
Планировщик синхронизации дат между KPI Sheets и NocoDB.
Логика:
1. Менеджер заполняет дату начала учебы в колонке H листа "Общий список new"
2. Даты окончания поддержки (I) и окупаемости (J) рассчитываются автоматически:
   - ВПР ищет курс из колонки D в листе "Матрица курсов"
   - ДАТАМЕС прибавляет месяцы к дате начала учебы
3. Бот синхронизирует все 3 даты в NocoDB ("Ученики все")
"""

import asyncio
import logging
from datetime import datetime, time
from typing import List, Dict, Any
from vipalina_kpi_sheets import create_kpi_sheets_integration
from vipalina_nocodb import create_nocodb_integration
from config import (
    NOCODB_API_URL, NOCODB_API_TOKEN,
    NOCODB_BASE_ID, NOCODB_TABLE_ID, NOCODB_VIEW_ID
)

logger = logging.getLogger('date_sync_scheduler')


class DateSyncScheduler:
    """
    Планировщик синхронизации дат между KPI Sheets и NocoDB.
    """
    
    def __init__(self):
        """Инициализация планировщика"""
        self.kpi_sheets = None
        self.nocodb = None
        self.last_sync_time = {}  # {getcourse_id: datetime}
        self.sync_interval = 300  # 5 минут (в секундах)
        
    async def initialize(self):
        """Инициализирует интеграции с KPI Sheets и NocoDB"""
        try:
            # KPI Sheets
            self.kpi_sheets = create_kpi_sheets_integration()
            logger.info("✅ KPI Sheets интеграция инициализирована")
            
            # NocoDB
            self.nocodb = create_nocodb_integration(
                api_url=NOCODB_API_URL,
                api_token=NOCODB_API_TOKEN,
                base_id=NOCODB_BASE_ID,
                table_id=NOCODB_TABLE_ID,
                view_id=NOCODB_VIEW_ID
            )
            logger.info("✅ NocoDB интеграция инициализирована")
            
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации планировщика синхронизации дат: {e}", exc_info=True)
            return False
    
    async def get_students_with_training_dates(self) -> List[Dict[str, Any]]:
        """
        Получает список студентов, у которых есть дата начала учебы.
        
        Returns:
            Список словарей с данными студентов
        """
        try:
            # Читаем все данные из листа начиная со строки 21
            all_data = self.kpi_sheets.worksheet.get_all_values()
            
            students = []
            for i in range(20, len(all_data)):  # Начинаем со строки 21 (индекс 20)
                row = all_data[i]
                
                # Пропускаем пустые строки
                if len(row) < 8 or not row[0]:  # Колонка A (GetCourse ID)
                    continue
                
                getcourse_id = row[0]  # Колонка A
                training_start = row[7] if len(row) > 7 else ''  # Колонка H
                
                # Пропускаем, если нет даты начала учебы
                if not training_start or training_start.strip() == '':
                    continue
                
                students.append({
                    'getcourse_id': getcourse_id,
                    'row_number': i + 1,  # +1 потому что индексация с 0
                    'training_start': training_start
                })
            
            logger.info(f"📊 Найдено {len(students)} студентов с датой начала учебы")
            return students
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении списка студентов: {e}", exc_info=True)
            return []
    
    async def sync_single_student(self, getcourse_id: str) -> bool:
        """
        Синхронизирует даты для одного студента.
        
        Args:
            getcourse_id: ID студента в GetCourse
            
        Returns:
            True если синхронизация успешна
        """
        try:
            # Проверяем время последней синхронизации
            last_sync = self.last_sync_time.get(getcourse_id)
            if last_sync:
                time_diff = (datetime.now() - last_sync).total_seconds()
                if time_diff < self.sync_interval:
                    logger.debug(f"⏭️ Пропускаем синхронизацию для {getcourse_id} (последняя синхронизация {int(time_diff)}с назад)")
                    return True
            
            # Выполняем синхронизацию
            result = await self.kpi_sheets.sync_dates_to_nocodb(getcourse_id, self.nocodb)
            
            if result:
                self.last_sync_time[getcourse_id] = datetime.now()
                logger.info(f"✅ Даты синхронизированы для студента {getcourse_id}")
            else:
                logger.debug(f"ℹ️ Синхронизация не требуется для студента {getcourse_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка синхронизации для студента {getcourse_id}: {e}", exc_info=True)
            return False
    
    async def sync_all_students(self):
        """Синхронизирует даты для всех студентов с датой начала учебы"""
        try:
            logger.info("🔄 Начинаем синхронизацию дат для всех студентов...")
            
            students = await self.get_students_with_training_dates()
            
            if not students:
                logger.info("ℹ️ Нет студентов для синхронизации")
                return
            
            success_count = 0
            for student in students:
                result = await self.sync_single_student(student['getcourse_id'])
                if result:
                    success_count += 1
                
                # Небольшая задержка между запросами
                await asyncio.sleep(1)
            
            logger.info(f"✅ Синхронизация завершена: {success_count}/{len(students)} студентов обновлено")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при синхронизации всех студентов: {e}", exc_info=True)
    
    async def run_periodic_sync(self, interval_minutes: int = 30):
        """
        Запускает периодическую синхронизацию дат.
        
        Args:
            interval_minutes: Интервал между синхронизациями (в минутах)
        """
        logger.info(f"🚀 Запуск планировщика синхронизации дат (интервал: {interval_minutes} минут)")
        
        while True:
            try:
                await self.sync_all_students()
                
                # Ждем до следующей синхронизации
                logger.info(f"⏰ Следующая синхронизация через {interval_minutes} минут")
                await asyncio.sleep(interval_minutes * 60)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле синхронизации: {e}", exc_info=True)
                # Ждем 5 минут перед повторной попыткой
                await asyncio.sleep(300)


async def main():
    """Основная функция для запуска планировщика"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    scheduler = DateSyncScheduler()
    
    # Инициализация
    if not await scheduler.initialize():
        logger.error("❌ Не удалось инициализировать планировщик")
        return
    
    # Запуск периодической синхронизации
    await scheduler.run_periodic_sync(interval_minutes=30)


if __name__ == '__main__':
    asyncio.run(main())
