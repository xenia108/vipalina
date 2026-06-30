"""
Тест миграции с отслеживанием лимитов Telegram на EditCreatorRequest.

Запускает миграцию на N чатов (по умолчанию 5) и детально логирует:
- Время каждого вызова API
- FloodWait на каждом шаге (особенно EditCreatorRequest)
- Расстояние между вызовами EditCreatorRequest
- Рекомендуемый интервал между передачами владения

Запуск:
    python3 test_migration_limits.py [--limit 5] [--delay 10]
"""

import os, sys, asyncio, argparse, time, logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    handlers=[
        logging.FileHandler(f'test_limits_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
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
    ChatAdminRights, ChannelParticipantCreator,
    ChannelParticipantsAdmins, MessageService,
    MessageActionChatAddUser, MessageActionChatDeleteUser,
    MessageActionChatJoinedByLink
)
from telethon.errors import (
    FloodWaitError, UserAlreadyParticipantError, ChannelPrivateError,
    ChatAdminRequiredError, UserPrivacyRestrictedError
)

import struct
from telethon.tl.tlobject import TLRequest


class EditCreatorRequest(TLRequest):
    CONSTRUCTOR_ID = 0x8f38cd1f
    SUBCLASS_OF_ID = 0x8af52aac

    def __init__(self, channel, user_id, password):
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
            b'\x1f\xcd\x38\x8f',
            self.channel._bytes(),
            self.user_id._bytes(),
            self.password._bytes(),
        ))

    @classmethod
    def from_reader(cls, reader):
        _channel = reader.tgread_object()
        _user_id = reader.tgread_object()
        _password = reader.tgread_object()
        return cls(channel=_channel, user_id=_user_id, password=_password)


from config import (
    API_ID, API_HASH, TELETHON_BOT_TOKEN, ULTRALINA_BOT_USERNAME,
    VIPALINA_LOGS_SPREADSHEET_ID, VIP_DEPARTMENT_CHAT_ID,
    VIP_MANAGERS_VIP, VIP_MANAGERS_LUXURY, ON_DUTY_ACCOUNTS, VIP_HEAD,
    VIPALINA_2FA_PASSWORD
)

ALL_VIP_MANAGER_IDS = set(
    [m['telegram_id'] for m in VIP_MANAGERS_VIP] +
    [m['telegram_id'] for m in VIP_MANAGERS_LUXURY]
)
EXCLUDED_OWNER_IDS = set(
    [m['telegram_id'] for m in ON_DUTY_ACCOUNTS] +
    [VIP_HEAD['telegram_id']]
)


