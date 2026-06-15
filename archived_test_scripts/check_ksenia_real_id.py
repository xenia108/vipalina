#!/usr/bin/env python3
"""
Проверяем реальный Telegram ID Ксении Улановой (студента)
"""
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Аутентификация Google Sheets
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('vipalina_google_service_account.json', scope)
client = gspread.authorize(creds)

# Открываем таблицу "Логи Випалина"
logs_sheet = client.open_by_key('1mKcD7wI8CDOZRHHy8bFOD24d6X6UJqxj2XR_kN5_7fU')

# Проверяем лист Chat_To_Student
print("🔍 ПРОВЕРКА РЕАЛЬНОГО ID КСЕНИИ\n")
chat_to_student = logs_sheet.worksheet('Chat_To_Student')
all_data = chat_to_student.get_all_values()

print(f"Всего строк: {len(all_data)}\n")
print("Все связи:")
for i, row in enumerate(all_data):
    if i == 0:
        print(f"   Заголовки: {row}")
        continue
    if len(row) >= 3 and row[0]:
        chat_id = row[0]
        getcourse_id = row[1]
        telegram_id = row[2] if len(row) > 2 else "нет"
        print(f"   {i}. chat_id={chat_id}, getcourse_id={getcourse_id}, telegram_id={telegram_id}")
        
        if getcourse_id == "309200567":
            print(f"\n✅ НАШЛИ КСЕНИЮ!")
            print(f"   GetCourse ID: {getcourse_id}")
            print(f"   Telegram ID: {telegram_id}")
            print(f"   Chat ID: {chat_id}")
