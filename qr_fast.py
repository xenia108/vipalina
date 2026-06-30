#!/usr/bin/env python3
"""Быстрая генерация QR с автообновлением + попытка кода."""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import qrcode as qrcode_lib
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl import functions, types
from config import API_ID, API_HASH

PHONE = '+79996696144'
PASSWORD_2FA = '0108'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_ID = datetime.now().strftime('%Y%m%d_%H%M%S')
RESULT_FILE = os.path.join(BASE_DIR, f'runtime_session_{RUN_ID}.txt')
QR_FILE = os.path.join(BASE_DIR, f'runtime_qr_{RUN_ID}.png')
URL_FILE = os.path.join(BASE_DIR, f'runtime_qr_{RUN_ID}.txt')
CODE_FILE = os.path.join(BASE_DIR, f'runtime_code_{RUN_ID}.txt')


def save_session(client):
    s = client.session.save()
    with open(RESULT_FILE, 'w') as f:
        f.write(s)
    print(f"RESULT {RESULT_FILE}", flush=True)
    return s


async def do_qr_login(client, attempt):
    """QR-вход с одним токеном."""
    qr = await client.qr_login()
    
    import datetime as dt
    now = dt.datetime.now(tz=dt.timezone.utc)
    lifetime = (qr.expires - now).total_seconds()
    
    url = qr.url
    img = qrcode_lib.make(url)
    img.save(QR_FILE)
    with open(URL_FILE, 'w') as f:
        f.write(url)
    
    print(f"QR_URL {url}", flush=True)
    print(f"QR_FILE {QR_FILE}", flush=True)
    print(f"ATTEMPT {attempt} LIFETIME {lifetime:.0f}s", flush=True)
    print(f"SCAN_NOW", flush=True)
    
    return qr, lifetime


async def main():
    print(f"START {RUN_ID}", flush=True)
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    print(f"CONNECTED", flush=True)
    
    # Сначала попробуем отправить код
    print(f"\n>>> Попытка отправить код на {PHONE}...", flush=True)
    try:
        result = await client.send_code_request(PHONE)
        code_type = type(getattr(result, 'type', None)).__name__
        phone_code_hash = result.phone_code_hash
        print(f"CODE_SENT type={code_type} hash={phone_code_hash[:16]}...", flush=True)
        print(f"CODE_FILE {CODE_FILE}", flush=True)
        print(f"WAITING_CODE 30s", flush=True)
        
        # Ждём код 30 секунд
        code = None
        for i in range(30):
            if os.path.exists(CODE_FILE):
                with open(CODE_FILE) as f:
                    code = f.read().strip()
                if code:
                    break
            await asyncio.sleep(1)
        
        if code:
            print(f"CODE_RECEIVED {code}", flush=True)
            try:
                await client.sign_in(phone=PHONE, code=code, phone_code_hash=phone_code_hash)
                save_session(client)
                me = await client.get_me()
                print(f"SUCCESS_CODE user={me.username} id={me.id}", flush=True)
                await client.disconnect()
                return
            except SessionPasswordNeededError:
                await client.sign_in(password=PASSWORD_2FA)
                save_session(client)
                me = await client.get_me()
                print(f"SUCCESS_2FA user={me.username} id={me.id}", flush=True)
                await client.disconnect()
                return
            except Exception as e:
                print(f"CODE_FAILED {e}", flush=True)
        else:
            print(f"NO_CODE_RECEIVED", flush=True)
    except Exception as e:
        print(f"SEND_CODE_FAILED {e}", flush=True)
    
    # QR-вход с автообновлением
    print(f"\n>>> QR-вход (5 попыток с автообновлением)...", flush=True)
    
    for attempt in range(1, 6):
        try:
            qr, lifetime = await do_qr_login(client, attempt)
            
            # Ждём сканирование
            await qr.wait()
            print(f"QR_SCANNED attempt={attempt}", flush=True)
            
            # Проверяем 2FA
            try:
                me = await client.get_me()
            except SessionPasswordNeededError:
                print(f"TWO_FA_REQUIRED", flush=True)
                await client.sign_in(password=PASSWORD_2FA)
                me = await client.get_me()
            
            save_session(client)
            print(f"SUCCESS_QR user={me.username} id={me.id}", flush=True)
            await client.disconnect()
            return
            
        except asyncio.TimeoutError:
            print(f"QR_EXPIRED attempt={attempt}", flush=True)
            if attempt < 5:
                print(f"REGENERATING...", flush=True)
                await asyncio.sleep(1)
            continue
        except Exception as e:
            print(f"QR_ERROR attempt={attempt}: {e}", flush=True)
            if attempt < 5:
                await asyncio.sleep(1)
            continue
    
    print(f"ALL_ATTEMPTS_FAILED", flush=True)
    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