# ===========================================================================
# Трекер лимитов — замеряет каждый вызов и FloodWait
# ===========================================================================
class RateLimitTracker:
    def __init__(self):
        self.operations = []  # (timestamp, operation, duration, flood_wait)
        self.edit_creator_calls = []  # только для EditCreator
        self.flood_waits = []  # (timestamp, operation, wait_seconds)

    def record(self, operation: str, duration: float, flood_wait: float = 0):
        self.operations.append((time.time(), operation, duration, flood_wait))
        if operation == 'EditCreatorRequest':
            self.edit_creator_calls.append((time.time(), duration, flood_wait))
        if flood_wait > 0:
            self.flood_waits.append((time.time(), operation, flood_wait))

    def edit_creator_intervals(self):
        """Возвращает интервалы (в секундах) между вызовами EditCreatorRequest."""
        intervals = []
        for i in range(1, len(self.edit_creator_calls)):
            interval = self.edit_creator_calls[i][0] - self.edit_creator_calls[i-1][0]
            intervals.append(interval)
        return intervals

    def summary(self):
        lines = []
        lines.append("=" * 70)
        lines.append("📊 ОТЧЁТ ПО ЛИМИТАМ TELEGRAM")
        lines.append("=" * 70)

        # Общая статистика по операциям
        op_counts = {}
        op_durations = {}
        for _, op, dur, fw in self.operations:
            op_counts[op] = op_counts.get(op, 0) + 1
            if op not in op_durations:
                op_durations[op] = []
            op_durations[op].append(dur)

        lines.append("\n📋 Статистика по операциям:")
        for op in sorted(op_counts.keys()):
            durs = op_durations[op]
            avg = sum(durs) / len(durs)
            lines.append(f"  {op}: {op_counts[op]} вызовов, "
                         f"ср. {avg:.1f}с, мин {min(durs):.1f}с, макс {max(durs):.1f}с")

        # FloodWait события
        lines.append(f"\n⏳ FloodWait события ({len(self.flood_waits)} шт):")
        if self.flood_waits:
            for ts, op, fw in self.flood_waits:
                t = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                lines.append(f"  {t} | {op}: ждём {fw:.0f}с")
        else:
            lines.append("  ✅ Ни одного FloodWait!")

        # Интервалы между EditCreatorRequest
        intervals = self.edit_creator_intervals()
        lines.append(f"\n👑 EditCreatorRequest вызовы ({len(self.edit_creator_calls)} шт):")
        for i, (ts, dur, fw) in enumerate(self.edit_creator_calls):
            t = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
            fw_str = f", FloodWait {fw:.0f}с" if fw > 0 else ""
            interval_str = ""
            if i > 0:
                interval_str = f", интервал от предыдущего: {intervals[i-1]:.1f}с"
            lines.append(f"  #{i+1} {t} | длит. {dur:.1f}с{fw_str}{interval_str}")

        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            lines.append(f"\n  Ср. интервал между вызовами: {avg_interval:.1f}с")
            lines.append(f"  Мин. интервал: {min(intervals):.1f}с")
            lines.append(f"  Макс. интервал: {max(intervals):.1f}с")

        # Рекомендация
        lines.append("\n💡 РЕКОМЕНДАЦИЯ:")
        if self.flood_waits:
            max_fw = max(fw for _, _, fw in self.flood_waits)
            fw_for_creator = [fw for _, op, fw in self.flood_waits
                              if op == 'EditCreatorRequest']
            if fw_for_creator:
                lines.append(f"  EditCreatorRequest получает FloodWait до "
                             f"{max(fw_for_creator):.0f}с!")
                lines.append(f"  Рекомендуемый интервал между передачами владения: "
                             f"{max(fw_for_creator):.0f}с + 5с буфер")
            else:
                lines.append(f"  FloodWait на других операциях до {max_fw:.0f}с")
                lines.append(f"  Рекомендуемый интервал между чатами: {max_fw:.0f}с + 5с")
        else:
            lines.append("  ✅ Без FloodWait — можно пробовать интервал 10-15с между чатами")
            if len(self.edit_creator_calls) >= 3:
                lines.append("  Но для 225 чатов рекомендуется 15-20с между передачами владения")

        return "\n".join(lines)


tracker = RateLimitTracker()


async def timed_call(coro, operation_name):
    """Вызывает coroutine с замером времени и обработкой FloodWait."""
    start = time.time()
    try:
        result = await coro
        duration = time.time() - start
        tracker.record(operation_name, duration)
        return result, duration, 0
    except FloodWaitError as e:
        duration = time.time() - start
        tracker.record(operation_name, duration, flood_wait=e.seconds)
        logger.warning(f"  ⏳ FloodWait на {operation_name}: {e.seconds}с — ждём...")
        await asyncio.sleep(e.seconds + 1)
        # Повторная попытка
        start2 = time.time()
        try:
            result = await coro
            dur2 = time.time() - start2
            tracker.record(f"{operation_name}_retry", dur2)
            return result, duration + dur2 + e.seconds, e.seconds
        except FloodWaitError as e2:
            dur2 = time.time() - start2
            tracker.record(f"{operation_name}_retry2", dur2, flood_wait=e2.seconds)
            raise


async def find_vip_manager(client, chat_id, my_id):
    """Находит VIP-менеджера среди админов чата."""
    try:
        result = await client(GetParticipantsRequest(
            channel=chat_id, filter=ChannelParticipantsAdmins(),
            offset=0, limit=50, hash=0
        ))
        for p in result.participants:
            uid = p.user_id
            if uid == my_id or uid in EXCLUDED_OWNER_IDS:
                continue
            if uid in ALL_VIP_MANAGER_IDS:
                name = "VIP-менеджер"
                for m in VIP_MANAGERS_VIP + VIP_MANAGERS_LUXURY:
                    if m['telegram_id'] == uid:
                        name = m['name']
                        break
                return uid, name
        # Fallback: любой не-бот, не-дежурный
        for p in result.participants:
            uid = p.user_id
            if uid == my_id or uid in EXCLUDED_OWNER_IDS:
                continue
            user_obj = next((u for u in result.users if u.id == uid), None)
            if user_obj and user_obj.bot:
                continue
            name = (f"{user_obj.first_name or ''} {user_obj.last_name or ''}"
                    .strip()) if user_obj else "Неизвестный"
            return uid, name
    except Exception as e:
        logger.warning(f"  ⚠️ Не удалось получить админов {chat_id}: {e}")
    return None, None


