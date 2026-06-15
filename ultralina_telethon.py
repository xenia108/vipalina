#!/usr/bin/env python3
"""
Telethon клиент для @ultralina_zerocoder
"""

import asyncio
import logging
import os
from config import API_ID, API_HASH
from telethon import TelegramClient
from telethon.events import NewMessage

# Настройка логгирования
def setup_logging():
    """Настраивает логгирование"""
    # Создаем папку для логов если её нет
    os.makedirs('vipalina_logs', exist_ok=True)
    
    # Настройка логгера
    logger = logging.getLogger('ultralina_telethon')
    logger.setLevel(logging.INFO)
    
    # Хендлер для файла
    file_handler = logging.FileHandler('vipalina_logs/ultralina_telethon.log', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # Формат логов
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    file_handler.setFormatter(formatter)
    
    # Добавляем хендлер к логгеру
    logger.addHandler(file_handler)
    
    return logger

# Инициализируем логгер
logger = setup_logging()

# Номер телефона для Telethon аккаунта
PHONE_NUMBER = "89996696144"

async def main():
    """Основная функция для запуска Telethon клиента"""
    # Создаем клиент для Telethon аккаунта (8447325453)
    client = TelegramClient('ultralina_session', API_ID, API_HASH)
    
    try:
        # Авторизация через номер телефона (без интерактивного ввода)
        await client.start(phone=PHONE_NUMBER)
        
        # Получаем информацию о себе
        me = await client.get_me()
        logger.info(f'Запущен клиент Telethon для {me.username} (ID: {me.id})')
        print(f'Запущен клиент Telethon для {me.username} (ID: {me.id})')
        
        # Обработчик новых сообщений
        @client.on(NewMessage(incoming=True))
        async def handler(event):
            # Отвечаем только в личных чатах
            if event.is_private:
                user = await event.get_sender()
                user_id = user.id
                message_text = event.message.text if event.message.text else ""
                logger.info(f"Получено сообщение от пользователя {user_id}: {message_text}")
                
                # Определяем роль пользователя и отвечаем соответствующе
                # Для VIP-отдела (менеджеры)
                if user_id in [5169675294, 6327692209, 7089851957, 6467441345, 6468860203, 7814751891, 8026625530, 268400185, 6323266269, 7692022284, 6490807977]:
                    response = "Привет, моя радость! Я тут пока ничего не отвечу, но однажды Ксюша меня настроит и заживем. Держись"
                else:
                    # Для студентов и других пользователей
                    response = "Привет! Я @ultralina_zerocoder - Telethon аккаунт для обработки личных сообщений VIP-студентов."
                
                await event.reply(response)
                logger.info(f"Отправлен ответ пользователю {user_id}")
        
        logger.info("Ultralina Telethon клиент запущен и ожидает сообщений...")
        print("Ultralina Telethon клиент запущен и ожидает сообщений...")
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"Ошибка запуска Telethon клиента: {e}")
        print(f"Ошибка запуска Telethon клиента: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())