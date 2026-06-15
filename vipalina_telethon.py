from telethon import TelegramClient, events
import asyncio
import os
import openai
from datetime import datetime
import re
from telethon.errors import RPCError
import random
import gspread
from google.oauth2.service_account import Credentials
import requests
from pydub import AudioSegment
from PIL import Image
import io
from telethon.errors.rpcerrorlist import VoiceMessagesForbiddenError
import base64
import time
from collections import defaultdict
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler

# Импорт конфигурации
from config import VIP_HEAD, HEAD_IDS, *

# Импорт модуля поиска курсов
# from course_search import search_courses, format_course_for_prompt  # Старая система
from vector_search_v2 import VectorCourseSearchV2

# Импорт классификатора сообщений
from message_classifier import MessageClassifier

# Настройка логгирования
def setup_logging():
    """Настраивает логгирование в файл и консоль"""
    # Создаем папку для логов
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    # Создаем логгер
    logger = logging.getLogger('vipalina_telethon')
    logger.setLevel(getattr(logging, LOG_LEVEL))
    
    # Форматирование логов
    formatter = logging.Formatter(
        LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT
    )
    
    # Хэндлер для файла с ротацией (максимум 10MB, до 5 файлов)
    file_handler = RotatingFileHandler(
        os.path.join(LOGS_DIR, 'vipalina_telethon.log'),
        maxBytes=LOG_MAX_SIZE,  # 10MB
        backupCount=LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, LOG_LEVEL))
    file_handler.setFormatter(formatter)
    
    # Хэндлер для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL))
    console_handler.setFormatter(formatter)
    
    # Добавляем хэндлеры к логгеру
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Инициализируем логгер
bot_logger = setup_logging()

# Инициализация Telethon клиента
client = TelegramClient('vipalina_session', API_ID, API_HASH)

# Настройки OpenAI - использование глобальной переменной окружения OPENAI_API_KEY
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)  # Автоматически использует OPENAI_API_KEY из конфигурации

# Глобальная переменная для системы поиска (инициализируется в main())
course_search_system = None

PROMPT_FILE = 'vipalina_prompt.txt'
HISTORY_DIR = 'vipalina_history'

if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# Google Sheets настройки
GSHEET_ID = GOOGLE_SHEETS_ID
GSHEET_TAB = GOOGLE_SHEETS_TAB
GSHEET_CREDS_FILE = GOOGLE_SHEETS_CREDENTIALS_FILE  # credentials файл сервисного аккаунта

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Переменные для группировки сообщений
pending_messages = defaultdict(list)  # user_id -> [{'event': event, 'time': timestamp}]
processing_users = set()  # множество user_id которые сейчас обрабатываются

# Хранилище информации о пользователях
user_info_cache = {}  # user_id -> {'name': str, 'gender': str, 'message_count': int, 'last_name_usage': int}

# Настройки для retry механизма
RETRY_DELAY = 5  # секунд
MAX_RETRIES = 10
GSHEET_RETRY_DELAY = 2  # секунд для Google Sheets
GSHEET_MAX_RETRIES = 5
MESSAGE_GROUP_TIMEOUT = 3  # секунд для группировки сообщений

# Инициализация классификатора сообщений
message_classifier = MessageClassifier()

# Переменные для PDF и ссылок больше не нужны - используем прямые ссылки

def log(message, level='info'):
    """Логгирование с поддержкой уровней"""
    if level.lower() == 'error':
        bot_logger.error(message)
    elif level.lower() == 'warning':
        bot_logger.warning(message)
    elif level.lower() == 'debug':
        bot_logger.debug(message)
    else:
        bot_logger.info(message)

def load_system_prompt():
    with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
        return f.read().strip()

