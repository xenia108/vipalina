#!/usr/bin/env python3
"""
Проверка загрузки chat_to_student с детальным логированием
"""
import gspread
from oauth2client.service_account import ServiceAccountCredentials

SERVICE_ACCOUNT_FILE = 'vipalina_google_service_account.json'
PERSISTENCE_TABLE_ID = '1wWbgAq92qehpTO0lm4AQJzTQ8RvpA9fX_vORYBqkHCE'

def init_sheets():
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    return gspread.authorize(creds)

def main():
    print("🔍 ДЕТАЛЬНАЯ ПРОВЕРКА ЗАГРУЗКИ CHAT_TO_STUDENT\n")
    
    client = init_sheets()
    spreadsheet = client.open_by_key(PERSISTENCE_TABLE_ID)
    worksheet = spreadsheet.worksheet('Chat_To_Student')
    
    all_data = worksheet.get_all_values()
    
    print(f"📋 Всего строк в таблице: {len(all_data)}")
    print(f"📋 Заголовки: {all_data[0]}\n")
    
    result = {}
    
    for idx, row in enumerate(all_data[1:], start=2):
        print(f"\n{'='*80}")
        print(f"Строка {idx}: {row}")
        print(f"{'='*80}")
        
        # Проверка длины
        if len(row) < 2:
            print(f"❌ ПРОПУЩЕНА: недостаточно столбцов (len={len(row)})")
            continue
        
        # Проверка наличия значений
        if not row[0]:
            print(f"❌ ПРОПУЩЕНА: пустой chat_id (row[0])")
            continue
            
        if not row[1]:
            print(f"❌ ПРОПУЩЕНА: пустой getcourse_id (row[1])")
            continue
        
        # Попытка преобразования
        try:
            chat_id = int(row[0])
            getcourse_id = row[1]
            
            print(f"✅ УСПЕШНО ЗАГРУЖЕНА:")
            print(f"   chat_id: {chat_id}")
            print(f"   getcourse_id: {getcourse_id}")
            print(f"   student_name: {row[2] if len(row) > 2 else 'N/A'}")
            print(f"   invite_link: {row[3] if len(row) > 3 else 'N/A'}")
            
            result[chat_id] = getcourse_id
            
        except ValueError as e:
            print(f"❌ ОШИБКА ПРЕОБРАЗОВАНИЯ: {e}")
            print(f"   row[0] = '{row[0]}'")
            print(f"   row[1] = '{row[1]}'")
            continue
    
    print(f"\n{'='*80}")
    print(f"📊 ИТОГО ЗАГРУЖЕНО: {len(result)} связей")
    print(f"{'='*80}\n")
    
    for chat_id, getcourse_id in result.items():
        print(f"  {chat_id} → {getcourse_id}")
    
    # Проверяем Ксению
    ksenia_chat_id = -1003279277783
    if ksenia_chat_id in result:
        print(f"\n✅ ЧАТ КСЕНИИ НАЙДЕН: {ksenia_chat_id} → {result[ksenia_chat_id]}")
    else:
        print(f"\n❌ ЧАТ КСЕНИИ НЕ НАЙДЕН: {ksenia_chat_id}")

if __name__ == '__main__':
    main()
