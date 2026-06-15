#!/usr/bin/env python3
"""
Проверка, добавлен ли бот в чат Ксении
"""
from telethon import TelegramClient
import asyncio

API_ID = 21020399
API_HASH = "7109b029aeaa5037021d8af08e4d7d8d"
SESSION_NAME = "vipalina_telethon_session"
KSENIA_CHAT_ID = -1003279277783
BOT_USER_ID = 8447325453

async def main():
    print("🔍 ПРОВЕРКА БОТА В ЧАТЕ КСЕНИИ\n")
    
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    
    try:
        # Получаем информацию о чате
        chat = await client.get_entity(KSENIA_CHAT_ID)
        print(f"✅ Чат найден: {chat.title}")
        print(f"   ID: {chat.id}")
        print(f"   Тип: {'Супергруппа' if hasattr(chat, 'megagroup') and chat.megagroup else 'Обычная группа'}\n")
        
        # Получаем участников чата
        participants = await client.get_participants(KSENIA_CHAT_ID)
        
        print(f"👥 Всего участников: {len(participants)}\n")
        
        bot_found = False
        for p in participants:
            if p.id == BOT_USER_ID:
                bot_found = True
                print(f"✅ БОТ НАЙДЕН В ЧАТЕ!")
                print(f"   ID: {p.id}")
                print(f"   Имя: {p.first_name} {p.last_name or ''}")
                print(f"   Username: @{p.username or 'N/A'}")
                print(f"   Бот: {p.bot}")
                
                # Проверяем права
                try:
                    full_chat = await client.get_entity(KSENIA_CHAT_ID)
                    from telethon.tl.functions.channels import GetParticipantRequest
                    participant_info = await client(GetParticipantRequest(
                        channel=full_chat,
                        participant=p.id
                    ))
                    
                    print(f"\n   Роль в чате:")
                    if hasattr(participant_info.participant, 'admin_rights'):
                        print(f"      Администратор: ✅")
                        rights = participant_info.participant.admin_rights
                        print(f"      Права: {rights}")
                    else:
                        print(f"      Обычный участник")
                        
                except Exception as e:
                    print(f"   ⚠️ Не удалось проверить права: {e}")
                break
        
        if not bot_found:
            print(f"❌ БОТ НЕ НАЙДЕН В ЧАТЕ!")
            print(f"\n📋 Список участников:")
            for p in participants[:10]:
                print(f"   - {p.first_name} {p.last_name or ''} (@{p.username or 'N/A'}) [ID: {p.id}]")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
