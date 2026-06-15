"""
Скрипт: поиск и автозаполнение пустых значений в колонках B, C, F листа "Випалина".
Источник данных: листы Chat_To_Student и Students_Data из "Логи Випалина".

Колонки Випалина:
  A = GetCourse ID
  B = Telegram ID (telegram_id)
  C = Chat ID     (chat_id)
  D = Имя
  F = Username    (telegram_username)
  L = Статус
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))

import gspread
from google.oauth2.service_account import Credentials

VIPALINA_ID      = '1MhDUG9IuYJN9lWG_p88UviOnQeiDM3Hj1eVqaoqPqYM'
LOGS_ID          = '1wWbgAq92qehpTO0lm4AQJzTQ8RvpA9fX_vORYBqkHCE'
VIPALINA_TAB     = 'Випалина'
SERVICE_ACCOUNT  = os.path.join(os.path.dirname(__file__), 'vipalina_google_service_account.json')

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

def is_empty(val):
    return not val or val.strip() in ('', '-', 'None')

def main():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT, scopes=SCOPES)
    gc    = gspread.authorize(creds)

    # ── 1. Читаем Chat_To_Student → reverse map: getcourse_id → chat_id
    print("Читаю Chat_To_Student...")
    cts_ws  = gc.open_by_key(LOGS_ID).worksheet('Chat_To_Student')
    cts_rows = cts_ws.get_all_values()
    # A=chat_id, B=getcourse_id
    chat_by_gid = {}
    for row in cts_rows[1:]:
        if len(row) >= 2 and row[0] and row[1]:
            gid = str(row[1]).strip()
            cid = str(row[0]).strip()
            if gid and cid:
                chat_by_gid[gid] = cid
    print(f"  Загружено {len(chat_by_gid)} пар chat_id↔getcourse_id")

    # ── 2. Читаем Students_Data → getcourse_id → {telegram_id, username}
    print("Читаю Students_Data...")
    sd_ws   = gc.open_by_key(LOGS_ID).worksheet('Students_Data')
    sd_rows = sd_ws.get_all_values()
    # A=getcourse_id, F=username(idx5), G=telegram_id(idx6)
    tg_by_gid = {}
    for row in sd_rows[1:]:
        if len(row) >= 1 and row[0]:
            gid = str(row[0]).strip()
            tg_id  = str(row[6]).strip() if len(row) > 6 else ''
            tg_usr = str(row[5]).strip() if len(row) > 5 else ''
            tg_by_gid[gid] = {'telegram_id': tg_id, 'username': tg_usr}
    print(f"  Загружено {len(tg_by_gid)} студентов из Students_Data\n")

    # ── 3. Читаем Випалина
    print("Читаю Випалина...")
    vip_ws   = gc.open_by_key(VIPALINA_ID).worksheet(VIPALINA_TAB)
    vip_rows = vip_ws.get_all_values()

    to_fix = []  # (row_idx, getcourse_id, name, miss_b, miss_c, miss_f, new_b, new_c, new_f)

    for idx, row in enumerate(vip_rows[1:], start=2):
        if not any(row):
            continue
        status = row[11].strip() if len(row) > 11 else ''
        if status == 'Неактивен':
            continue

        gid   = row[0].strip() if len(row) > 0 else ''
        name  = row[3].strip() if len(row) > 3 else ''
        b_val = row[1].strip() if len(row) > 1 else ''
        c_val = row[2].strip() if len(row) > 2 else ''
        f_val = row[5].strip() if len(row) > 5 else ''

        miss_b = is_empty(b_val)
        miss_c = is_empty(c_val)
        miss_f = is_empty(f_val)

        if not (miss_b or miss_c or miss_f):
            continue

        # Ищем данные из логов
        new_b = tg_by_gid.get(gid, {}).get('telegram_id', '') if miss_b else ''
        new_c = chat_by_gid.get(gid, '')                        if miss_c else ''
        new_f = tg_by_gid.get(gid, {}).get('username', '')     if miss_f else ''

        # Очищаем если пусто/невалидно
        if is_empty(new_b): new_b = ''
        if is_empty(new_c): new_c = ''
        if is_empty(new_f): new_f = ''

        to_fix.append((idx, gid, name, miss_b, miss_c, miss_f, new_b, new_c, new_f))

    # ── 4. Отчёт
    print(f"{'='*65}")
    print(f"Активных строк с пропусками: {len(to_fix)}")
    print(f"{'='*65}")
    fmt = "{:<5} {:<12} {:<18} {:^5} {:^5} {:^5}  {}"
    print(fmt.format("Стр.", "GetCourse ID", "Имя", "B?", "C?", "F?", "Можем заполнить"))
    print("─" * 65)

    fixable = []
    for row in to_fix:
        idx, gid, name, mb, mc, mf, nb, nc, nf = row
        flags = []
        can   = []
        if mb: flags.append('B'); (can.append(f'B={nb[:12]}') if nb else None)
        if mc: flags.append('C'); (can.append(f'C={nc[:15]}') if nc else None)
        if mf: flags.append('F'); (can.append(f'F={nf[:15]}') if nf else None)
        has_fix = bool(nb or nc or nf)
        print(fmt.format(
            idx, gid[:12], name[:18],
            'X' if mb else '.', 'X' if mc else '.', 'X' if mf else '.',
            ', '.join(can) if can else '—'
        ))
        if has_fix:
            fixable.append(row)

    print(f"\nМожно заполнить из логов: {len(fixable)} из {len(to_fix)}")

    if not fixable:
        print("Нет данных для заполнения.")
        return

    # ── 5. Спрашиваем подтверждение
    print(f"\n{'='*65}")
    ans = input(f"Заполнить {len(fixable)} строк? [да/нет]: ").strip().lower()
    if ans not in ('да', 'y', 'yes', 'd'):
        print("Отмена.")
        return

    # ── 6. Обновляем ячейки
    updated = 0
    errors  = 0
    for row in fixable:
        idx, gid, name, mb, mc, mf, nb, nc, nf = row
        try:
            if mb and nb:
                vip_ws.update(f'B{idx}', [[nb]])
                time.sleep(0.5)
            if mc and nc:
                vip_ws.update(f'C{idx}', [[nc]])
                time.sleep(0.5)
            if mf and nf:
                vip_ws.update(f'F{idx}', [[nf]])
                time.sleep(0.5)
            print(f"  ✅ Стр.{idx} ({name}): обновлено")
            updated += 1
        except Exception as e:
            print(f"  ❌ Стр.{idx} ({name}): ошибка — {e}")
            errors += 1
            time.sleep(2)

    print(f"\n{'='*65}")
    print(f"Готово: обновлено {updated}, ошибок {errors}")
    print(f"{'='*65}\n")

if __name__ == '__main__':
    main()

