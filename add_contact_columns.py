#!/usr/bin/env python3
"""
Скрипт для добавления колонок "Дата последнего контакта" (O) и "Выходит на связь?" (P)
на лист "Випалина".
"""

import gspread
from google.oauth2.service_account import Credentials

# ID таблицы KPI Ultra
KPI_ULTRA_ID = '1MhDUG9IuYJN9lWG_p88UviOnQeiDM3Hj1eVqaoqPqYM'
CREDENTIALS_FILE = 'vipalina_google_credentials.json'

def add_contact_columns():
    """Добавляет колонки для отслеживания активности студентов"""
    
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    gc = gspread.authorize(credentials)
    
    spreadsheet = gc.open_by_key(KPI_ULTRA_ID)
    worksheet = spreadsheet.worksheet('Випалина')
    
    # 1. Добавляем заголовки O1, P1, Q1
    print("Добавлю заголовки O1, P1, Q1...")
    worksheet.update('O1:Q1', [['Дата последнего контакта', 'Выходит на связь?', 'Уведомление о пропаже']])
    
    # 2. Форматируем заголовки
    print("Форматирую заголовки...")
    worksheet.format('O1:Q1', {
        'textFormat': {'bold': True},
        'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
    })
    
    # 3. Получаем количество строк с данными
    all_values = worksheet.col_values(1)  # Колонка A
    last_row = len(all_values)
    print(f"Найдено {last_row} строк")
    
    if last_row > 1:
        # 4. Добавляем формулу для колонки P (для всех строк с данными)
        # Градация:
        # <=3 дней -> 🟢 Активен
        # <=7 дней -> 🔵 Средне
        # <=14 дней -> 🟡 Редко
        # >30 дней -> 🔴 Пропал
        print(f"Добавляю формулы в P2:P{last_row}...")
        
        formulas = []
        for row in range(2, last_row + 1):
            formula = f'=IF(O{row}="";"-";IF(TODAY()-DATEVALUE(LEFT(O{row};10))<=3;"🟢 Активен";IF(TODAY()-DATEVALUE(LEFT(O{row};10))<=7;"🔵 Средне";IF(TODAY()-DATEVALUE(LEFT(O{row};10))<=14;"🟡 Редко";IF(TODAY()-DATEVALUE(LEFT(O{row};10))>30;"🔴 Пропал";"🟡 Редко")))))'
            formulas.append([formula])
        
        worksheet.update(f'P2:P{last_row}', formulas, value_input_option='USER_ENTERED')
    
    print("✅ Готово!")
    print("- Колонка O: Дата последнего контакта (заполняется ботом)")
    print("- Колонка P: Выходит на связь? (формула)")
    print("- Колонка Q: Уведомление о пропаже (дата последнего уведомления)")
    print("")
    print("Статусы:")
    print("  🟢 Активен — писал в последние 3 дня")
    print("  🔵 Средне — писал 4-7 дней назад")
    print("  🟡 Редко — писал 8-14 дней назад")
    print("  🔴 Пропал — не писал более 30 дней")
    print("")
    print("Уведомления:")
    print("  - Первое уведомление при статусе '🔴 Пропал'")
    print("  - Повторное через 7 дней, если чат не деактивирован")

if __name__ == '__main__':
    add_contact_columns()
