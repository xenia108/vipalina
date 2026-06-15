#!/usr/bin/env python3
"""
Одноразовый скрипт: добавляет Оксану Ногину в "Общий список new" (KPI Ultra).
Повторяет логику add_student_to_kpi_sheet из vipalina_kpi_sheets.py.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from config import GOOGLE_SHEETS_ID, GOOGLE_SHEETS_KPI_TAB, GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE
from shared_gspread_client import get_shared_gspread_client

# --- Данные студентки ---
STUDENT = {
    'getcourse_url': 'https://go.zerocoder.ru/cms/system/people/user/434972327',
    'name': 'Оксана Ногина',
    'course': 'Абонемент Навсегда, VIP',
    'manager': 'Оля Антипанова',
    'tracker_url': 'https://docs.google.com/spreadsheets/d/1AH5AMP9TDPZEk0L23W2exeJstDtNegwxvWGUliFOOvI',
    'invite_link': 'https://t.me/+OJvfgAZ5PMcwMDky',
}

TARGET_ROW = 21

def main():
    print(f"Подключение к таблице {GOOGLE_SHEETS_ID}, лист '{GOOGLE_SHEETS_KPI_TAB}'...")
    gc = get_shared_gspread_client(GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE)
    spreadsheet = gc.open_by_key(GOOGLE_SHEETS_ID)
    ws = spreadsheet.worksheet(GOOGLE_SHEETS_KPI_TAB)
    print("✅ Подключено")

    # 1. Вставляем пустую строку над 21
    print("Вставка новой строки над строкой 21...")
    ws.insert_row([], index=TARGET_ROW)
    print("✅ Строка вставлена")
    time.sleep(2)

    # 2. Копируем формулы из строки 22 (бывшей 21) в строку 21
    print("Копирование формул из строки 22 → строку 21 (T:ZZ)...")
    source_row = 22
    source_formulas = ws.get(f'T{source_row}:GY{source_row}', value_render_option='FORMULA')
    source_formulas = source_formulas[0] if source_formulas else []
    
    updated_formulas = []
    for formula in source_formulas:
        if formula and str(source_row) in str(formula):
            updated_formulas.append(str(formula).replace(str(source_row), str(TARGET_ROW)))
        else:
            updated_formulas.append(formula)
    
    if updated_formulas:
        ws.update(f'T{TARGET_ROW}:GY{TARGET_ROW}', [updated_formulas], value_input_option='USER_ENTERED')
        print(f"✅ {len(updated_formulas)} формул скопировано")
    time.sleep(2)

    # 3. Заполняем основные данные (RAW)
    first_name = STUDENT['name'].split()[0]  # Оксана
    print(f"Заполнение данных: {first_name}, курс: {STUDENT['course']}, менеджер: {STUDENT['manager']}")
    
    ws.batch_update([
        {'range': f'B{TARGET_ROW}', 'values': [[STUDENT['getcourse_url']]]},
        {'range': f'C{TARGET_ROW}', 'values': [[first_name]]},
        {'range': f'D{TARGET_ROW}', 'values': [[STUDENT['course']]]},
        {'range': f'E{TARGET_ROW}', 'values': [['']]},  # NocoDB — не создана
        {'range': f'F{TARGET_ROW}', 'values': [[STUDENT['tracker_url']]]},
        {'range': f'G{TARGET_ROW}', 'values': [[STUDENT['invite_link']]]},
        {'range': f'K{TARGET_ROW}', 'values': [[STUDENT['manager']]]},
    ], value_input_option='RAW')
    print("✅ RAW данные записаны")
    time.sleep(1)

    # 4. Формулы (USER_ENTERED)
    id_formula = f'=REGEXEXTRACT(B{TARGET_ROW};"id/(\\d+)")'
    h_formula = f'=IMPORTRANGE(F{TARGET_ROW};"📈 Статистика!C4")'
    support_end = f'=ЕСЛИ(ИЛИ(H{TARGET_ROW}="";H{TARGET_ROW}="");"";ДАТАМЕС(H{TARGET_ROW};ЕСЛИОШИБКА(ВПР(D{TARGET_ROW};\'Матрица курсов\'!B:F;5;0);0)))'
    profitability_end = f'=ЕСЛИ(ИЛИ(H{TARGET_ROW}="";H{TARGET_ROW}="");"";ДАТАМЕС(H{TARGET_ROW};ЕСЛИОШИБКА(ВПР(D{TARGET_ROW};\'Матрица курсов\'!B:G;6;0);0)))'

    ws.batch_update([
        {'range': f'A{TARGET_ROW}', 'values': [[id_formula]]},
        {'range': f'H{TARGET_ROW}', 'values': [[h_formula]]},
        {'range': f'I{TARGET_ROW}', 'values': [[support_end]]},
        {'range': f'J{TARGET_ROW}', 'values': [[profitability_end]]},
    ], value_input_option='USER_ENTERED')
    print("✅ Формулы записаны")

    print("\n🎉 Готово! Оксана Ногина добавлена в 'Общий список new', строка 21")

if __name__ == '__main__':
    main()
