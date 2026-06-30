#!/usr/bin/env python3
"""QR-login с правильной обработкой 2FA."""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import qrcode as qrcode_lib
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH

PASSWORD_2FA = '0108'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_ID = datetime.now().strftime('%Y%m%d_%H%M%S')
RESULT_FILE = os.path.join(BASE_DIR, f'runtime_session_{RUN_ID}.txt')
QR_FILE = os.path.join(BASE_DIR, f'runtime_qr_{RUN_ID}.png')
URL_FILE = os.path.join(BASE_DIR, f'runtime_qr_{RUN_ID}.txt')


async def main():
    print(f"START {RUN_ID}", flush=True)
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    print(f"CONNECTED", flush=True)
    
    for attempt in range(1, 6):
        print(f"\n>>> Попытка {attempt}/5", flush=True)
        
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
        print(f"LIFETIME {lifetime:.0f}s", flush=True)
        print(f"SCAN_NOW", flush=True)
        
        try:
            # Ждём сканирование QR
            await qr.wait()
            print(f"QR_SCANNED", flush=True)
            
            # Проверяем, нужен ли 2FA
            try:
                me = await client.get_me()
            except SessionPasswordNeededError:
                print(f"TWO_FA_REQUIRED", flush=True)
                await client.sign_in(password=PASSWORD_2FA)
                me = await client.get_me()
            
            # Сохраняем сессию
            session_string = client.session.save()
            with open(RESULT_FILE, 'w') as f:
                f.write(session_string)
            
            print(f"RESULT {RESULT_FILE}", flush=True)
            print(f"SUCCESS user={me.username} id={me.id}", flush=True)
            
            await client.disconnect()
            return
            
        except asyncio.TimeoutError:
            print(f"QR_EXPIRED", flush=True)
            if attempt < 5:
                print(f"REGENERATING...", flush=True)
                await asyncio.sleep(1)
            continue
            
        except SessionPasswordNeededError:
            # 2FA требуется прямо во время wait()
            print(f"TWO_FA_DURING_WAIT", flush=True)
            try:
                await client.sign_in(password=PASSWORD_2FA)
                me = await client.get_me()
                
                session_string = client.session.save()
                with open(RESULT_FILE, 'w') as f:
                    f.write(session_string)
                
                print(f"RESULT {RESULT_FILE}", flush=True)
                print(f"SUCCESS user={me.username} id={me.id}", flush=True)
                
                await client.disconnect()
                return
            except Exception as e:
                print(f"TWO_FA_ERROR {e}", flush=True)
                continue
        
        except Exception as e:
            print(f"ERROR {e}", flush=True)
            if attempt < 5:
                await asyncio.sleep(1)
            continue
    
    print(f"ALL_ATTEMPTS_FAILED", flush=True)
    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
