#!/usr/bin/env python3
"""One-time Telethon StringSession recovery for Vipalina user client."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH

PHONE = '+79996696144'
PASSWORD_2FA = '0108'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HASH_FILE = os.path.join(BASE_DIR, 'runtime_telethon_code_hash_14227ba7.txt')
CODE_FILE = os.path.join(BASE_DIR, 'runtime_telethon_code_input_14227ba7.txt')
RESULT_FILE = os.path.join(BASE_DIR, 'runtime_telethon_session_result_14227ba7.txt')

async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    result = await client.send_code_request(PHONE)
    phone_code_hash = result.phone_code_hash
    print(f"CODE_SENT {PHONE}")
    print(f"PHONE_CODE_HASH {phone_code_hash}")

    with open(HASH_FILE, 'w') as file:
        file.write(phone_code_hash)

    print(f"WAITING_FOR_CODE_FILE {CODE_FILE}")
    while not os.path.exists(CODE_FILE):
        await asyncio.sleep(1)

    with open(CODE_FILE, 'r') as file:
        code = file.read().strip()

    print("CODE_FILE_READ")
    try:
        await client.sign_in(PHONE, code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        print("TWO_FA_REQUIRED")
        await client.sign_in(password=PASSWORD_2FA)

    session_string = client.session.save()
    with open(RESULT_FILE, 'w') as file:
        file.write(session_string)

    me = await client.get_me()
    print(f"SUCCESS user_id={me.id} username={me.username} session_length={len(session_string)}")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
