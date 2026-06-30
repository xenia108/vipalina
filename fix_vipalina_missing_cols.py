"""
Скрипт: заполняет пустые B (telegram_id), C (chat_id), F (username) на листе Випалина
Источники данных:
  1. Логи Випалина / Students_Data  → telegram_id, telegram_username
  2. Логи Випалина / Chat_To_Student → chat_id (по getcourse_id)
  3. KPI Ultra / Общий список new   → ссылка на чат (колонка G)
"""
import sys, os, json
os.chdir('/root/ksushiny_terminatory/vipalina')
sys.path.insert(0, '.')

DRY_RUN = False  # Поменяй на False для реального применения

from tracker_creator import TrackerCreator
creator = TrackerCreator('vipalina_google_credentials.json')
gc = creator.sheets_client

LOGS_ID = '1wWbgAq92qehpTO0lm4AQJzTQ8RvpA9fX_vORYBqkHCE'
KPI_ID  = '1MhDUG9IuYJN9lWG_p88UviOnQeiDM3Hj1eVqaoqPqYM'

print("=== Загружаю данные ===")

# 1. Логи Випалина → Students_Data: getcourse_id → {telegram_id, username}
logs_ss = gc.open_by_key(LOGS_ID)
students_data_ws = logs_ss.worksheet('Students_Data')
sd_rows = students_data_ws.get_all_values()
# Колонки: getcourse_id(0), name(1), email(2), phone(3), course(4), telegram_username(5), telegram_id(6)
students_lookup = {}  # getcourse_id → {telegram_id, username}
for row in sd_rows[1:]:
    if not row or not row[0]:
        continue
    gcid = row[0].strip()
    tg_id = row[6].strip() if len(row) > 6 else ''
    tg_user = row[5].strip() if len(row) > 5 else ''
    if gcid:
        students_lookup[gcid] = {'telegram_id': tg_id, 'username': tg_user}
print(f"  Students_Data: {len(students_lookup)} записей")

# 2. Логи Випалина → Chat_To_Student: getcourse_id → chat_id
chat_ws = logs_ss.worksheet('Chat_To_Student')
chat_rows = chat_ws.get_all_values()
# Колонки: chat_id(0), getcourse_id(1), student_name(2), invite_link(3)
chat_lookup = {}  # getcourse_id → {chat_id, invite_link}
for row in chat_rows[1:]:
    if not row or not row[1]:
        continue
    gcid = row[1].strip()
    cid = row[0].strip()
    inv = row[3].strip() if len(row) > 3 else ''
    if gcid and cid:
        chat_lookup[gcid] = {'chat_id': cid, 'invite_link': inv}
print(f"  Chat_To_Student: {len(chat_lookup)} записей")

# 3. KPI Ultra → Общий список new: getcourse_id → invite_link (колонка G)
kpi_lookup = {}
try:
    kpi_ss = gc.open_by_key(KPI_ID)
    kpi_ws = kpi_ss.worksheet('Общий список new')
    kpi_rows = kpi_ws.get_all_values()
    # A: формула/ID, нужен GetCourse ID из колонки A (числовой)
    # B: GetCourse URL, C: имя, D: курс, F: трекер, G: invite link
    for row in kpi_rows[1:]:
        if not row or not row[0]:
            continue
        gcid = row[0].strip()
        invite = row[6].strip() if len(row) > 6 else ''
        if gcid and gcid.isdigit():
            kpi_lookup[gcid] = {'invite_link': invite}
    print(f"  KPI Общий список new: {len(kpi_lookup)} записей")
except Exception as e:
    print(f"  KPI Ultra недоступен: {e}")

# 4. Читаем Випалина
kpi_ss2 = gc.open_by_key(KPI_ID)
vip_ws = kpi_ss2.worksheet('Випалина')
vip_data = vip_ws.get_all_values()
# A:GetCourseID, B:TelegramID, C:ChatID, D:Name, E:Course, F:Username, ...

print(f"\nВипалина: {len(vip_data)-1} строк данных")
print("=== Анализ ===\n")

updates = []  # список: (row_idx, col_letter, new_value, reason)

for i, row in enumerate(vip_data[1:], start=2):
    if not row or not row[0]:
        continue
    gcid = row[0].strip()
    b_val = row[1].strip() if len(row) > 1 else ''
    c_val = row[2].strip() if len(row) > 2 else ''
    f_val = row[5].strip() if len(row) > 5 else ''

    needs_b = not b_val or b_val == '-'
    needs_c = not c_val or c_val == '-'
    needs_f = not f_val or f_val == '-'

    if not (needs_b or needs_c or needs_f):
        continue

    sd = students_lookup.get(gcid, {})
    cd = chat_lookup.get(gcid, {})

    # B: Telegram ID
    if needs_b and sd.get('telegram_id') and sd['telegram_id'] != '0':
        updates.append((i, 'B', sd['telegram_id'], f'Students_Data'))

    # C: Chat ID
    if needs_c and cd.get('chat_id'):
        updates.append((i, 'C', cd['chat_id'], f'Chat_To_Student'))

    # F: Username
    if needs_f and sd.get('username'):
        updates.append((i, 'F', sd['username'], f'Students_Data'))

    if needs_b or needs_c or needs_f:
        name = row[3].strip() if len(row) > 3 else '?'
        found_b = sd.get('telegram_id', '') if needs_b else '(уже есть)'
        found_c = cd.get('chat_id', '') if needs_c else '(уже есть)'
        found_f = sd.get('username', '') if needs_f else '(уже есть)'
        print(f"  Строка {i}: {gcid} ({name})")
        if needs_b: print(f"    B (telegram_id): '{b_val}' → '{found_b or '❌ не найден'}'")
        if needs_c: print(f"    C (chat_id):     '{c_val}' → '{found_c or '❌ не найден'}'")
        if needs_f: print(f"    F (username):    '{f_val}' → '{found_f or '❌ не найден'}'")

print(f"\n=== Итог: {len(updates)} ячеек для обновления ===")

if DRY_RUN:
    print("\n[DRY RUN] Изменения НЕ применены. Поменяй DRY_RUN=False для применения.")
else:
    print("\nПрименяю изменения...")
    for row_idx, col, val, src in updates:
        try:
            vip_ws.update(f'{col}{row_idx}', [[val]])
            print(f"  ✅ {col}{row_idx} = '{val}' (из {src})")
        except Exception as e:
            print(f"  ❌ {col}{row_idx}: {e}")
    print("Готово.")
