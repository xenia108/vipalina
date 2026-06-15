"""Проверка студента в листе Випалина"""
import gspread
from shared_gspread_client import get_shared_gspread_client
from config import GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE, GOOGLE_SHEETS_ID

gc = get_shared_gspread_client(GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE)
spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)

target_id = '483755148'

# Проверяем в "Общий список new"
ws_kpi = spreadsheet.worksheet('Общий список new')
kpi_data = ws_kpi.get_all_values()
kpi_found = False
for idx, row in enumerate(kpi_data, start=1):
    if len(row) > 0 and row[0] == target_id:
        kpi_found = True
        print(f"✅ НАЙДЕН в 'Общий список new' (строка {idx})")
        print(f"   Имя: {row[2] if len(row) > 2 else 'N/A'}")
        print(f"   Менеджер: {row[10] if len(row) > 10 else 'N/A'}")
        break

if not kpi_found:
    print(f"❌ НЕ НАЙДЕН в 'Общий список new'")

# Проверяем в "Випалина"
ws_vip = spreadsheet.worksheet('Випалина')
vip_data = ws_vip.get_all_values()
vip_found = False
for idx, row in enumerate(vip_data, start=1):
    if len(row) > 0 and row[0] == target_id:
        vip_found = True
        print(f"\n✅ НАЙДЕН в 'Випалина' (строка {idx})")
        print(f"   Имя: {row[3] if len(row) > 3 else 'N/A'}")
        print(f"   Менеджер: {row[7] if len(row) > 7 else 'N/A'}")
        break

if not vip_found:
    print(f"\n❌ НЕ НАЙДЕН в 'Випалина'")
    print(f"   ⚠️ Возможно студент еще не прошел онбординг через Випалину")
