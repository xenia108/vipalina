import sys, os
sys.path.insert(0, '/root/ksushiny_terminatory/vipalina')
os.chdir('/root/ksushiny_terminatory/vipalina')

from tracker_creator import TrackerCreator

creator = TrackerCreator('vipalina_google_credentials.json')

# Два тестовых трекера созданных ранее
trackers = [
    '1jKepqCX-zyTcMdUXEo3kL2G6boZduoMyq7KhzrRkw4c',  # Абонемент на год VIP
    '1rTctq93QlziXnP2xTXTvgd6PJvfB5EKWzKkB1tA-ZRw',   # Чат-боты 2.0 VIP с гарантией
]

NEW_STATUS_FORMULA_TEMPLATE = '=ЕСЛИ(D{row}>=C{row};"✅";ЕСЛИ(D{row}>4;"🆗";ЕСЛИ(D{row}>2;"⚠️";"❌")))'

for tracker_id in trackers:
    print(f'\nПравлю трекер: {tracker_id}', flush=True)
    try:
        tracker = creator.sheets_client.open_by_key(tracker_id)
        ws = tracker.sheet1  # 📈 Статистика
        
        all_vals = ws.get_all_values()
        # Найти строку заголовка прогресса (где B=Месяц, C=Цель, D=Факт)
        header_row = None
        for i, row in enumerate(all_vals):
            if len(row) >= 4 and row[1] == 'Месяц' and row[2] == 'Цель' and row[3] == 'Факт':
                header_row = i + 1  # 1-based
                break
        
        if header_row is None:
            print('  Заголовок не найден!', flush=True)
            continue
        
        print(f'  Заголовок в строке {header_row}', flush=True)
        
        # Обновляем формулы F в строках месяцев
        updated = 0
        row_num = header_row + 1
        while row_num <= len(all_vals):
            b_val = all_vals[row_num - 1][1] if len(all_vals[row_num - 1]) > 1 else ''
            if not b_val.startswith('Месяц'):
                break
            formula = NEW_STATUS_FORMULA_TEMPLATE.replace('{row}', str(row_num))
            ws.update([[formula]], f'F{row_num}', value_input_option='USER_ENTERED')
            print(f'  F{row_num}: {formula}', flush=True)
            updated += 1
            row_num += 1
        
        print(f'  Обновлено {updated} строк ✅', flush=True)
    except Exception as e:
        import traceback
        print(f'  ОШИБКА: {e}', flush=True)
        traceback.print_exc()
