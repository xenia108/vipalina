#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Унифицированный скрипт для запуска Vipalina
"""

import argparse
import asyncio
import sys
import os

# Добавляем текущую директорию в путь поиска модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def run_telegram_bot():
    """Запуск бота на основе pyTelegramBotAPI"""
    print("Запуск Vipalina Telegram бота (pyTelegramBotAPI)...")
    
    try:
        from vipalina_bot import bot
        print("Бот запущен. Для остановки нажмите Ctrl+C")
        bot.polling(none_stop=True)
    except KeyboardInterrupt:
        print("\nБот остановлен пользователем")
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")
        return False
    
    return True

def run_telethon_client():
    """Запуск клиента на основе Telethon"""
    print("Запуск Vipalina Telethon клиента...")
    
    try:
        from vipalina_telethon import main as telethon_main
        print("Клиент запущен. Для остановки нажмите Ctrl+C")
        asyncio.run(telethon_main())
    except KeyboardInterrupt:
        print("\nКлиент остановлен пользователем")
    except Exception as e:
        print(f"Ошибка при запуске клиента: {e}")
        return False
    
    return True

def setup_environment():
    """Настройка окружения перед запуском"""
    print("Настройка окружения для Vipalina...")
    
    # Создаем необходимые директории
    directories = ['vipalina_history', 'vipalina_logs', 'data', 'vipalina_processed_courses']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"Директория {directory} готова")

def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(description="Vipalina - Персональный ассистент VIP-менеджеров")
    parser.add_argument(
        "--mode", 
        choices=["bot", "telethon", "both"],
        default="bot",
        help="Режим запуска: bot (pyTelegramBotAPI), telethon (Telethon клиент), both (оба одновременно)"
    )
    parser.add_argument(
        "--setup", 
        action="store_true", 
        help="Настройка окружения перед запуском"
    )
    
    args = parser.parse_args()
    
    # Настройка окружения при необходимости
    if args.setup:
        setup_environment()
    
    # Запуск в зависимости от режима
    if args.mode == "bot":
        run_telegram_bot()
    elif args.mode == "telethon":
        run_telethon_client()
    elif args.mode == "both":
        print("Запуск обоих версий пока не поддерживается. Запускаю основную версию бота.")
        run_telegram_bot()

if __name__ == "__main__":
    main()