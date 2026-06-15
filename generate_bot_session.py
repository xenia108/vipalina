#!/usr/bin/env python3
"""
Генерирует StringSession для bot_client чтобы избежать SQLite файлов
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH, TELETHON_BOT_TOKEN

async def main():
    print("Генерация StringSession для bot_client...")
    print(f"BOT_TOKEN: {TELETHON_BOT_TOKEN[:20]}...")
    
    # Создаём временную сессию
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    # Авторизуемся через бот токен
    await client.start(bot_token=TELETHON_BOT_TOKEN)
    
    # Получаем строку сессии
    session_string = client.session.save()
    
    print("\n" + "="*80)
    print("BOT_SESSION_STRING сгенерирована успешно!")
    print("="*80)
    print("\nДобавь в .env файл:")
    print(f"BOT_SESSION_STRING={session_string}")
    print("="*80)
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
