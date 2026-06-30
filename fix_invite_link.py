#!/usr/bin/env python3
"""
Скрипт для обновления invite_link для чата Ксении Улановой
"""
import os
import sys
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telethon import TelegramClient
from telethon.tl.functions.messages import ExportChatInviteRequest
import asyncio

# Конфигурация
SERVICE_ACCOUNT_FILE = 'vipalina_google_service_account.json'
PERSISTENCE_TABLE_ID = '1wWbgAq92qehpTO0lm4AQJzTQ8RvpA9fX_vORYBqkHCE'
CHAT_ID = -1003279277783
STUDENT_NAME = 'Ксения Уланова'

# Telethon credentials (из config.py)
API_ID = 21020399
API_HASH = "7109b029aeaa5037021d8af08e4d7d8d"
SESSION_NAME = "vipalina_telethon_session"

def init_google_sheets():
    """Инициализация Google Sheets"""
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(creds)
    return client

async def get_invite_link(client: TelegramClient, chat_id: int) -> str:
    """Получает invite-ссылку для чата"""
    try:
        result = await client(ExportChatInviteRequest(peer=chat_id))
        if result and hasattr(result, 'link'):
            return result.link
        return None
    except Exception as e:
        print(f"❌ Ошибка получения invite-ссылки: {e}")
        return None

async def main():
    print("🚀 ОБНОВЛЕНИЕ INVITE-ССЫЛКИ")
    print(f"👤 Студент: {STUDENT_NAME}")
    print(f"💬 Chat ID: {CHAT_ID}")
    print()
    
    # Инициализация Telethon
    print("🔌 Подключение к Telegram...")
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    print("   ✅ Подключено")
    
    # Получаем invite-ссылку
    print("\n🔗 Получение invite-ссылки...")
    invite_link = await get_invite_link(client, CHAT_ID)
    
    if not invite_link:
        print("   ❌ Не удалось получить invite-ссылку!")
        await client.disconnect()
        sys.exit(1)
    
    print(f"   ✅ Получена: {invite_link}")
    
    # Инициализация Google Sheets
    print("\n📊 Подключение к Google Sheets...")
    try:
        sheets_client = init_google_sheets()
        spreadsheet = sheets_client.open_by_key(PERSISTENCE_TABLE_ID)
        print("   ✅ Подключено")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        await client.disconnect()
        sys.exit(1)
    
    # Обновляем Chat_To_Student
    print("\n📝 Обновление таблицы 'Chat_To_Student'...")
    try:
        sheet = spreadsheet.worksheet('Chat_To_Student')
        all_values = sheet.get_all_values()
        
        # Ищем строку с нашим чатом
        row_index = None
        for idx, row in enumerate(all_values[1:], start=2):  # Пропускаем заголовки
            if len(row) > 0 and str(CHAT_ID) in row[0]:
                row_index = idx
                break
        
        if not row_index:
            print(f"   ❌ Чат {CHAT_ID} не найден в таблице!")
            await client.disconnect()
            sys.exit(1)
        
        print(f"   ✅ Найдена строка: {row_index}")
        print(f"   📍 Обновление столбца D (invite_link)...")
        
        # Обновляем invite_link (столбец D, индекс 4)
        sheet.update_cell(row_index, 4, invite_link)
        
        print(f"   ✅ Invite-ссылка обновлена!")
        print(f"      Новое значение: {invite_link}")
        
    except Exception as e:
        print(f"   ❌ Ошибка обновления: {e}")
        import traceback
        traceback.print_exc()
    
    # Отключаемся
    await client.disconnect()
    
    print("\n" + "="*80)
    print("✅ ОБНОВЛЕНИЕ ЗАВЕРШЕНО")
    print("="*80)

if __name__ == '__main__':
    asyncio.run(main())
