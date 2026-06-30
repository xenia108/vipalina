#!/usr/bin/env python3
"""QR-login Telethon StringSession recovery for Vipalina user client."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import qrcode
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH

PASSWORD_2FA = '0108'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(BASE_DIR, 'runtime_telethon_session_result_qr_20260629_14227ba7.txt')
QR_FILE = os.path.join(BASE_DIR, 'runtime_vipalina_qr_20260629_14227ba7.png')
URL_FILE = os.path.join(BASE_DIR, 'runtime_vipalina_qr_20260629_14227ba7.txt')

async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    qr_login = await client.qr_login()
    with open(URL_FILE, 'w') as file:
        file.write(qr_login.url)

    image = qrcode.make(qr_login.url)
    image.save(QR_FILE)

    print(f"QR_URL {qr_login.url}", flush=True)
    print(f"QR_FILE {QR_FILE}", flush=True)
    print("WAITING_FOR_QR_SCAN", flush=True)

    try:
        await qr_login.wait(timeout=180)
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
