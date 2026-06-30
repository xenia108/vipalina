#!/usr/bin/env python3
"""Генератор новой StringSession для Telethon"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH
import socks

PHONE = '89996696144'
proxy = (socks.SOCKS5, '127.0.0.1', 9050)

async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH, proxy=proxy)
    await client.start(phone=PHONE)
    session_string = client.session.save()
    print(f'\n\n=== НОВАЯ SESSION STRING ===')
    print(session_string)
    print(f'=== КОНЕЦ ===\n')
    print('Скопируйте строку выше и вставьте в .env как TELETHON_SESSION_STRING=...')
    await client.disconnect()

asyncio.run(main())
