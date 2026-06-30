"""
Очистка лишних колонок после миграции.
"""

import gspread
from google.oauth2.service_account import Credentials

GOOGLE_SHEETS_CREDENTIALS_FILE = "vipalina_google_credentials.json"
KPI_ULTRA_ID = '1MhDUG9IuYJN9lWG_p88UviOnQeiDM3Hj1eVqaoqPqYM'


def get_client():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_file(
        GOOGLE_SHEETS_CREDENTIALS_FILE,
        scopes=scopes
    )
    return gspread.authorize(credentials)


def cleanup_vipalina_sheet():
    """Удаляем лишнюю пустую колонку K и дубликат O"""
    gc = get_client()
    
    print("Очистка листа 'Випалина' в KPI Ultra...")
    
    try:
        spreadsheet = gc.open_by_key(KPI_ULTRA_ID)
        worksheet = spreadsheet.worksheet('Випалина')
        
        headers = worksheet.row_values(1)
        print(f"Текущие заголовки: {headers}")
        
        # Удаляем колонку O (дубликат "Последнее обновление") - индекс 15
        # Потом удаляем колонку K (пустую) - индекс 11
        # ВАЖНО: удаляем с конца, чтобы не сбить индексы
        
        # Находим индексы для удаления
        indices_to_delete = []
        
        # Проверяем O (индекс 14, колонка 15)
        if len(headers) >= 15 and headers[14] == headers[13]:  # Дубликат
            indices_to_delete.append(15)  # 1-based для gspread
            print(f"Будет удалена дублирующая колонка O: '{headers[14]}'")
        
        # Проверяем K (индекс 10, колонка 11)
        if len(headers) >= 11 and headers[10] == '':  # Пустая
            indices_to_delete.append(11)
            print(f"Будет удалена пустая колонка K")
        
        # Удаляем с конца (чтобы не сбить индексы)
        indices_to_delete.sort(reverse=True)
        
        for col_idx in indices_to_delete:
            worksheet.delete_columns(col_idx)
            print(f"Удалена колонка {col_idx}")
        
        # Проверяем результат
        new_headers = worksheet.row_values(1)
        print(f"\nНовые заголовки: {new_headers}")
        print(f"Количество колонок: {len(new_headers)}")
        
        # Ожидаемые заголовки:
        expected = [
            'GetCourse ID', 'Telegram ID', 'Chat ID', 'Имя студента', 'Курс',
            'Username', 'Менеджер ID', 'Менеджер Имя', 'Трекер', 'Ссылка на чат',
            'Дата создания чата', 'Статус', 'Последнее обновление'
        ]
        
        if new_headers == expected:
            print("\n✅ Заголовки соответствуют ожидаемым!")
        else:
            print(f"\n⚠️ Заголовки отличаются от ожидаемых:")
            print(f"Ожидаемые: {expected}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


if __name__ == "__main__":
    cleanup_vipalina_sheet()
