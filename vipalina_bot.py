import telebot
from telebot import types
import os
import openai
from datetime import datetime
import re
import random
import gspread
from google.oauth2.service_account import Credentials
import requests
from pydub import AudioSegment
from PIL import Image
import io
import base64
import time
from collections import defaultdict
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import json
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Импорт конфигурации
from config import VIP_HEAD, HEAD_IDS, *

# Импорт модуля управления пользователями
from user_management import get_role_manager, get_user_role, is_authorized_vip_user, is_vip_manager

# Импорт модуля поиска курсов
from vector_search_v2 import VectorCourseSearchV2

# Импорт классификатора сообщений
from message_classifier import MessageClassifier

# Настройка логгирования
def setup_logging():
    """Настраивает логгирование в файл и консоль"""
    # Создаем папку для логов
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    # Создаем логгер
    logger = logging.getLogger('vipalina_bot')
    logger.setLevel(getattr(logging, LOG_LEVEL))
    
    # Форматирование логов
    formatter = logging.Formatter(
        LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT
    )
    
    # Хэндлер для файла с ротацией
    file_handler = RotatingFileHandler(
        os.path.join(LOGS_DIR, 'vipalina_bot.log'),
        maxBytes=LOG_MAX_SIZE,
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

# Создаем бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Настройки OpenAI
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Глобальная переменная для системы поиска
course_search_system = None

# Константы
PROMPT_FILE = 'vipalina_prompt.txt'

# Создаем необходимые директории
os.makedirs(HISTORY_DIR, exist_ok=True)

# Google Sheets настройки
GSHEET_ID = GOOGLE_SHEETS_ID
GSHEET_TAB = GOOGLE_SHEETS_TAB
GSHEET_CREDS_FILE = GOOGLE_SHEETS_CREDENTIALS_FILE

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Переменные для группировки сообщений
pending_messages = defaultdict(list)
processing_users = set()

# Хранилище информации о пользователях
user_info_cache = {}

# Настройки для retry механизма
RETRY_DELAY = 5
MAX_RETRIES = 10
GSHEET_RETRY_DELAY = 2
GSHEET_MAX_RETRIES = 5
MESSAGE_GROUP_TIMEOUT = 3

# Инициализация классификатора сообщений
message_classifier = MessageClassifier()

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
    """Загружает системный промпт для бота"""
    try:
        with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        log(f"⚠️ Файл {PROMPT_FILE} не найден", level='warning')
        return "Вы помощник VIP-менеджеров университета Зерокодер."

def is_authorized_vip_user(user_id):
    """Проверяет, является ли пользователь авторизованным VIP-пользователем"""
    from user_management import is_authorized_vip_user as _is_authorized
    return _is_authorized(user_id)

def is_vip_manager(user_id):
    """Проверяет, является ли пользователь VIP-менеджером"""
    from user_management import is_vip_manager as _is_manager
    return _is_manager(user_id)

def get_user_role(user_id):
    """Определяет роль пользователя"""
    from user_management import get_user_role as _get_role
    return _get_role(user_id)

def is_message_authorized(message_text):
    """Проверяет, относится ли сообщение к авторизованным темам"""
    return message_classifier.is_authorized_topic(message_text)

def should_forward_to_manager(message_text, user_role):
    """Определяет, нужно ли переслать сообщение VIP-менеджеру"""
    return message_classifier.should_forward_to_manager(message_text, user_role)

# Обработчики сообщений
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Обработчик команды /start и /help"""
    user_id = message.from_user.id
    user_role = get_user_role(user_id)
    
    log(f"Пользователь {user_id} ({user_role}) вызвал команду /start в боте")
    
    # Проверяем авторизацию
    if user_role == "unauthorized":
        bot.reply_to(message, "Извините, но у вас нет доступа к этому боту. Обратитесь к вашему VIP-менеджеру.")
        return
    
    # Формируем ответ в зависимости от роли
    if user_role in ["vip_manager", "on_duty", "head"]:
        # Ответ для VIP-отдела
        welcome_text = f"""🤖 Привет, {message.from_user.first_name}! Я @Vipalina_zerocoder_bot - автоматизированный помощник VIP-отдела.

Моя основная задача - упростить работу VIP-менеджеров и автоматизировать процессы онбординга студентов.

✅ Что я умею:
• Мониторить чат VIP-отдела на наличие новых студентов
• Распределять студентов между менеджерами по очереди
• Создавать учебные чаты со студентами
• Отправлять уведомления с кнопками для управления студентами
• Интегрироваться с Google Sheets, Airtable и KPI-системами
• Отслеживать SLA и CSI показатели

💡 Основные команды:
• /принять_[ID] - принять студента и начать онбординг
• /пропустить_[ID] - передать студента следующему менеджеру
• /addnew - добавить студента вручную

Если у вас есть вопросы по работе системы, обратитесь к руководителю VIP-отдела."""
    else:
        # Ответ для VIP-студентов
        welcome_text = f"""🤖 Привет, {message.from_user.first_name}! Я @Vipalina_zerocoder_bot - ваш помощник в VIP-программе.

Я помогаю VIP-менеджерам в работе с вами и автоматизирую процессы обучения.

Если у вас есть вопросы по обучению или вам нужна помощь, пожалуйста:
1. Обратитесь к вашему персональному VIP-менеджеру
2. Или напишите в ваш учебный чат

Команда Zerocoder University 🚀"""
    
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['info'])
def send_info(message):
    """Обработчик команды /info"""
    user_id = message.from_user.id
    user_role = get_user_role(user_id)
    
    # Проверяем авторизацию
    if user_role == "unauthorized":
        bot.reply_to(message, "Извините, но у вас нет доступа к этому боту. Обратитесь к вашему VIP-менеджеру.")
        return
    
    info_text = "ℹ️ Информация о Vipalina:\n\n"
    info_text += "• Я помощник VIP-менеджеров в общении с VIP-студентами\n"
    info_text += "• Могу предоставлять информацию о VIP-курсах\n"
    info_text += "• Помогаю в организации взаимодействия между менеджерами и студентами\n"
    info_text += "• Обрабатываю только авторизованные запросы\n\n"
    
    if user_role == "vip_manager":
        info_text += "Как VIP-менеджер, вы можете:\n"
        info_text += "• Получать запросы от VIP-студентов\n"
        info_text += "• Предоставлять информацию о курсах\n"
        info_text += "• Управлять взаимодействием со студентами"
    else:
        info_text += "Как VIP-студент, вы можете:\n"
        info_text += "• Задавать вопросы о курсах\n"
        info_text += "• Получать помощь от менеджеров\n"
        info_text += "• Получать информацию о VIP-программах"
    
    bot.reply_to(message, info_text)

@bot.message_handler(func=lambda message: message.chat.type == 'private')
def handle_message(message):
    """Обработчик всех текстовых сообщений (ТОЛЬКО в личных чатах)"""
    user_id = message.from_user.id
    user_role = get_user_role(user_id)
    message_text = message.text if message.text else ""
    
    log(f"Получено личное сообщение от пользователя {user_id} ({user_role}): {message_text[:50]}...")
    
    # Проверяем авторизацию
    if user_role == "unauthorized":
        bot.reply_to(message, "Извините, но у вас нет доступа к этому боту. Обратитесь к вашему VIP-менеджеру.")
        return
    
    # Проверяем, относится ли сообщение к авторизованным темам
    if not is_message_authorized(message_text):
        bot.reply_to(message, "Извините, но я могу помочь только с вопросами, связанными с VIP-программами, курсами и поддержкой.")
        return
    
    # Проверяем, нужно ли переслать сообщение менеджеру
    if should_forward_to_manager(message_text, user_role):
        forward_message_to_manager(message, user_role)
    else:
        # Обрабатываем сообщение в зависимости от роли пользователя
        if user_role == "vip_manager":
            handle_vip_manager_message(message)
        else:
            handle_vip_student_message(message)

def forward_message_to_manager(message, user_role):
    """Пересылает сообщение VIP-менеджеру"""
    user_id = message.from_user.id
    message_text = message.text if message.text else ""
    
    log(f"Пересылаю сообщение от {user_id} ({user_role}) VIP-менеджерам")
    
    # Здесь должна быть логика пересылки сообщения менеджерам
    # Пока просто отправляем уведомление пользователю
    bot.reply_to(message, "Ваш запрос передан VIP-менеджеру. Ожидайте ответа.")
    
    # Отправляем уведомление всем VIP-менеджерам
    notification = f"Новый запрос от VIP-студента:\n\n{message_text}"
    for manager_id in VIP_MANAGER_CHAT_IDS:
        try:
            bot.send_message(manager_id, notification)
        except Exception as e:
            log(f"Ошибка при отправке уведомления менеджеру {manager_id}: {e}", level='error')

def handle_vip_manager_message(message):
    """Обработчик сообщений от VIP-менеджеров"""
    message_text = message.text if message.text else ""
    
    log(f"Обработка сообщения от VIP-менеджера: {message_text[:50]}...")
    
    # Здесь будет логика обработки сообщений от VIP-менеджеров
    bot.reply_to(message, "Сообщение от VIP-менеджера получено. Обрабатываю...")

def handle_vip_student_message(message):
    """Обработчик сообщений от VIP-студентов"""
    user_id = message.from_user.id
    message_text = message.text if message.text else ""
    
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
    
    bot.reply_to(message, response)

# Запуск бота
if __name__ == "__main__":
    # ⛔ БОТ ЗАБЛОКИРОВАН - НЕ ИСПОЛЬЗУЕТСЯ В ТЕКУЩЕЙ СИСТЕМЕ
    # Используется только Telethon-аккаунт (@ultralina_zerocoder) и Bot Client (@zerocoder_ultralina_bot)
    log("⛔ ВНИМАНИЕ: Бот @Vipalina_zerocoder_bot заблокирован и не запускается!")
    log("Используйте vip_automation_main.py для запуска системы")
    print("\n" + "="*60)
    print("⛔ БОТ @Vipalina_zerocoder_bot ЗАБЛОКИРОВАН")
    print("="*60)
    print("\nЭтот бот больше не используется в системе.")
    print("\nДля запуска системы используйте:")
    print("  python3 vip_automation_main.py")
    print("\n" + "="*60)
    exit(0)
    
    # ЗАБЛОКИРОВАННЫЙ КОД - НЕ ВЫПОЛНЯЕТСЯ
    # log("Vipalina бот запущен")
    # try:
    #     bot.polling(none_stop=True)
    # except KeyboardInterrupt:
    #     log("Бот остановлен пользователем")
    # except Exception as e:
    #     log(f"Ошибка при запуске бота: {e}", level='error')