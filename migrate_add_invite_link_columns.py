"""
Скрипт миграции: добавление колонки invite_link во все таблицы.
Запустить один раз для обновления существующих таблиц.
"""

import gspread
from google.oauth2.service_account import Credentials
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('migration')

# Credentials
GOOGLE_SHEETS_CREDENTIALS_FILE = "vipalina_google_credentials.json"

# Таблицы
KPI_ULTRA_ID = '1MhDUG9IuYJN9lWG_p88UviOnQeiDM3Hj1eVqaoqPqYM'
SLA_TABLE_ID = '19YcEHA1HvBSfNRHFBK06eC7aRurH5NG6mhyE061BdNY'
LOGS_VIPALINA_ID = '1wWbgAq92qehpTO0lm4AQJzTQ8RvpA9fX_vORYBqkHCE'


def get_client():
    """Получить авторизованный клиент Google Sheets"""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_file(
        GOOGLE_SHEETS_CREDENTIALS_FILE,
        scopes=scopes
    )
    return gspread.authorize(credentials)


def add_column_to_sheet(gc, spreadsheet_id, sheet_name, column_letter, header_name):
    """
    Добавляет заголовок в указанную колонку существующего листа.
    НЕ сдвигает существующие данные!
    
    Args:
        gc: gspread client
        spreadsheet_id: ID таблицы
        sheet_name: Название листа
        column_letter: Буква колонки (например, 'J')
        header_name: Название заголовка
    """
    try:
        spreadsheet = gc.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        # Проверяем текущее значение
        current_value = worksheet.acell(f'{column_letter}1').value
        
        if current_value == header_name:
            logger.info(f"✅ Колонка '{header_name}' уже существует в {sheet_name}")
            return True
        
        if current_value:
            logger.warning(f"⚠️ Колонка {column_letter}1 уже содержит: '{current_value}'")
            logger.warning(f"   Пропускаем, чтобы не потерять данные!")
            return False
        
        # Добавляем заголовок
        worksheet.update(f'{column_letter}1', [[header_name]])
        logger.info(f"✅ Добавлен заголовок '{header_name}' в {sheet_name}!{column_letter}1")
        return True
        
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"❌ Лист '{sheet_name}' не найден в таблице {spreadsheet_id}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении {sheet_name}: {e}")
        return False


