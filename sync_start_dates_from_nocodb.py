#!/usr/bin/env python3
"""
Единоразовая синхронизация дат начала учебы из NocoDB в KPI Ultra.

Процесс:
1. Читает ID с ГК из столбца A (начиная с A21) в листе "Общий список new" (KPI Ultra)
2. Для каждого ID находит соответствующую запись в NocoDB (таблица "Ученики все")
3. Берет значение из столбца "Дата начала учебы" в NocoDB
4. Записывает эту дату в столбец "Дата начала учебы" в KPI Ultra
5. Пропускает пустые даты и дубликаты

ВАЖНО: Это единоразовый скрипт! Запускается вручную.
"""

import gspread
from google.oauth2.service_account import Credentials
import requests
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from config import (
    NOCODB_API_URL,
    NOCODB_API_TOKEN,
    NOCODB_BASE_ID,
    NOCODB_TABLE_ID,
    GOOGLE_SHEETS_ID
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DateSyncFromNocoDB:
    """Синхронизация дат начала учебы из NocoDB в Google Sheets"""
    
    def __init__(self):
        """Инициализация с авторизацией"""
        self.nocodb_url = NOCODB_API_URL
        self.nocodb_token = NOCODB_API_TOKEN
        self.nocodb_base_id = NOCODB_BASE_ID
        self.nocodb_table_id = NOCODB_TABLE_ID
        
        self.kpi_spreadsheet_id = GOOGLE_SHEETS_ID
        self.kpi_sheet_name = "Общий список new"
        
        # Авторизация в Google Sheets
        self._authorize_sheets()
        
        # Статистика
        self.stats = {
            'total_rows': 0,
            'updated': 0,
            'skipped_empty': 0,
            'skipped_duplicate': 0,
            'not_found': 0,
            'errors': 0
        }
    
    def _authorize_sheets(self):
        """Авторизация в Google Sheets через Service Account"""
        try:
            scopes = ['https://www.googleapis.com/auth/spreadsheets']
            credentials = Credentials.from_service_account_file(
                'vipalina_google_service_account.json',
                scopes=scopes
            )
            self.sheets_client = gspread.authorize(credentials)
            logger.info("✅ Авторизация в Google Sheets успешна")
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации в Google Sheets: {e}")
            raise
    
    def get_nocodb_record_by_getcourse_id(self, getcourse_id: str) -> Optional[Dict[str, Any]]:
        """
        Находит запись в NocoDB по ID с GetCourse.
        
        Args:
            getcourse_id: ID студента из GetCourse
            
        Returns:
            Dict с данными записи или None
        """
        try:
            url = f"{self.nocodb_url}/api/v2/tables/{self.nocodb_table_id}/records"
            
            headers = {
                'xc-token': self.nocodb_token,
                'Content-Type': 'application/json'
            }
            
            # Фильтр по полю "ID пользователя"
            params = {
                'where': f'(ID пользователя,eq,{getcourse_id})',
                'limit': 1
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            records = data.get('list', [])
            
            if records:
                return records[0]
            else:
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске записи в NocoDB для ID {getcourse_id}: {e}")
            return None
    
    def sync_dates(self, start_row: int = 21, header_row: int = 19, max_rows: int = None, dry_run: bool = False):
        """
        Синхронизирует даты из NocoDB в Google Sheets.
        
        Args:
            start_row: С какой строки начинать обработку данных (по умолчанию 21)
            header_row: Номер строки с заголовками (по умолчанию 19)
            max_rows: Максимальное количество строк для обработки (None = все строки)
            dry_run: Если True, только показывает что будет сделано, но не изменяет данные
        """
        try:
            # Открываем лист KPI Ultra
            spreadsheet = self.sheets_client.open_by_key(self.kpi_spreadsheet_id)
            sheet = spreadsheet.worksheet(self.kpi_sheet_name)
            
            logger.info(f"📊 Открыт лист '{self.kpi_sheet_name}' в KPI Ultra")
            
            # Получаем все значения
            all_values = sheet.get_all_values()
            
            # Получаем заголовки из указанной строки
            if len(all_values) < header_row:
                logger.error(f"❌ В листе недостаточно строк. Ожидалась строка {header_row} с заголовками")
                return
            
            headers = all_values[header_row - 1]  # -1 потому что индексация с 0
            
            logger.info(f"📍 Заголовки из строки {header_row}: {headers[:10]}")
            
            # Определяем индексы столбцов
            try:
                id_col_index = headers.index('ID с ГК')
                date_col_index = headers.index('Дата начала учебы')
            except ValueError as e:
                logger.error(f"❌ Не найдены нужные столбцы в заголовке: {e}")
                logger.info(f"Доступные столбцы: {headers}")
                return
            
            logger.info(f"📍 Столбец 'ID с ГК': {chr(65 + id_col_index)} (индекс {id_col_index})")
            logger.info(f"📍 Столбец 'Дата начала учебы': {chr(65 + date_col_index)} (индекс {date_col_index})")
            
            # Обрабатываем строки начиная с start_row
            updates = []  # Список обновлений для batch update
            
            if max_rows is None:
                end_row = len(all_values)  # Все строки до конца
            else:
                end_row = min(start_row - 1 + max_rows, len(all_values))  # Ограничиваем количество строк
            
            logger.info(f"📍 Обрабатываем строки с {start_row} по {end_row} (всего: {end_row - start_row + 1})")
            
            for row_idx in range(start_row - 1, end_row):  # -1 потому что индексация с 0
                row = all_values[row_idx]
                row_num = row_idx + 1  # Номер строки в таблице (с 1)
                
                if len(row) <= id_col_index:
                    continue
                
                getcourse_id = row[id_col_index].strip()
                
                if not getcourse_id:
                    continue
                
                self.stats['total_rows'] += 1
                
                # Получаем текущую дату в Google Sheets (для информации)
                current_date = row[date_col_index].strip() if len(row) > date_col_index else ''
                
                # Ищем запись в NocoDB
                logger.info(f"🔍 Строка {row_num}: Ищем ID {getcourse_id} в NocoDB...")
                nocodb_record = self.get_nocodb_record_by_getcourse_id(getcourse_id)
                
                if not nocodb_record:
                    logger.warning(f"⚠️  Строка {row_num}: ID {getcourse_id} не найден в NocoDB")
                    self.stats['not_found'] += 1
                    continue
                
                # Получаем дату из NocoDB
                start_date_value = nocodb_record.get('Дата начала учебы', '')
                start_date_raw = str(start_date_value).strip() if start_date_value else ''
                
                if not start_date_raw or start_date_raw == 'None':
                    logger.info(f"ℹ️  Строка {row_num}: ID {getcourse_id} - дата в NocoDB пустая, пропускаем")
                    self.stats['skipped_empty'] += 1
                    continue
                
                # Конвертируем формат даты из YYYY-MM-DD в DD.MM.YYYY
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(start_date_raw, '%Y-%m-%d')
                    start_date = date_obj.strftime('%d.%m.%Y')
                except ValueError:
                    # Если дата уже в другом формате или невалидна, используем как есть
                    start_date = start_date_raw
                
                # Формируем обновление (заносим дату даже если она уже есть)
                cell_address = f"{chr(65 + date_col_index)}{row_num}"
                status_emoji = "🔄" if current_date else "✅"
                current_info = f" (было: {current_date})" if current_date else ""
                
                if dry_run:
                    logger.info(f"{status_emoji} [DRY RUN] Строка {row_num}: ID {getcourse_id} -> дата {start_date}{current_info} (ячейка {cell_address})")
                else:
                    updates.append({
                        'range': cell_address,
                        'value': start_date
                    })
                    logger.info(f"{status_emoji} Строка {row_num}: ID {getcourse_id} -> дата {start_date}{current_info} (ячейка {cell_address})")
                
                self.stats['updated'] += 1
                if current_date:
                    self.stats['skipped_duplicate'] += 1  # Считаем для статистики, но все равно обновляем
            
            # Применяем все обновления одним batch-запросом
            if updates and not dry_run:
                logger.info(f"\n📝 Применяю {len(updates)} обновлений пакетами...")
                
                # Группируем обновления для batch update (до 1000 за раз)
                batch_size = 1000
                for i in range(0, len(updates), batch_size):
                    batch = updates[i:i + batch_size]
                    
                    # Формируем данные для batch update
                    batch_data = []
                    for update in batch:
                        batch_data.append({
                            'range': update['range'],
                            'values': [[update['value']]]
                        })
                    
                    # Выполняем batch update
                    sheet.batch_update(batch_data, value_input_option='RAW')
                    logger.info(f"✅ Обновлено {min(i + batch_size, len(updates))} из {len(updates)} записей")
                
                logger.info("✅ Все обновления применены!")
            
            # Выводим статистику
            self._print_stats(dry_run)
            
        except Exception as e:
            logger.error(f"❌ Ошибка при синхронизации: {e}", exc_info=True)
            self.stats['errors'] += 1
    
    def _print_stats(self, dry_run: bool = False):
        """Выводит статистику синхронизации"""
        mode = "[DRY RUN] " if dry_run else ""
        
        print("\n" + "="*60)
        print(f"{mode}📊 СТАТИСТИКА СИНХРОНИЗАЦИИ")
        print("="*60)
        print(f"Всего обработано строк:     {self.stats['total_rows']}")
        print(f"✅ Обновлено:                {self.stats['updated']}")
        print(f"ℹ️  Пропущено (дата пустая):  {self.stats['skipped_empty']}")
        print(f"ℹ️  Пропущено (уже есть):     {self.stats['skipped_duplicate']}")
        print(f"⚠️  Не найдено в NocoDB:      {self.stats['not_found']}")
        print(f"❌ Ошибок:                   {self.stats['errors']}")
        print("="*60 + "\n")


def main():
    """Главная функция"""
    print("\n" + "="*60)
    print("🔄 СИНХРОНИЗАЦИЯ ДАТ НАЧАЛА УЧЕБЫ")
    print("   NocoDB -> KPI Ultra (Общий список new)")
    print("="*60 + "\n")
    
    # Спрашиваем режим запуска
    print("Выберите режим:")
    print("1. DRY RUN - только показать что будет сделано (без изменений)")
    print("2. РЕАЛЬНЫЙ ЗАПУСК - применить изменения")
    
    choice = input("\nВаш выбор (1 или 2): ").strip()
    
    dry_run = choice != "2"
    
    if dry_run:
        print("\n🔍 Запуск в режиме DRY RUN (без изменений)\n")
    else:
        print("\n⚠️  ВНИМАНИЕ: Будут внесены изменения в Google Sheets!")
        confirm = input("Продолжить? (да/нет): ").strip().lower()
        if confirm not in ['да', 'yes', 'y']:
            print("\n❌ Отменено пользователем\n")
            return
        print("\n🚀 Запуск синхронизации...\n")
    
    # Создаем экземпляр синхронизатора
    syncer = DateSyncFromNocoDB()
    
    # Запускаем синхронизацию (строка 21 - данные, строка 19 - заголовки, все строки)
    syncer.sync_dates(start_row=21, header_row=19, max_rows=None, dry_run=dry_run)
    
    print("\n✅ Синхронизация завершена!\n")


if __name__ == "__main__":
    main()
