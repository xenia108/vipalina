"""Проверка местоположения студента в таблице"""
import gspread
from shared_gspread_client import get_shared_gspread_client
from config import GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE, GOOGLE_SHEETS_ID

gc = get_shared_gspread_client(GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE)
spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
ws = spreadsheet.worksheet('Общий список new')

# Ищем студента 483755148
target_id = '483755148'
all_data = ws.get_all_values()

print(f"Всего строк в таблице: {len(all_data)}")
print(f"Ищем студента с ID: {target_id}\n")

for idx, row in enumerate(all_data, start=1):
    if len(row) > 0 and row[0] == target_id:
        print(f"✅ НАЙДЕН в строке {idx}!")
        print(f"   GetCourse ID: {row[0]}")
        print(f"   Имя: {row[2] if len(row) > 2 else 'N/A'}")
        print(f"   Курс: {row[3] if len(row) > 3 else 'N/A'}")
        print(f"   Менеджер: {row[10] if len(row) > 10 else 'N/A'}")
        print(f"\n⚠️ Бот читает только со строки 21 и ниже!")
        if idx < 21:
            print(f"   ПРОБЛЕМА: Студент в строке {idx}, но бот начинает со строки 21")
        break
else:
    print(f"❌ Студент {target_id} не найден в таблице")
