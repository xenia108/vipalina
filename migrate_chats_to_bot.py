"""
Скрипт миграции: добавление @zerocoder_ultralina_bot в существующие учебные чаты.

Логика:
1. Подключаемся как userbot (он ещё в старых чатах)
2. Загружаем chat_to_student маппинг из Google Sheets
3. Для каждого чата:
   a) Добавляем @zerocoder_ultralina_bot и назначаем админом
   b) Находим VIP-менеджера среди админов чата
   c) Передаём владение менеджеру (EditCreatorRequest + 2FA)
   d) Userbot покидает чат (освобождает слот из лимита 1000)
4. Задержки 5 сек между чатами (FloodWait protection)
5. Логируем результат

Запуск:
    python migrate_chats_to_bot.py [--dry-run] [--limit N]
"""

import os
import sys
import asyncio
import argparse
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(f'migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import (
    InviteToChannelRequest, EditAdminRequest, LeaveChannelRequest,
    GetParticipantsRequest
)
from telethon.tl.functions.account import GetPasswordRequest
from telethon import password as telethon_password_utils
from telethon.tl.types import (
    ChatAdminRights, ChannelParticipantAdmin, ChannelParticipantCreator,
    ChannelParticipantsAdmins, MessageService,
    MessageActionChatAddUser, MessageActionChatDeleteUser,
    MessageActionChatJoinedByLink, MessageActionChatEditTitle
)
from telethon.errors import (
    FloodWaitError, UserNotMutualContactError, UserPrivacyRestrictedError,
    ChatAdminRequiredError, UserAlreadyParticipantError, ChannelPrivateError
)


# ---------------------------------------------------------------------------
# Кастомный EditCreatorRequest — channels.editCreator#8f38fb1f
# В Telethon 1.43.2 (layer 224) этот класс не сгенерирован,
# но сервер Telegram всё ещё принимает этот метод.
# Schema: channels.editCreator channel:InputChannel user_id:InputUser
#          password:InputCheckPasswordSRP = Updates;
# ---------------------------------------------------------------------------
import struct
from telethon.tl.tlobject import TLRequest


class EditCreatorRequest(TLRequest):
    CONSTRUCTOR_ID = 0x8f38cd1f
    SUBCLASS_OF_ID = 0x8af52aac  # Updates

    def __init__(self, channel, user_id, password):
        """
        :param channel: InputChannel
        :param user_id: InputUser
        :param password: InputCheckPasswordSRP
        :returns Updates
        """
        self.channel = channel
        self.user_id = user_id
        self.password = password

    async def resolve(self, client, utils):
        self.channel = utils.get_input_channel(
            await client.get_input_entity(self.channel))
        self.user_id = utils.get_input_user(
            await client.get_input_entity(self.user_id))

    def to_dict(self):
        return {
            '_': 'EditCreatorRequest',
            'channel': (self.channel.to_dict()
                        if isinstance(self.channel, TLObject)
                        else self.channel),
            'user_id': (self.user_id.to_dict()
                        if isinstance(self.user_id, TLObject)
                        else self.user_id),
            'password': (self.password.to_dict()
                         if isinstance(self.password, TLObject)
                         else self.password),
        }

    def _bytes(self):
        return b''.join((
            b'\x1f\xcd\x38\x8f',     # CONSTRUCTOR_ID 0x8f38cd1f LE
            self.channel._bytes(),
            self.user_id._bytes(),
            self.password._bytes(),
        ))

    @classmethod
    def from_reader(cls, reader):
        _channel = reader.tgread_object()
        _user_id = reader.tgread_object()
        _password = reader.tgread_object()
        return cls(channel=_channel, user_id=_user_id,
                   password=_password)

from config import (
    API_ID, API_HASH, TELETHON_BOT_TOKEN, ULTRALINA_BOT_USERNAME,
    VIP_DEPARTMENT_CHAT_ID, VIPALINA_LOGS_SPREADSHEET_ID,
    VIP_MANAGERS_VIP, VIP_MANAGERS_LUXURY, ON_DUTY_ACCOUNTS, VIP_HEAD,
    VIPALINA_2FA_PASSWORD
)

