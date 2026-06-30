#!/usr/bin/env python3
"""
Robust Telethon session recovery for Vipalina.
Strategy:
  1. Phone code login (send_code_request -> wait -> sign_in)
  2. If code doesn't arrive, resend
  3. QR login with auto-recreate as fallback
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberUnoccupiedError,
)
from telethon.tl import functions, types
from config import API_ID, API_HASH

PHONE = '+79996696144'
PASSWORD_2FA = '0108'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_ID = datetime.now().strftime('%Y%m%d_%H%M%S')
RESULT_FILE = os.path.join(BASE_DIR, f'runtime_session_result_{RUN_ID}.txt')


def save_session(client, label):
    session_string = client.session.save()
    with open(RESULT_FILE, 'w') as f:
        f.write(session_string)
    print(f"✅ [{label}] Сессия сохранена ({len(session_string)} символов)", flush=True)
    print(f"RESULT_FILE {RESULT_FILE}", flush=True)
    return session_string


async def try_phone_code_login(client):
    """Попытка входа по коду (SMS / in-app)."""
    print(f"\n{'='*60}", flush=True)
    print(f"📱 СТРАТЕГИЯ 1: Вход по коду на {PHONE}", flush=True)
    print(f"{'='*60}", flush=True)

    # Отправляем код (force_sms=True для принудительной SMS)
    print("📤 Отправляю запрос кода (force_sms=True)...", flush=True)
    result = await client.send_code_request(PHONE, force_sms=True)
    phone_code_hash = result.phone_code_hash
    code_type = type(getattr(result, 'type', None)).__name__
    next_type = type(getattr(result, 'next_type', None)).__name__
    timeout = getattr(result, 'timeout', None)

    print(f"   Тип кода: {code_type}", flush=True)
    print(f"   Следующий тип: {next_type}", flush=True)
    print(f"   Таймаут: {timeout}", flush=True)
    print(f"   Hash: {phone_code_hash[:20]}...", flush=True)

    if code_type == 'SentCodeTypeApp':
        print("⚠️  Код отправлен как in-app (в Telegram).", flush=True)
        print("   Ожидаю 15 секунд, затем попробую повторный запрос...", flush=True)
        await asyncio.sleep(15)

        print("📤 Повторный запрос кода (resend)...", flush=True)
        try:
            result2 = await client(functions.auth.ResendCodeRequest(
                phone_number=PHONE,
                phone_code_hash=phone_code_hash
            ))
            code_type2 = type(getattr(result2, 'type', None)).__name__
            next_type2 = type(getattr(result2, 'next_type', None)).__name__
            phone_code_hash = result2.phone_code_hash
            print(f"   Тип после resend: {code_type2}", flush=True)
            print(f"   Следующий тип: {next_type2}", flush=True)
        except Exception as e:
            print(f"   ⚠️ Resend не удался: {e}", flush=True)

    # Ожидаем ввод кода через файл
    code_file = os.path.join(BASE_DIR, f'runtime_code_input_{RUN_ID}.txt')
    print(f"\n🔢 Ожидаю код в файле: {code_file}", flush=True)
    print(f"   (или введите код в терминале)", flush=True)
    print(f"CODE_FILE {code_file}", flush=True)
    print(f"WAITING_FOR_CODE", flush=True)

    code = None
    for i in range(300):  # 5 минут
        if os.path.exists(code_file):
            with open(code_file, 'r') as f:
                code = f.read().strip()
            if code:
                break
        await asyncio.sleep(1)

    if not code:
        try:
            code = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("   Код: ").strip()
            )
        except EOFError:
            pass

    if not code:
        print("❌ Код не получен", flush=True)
        return False

    print(f"📥 Пробую войти с кодом: {code}", flush=True)
    try:
        await client.sign_in(phone=PHONE, code=code, phone_code_hash=phone_code_hash)
        print("✅ Вход по коду выполнен!", flush=True)
        return True
    except PhoneCodeExpiredError:
        print("❌ Код истёк. Попробую отправить новый...", flush=True)
        # Повторная отправка
        result3 = await client.send_code_request(PHONE, force_sms=True)
        phone_code_hash = result3.phone_code_hash
        code_type3 = type(getattr(result3, 'type', None)).__name__
        print(f"   Новый тип: {code_type3}", flush=True)
        code_file2 = code_file + '.2'
        print(f"   Ожидаю новый код в файле: {code_file2}", flush=True)
        print(f"CODE_FILE {code_file2}", flush=True)
        code2 = None
        for i in range(300):
            if os.path.exists(code_file2):
                with open(code_file2, 'r') as f:
                    code2 = f.read().strip()
                if code2:
                    break
            await asyncio.sleep(1)
        if not code2:
            try:
                code2 = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("   Новый код: ").strip()
                )
            except EOFError:
                pass
        if code2:
            await client.sign_in(phone=PHONE, code=code2, phone_code_hash=phone_code_hash)
            return True
    except PhoneCodeInvalidError:
        print("❌ Неверный код", flush=True)
    except SessionPasswordNeededError:
        print("🔐 Требуется 2FA пароль", flush=True)
        await client.sign_in(password=PASSWORD_2FA)
        return True

    return False


async def try_qr_login(client):
    """Попытка входа через QR-код с автоматическим обновлением."""
    import qrcode as qrcode_lib

    print(f"\n{'='*60}", flush=True)
    print(f"📷 СТРАТЕГИЯ 2: QR-вход (с автообновлением)", flush=True)
    print(f"{'='*60}", flush=True)

    qr_login = await client.qr_login()

    # Рассчитываем время жизни токена
    import datetime as dt
    now = dt.datetime.now(tz=dt.timezone.utc)
    expires = qr_login.expires
    token_lifetime = (expires - now).total_seconds()
    print(f"   Токен живёт: {token_lifetime:.0f} секунд", flush=True)

    # Сохраняем QR
    url = qr_login.url
    qr_file = os.path.join(BASE_DIR, f'runtime_qr_{RUN_ID}.png')
    url_file = os.path.join(BASE_DIR, f'runtime_qr_{RUN_ID}.txt')

    image = qrcode_lib.make(url)
    image.save(qr_file)

    with open(url_file, 'w') as f:
        f.write(url)

    print(f"QR_URL {url}", flush=True)
    print(f"QR_FILE {qr_file}", flush=True)
    print(f"URL_FILE {url_file}", flush=True)
    print(f"⏱️  Сканруйте QR в Telegram → Настройки → Устройства → Привязать устройство", flush=True)
    print(f"   Ожидаю сканирование ({token_lifetime:.0f} сек)...", flush=True)

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            # wait() блокирует до UpdateLoginToken или timeout
            await qr_login.wait()
            print("✅ QR-токен импортирован!", flush=True)

            # Проверяем 2FA
            try:
                me = await client.get_me()
                print(f"✅ Вошли как {me.username} (ID: {me.id})", flush=True)
                return True
            except SessionPasswordNeededError:
                print("🔐 Требуется 2FA пароль", flush=True)
                await client.sign_in(password=PASSWORD_2FA)
                return True

        except asyncio.TimeoutError:
            print(f"⏰ Попытка {attempt}/{max_attempts}: QR-токен истёк", flush=True)
            if attempt < max_attempts:
                print("🔄 Генерирую новый QR-токен...", flush=True)
                await qr_login.recreate()

                now = dt.datetime.now(tz=dt.timezone.utc)
                token_lifetime = (qr_login.expires - now).total_seconds()

                url = qr_login.url
                image = qrcode_lib.make(url)
                image.save(qr_file)
                with open(url_file, 'w') as f:
                    f.write(url)

                print(f"QR_URL {url}", flush=True)
                print(f"QR_FILE {qr_file}", flush=True)
                print(f"   Новый токен живёт: {token_lifetime:.0f} секунд", flush=True)
                print(f"   Сканруйте обновлённый QR...", flush=True)

    print("❌ Все попытки QR-входа исчерпаны", flush=True)
    return False


async def main():
    print(f"🚀 Vipalina Session Recovery (RUN_ID={RUN_ID})", flush=True)
    print(f"   API_ID: {API_ID}", flush=True)
    print(f"   Phone: {PHONE}", flush=True)
    print(f"   Время: {datetime.now().isoformat()}", flush=True)

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    print("✅ Подключено к Telegram", flush=True)

    success = False

    # Стратегия 1: Phone code
    try:
        success = await try_phone_code_login(client)
    except Exception as e:
        print(f"❌ Стратегия 1 не удалась: {e}", flush=True)

    # Стратегия 2: QR login
    if not success:
        try:
            success = await try_qr_login(client)
        except Exception as e:
            print(f"❌ Стратегия 2 не удалась: {e}", flush=True)

    if success:
        session_string = save_session(client, "FINAL")
        me = await client.get_me()
        print(f"\n🎉 УСПЕХ! user_id={me.id} username={me.username}", flush=True)
        print(f"RESULT_FILE {RESULT_FILE}", flush=True)
    else:
        print("\n💀 Все стратегии не удались", flush=True)

    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
