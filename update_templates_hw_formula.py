"""
Обновляет лист "📊 Сданные ДЗ" в обоих шаблонах трекеров:
  - B2: QUERY(IMPORTRANGE) — один вызов вместо восьми
  - C2:E2: очищаются (заполняет спилл QUERY)

Запускать на сервере: python3 update_templates_hw_formula.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from tracker_creator import TrackerCreator, _sheets_call_with_retry

HW_SPREADSHEET_ID = "1BvRH7-KL5glYXEgRJsa2s49BiHh4m875iQ8nBJDIcu4"

FORMULA_B2 = (
    f'=ЕСЛИ(A2="";"";QUERY(IMPORTRANGE("{HW_SPREADSHEET_ID}";"\'ВСЕ ДЗ\'!A:H");'
    '"SELECT Col2, Col5, Col6, Col8 WHERE Col1 = "&ТЕКСТ(A2;"0")&" LABEL Col2 \'\', Col5 \'\', Col6 \'\', Col8 \'\'"'
    ';0))'
)

TEMPLATES = {
    'ШАБЛОН (Курс)':  '1gH1Sd7BCeUFBqufXUy63nVjWPcNmGNq312iL8-_Y_rQ',
    'ШАБЛОН (Абоны)': os.getenv('TEMPLATE_TARIFF_TRACKER_ID', '1WDtCWwCDxgmv106v5nRAiy1V_zNOFRhz3PH481NuWAw'),
}


def update_template(creator, name, spreadsheet_id):
    print(f"\n📋 {name}  ({spreadsheet_id})")
    ss = _sheets_call_with_retry(creator.sheets_client.open_by_key, spreadsheet_id)

    hw_sheet = None
    for variant in ["📊 Сданные ДЗ", "Сданные ДЗ"]:
        try:
            hw_sheet = ss.worksheet(variant)
            print(f"  ✅ Лист: '{variant}'")
            break
        except Exception:
            continue

    if hw_sheet is None:
        print("  ⚠️ Лист '📊 Сданные ДЗ' не найден — пропускаем")
        return

    print(f"  Текущие B2:E2: {hw_sheet.get('B2:E2')}")

    _sheets_call_with_retry(hw_sheet.update, [[FORMULA_B2]], 'B2', value_input_option='USER_ENTERED')
    _sheets_call_with_retry(hw_sheet.update, [['', '', '']], 'C2:E2', value_input_option='USER_ENTERED')

    print("  ✅ B2 = QUERY/IMPORTRANGE, C2:E2 очищены")


def main():
    print(f"Формула: {FORMULA_B2}\n")
    creator = TrackerCreator()
    for name, sid in TEMPLATES.items():
        try:
            update_template(creator, name, sid)
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
    print("\n✅ Готово!")


if __name__ == '__main__':
    main()