# Собираем ID всех VIP-менеджеров (для поиска владельца)
ALL_VIP_MANAGER_IDS = set(
    [m['telegram_id'] for m in VIP_MANAGERS_VIP] +
    [m['telegram_id'] for m in VIP_MANAGERS_LUXURY]
)

# ID, которым НЕ передаём владение (дежурные, руководитель, боты)
EXCLUDED_OWNER_IDS = set(
    [m['telegram_id'] for m in ON_DUTY_ACCOUNTS] +
    [VIP_HEAD['telegram_id']]
)


async def find_vip_manager_in_chat(client, chat_id, my_id):
    """
    Находит VIP-менеджера среди админов чата.
    Возвращает (user_id, name) или (None, None).
    """
    try:
        result = await client(GetParticipantsRequest(
            channel=chat_id,
            filter=ChannelParticipantsAdmins(),
            offset=0,
            limit=50,
            hash=0
        ))
        
        for participant in result.participants:
            uid = participant.user_id
            # Пропускаем себя (userbot), ботов, дежурных
            if uid == my_id:
                continue
            if uid in EXCLUDED_OWNER_IDS:
                continue
            # Ищем VIP-менеджера
            if uid in ALL_VIP_MANAGER_IDS:
                # Найдём имя
                name = "VIP-менеджер"
                for m in VIP_MANAGERS_VIP + VIP_MANAGERS_LUXURY:
                    if m['telegram_id'] == uid:
                        name = m['name']
                        break
                return uid, name
        
        # Если не нашли VIP-менеджера, ищем любого не-бота/не-дежурного админа
        for participant in result.participants:
            uid = participant.user_id
            if uid == my_id:
                continue
            if uid in EXCLUDED_OWNER_IDS:
                continue
            # Пропускаем ботов (ID ботов обычно > 8000000000 или имеют bot flag)
            user_obj = next((u for u in result.users if u.id == uid), None)
            if user_obj and user_obj.bot:
                continue
            name = f"{user_obj.first_name or ''} {user_obj.last_name or ''}".strip() if user_obj else "Неизвестный"
            return uid, name
                
    except Exception as e:
        logger.warning(f"  ⚠️ Не удалось получить список админов чата {chat_id}: {e}")
    
    return None, None


async def transfer_ownership(client, chat_id, new_owner_id, owner_name):
    """
    Передаёт владение чатом через EditCreatorRequest (требует 2FA).
    Возвращает True при успехе.
    """
    try:
        pwd_settings = await client(GetPasswordRequest())
        srp = telethon_password_utils.compute_check(pwd_settings, VIPALINA_2FA_PASSWORD)
        await client(EditCreatorRequest(
            channel=chat_id,
            user_id=new_owner_id,
            password=srp
        ))
        logger.info(f"  👑 Владение передано: {owner_name} (ID: {new_owner_id})")
        return True
    except Exception as e:
        logger.warning(f"  ⚠️ Не удалось передать владение → {owner_name}: {e}")
        return False