def update_existing_headers(gc, spreadsheet_id, sheet_name, new_headers, start_col='A'):
    """
    Обновляет ВСЕ заголовки на листе (перезаписывает первую строку).
    ВНИМАНИЕ: Использовать осторожно!
    """
    try:
        spreadsheet = gc.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        end_col = chr(ord(start_col) + len(new_headers) - 1)
        worksheet.update(f'{start_col}1:{end_col}1', [new_headers])
        logger.info(f"✅ Заголовки обновлены в {sheet_name}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False


def migrate_kpi_ultra_vipalina(gc):
    """Добавить колонку 'Ссылка на чат' на лист 'Випалина' в KPI Ultra"""
    logger.info("=" * 50)
    logger.info("Миграция KPI Ultra - лист 'Випалина'")
    logger.info("=" * 50)
    
    try:
        spreadsheet = gc.open_by_key(KPI_ULTRA_ID)
        worksheet = spreadsheet.worksheet('Випалина')
        
        # Читаем текущие заголовки
        headers = worksheet.row_values(1)
        logger.info(f"Текущие заголовки: {headers}")
        
        # Проверяем, есть ли уже "Ссылка на чат"
        if 'Ссылка на чат' in headers:
            logger.info("✅ Колонка 'Ссылка на чат' уже существует")
            return True
        
        # Вставляем новую колонку после "Трекер" (колонка I -> J)
        # Для этого используем Google Sheets API для вставки колонки
        
        # Индекс колонки J = 9 (0-based)
        # Вставляем колонку после Трекер (I=8)
        insert_col_index = 9  # J (0-based: 9)
        
        # Вставляем пустую колонку
        worksheet.insert_cols([[""] for _ in range(worksheet.row_count)], col=insert_col_index + 1)
        
        # Добавляем заголовок
        worksheet.update(values=[["Ссылка на чат"]], range_name='J1')
        
        logger.info("✅ Вставлена колонка 'Ссылка на чат' в позицию J")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False


def migrate_sla_data(gc):
    """Добавить колонку 'Ссылка на чат' на лист 'SLA_Data'"""
    logger.info("=" * 50)
    logger.info("Миграция SLA - лист 'SLA_Data'")
    logger.info("=" * 50)
    
    try:
        spreadsheet = gc.open_by_key(SLA_TABLE_ID)
        worksheet = spreadsheet.worksheet('SLA_Data')
        
        # Читаем текущие заголовки
        headers = worksheet.row_values(1)
        logger.info(f"Текущие заголовки ({len(headers)}): {headers}")
        
        # Проверяем, есть ли уже "Ссылка на чат"
        if 'Ссылка на чат' in headers:
            logger.info("✅ Колонка 'Ссылка на чат' уже существует")
            return True
        
        # Расширяем таблицу до 20 колонок
        current_cols = worksheet.col_count
        if current_cols < 20:
            worksheet.resize(cols=20)
            logger.info(f"Расширена таблица с {current_cols} до 20 колонок")
        
        # Находим следующую колонку
        next_col = chr(ord('A') + len(headers))
        
        # Добавляем заголовок
        worksheet.update(values=[['Ссылка на чат']], range_name=f'{next_col}1')
        logger.info(f"✅ Добавлен заголовок 'Ссылка на чат' в колонку {next_col}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False


def migrate_logs_vipalina_chat_to_student(gc):
    """Добавить колонку 'invite_link' на лист 'Chat_To_Student'"""
    logger.info("=" * 50)
    logger.info("Миграция Логи Випалина - лист 'Chat_To_Student'")
    logger.info("=" * 50)
    
    try:
        spreadsheet = gc.open_by_key(LOGS_VIPALINA_ID)
        worksheet = spreadsheet.worksheet('Chat_To_Student')
        
        # Читаем текущие заголовки
        headers = worksheet.row_values(1)
        logger.info(f"Текущие заголовки: {headers}")
        
        # Проверяем, есть ли уже invite_link
        if 'invite_link' in headers:
            logger.info("✅ Колонка 'invite_link' уже существует")
            return True
        
        # Обновляем заголовки - вставляем invite_link после student_name
        new_headers = ["chat_id", "getcourse_id", "student_name", "invite_link", "created_at", "updated_at"]
        worksheet.update(values=[new_headers], range_name='A1:F1')
        logger.info("✅ Заголовки обновлены с добавлением 'invite_link'")
        return True
            
    except gspread.exceptions.WorksheetNotFound:
        logger.error("❌ Лист 'Chat_To_Student' не найден")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False


def main():
    """Запуск миграции"""
    logger.info("🚀 Начинаем миграцию таблиц...")
    logger.info("")
    
    gc = get_client()
    
    results = []
    
    # 1. KPI Ultra - Випалина
    results.append(("KPI Ultra - Випалина", migrate_kpi_ultra_vipalina(gc)))
    
    # 2. SLA Data
    results.append(("SLA Data", migrate_sla_data(gc)))
    
    # 3. Логи Випалина - Chat_To_Student
    results.append(("Логи Випалина - Chat_To_Student", migrate_logs_vipalina_chat_to_student(gc)))
    
    # Итоги
    logger.info("")
    logger.info("=" * 50)
    logger.info("РЕЗУЛЬТАТЫ МИГРАЦИИ:")
    logger.info("=" * 50)
    
    for name, success in results:
        status = "✅ OK" if success else "❌ ОШИБКА"
        logger.info(f"  {status}: {name}")
    
    all_success = all(r[1] for r in results)
    if all_success:
        logger.info("")
        logger.info("🎉 Миграция завершена успешно!")
    else:
        logger.info("")
        logger.warning("⚠️ Некоторые миграции не выполнены. Проверьте логи.")
    
    return all_success


if __name__ == "__main__":
    main()