async def main(limit: int = 5, delay: float = 10):
    """Основная функция тестирования лимитов."""

    logger.info(f"🧪 ТЕСТ МИГРАЦИИ С ОТСЛЕЖИВАНИЕМ ЛИМИТОВ")
    logger.info(f"   Лимит чатов: {limit}, задержка между чатами: {delay}с")

    # Проверяем 2FA пароль
    if not VIPALINA_2FA_PASSWORD:
        logger.error("❌ VIPALINA_2FA_PASSWORD не задан в .env!")
        sys.exit(1)

    # Подключаем userbot
    session_string = os.getenv('TELETHON_SESSION_STRING')
    if not session_string:
        logger.error("❌ TELETHON_SESSION_STRING не найден в .env")
        sys.exit(1)

    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    my_id = me.id
    logger.info(f"✅ Userbot подключён (ID: {my_id})")

    # Прогреваем кэш сущностей
    logger.info("🔄 Прогрев диалогов для кэша сущностей...")
    dialog_count = 0
    async for dialog in client.iter_dialogs():
        dialog_count += 1
    logger.info(f"✅ Прогрето {dialog_count} диалогов")

    # Подключаем bot_client
    bot_client = TelegramClient(StringSession(), API_ID, API_HASH)
    await bot_client.start(bot_token=TELETHON_BOT_TOKEN)
    logger.info("✅ Bot client подключён")

    # Загружаем chat_to_student
    import gspread
    from google.oauth2.service_account import Credentials
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
              'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(
        'vipalina_google_service_account.json', scopes=SCOPES)
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

    # Получаем entity бота
    bot_entity = await client.get_entity(f"@{ULTRALINA_BOT_USERNAME}")
    logger.info(f"✅ Найден бот @{ULTRALINA_BOT_USERNAME} (ID: {bot_entity.id})")

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

    # Сначала ФИЛЬТРУЕМ: только чаты, где userbot=владелец и нужна миграция
    logger.info(f"\n🔍 Фильтрация чатов (ищем те, где userbot=владелец)...")
    migration_targets = []

    for i, chat_id in enumerate(chat_ids):
        if len(migration_targets) >= limit:
            break
        try:
            entity = await client.get_entity(chat_id)
            if not hasattr(entity, 'megagroup') and not hasattr(entity, 'broadcast'):
                continue
            participants, dur, _ = await timed_call(
                client(GetParticipantsRequest(
                    channel=chat_id, filter=ChannelParticipantsAdmins(),
                    offset=0, limit=50, hash=0
                )),
                'GetParticipantsRequest_check'
            )
            is_owner = any(
                isinstance(p, ChannelParticipantCreator) and p.user_id == my_id
                for p in participants.participants
            )
            bot_in_chat = any(
                p.user_id == bot_entity.id
                for p in participants.participants
            )
            if is_owner:
                status = "бот есть, владение НЕ передано" if bot_in_chat else "бота НЕТ"
                logger.info(f"  ✅ [{len(migration_targets)+1}] Чат {chat_id}: "
                            f"userbot=владелец, {status}")
                migration_targets.append((chat_id, bot_in_chat))
            # Если не владелец — пропускаем молча
        except Exception as e:
            logger.warning(f"  ⚠️ Чат {chat_id}: ошибка при проверке — {e}")
        await asyncio.sleep(1)

    logger.info(f"\n📋 Найдено {len(migration_targets)} чатов для миграции из первых "
                f"{min(len(chat_ids), limit*5)} проверенных")

    if not migration_targets:
        logger.info("❌ Нет чатов для миграции в заданном диапазоне")
        await client.disconnect()
        await bot_client.disconnect()
        return

    # ===================================================================
    # ОСНОВНОЙ ЦИКЛ МИГРАЦИИ С ДЕТАЛЬНЫМ ЛОГИРОВАНИЕМ
    # ===================================================================
    results = {
        'success': 0,
        'bot_added': 0,
        'bot_already': 0,
        'ownership_ok': 0,
        'ownership_fail': 0,
        'userbot_left': 0,
        'skipped': 0,
        'errors': 0,
    }

    for idx, (chat_id, bot_already) in enumerate(migration_targets):
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 [{idx+1}/{len(migration_targets)}] Чат {chat_id} "
                     f"(бот {'УЖЕ ЕСТЬ' if bot_already else 'НЕТ'})")
        logger.info(f"{'='*60}")

        try:
            # 1. Добавляем бота (если ещё не добавлен)
            if not bot_already:
                logger.info(f"  1️⃣ Добавляем бота в чат...")
                try:
                    _, dur, fw = await timed_call(
                        client(InviteToChannelRequest(
                            channel=chat_id, users=[bot_entity]
                        )),
                        'InviteToChannelRequest'
                    )
                    logger.info(f"     ✅ Бот добавлен ({dur:.1f}с{f', FW {fw:.0f}с' if fw else ''})")
                    results['bot_added'] += 1
                    await asyncio.sleep(2)
                except UserAlreadyParticipantError:
                    logger.info(f"     ℹ️ Бот уже в чате")
                    results['bot_already'] += 1
                except FloodWaitError as e:
                    logger.warning(f"     ⏳ FloodWait при добавлении бота: {e.seconds}с")
                    await asyncio.sleep(e.seconds + 1)
                    try:
                        await client(InviteToChannelRequest(
                            channel=chat_id, users=[bot_entity]))
                        results['bot_added'] += 1
                    except:
                        results['errors'] += 1
                        continue
            else:
                logger.info(f"  1️⃣ Бот уже в чате — пропускаем добавление")
                results['bot_already'] += 1

            # 2. Назначаем бота админом
            logger.info(f"  2️⃣ Назначаем бота админом...")
            try:
                _, dur, fw = await timed_call(
                    client(EditAdminRequest(
                        channel=chat_id, user_id=bot_entity,
                        admin_rights=admin_rights, rank="Випалина"
                    )),
                    'EditAdminRequest'
                )
                logger.info(f"     ✅ Бот назначен админом ({dur:.1f}с{f', FW {fw:.0f}с' if fw else ''})")
            except Exception as e:
                logger.warning(f"     ⚠️ Не удалось назначить админом: {e}")

            # 3. Находим VIP-менеджера и передаём владение
            logger.info(f"  3️⃣ Ищем VIP-менеджера и передаём владение...")
            manager_id, manager_name = await find_vip_manager(client, chat_id, my_id)

            if manager_id:
                logger.info(f"     Найден: {manager_name} (ID: {manager_id})")
                try:
                    pwd_settings = await client(GetPasswordRequest())
                    srp = telethon_password_utils.compute_check(
                        pwd_settings, VIPALINA_2FA_PASSWORD)

                    _, dur, fw = await timed_call(
                        client(EditCreatorRequest(
                            channel=chat_id,
                            user_id=manager_id,
                            password=srp
                        )),
                        'EditCreatorRequest'
                    )
                    fw_str = f', FW {fw:.0f}с' if fw else ''
                    logger.info(f"     👑 Владение передано: {manager_name} "
                                f"({dur:.1f}с{fw_str})")
                    results['ownership_ok'] += 1

                except FloodWaitError as e:
                    logger.warning(f"     ⏳ FloodWait на EditCreator: {e.seconds}с!")
                    tracker.record('EditCreatorRequest', 0, flood_wait=e.seconds)
                    results['ownership_fail'] += 1
                    await asyncio.sleep(e.seconds + 1)
                    # НЕ пытаемся снова — просто помечаем

                except Exception as e:
                    logger.warning(f"     ❌ Не удалось передать владение: {e}")
                    results['ownership_fail'] += 1
            else:
                logger.info(f"     ℹ️ VIP-менеджер не найден — владение не передано")
                results['ownership_fail'] += 1

            # 4. Удаляем сервисные сообщения
            logger.info(f"  4️⃣ Очистка сервисных сообщений...")
            try:
                service_msg_ids = []
                async for msg in client.iter_messages(chat_id, limit=50):
                    if isinstance(msg, MessageService):
                        action = msg.action
                        if isinstance(action, (MessageActionChatAddUser,
                                               MessageActionChatDeleteUser,
                                               MessageActionChatJoinedByLink)):
                            service_msg_ids.append(msg.id)
                if service_msg_ids:
                    _, dur, _ = await timed_call(
                        client.delete_messages(chat_id, service_msg_ids),
                        'DeleteServiceMessages'
                    )
                    logger.info(f"     🧹 Удалено {len(service_msg_ids)} сообщений ({dur:.1f}с)")
                else:
                    logger.info(f"     ℹ️ Нет сервисных сообщений для удаления")
            except Exception as e:
                logger.warning(f"     ⚠️ Не удалось удалить сервисные: {e}")

            # 5. Userbot покидает чат (ТОЛЬКО если владение передано)
            if results['ownership_ok'] > 0 and \
               any(p[0] == chat_id for p in migration_targets[:idx+1]):
                # Проверяем, было ли владение передано именно в этом чате
                pass  # Проверка через results слишком сложная, используем флаг

            # Проверяем: стал ли новый пользователь владельцем
            ownership_transferred = False
            try:
                new_participants = await client(GetParticipantsRequest(
                    channel=chat_id, filter=ChannelParticipantsAdmins(),
                    offset=0, limit=50, hash=0
                ))
                for p in new_participants.participants:
                    if isinstance(p, ChannelParticipantCreator) and p.user_id != my_id:
                        ownership_transferred = True
                        break
            except:
                pass

            if ownership_transferred:
                logger.info(f"  5️⃣ Userbot покидает чат (владение передано)...")
                try:
                    last_msg = (await client.get_messages(chat_id, limit=1))
                    last_msg_id = last_msg[0].id if last_msg else 0

                    _, dur, _ = await timed_call(
                        client(LeaveChannelRequest(channel=chat_id)),
                        'LeaveChannelRequest'
                    )
                    results['userbot_left'] += 1
                    logger.info(f"     🚪 Userbot вышел ({dur:.1f}с)")

                    # Удалить сообщение "покинул группу" через бота
                    if last_msg_id:
                        await asyncio.sleep(1)
                        try:
                            await bot_client.delete_messages(
                                chat_id, [last_msg_id + 1])
                            logger.info(f"     🧹 Удалено сообщение 'покинул группу'")
                        except Exception as e:
                            logger.warning(f"     ⚠️ Bot не удалил сообщение о выходе: {e}")

                except Exception as e:
                    logger.warning(f"     ⚠️ Не удалось покинуть чат: {e}")
            else:
                logger.info(f"  5️⃣ Владение НЕ передано — userbot остаётся в чате")
                logger.warning(f"     ⛔ НЕ покидаем чат {chat_id}")

            results['success'] += 1

        except (ChannelPrivateError, ChatAdminRequiredError) as e:
            results['errors'] += 1
            logger.warning(f"  ❌ Нет доступа: {e}")
        except Exception as e:
            results['errors'] += 1
            logger.error(f"  ❌ Ошибка: {e}")

        # Задержка между чатами
        if idx < len(migration_targets) - 1:
            logger.info(f"  ⏳ Ждём {delay}с перед следующим чатом...")
            await asyncio.sleep(delay)

    # ===================================================================
    # ИТОГОВЫЙ ОТЧЁТ
    # ===================================================================
    logger.info("\n" + tracker.summary())

    logger.info("\n" + "=" * 70)
    logger.info("📊 ИТОГИ ТЕСТА МИГРАЦИИ")
    logger.info("=" * 70)
    logger.info(f"  ✅ Успешно обработано: {results['success']}")
    logger.info(f"  🤖 Бот добавлен: {results['bot_added']}")
    logger.info(f"  ℹ️ Бот уже был: {results['bot_already']}")
    logger.info(f"  👑 Владение передано: {results['ownership_ok']}")
    logger.info(f"  ⚠️ Владение НЕ передано: {results['ownership_fail']}")
    logger.info(f"  🚪 Userbot покинул: {results['userbot_left']}")
    logger.info(f"  ❌ Ошибки: {results['errors']}")

    # Оценка времени для полной миграции
    if results['ownership_ok'] > 0 and len(tracker.edit_creator_calls) >= 2:
        avg_interval = sum(tracker.edit_creator_intervals()) / len(tracker.edit_creator_intervals())
        total_estimated = 225 * avg_interval / 60  # минуты
        logger.info(f"\n⏱️ ОРИЕНТИРОВОЧНОЕ ВРЕМЯ для 225 чатов: "
                     f"{total_estimated:.0f} мин ({total_estimated/60:.1f} ч)")
        logger.info(f"   При среднем интервале {avg_interval:.0f}с между передачами владения")

    await client.disconnect()
    await bot_client.disconnect()
    logger.info("\n✅ Тест завершён")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Тест миграции с отслеживанием лимитов Telegram")
    parser.add_argument('--limit', type=int, default=5,
                        help='Количество чатов для миграции (по умолчанию 5)')
    parser.add_argument('--delay', type=float, default=10,
                        help='Задержка между чатами в секундах (по умолчанию 10)')
    args = parser.parse_args()

    asyncio.run(main(limit=args.limit, delay=args.delay))
