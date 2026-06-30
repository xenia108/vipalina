"""Проверка: сколько чатов ещё не мигрированы (userbot = владелец, бота нет)."""
import os, sys, asyncio, logging
from datetime import datetime
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s | %(message)s',
    handlers=[
        logging.FileHandler(f'check_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantCreator, ChannelParticipantsAdmins

from config import (
    API_ID, API_HASH, TELETHON_BOT_TOKEN, ULTRALINA_BOT_USERNAME,
    VIPALINA_LOGS_SPREADSHEET_ID, VIP_DEPARTMENT_CHAT_ID
)

async def main():
    session_string = os.getenv('TELETHON_SESSION_STRING')
    if not session_string:
        logger.error("❌ TELETHON_SESSION_STRING не найден в .env")
        sys.exit(1)

    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    my_id = me.id
    bot_id = None

    # Прогреваем диалоги чтобы закешировать entities (все!)
    logger.info("🔄 Прогрев диалогов...")
    dialog_count = 0
    async for dialog in client.iter_dialogs():
        dialog_count += 1
    logger.info(f"✅ Прогрето {dialog_count} диалогов")

    # Получаем ID бота
    try:
        bot_entity = await client.get_entity(f"@{ULTRALINA_BOT_USERNAME}")
        bot_id = bot_entity.id
        logger.info(f"✅ Userbot ID: {my_id}, Bot ID: {bot_id}")
    except Exception as e:
        logger.error(f"❌ Не удалось найти бота: {e}")
        sys.exit(1)

    # Загружаем chat_to_student
    import gspread
    from google.oauth2.service_account import Credentials
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('vipalina_google_service_account.json', scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(VIPALINA_LOGS_SPREADSHEET_ID)
    ws = spreadsheet.worksheet("Chat_To_Student")
    all_data = ws.get_all_values()

    chat_ids = []
    for row in all_data[1:]:
        if row and row[0].strip():
            try:
                cid = int(row[0].strip())
                if cid != VIP_DEPARTMENT_CHAT_ID:
                    chat_ids.append(cid)
            except ValueError:
                continue

    logger.info(f"📊 Всего чатов в Chat_To_Student: {len(chat_ids)}")

    # Проверяем каждый чат
    need_migration = []  # userbot = владелец (бота нет ИЛИ владение не передано)
    already_migrated = []  # бот есть, userbot НЕ владелец
    not_owner = []  # userbot не владелец, бота тоже нет
    errors = []
    no_access = []  # чаты, к которым нет доступа

    for i, chat_id in enumerate(chat_ids):
        try:
            # Получаем entity чата
            try:
                entity = await client.get_entity(chat_id)
            except Exception as get_e:
                errors.append((chat_id, f"Нет доступа: {get_e}"))
                continue

            participants = await client(GetParticipantsRequest(
                channel=entity, filter=ChannelParticipantsAdmins(),
                offset=0, limit=50, hash=0
            ))

            is_owner = any(
                isinstance(p, ChannelParticipantCreator) and p.user_id == my_id
                for p in participants.participants
            )
            bot_in_chat = any(p.user_id == bot_id for p in participants.participants)

            if is_owner and not bot_in_chat:
                need_migration.append(chat_id)
                logger.info(f"  ⚠️ [{i+1}] Чат {chat_id}: userbot=владелец, бота НЕТ → нужна миграция")
            elif is_owner and bot_in_chat:
                need_migration.append(chat_id)  # владение ещё не передано!
                logger.info(f"  🟡 [{i+1}] Чат {chat_id}: userbot=владелец, бот есть, но владение НЕ передано")
            elif not is_owner and bot_in_chat:
                already_migrated.append(chat_id)
            else:
                not_owner.append(chat_id)

        except Exception as e:
            errors.append((chat_id, str(e)))
            logger.warning(f"  ❌ [{i+1}] Чат {chat_id}: ошибка — {e}")

        await asyncio.sleep(1)

    logger.info("\n" + "=" * 60)
    logger.info("📊 ИТОГИ ПРОВЕРКИ")
    logger.info("=" * 60)
    logger.info(f"  Всего чатов: {len(chat_ids)}")
    logger.info(f"  ⚠️ Нужна миграция (userbot=владелец): {len(need_migration)}")
    logger.info(f"  ✅ Уже мигрированы (бот=владелец): {len(already_migrated)}")
    logger.info(f"  ⏭️ Userbot не владелец: {len(not_owner)}")
    logger.info(f"  ❌ Ошибки доступа: {len(errors)}")

    if need_migration:
        logger.info(f"\n⚠️ ЧАТЫ ДЛЯ МИГРАЦИИ ({len(need_migration)} шт):")
        for cid in need_migration:
            logger.info(f"  {cid}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
