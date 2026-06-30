#!/usr/bin/env python3
"""Request Telegram auth-code fallback using the existing phone_code_hash."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from config import API_ID, API_HASH

PHONE = '+79996696144'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OLD_HASH_FILE = os.path.join(BASE_DIR, 'runtime_telethon_code_hash_14227ba7.txt')
NEW_HASH_FILE = os.path.join(BASE_DIR, 'runtime_telethon_code_hash_sms_14227ba7.txt')

async def main():
    with open(OLD_HASH_FILE, 'r') as file:
        phone_code_hash = file.read().strip()

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    result = await client(functions.auth.ResendCodeRequest(
        phone_number=PHONE,
        phone_code_hash=phone_code_hash,
    ))

    with open(NEW_HASH_FILE, 'w') as file:
        file.write(result.phone_code_hash)

    code_type = type(getattr(result, 'type', None)).__name__
    next_type = type(getattr(result, 'next_type', None)).__name__
    timeout = getattr(result, 'timeout', None)
    print(f"RESEND_OK code_type={code_type} next_type={next_type} timeout={timeout}")
    print(f"NEW_PHONE_CODE_HASH {result.phone_code_hash}")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
