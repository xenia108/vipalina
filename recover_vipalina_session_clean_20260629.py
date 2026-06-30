#!/usr/bin/env python3
"""Clean one-time Telethon StringSession recovery for Vipalina user client."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH

PHONE = '+79996696144'
PASSWORD_2FA = '0108'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_ID = 'clean_20260629_14227ba7'
HASH_FILE = os.path.join(BASE_DIR, f'runtime_telethon_code_hash_{RUN_ID}.txt')
CODE_FILE = os.path.join(BASE_DIR, f'runtime_telethon_code_input_{RUN_ID}.txt')
RESULT_FILE = os.path.join(BASE_DIR, f'runtime_telethon_session_result_{RUN_ID}.txt')

async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    result = await client.send_code_request(PHONE)
    phone_code_hash = result.phone_code_hash
    code_type = type(getattr(result, 'type', None)).__name__
    next_type = type(getattr(result, 'next_type', None)).__name__
    timeout = getattr(result, 'timeout', None)

    with open(HASH_FILE, 'w') as file:
        file.write(phone_code_hash)

    print(f"CODE_SENT phone={PHONE} code_type={code_type} next_type={next_type} timeout={timeout}", flush=True)
    print(f"PHONE_CODE_HASH {phone_code_hash}", flush=True)
    print(f"WAITING_FOR_CODE_FILE {CODE_FILE}", flush=True)

    while not os.path.exists(CODE_FILE):
        await asyncio.sleep(1)

    with open(CODE_FILE, 'r') as file:
        code = file.read().strip()

    print("CODE_FILE_READ", flush=True)
    try:
        await client.sign_in(PHONE, code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        print("TWO_FA_REQUIRED", flush=True)
        await client.sign_in(password=PASSWORD_2FA)

    session_string = client.session.save()
    with open(RESULT_FILE, 'w') as file:
        file.write(session_string)

    me = await client.get_me()
    print(f"SUCCESS user_id={me.id} username={me.username} session_length={len(session_string)}", flush=True)
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
