#!/usr/bin/env python3
"""
Диагностика проблем после онбординга Ксении Улановой
"""
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Google Sheets credentials
SERVICE_ACCOUNT_FILE = 'vipalina_google_service_account.json'

# Таблицы для проверки
TABLES = {
    'Логи Випалина': '1wWbgAq92qehpTO0lm4AQJzTQ8RvpA9fX_vORYBqkHCE',
    'SLA Випалина': '19YcEHA1HvBSfNRHFBK06eC7aRurH5NG6mhyE061BdNY',
    'KPI Ultra': '1F6LFT_VWhcNX61bPJqHUgC78eHj6fgNwKbGcTXQ1j78'
}

# Данные студента для поиска
STUDENT_GETCOURSE_ID = '309200567'
STUDENT_NAME = 'Ксения Уланова'
CHAT_ID = '-1003279277783'

def init_google_sheets():
    """Инициализация Google Sheets API"""
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(creds)
    return client

def check_logs_vipalina(client):
    """Проверяет таблицу 'Логи Випалина'"""
    print("\n" + "="*80)
    print("🔍 ПРОВЕРКА: Логи Випалина")
    print("="*80)
    
    try:
        spreadsheet = client.open_by_key(TABLES['Логи Випалина'])
        
        # Проверяем Chat_To_Student
        print("\n📋 Лист: Chat_To_Student")
        try:
            sheet = spreadsheet.worksheet('Chat_To_Student')
            all_values = sheet.get_all_values()
            
            if len(all_values) <= 1:
                print("   ❌ Нет данных (только заголовки)")
            else:
                headers = all_values[0]
                print(f"   ✅ Заголовки: {headers}")
                print(f"   📊 Всего записей: {len(all_values) - 1}")
                
                # Ищем наш чат
                found = False
                for row in all_values[1:]:
                    if len(row) > 0 and CHAT_ID in str(row[0]):
                        print(f"\n   ✅ НАЙДЕН ЧАТ {CHAT_ID}:")
                        for i, header in enumerate(headers):
                            if i < len(row):
                                print(f"      {header}: {row[i]}")
                        found = True
                        break
                
                if not found:
                    print(f"   ❌ Чат {CHAT_ID} НЕ НАЙДЕН в таблице!")
                    print("   📝 Последние 3 записи:")
                    for row in all_values[-3:]:
                        print(f"      {row}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        # Проверяем Active_SLA_Requests
        print("\n📋 Лист: Active_SLA_Requests")
        try:
            sheet = spreadsheet.worksheet('Active_SLA_Requests')
            all_values = sheet.get_all_values()
            
            if len(all_values) <= 1:
                print("   ℹ️ Нет активных SLA-запросов (это нормально)")
            else:
                print(f"   📊 Активных SLA-запросов: {len(all_values) - 1}")
                for row in all_values[1:]:
                    if CHAT_ID in str(row):
                        print(f"   ✅ Найден SLA-запрос для чата {CHAT_ID}")
                        print(f"      Данные: {row}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        # Проверяем Student_Messages
        print("\n📋 Лист: Student_Messages")
        try:
            sheet = spreadsheet.worksheet('Student_Messages')
            all_values = sheet.get_all_values()
            
            if len(all_values) <= 1:
                print("   ❌ НЕТ СООБЩЕНИЙ! Это проблема!")
            else:
                headers = all_values[0]
                print(f"   ✅ Заголовки: {headers}")
                print(f"   📊 Всего сообщений: {len(all_values) - 1}")
                
                # Ищем сообщения нашего студента
                student_messages = []
                for row in all_values[1:]:
                    if len(row) > 0 and (CHAT_ID in str(row) or STUDENT_GETCOURSE_ID in str(row)):
                        student_messages.append(row)
                
                if student_messages:
                    print(f"\n   ✅ НАЙДЕНО {len(student_messages)} сообщений студента:")
                    for row in student_messages:
                        print(f"      {row}")
                else:
                    print(f"   ❌ Сообщения студента {STUDENT_NAME} НЕ НАЙДЕНЫ!")
                    print("   📝 Последние 5 записей в таблице:")
                    for row in all_values[-5:]:
                        print(f"      {row}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    except Exception as e:
        print(f"❌ Критическая ошибка при проверке 'Логи Випалина': {e}")

def check_sla_vipalina(client):
    """Проверяет таблицу 'SLA Випалина'"""
    print("\n" + "="*80)
    print("🔍 ПРОВЕРКА: SLA Випалина")
    print("="*80)
    
    try:
        spreadsheet = client.open_by_key(TABLES['SLA Випалина'])
        
        print("\n📋 Лист: SLA_Data")
        try:
            sheet = spreadsheet.worksheet('SLA_Data')
            all_values = sheet.get_all_values()
            
            if len(all_values) <= 1:
                print("   ❌ НЕТ ДАННЫХ! Это проблема!")
            else:
                headers = all_values[0]
                print(f"   ✅ Заголовки: {headers}")
                print(f"   📊 Всего записей: {len(all_values) - 1}")
                
                # Ищем записи нашего студента
                student_records = []
                for row in all_values[1:]:
                    if len(row) > 0 and (STUDENT_NAME in str(row) or STUDENT_GETCOURSE_ID in str(row)):
                        student_records.append(row)
                
                if student_records:
                    print(f"\n   ✅ НАЙДЕНО {len(student_records)} SLA-записей студента:")
                    for row in student_records:
                        print(f"      {row}")
                else:
                    print(f"   ❌ SLA-записи студента {STUDENT_NAME} НЕ НАЙДЕНЫ!")
                    print("   📝 Последняя запись в таблице:")
                    if len(all_values) > 1:
                        print(f"      {all_values[-1]}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    except Exception as e:
        print(f"❌ Критическая ошибка при проверке 'SLA Випалина': {e}")

def check_kpi_ultra(client):
    """Проверяет таблицу 'KPI Ultra'"""
    print("\n" + "="*80)
    print("🔍 ПРОВЕРКА: KPI Ultra")
    print("="*80)
    
    try:
        spreadsheet = client.open_by_key(TABLES['KPI Ultra'])
        
        # Проверяем Випалина
        print("\n📋 Лист: Випалина")
        try:
            sheet = spreadsheet.worksheet('Випалина')
            all_values = sheet.get_all_values()
            
            if len(all_values) <= 1:
                print("   ❌ Нет данных")
            else:
                headers = all_values[0]
                print(f"   ✅ Заголовки найдены ({len(headers)} столбцов)")
                print(f"   📊 Всего записей: {len(all_values) - 1}")
                
                # Ищем invite_link столбец
                invite_col = None
                for i, header in enumerate(headers):
                    if 'invite' in header.lower() or 'ссылка' in header.lower():
                        invite_col = i
                        print(f"   ✅ Столбец для invite link: '{header}' (индекс {i})")
                        break
                
                if not invite_col:
                    print("   ⚠️ Столбец для invite link не найден!")
                
                # Ищем нашего студента
                found = False
                for row_idx, row in enumerate(all_values[1:], start=2):
                    if len(row) > 0 and (STUDENT_GETCOURSE_ID in str(row) or STUDENT_NAME in str(row)):
                        print(f"\n   ✅ СТУДЕНТ НАЙДЕН (строка {row_idx}):")
                        for i, header in enumerate(headers):
                            if i < len(row):
                                value = row[i]
                                if i == invite_col:
                                    print(f"      🔗 {header}: '{value}' {'❌ ПУСТО!' if not value else '✅'}")
                                else:
                                    print(f"      {header}: {value}")
                        found = True
                        break
                
                if not found:
                    print(f"   ❌ Студент {STUDENT_NAME} НЕ НАЙДЕН!")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        # Проверяем Общий список new
        print("\n📋 Лист: Общий список new")
        try:
            sheet = spreadsheet.worksheet('Общий список new')
            all_values = sheet.get_all_values()
            
            if len(all_values) <= 1:
                print("   ❌ Нет данных")
            else:
                headers = all_values[0]
                print(f"   ✅ Заголовки найдены ({len(headers)} столбцов)")
                print(f"   📊 Всего записей: {len(all_values) - 1}")
                
                # Ищем invite_link столбец
                invite_col = None
                for i, header in enumerate(headers):
                    if 'invite' in header.lower() or 'ссылка' in header.lower():
                        invite_col = i
                        print(f"   ✅ Столбец для invite link: '{header}' (индекс {i})")
                        break
                
                if not invite_col:
                    print("   ⚠️ Столбец для invite link не найден!")
                
                # Ищем нашего студента
                found = False
                for row_idx, row in enumerate(all_values[1:], start=2):
                    if len(row) > 0 and (STUDENT_GETCOURSE_ID in str(row) or STUDENT_NAME in str(row)):
                        print(f"\n   ✅ СТУДЕНТ НАЙДЕН (строка {row_idx}):")
                        for i, header in enumerate(headers):
                            if i < len(row):
                                value = row[i]
                                if i == invite_col:
                                    print(f"      🔗 {header}: '{value}' {'❌ ПУСТО!' if not value else '✅'}")
                                else:
                                    print(f"      {header}: {value}")
                        found = True
                        break
                
                if not found:
                    print(f"   ❌ Студент {STUDENT_NAME} НЕ НАЙДЕН!")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    except Exception as e:
        print(f"❌ Критическая ошибка при проверке 'KPI Ultra': {e}")

def main():
    print("🚀 ДИАГНОСТИКА ПРОБЛЕМ ПОСЛЕ ОНБОРДИНГА")
    print(f"👤 Студент: {STUDENT_NAME}")
    print(f"🆔 GetCourse ID: {STUDENT_GETCOURSE_ID}")
    print(f"💬 Chat ID: {CHAT_ID}")
    print(f"⏰ Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Инициализация
    print("\n🔑 Инициализация Google Sheets API...")
    try:
        client = init_google_sheets()
        print("   ✅ API инициализирован")
    except Exception as e:
        print(f"   ❌ Ошибка инициализации: {e}")
        return
    
    # Проверки
    check_logs_vipalina(client)
    check_sla_vipalina(client)
    check_kpi_ultra(client)
    
    print("\n" + "="*80)
    print("✅ ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("="*80)

if __name__ == '__main__':
    main()