def load_course_list():
    """Загружает список курсов для Алины"""
    try:
        with open('course_list_for_vip.txt', 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        log("⚠️ Файл course_list_for_vip.txt не найден")
        return ""

def is_authorized_vip_user(user_id):
    """Проверяет, является ли пользователь авторизованным VIP-пользователем"""
    return user_id in AUTHORIZED_VIP_USERS or str(user_id) in AUTHORIZED_VIP_USERS

def is_vip_manager(user_id):
    """Проверяет, является ли пользователь VIP-менеджером"""
    return user_id in VIP_MANAGER_CHAT_IDS or str(user_id) in VIP_MANAGER_CHAT_IDS

def get_user_role(user_id):
    """Определяет роль пользователя"""
    if user_id in HEAD_IDS:
        return "head"
    elif is_vip_manager(user_id):
        return "vip_manager"
    elif is_authorized_vip_user(user_id):
        return "vip_student"
    else:
        return "unauthorized"

def should_forward_to_manager(message_text, user_role):
    """Определяет, нужно ли переслать сообщение VIP-менеджеру"""
    return message_classifier.should_forward_to_manager(message_text, user_role)

@client.on(events.NewMessage(incoming=True))
async def handle_new_message(event):
    """Обработчик новых входящих сообщений"""
    # Получаем информацию о пользователе
    user = await event.get_sender()
    user_id = user.id
    user_role = get_user_role(user_id)
    
    # Логируем сообщение
    message_text = event.message.text if event.message.text else ""
    log(f"Получено сообщение от пользователя {user_id} ({user_role}): {message_text[:50]}...")
    
    # Проверяем, является ли это личным сообщением
    if not event.is_private:
        # Для сообщений в группах просто игнорируем (не отвечаем)
        return
    
    # Проверяем авторизацию (только для личных сообщений)
    if user_role == "unauthorized":
        await event.reply("Извините, но у вас нет доступа к этому боту. Обратитесь к вашему VIP-менеджеру.")
        return
    
    # Проверяем, относится ли сообщение к авторизованным темам
    if not message_classifier.is_authorized_topic(message_text):
        await event.reply("Извините, но я могу помочь только с вопросами, связанными с VIP-программами, курсами и поддержкой.")
        return
    
    # Проверяем, нужно ли переслать сообщение менеджеру
    if should_forward_to_manager(message_text, user_role):
        await forward_message_to_manager(event, user_role)
    else:
        # Обрабатываем сообщение в зависимости от роли пользователя
        if user_role == "vip_manager":
            await handle_vip_manager_message(event)
        else:
            await handle_vip_student_message(event)

async def forward_message_to_manager(event, user_role):
    """Пересылает сообщение VIP-менеджеру"""
    user = await event.get_sender()
    user_id = user.id
    message_text = event.message.text if event.message.text else ""
    
    log(f"Пересылаю сообщение от {user_id} ({user_role}) VIP-менеджерам")
    
    # Здесь должна быть логика пересылки сообщения менеджерам
    # Пока просто отправляем уведомление пользователю
    await event.reply("Ваш запрос передан VIP-менеджеру. Ожидайте ответа.")
    
    # Отправляем уведомление всем VIP-менеджерам
    notification = f"Новый запрос от VIP-студента:\n\n{message_text}"
    for manager_id in VIP_MANAGER_CHAT_IDS:
        try:
            await client.send_message(manager_id, notification)
        except Exception as e:
            log(f"Ошибка при отправке уведомления менеджеру {manager_id}: {e}", level='error')

async def handle_vip_manager_message(event):
    """Обработчик сообщений от VIP-менеджеров"""
    message_text = event.message.text if event.message.text else ""
    
    log(f"Обработка сообщения от VIP-менеджера: {message_text[:50]}...")
    
    # Здесь будет логика обработки сообщений от VIP-менеджеров
    await event.reply("Сообщение от VIP-менеджера получено. Обрабатываю...")

async def handle_vip_student_message(event):
    """Обработчик сообщений от VIP-студентов"""
    user = await event.get_sender()
    user_id = user.id
    message_text = event.message.text if event.message.text else ""
    
    log(f"Обработка сообщения от VIP-студента {user_id}: {message_text[:50]}...")
    
    # Классифицируем сообщение
    category, confidence = message_classifier.classify_message(message_text)
    
    # Здесь будет логика обработки сообщений от VIP-студентов
    response = f"Сообщение от VIP-студента получено.\n"
    response += f"Категория: {category}\n"
    response += f"Уверенность: {confidence:.2f}\n\n"
    
    if category == "course_inquiry":
        response += "Я могу предоставить информацию о VIP-курсах. Уточните, какой курс вас интересует?"
    elif category == "payment_inquiry":
        response += "По вопросам оплаты рекомендую обратиться к вашему VIP-менеджеру."
    elif category == "technical_support":
        response += "По техническим вопросам рекомендую обратиться к вашему VIP-менеджеру."
    else:
        response += "Ваш запрос будет передан VIP-менеджеру."
    
    await event.reply(response)

async def main():
    """Основная функция для запуска клиента"""
    # Авторизация
    await client.start()
    
    # Получаем информацию о себе
    me = await client.get_me()
    log(f'Запущен клиент Telethon для {me.username} (ID: {me.id})')
    
    # Запускаем клиента
    log("Vipalina Telethon клиент запущен и ожидает сообщений...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    # Запуск основной функции
    asyncio.run(main())