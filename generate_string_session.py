#!/usr/bin/env python3
"""
Скрипт для генерации StringSession для Telethon.
Запускается ОДИН РАЗ для получения session string.
"""

import os
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH

async def generate_session():
    """Генерирует StringSession и выводит его."""
    print("\n" + "="*60)
    print("🔑 ГЕНЕРАЦИЯ STRING SESSION")
    print("="*60 + "\n")
    
    print("📱 Сейчас откроется процесс авторизации в Telegram.")
    print("Введите номер телефона и код из Telegram.\n")
    
    # Используем пустую StringSession для первого запуска
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        # Авторизуемся (запросит телефон и код)
        await client.start()
        
        # Получаем session string
        session_string = client.session.save()
        
        print("\n" + "="*60)
        print("✅ SESSION STRING УСПЕШНО СОЗДАН!")
        print("="*60 + "\n")
        
        print("📋 Скопируй эту строку и сохрани в .env файл:\n")
        print("TELETHON_SESSION_STRING=\"" + session_string + "\"\n")
        
        print("="*60)
        print("⚠️  ВАЖНО:")
        print("1. Сохрани эту строку в безопасном месте")
        print("2. Добавь её в .env файл")
        print("3. НЕ делись этой строкой с другими!")
        print("="*60 + "\n")
        
        # Сохраняем в файл для удобства
        with open('.session_string.txt', 'w') as f:
            f.write(session_string)
        
        print("✅ Также сохранено в файл: .session_string.txt\n")

if __name__ == "__main__":
    import asyncio
    asyncio.run(generate_session())
