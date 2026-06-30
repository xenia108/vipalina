"""Детальная отладка поиска студента"""
import gspread
from shared_gspread_client import get_shared_gspread_client
from config import GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE, GOOGLE_SHEETS_ID

gc = get_shared_gspread_client(GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE)
spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
ws = spreadsheet.worksheet('Общий список new')

target_id = '483755148'
all_data = ws.get_all_values()

print(f"Ищем студента с ID: '{target_id}'")
print(f"Читаем со строки 21 (индекс 20)...\n")

# Эмулируем логику бота
students_found = []
for row_idx, row in enumerate(all_data[20:], start=21):
    if len(row) < 8 or not row[0]:
        continue
    
    getcourse_id = row[0]
    
    # Сравниваем
    if getcourse_id == target_id:
        print(f"✅ НАЙДЕН в строке {row_idx}")
        print(f"   ID из таблицы: '{getcourse_id}'")
        print(f"   ID для поиска: '{target_id}'")
        print(f"   Совпадение: {getcourse_id == target_id}")
        students_found.append(row_idx)
        break
    
    # Проверяем близкие совпадения
    if target_id in getcourse_id or getcourse_id in target_id:
        print(f"⚠️ Близкое совпадение в строке {row_idx}: '{getcourse_id}'")

if not students_found:
    print(f"❌ Студент НЕ НАЙДЕН при поиске со строки 21")
    print(f"\nПроверяем весь файл...")
    
    for idx, row in enumerate(all_data, start=1):
        if len(row) > 0:
            getcourse_id = row[0]
            if getcourse_id == target_id:
                print(f"   Студент ЕСТЬ в строке {idx}, но бот его пропустил!")
                print(f"   Причина: строка {idx} {'выше' if idx < 21 else 'должна была быть найдена'}")
                break
