"""
Вставляет таблицу аналитики KPI менеджеров на лист "Прогресс менеджеров".
Март26 → начало с O38.
Структура: Менеджер | Студентов | ✅ Норма | ❌ Не выполн. | KPI%
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))

import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID   = '1MhDUG9IuYJN9lWG_p88UviOnQeiDM3Hj1eVqaoqPqYM'
SHEET_NAME       = 'Прогресс менеджеров'
SERVICE_ACCOUNT  = os.path.join(os.path.dirname(__file__), 'vipalina_google_service_account.json')

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

# Параметры таблицы
MONTH_LABEL  = 'Март26'
START_ROW    = 38   # первая строка (заголовки)
START_COL    = 15   # O = 15

MANAGERS = [
    "Марина Иванова",
    "Оля Антипанова",
    "Кристина Махмудян",
    "Лиза Виноградова",
    "Катя Чайка",
    "Оля Тихонова",
    "Катя Пилипенко",
    "Ксюша Уланова",
]

# Диапазоны данных (строки 2..5000, чтобы не захватить будущие аналитики)
C = "$C$2:$C$5000"
M = "$M$2:$M$5000"
D = "$D$2:$D$5000"
J = "$J$2:$J$5000"

def col_letter(col_idx):
    """1-based → буква столбца (O=15 → 'O')"""
    result = ""
    while col_idx > 0:
        col_idx, rem = divmod(col_idx - 1, 26)
        result = chr(65 + rem) + result
    return result

O = col_letter(START_COL)      # O
P = col_letter(START_COL + 1)  # P
Q = col_letter(START_COL + 2)  # Q
R = col_letter(START_COL + 3)  # R
S = col_letter(START_COL + 4)  # S

def total_formula(row):
    return (
        f'=СЧЁТЕСЛИМН({C};{O}{row};{M};"{MONTH_LABEL}";{D};"Учится")'
    )

def done_formula(row):
    return (
        f'=СЧЁТЕСЛИМН({C};{O}{row};{M};"{MONTH_LABEL}";{D};"Учится";{J};"✅")'
    )

def not_done_formula(row):
    return f'={P}{row}-{Q}{row}'

def pct_formula(row):
    return f'=ЕСЛИ({P}{row}=0;"-";ТЕКСТ({Q}{row}/{P}{row};"0%"))'

def main():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    ws    = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

    header_row = START_ROW
    data_start = START_ROW + 1          # строка первого менеджера
    total_row  = data_start + len(MANAGERS)  # строка ИТОГО

    # ── Заголовки (O38:S38)
    print(f"Вставляю заголовки в {O}{header_row}:{S}{header_row}...")
    ws.update(
        f'{O}{header_row}:{S}{header_row}',
        [[f'📊 {MONTH_LABEL}', 'Студентов', '✅ Норма', '❌ Нет', 'KPI%']],
        value_input_option='USER_ENTERED'
    )
    time.sleep(1)

    # ── Строки по каждому менеджеру
    for i, mgr in enumerate(MANAGERS):
        row = data_start + i
        print(f"  Стр.{row}: {mgr}")
        ws.update(
            f'{O}{row}:{S}{row}',
            [[mgr, total_formula(row), done_formula(row), not_done_formula(row), pct_formula(row)]],
            value_input_option='USER_ENTERED'
        )
        time.sleep(0.8)

    # ── Строка ИТОГО
    print(f"Вставляю ИТОГО в строку {total_row}...")
    ws.update(
        f'{O}{total_row}:{S}{total_row}',
        [[
            'ИТОГО',
            f'=СУММ({P}{data_start}:{P}{total_row-1})',
            f'=СУММ({Q}{data_start}:{Q}{total_row-1})',
            f'=СУММ({R}{data_start}:{R}{total_row-1})',
            f'=ЕСЛИ({P}{total_row}=0;"-";ТЕКСТ({Q}{total_row}/{P}{total_row};"0%"))',
        ]],
        value_input_option='USER_ENTERED'
    )
    time.sleep(1)

    # ── Форматирование заголовков (жирный)
    print("Форматирую заголовки...")
    ws.format(f'{O}{header_row}:{S}{header_row}', {
        'textFormat': {'bold': True},
        'backgroundColor': {'red': 0.85, 'green': 0.92, 'blue': 0.98}
    })
    time.sleep(0.5)

    # ── Форматирование строки ИТОГО (жирный)
    ws.format(f'{O}{total_row}:{S}{total_row}', {
        'textFormat': {'bold': True},
        'backgroundColor': {'red': 0.95, 'green': 0.95, 'blue': 0.95}
    })

    print(f"\n✅ Таблица аналитики '{MONTH_LABEL}' вставлена: {O}{header_row}:{S}{total_row}")
    print(f"   Менеджеры: строки {data_start}–{total_row-1}")
    print(f"   ИТОГО: строка {total_row}")

if __name__ == '__main__':
    main()