async def main(dry_run: bool = False, limit: int = 0, offset: int = 0, stop_on_owner_error: bool = False):
    """Основная функция миграции."""
    
    # Прокси опциональный (на сервере через Tor, локально без прокси)
    proxy = None
    try:
        import socks
        import socket
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(2)
        result = test_sock.connect_ex(('127.0.0.1', 9050))
        test_sock.close()
        if result == 0:
            proxy = (socks.SOCKS5, '127.0.0.1', 9050)
            logger.info("🌐 Tor-прокси доступен, используем SOCKS5")
        else:
            logger.info("🌐 Tor-прокси недоступен, подключаемся напрямую")
    except ImportError:
        logger.info("🌐 Модуль socks не найден, подключаемся напрямую")
    
    # Подключаем userbot
    session_string = os.getenv('TELETHON_SESSION_STRING')
    if not session_string:
        logger.error("❌ TELETHON_SESSION_STRING не найден в .env")
        sys.exit(1)
    
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH, proxy=proxy)
    await client.start()
    me = await client.get_me()
    my_id = me.id
    logger.info(f"✅ Userbot подключён (ID: {my_id})")

    # Прогреваем кэш сущностей (StringSession не хранит сущности)
    logger.info("🔄 Прогрев диалогов для кэша сущностей...")
    dialog_count = 0
    async for dialog in client.iter_dialogs():
        dialog_count += 1
    logger.info(f"✅ Прогрето {dialog_count} диалогов")

    # Подключаем bot_client (для удаления сообщения "покинул группу" после выхода userbot)
    bot_client = TelegramClient(StringSession(), API_ID, API_HASH, proxy=proxy)
    await bot_client.start(bot_token=TELETHON_BOT_TOKEN)
    logger.info("✅ Bot client подключён (для очистки после выхода)")
    
    # Загружаем chat_to_student из Google Sheets
    import gspread
    from google.oauth2.service_account import Credentials
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('vipalina_google_service_account.json', scopes=SCOPES)
    gc = gspread.authorize(creds)
    
    spreadsheet = gc.open_by_key(VIPALINA_LOGS_SPREADSHEET_ID)
    chat_to_student_ws = spreadsheet.worksheet("Chat_To_Student")
    all_data = chat_to_student_ws.get_all_values()
    
    # Парсим chat_id из первого столбца
    chat_ids = []
    for row in all_data[1:]:
        if row and row[0].strip():
            try:
                cid = int(row[0].strip())
                if cid != VIP_DEPARTMENT_CHAT_ID:
                    chat_ids.append(cid)
            except ValueError:
                continue
    
    logger.info(f"📊 Найдено {len(chat_ids)} учебных чатов для миграции")
    
    if offset > 0:
        chat_ids = chat_ids[offset:]
        logger.info(f"⏩ Пропущено первых {offset} чатов")
    
    if limit > 0:
        chat_ids = chat_ids[:limit]
        logger.info(f"🔒 Ограничено до {limit} чатов")
    
    if dry_run:
        logger.info("🏃 DRY RUN — изменения НЕ применяются")
    
    # Получаем entity бота
    bot_entity = await client.get_entity(f"@{ULTRALINA_BOT_USERNAME}")
    logger.info(f"✅ Найден бот @{ULTRALINA_BOT_USERNAME} (ID: {bot_entity.id})")
    
    # Права администратора для бота
    admin_rights = ChatAdminRights(
        change_info=False,
        post_messages=True,
        edit_messages=False,
        delete_messages=True,
        ban_users=False,
        invite_users=False,
        pin_messages=True,
        add_admins=False,
        manage_call=False
    )
    
    # Статистика
    success = 0
    already_in = 0
    left_chats = 0
    ownership_transferred = 0
    failed = 0
    errors = []
    skipped_not_owner = []  # Чаты, где userbot не владелец
    
    for i, chat_id in enumerate(chat_ids):
        logger.info(f"[{i+1}/{len(chat_ids)}] Обработка чата {chat_id}...")
        
        if dry_run:
            success += 1
            continue
        
        # Проверяем, является ли userbot владельцем
        try:
            entity = await client.get_entity(chat_id)
            # Проверяем, что это супергруппа/канал (нужен InputChannel)
            if not hasattr(entity, 'megagroup') and not hasattr(entity, 'broadcast'):
                logger.info(f"  ⏭️ Пропускаем — не супергруппа {chat_id}")
                skipped_not_owner.append(chat_id)
                await asyncio.sleep(1)
                continue
            
            participants = await client(GetParticipantsRequest(
                channel=chat_id, filter=ChannelParticipantsAdmins(),
                offset=0, limit=50, hash=0
            ))
            is_owner = False
            bot_in_chat = False
            for p in participants.participants:
                if isinstance(p, ChannelParticipantCreator) and p.user_id == my_id:
                    is_owner = True
                if p.user_id == bot_entity.id:
                    bot_in_chat = True
            
            if not is_owner:
                logger.info(f"  ⏭️ Пропускаем — userbot не владелец чата {chat_id}")
                skipped_not_owner.append(chat_id)
                await asyncio.sleep(1)
                continue
                
            if bot_in_chat:
                logger.info(f"  ℹ️ Бот уже в чате {chat_id} — только передача владения")
                already_in += 1
        except Exception as check_e:
            logger.warning(f"  ⚠️ Не удалось проверить владение {chat_id}: {check_e}")
            errors.append((chat_id, f"Проверка владения: {check_e}"))
            failed += 1
            await asyncio.sleep(2)
            continue
        
        try:
            # 1. Добавляем бота в чат (если ещё не добавлен)
            if not bot_in_chat:
                try:
                    await client(InviteToChannelRequest(
                        channel=chat_id,
                        users=[bot_entity]
                    ))
                    logger.info(f"  ✅ Бот добавлен в чат {chat_id}")
                    await asyncio.sleep(2)  # Пауза после добавления
                except UserAlreadyParticipantError:
                    logger.info(f"  ℹ️ Бот уже в чате {chat_id}")
                    already_in += 1
            else:
                logger.info(f"  ℹ️ Бот уже присутствует — пропускаем добавление")
            
            # 2. Назначаем бота админом (если ещё не админ)
            bot_is_admin = False
            try:
                await client(EditAdminRequest(
                    channel=chat_id,
                    user_id=bot_entity,
                    admin_rights=admin_rights,
                    rank="Випалина"
                ))
                logger.info(f"  ✅ Бот назначен админом")
                bot_is_admin = True
            except Exception as admin_e:
                logger.warning(f"  ⚠️ Не удалось назначить бота админом: {admin_e}")
                logger.info(f"  ↪ Продолжаем остальные шаги...")
            success += 1
            
            # 3. Находим VIP-менеджера и передаём владение
            ownership_ok = False
            manager_id, manager_name = await find_vip_manager_in_chat(client, chat_id, my_id)
            if manager_id:
                transferred = await transfer_ownership(client, chat_id, manager_id, manager_name)
                if transferred:
                    ownership_transferred += 1
                    ownership_ok = True
                else:
                    # Передача прав ПРОВАЛИЛАСЬ — останавливаем если флаг установлен
                    if stop_on_owner_error:
                        logger.error(f"  🛑 СТОП: ошибка передачи прав для чата {chat_id}. Миграция прервана.")
                        logger.info(f"\n  Прогресс до остановки: успешно={success}, передано={ownership_transferred}, ошибки={failed}")
                        break
            else:
                logger.info(f"  ℹ️ VIP-менеджер не найден среди админов — владение не передано")
            
            # 4. Удаляем сервисные сообщения (пригласил/вышел/вступил)
            try:
                service_msg_ids = []
                async for msg in client.iter_messages(chat_id, limit=100):
                    if isinstance(msg, MessageService):
                        action = msg.action
                        if isinstance(action, (MessageActionChatAddUser, MessageActionChatDeleteUser, MessageActionChatJoinedByLink)):
                            service_msg_ids.append(msg.id)
                if service_msg_ids:
                    await client.delete_messages(chat_id, service_msg_ids)
                    logger.info(f"  🧹 Удалено {len(service_msg_ids)} сервисных сообщений")
            except Exception as clean_e:
                logger.warning(f"  ⚠️ Не удалось очистить сервисные сообщения: {clean_e}")
            
            # 5. Userbot покидает чат ТОЛЬКО если владение передано
            if not ownership_ok:
                logger.warning(f"  ⛔ НЕ покидаем чат {chat_id} — владение не передано (FloodWait/ошибка)")
            else:
                try:
                    # Запоминаем ID последнего сообщения перед выходом
                    last_msg = (await client.get_messages(chat_id, limit=1))[0]
                    last_msg_id = last_msg.id if last_msg else 0
                    
                    await client(LeaveChannelRequest(channel=chat_id))
                    left_chats += 1
                    logger.info(f"  🚪 Userbot покинул чат {chat_id}")
                    
                    # 6. Bot удаляет сообщение "покинул группу" (оно ID = last+1)
                    if last_msg_id:
                        try:
                            await asyncio.sleep(1)
                            leave_msg_id = last_msg_id + 1
                            await bot_client.delete_messages(chat_id, [leave_msg_id])
                            logger.info(f"  🧹 Удалено сообщение 'покинул группу' (ID: {leave_msg_id})")
                        except Exception as bot_clean_e:
                            logger.warning(f"  ⚠️ Bot не смог удалить сообщение о выходе: {bot_clean_e}")
                    
                except Exception as leave_e:
                    logger.warning(f"  ⚠️ Не удалось покинуть чат {chat_id}: {leave_e}")
            
        except FloodWaitError as e:
            logger.warning(f"  ⏳ FloodWait: ждём {e.seconds} сек...")
            await asyncio.sleep(e.seconds + 1)
            try:
                await client(InviteToChannelRequest(channel=chat_id, users=[bot_entity]))
                await client(EditAdminRequest(
                    channel=chat_id, user_id=bot_entity,
                    admin_rights=admin_rights, rank="Випалина"
                ))
                success += 1
                # Передача владения при retry
                manager_id, manager_name = await find_vip_manager_in_chat(client, chat_id, my_id)
                if manager_id:
                    if await transfer_ownership(client, chat_id, manager_id, manager_name):
                        ownership_transferred += 1
                # Выход
                try:
                    await client(LeaveChannelRequest(channel=chat_id))
                    left_chats += 1
                except:
                    pass
            except Exception as retry_e:
                failed += 1
                errors.append((chat_id, str(retry_e)))
                logger.error(f"  ❌ Повторная попытка не удалась: {retry_e}")
                
        except (ChannelPrivateError, ChatAdminRequiredError) as e:
            failed += 1
            errors.append((chat_id, str(e)))
            logger.warning(f"  ⚠️ Нет доступа к чату {chat_id}: {e}")
            
        except Exception as e:
            failed += 1
            errors.append((chat_id, str(e)))
            logger.error(f"  ❌ Ошибка для чата {chat_id}: {e}")
        
        # Задержка между чатами
        await asyncio.sleep(5)
    
    # Итоговая статистика
    logger.info("\n" + "="*60)
    logger.info("📊 ИТОГИ МИГРАЦИИ")
    logger.info("="*60)
    logger.info(f"  ✅ Успешно: {success}")
    logger.info(f"  ℹ️ Уже в чате: {already_in}")
    logger.info(f"  👑 Владение передано: {ownership_transferred}")
    logger.info(f"  🚪 Userbot покинул: {left_chats}")
    logger.info(f"  ⏭️ Пропущено (не владелец): {len(skipped_not_owner)}")
    logger.info(f"  ❌ Ошибки: {failed}")
    logger.info(f"  📊 Всего обработано: {success + failed + len(skipped_not_owner)}")
    logger.info(f"  🆓 Освобождено слотов: {left_chats}")
    
    if skipped_not_owner:
        logger.info(f"\n⏭️ ПРОПУЩЕННЫЕ (не владелец, {len(skipped_not_owner)} шт):")
        for cid in skipped_not_owner:
            logger.info(f"  {cid}")
    
    if errors:
        logger.info(f"\n❌ ОШИБКИ ({len(errors)} шт):")
        for chat_id, err in errors:
            logger.info(f"  Chat {chat_id}: {err}")
    
    await client.disconnect()
    await bot_client.disconnect()
    logger.info("\n✅ Миграция завершена")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Миграция учебных чатов на Classic Bot")
    parser.add_argument('--dry-run', action='store_true', help='Не применять изменения, только показать что будет сделано')
    parser.add_argument('--limit', type=int, default=0, help='Ограничить количество чатов для обработки')
    parser.add_argument('--offset', type=int, default=0, help='Пропустить первые N чатов')
    parser.add_argument('--stop-on-owner-error', action='store_true',
                        help='Остановить миграцию при первой ошибке передачи прав владения')
    args = parser.parse_args()
    
    asyncio.run(main(
        dry_run=args.dry_run,
        limit=args.limit,
        offset=args.offset,
        stop_on_owner_error=args.stop_on_owner_error
    ))
