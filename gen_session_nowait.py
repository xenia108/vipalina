#!/usr/bin/env python3
"""Generate new StringSession - two-phase approach."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH

PHONE = '+79996696144'
PASSWORD_2FA = '0108'
HASH_FILE = '/tmp/telethon_code_hash.txt'
CODE_FILE = '/tmp/telethon_code_input.txt'
RESULT_FILE = '/tmp/telethon_session_result.txt'

async def gen():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    
    # Step 1: request code
    result = await client.send_code_request(PHONE)
    phone_code_hash = result.phone_code_hash
    print(f"✅ Код отправлен на {PHONE}")
    print(f"   phone_code_hash: {phone_code_hash}")
    
    # Save hash
    with open(HASH_FILE, 'w') as f:
        f.write(phone_code_hash)
    
    # Step 2: wait for code file
    print(f"⏳ Жду код в файле {CODE_FILE} ...")
    while not os.path.exists(CODE_FILE):
        await asyncio.sleep(1)
    
    with open(CODE_FILE, 'r') as f:
        code = f.read().strip()
    
    print(f"📱 Получен код: {code}")
    os.remove(CODE_FILE)
    
    # Step 3: sign in
    try:
        await client.sign_in(PHONE, code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        print("🔐 Требуется 2FA пароль...")
        await client.sign_in(password=PASSWORD_2FA)
    
    # Step 4: save session
    session_string = client.session.save()
    print(f"\n✅ SUCCESS! Session length: {len(session_string)}")
    
    with open(RESULT_FILE, 'w') as f:
        f.write(session_string)
    
    print(f"💾 Сохранено в {RESULT_FILE}")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(gen())
