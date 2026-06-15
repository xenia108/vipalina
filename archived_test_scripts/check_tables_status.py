"""
Проверка статуса таблиц после миграции.
"""

import gspread
from google.oauth2.service_account import Credentials

# Credentials
GOOGLE_SHEETS_CREDENTIALS_FILE = "vipalina_google_credentials.json"

# Таблицы
KPI_ULTRA_ID = '1MhDUG9IuYJN9lWG_p88UviOnQeiDM3Hj1eVqaoqPqYM'
SLA_TABLE_ID = '19YcEHA1HvBSfNRHFBK06eC7aRurH5NG6mhyE061BdNY'
LOGS_VIPALINA_ID = '1wWbgAq92qehpTO0lm4AQJzTQ8RvpA9fX_vORYBqkHCE'


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


def check_sheets():
    gc = get_client()
    
    print("=" * 60)
    print("ПРОВЕРКА СТАТУСА ТАБЛИЦ")
    print("=" * 60)
    
    # 1. KPI Ultra - Випалина
    print("\n1. KPI Ultra - лист 'Випалина':")
    try:
        spreadsheet = gc.open_by_key(KPI_ULTRA_ID)
        worksheet = spreadsheet.worksheet('Випалина')
        headers = worksheet.row_values(1)
        print(f"   Количество колонок: {len(headers)}")
        for i, h in enumerate(headers):
            col_letter = chr(ord('A') + i)
            print(f"   {col_letter}: {h}")
        
        # Проверяем наличие "Ссылка на чат"
        if 'Ссылка на чат' in headers:
            idx = headers.index('Ссылка на чат')
            print(f"\n   ✅ Колонка 'Ссылка на чат' найдена в позиции {chr(ord('A') + idx)}")
        else:
            print(f"\n   ❌ Колонка 'Ссылка на чат' НЕ найдена!")
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    # 2. SLA Data
    print("\n2. SLA - лист 'SLA_Data':")
    try:
        spreadsheet = gc.open_by_key(SLA_TABLE_ID)
        worksheet = spreadsheet.worksheet('SLA_Data')
        headers = worksheet.row_values(1)
        print(f"   Количество колонок: {len(headers)}")
        for i, h in enumerate(headers):
            col_letter = chr(ord('A') + i) if i < 26 else chr(ord('A') + i // 26 - 1) + chr(ord('A') + i % 26)
            print(f"   {col_letter}: {h}")
        
        # Проверяем наличие "Ссылка на чат"
        if 'Ссылка на чат' in headers:
            idx = headers.index('Ссылка на чат')
            col_letter = chr(ord('A') + idx) if idx < 26 else chr(ord('A') + idx // 26 - 1) + chr(ord('A') + idx % 26)
            print(f"\n   ✅ Колонка 'Ссылка на чат' найдена в позиции {col_letter}")
        else:
            print(f"\n   ❌ Колонка 'Ссылка на чат' НЕ найдена!")
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    # 3. Логи Випалина - Chat_To_Student
    print("\n3. Логи Випалина - лист 'Chat_To_Student':")
    try:
        spreadsheet = gc.open_by_key(LOGS_VIPALINA_ID)
        worksheet = spreadsheet.worksheet('Chat_To_Student')
        headers = worksheet.row_values(1)
        print(f"   Количество колонок: {len(headers)}")
        for i, h in enumerate(headers):
            col_letter = chr(ord('A') + i)
            print(f"   {col_letter}: {h}")
        
        # Проверяем наличие "invite_link"
        if 'invite_link' in headers:
            idx = headers.index('invite_link')
            print(f"\n   ✅ Колонка 'invite_link' найдена в позиции {chr(ord('A') + idx)}")
        else:
            print(f"\n   ❌ Колонка 'invite_link' НЕ найдена!")
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    check_sheets()
