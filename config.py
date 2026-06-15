# Конфигурационный файл для Vipalina
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Telegram Bot Configuration
# Токен для pyTelegramBotAPI (vipalina_bot.py) - отвечает на прямые запросы пользователей
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# Токен для Telethon (vip_automation_main.py) - автоматизация онбординга
TELETHON_BOT_TOKEN = os.getenv('TELETHON_BOT_TOKEN', '')

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# Google Sheets Configuration
GOOGLE_SHEETS_CREDENTIALS_FILE = "vipalina_google_oauth_client.json"
GOOGLE_SHEETS_ID = os.getenv('GOOGLE_SHEETS_ID', '1MhDUG9IuYJN9lWG_p88UviOnQeiDM3Hj1eVqaoqPqYM')  # KPI Ultra
GOOGLE_SHEETS_TAB = "vip_users"

# Google Sheets Service Account for sheets operations
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = "vipalina_google_service_account.json"

# Google Drive Tracker Configuration
TRACKER_FOLDER_ID = "1RSBAWk3VH9_Gcd0vx83YCMXU9Ushh7Hw"  # Папка для трекеров
TRACKER_OWNER_EMAIL = "vipzerocoder@gmail.com"  # Владелец трекеров (9 ГБ свободного места)
# Путь к пользовательскому OAuth токену (если используется авторизация от имени vipzerocoder)
USER_OAUTH_TOKEN_PATH = os.getenv('USER_OAUTH_TOKEN_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'token_vipzerocoder.json'))

# SLA Google Sheets Configuration
SLA_GOOGLE_SHEETS_ID = os.getenv('SLA_GOOGLE_SHEETS_ID', '19YcEHA1HvBSfNRHFBK06eC7aRurH5NG6mhyE061BdNY')
SLA_GOOGLE_SHEETS_TAB = "SLA_Data"

# Логи Випалина - таблица для персистенции состояния бота
# Сохраняет все runtime-данные для восстановления после перезапуска
VIPALINA_LOGS_SPREADSHEET_ID = os.getenv('VIPALINA_LOGS_SPREADSHEET_ID', '1wWbgAq92qehpTO0lm4AQJzTQ8RvpA9fX_vORYBqkHCE')

# Directory Configuration
HISTORY_DIR = "vipalina_history"
LOGS_DIR = "vipalina_logs"
COURSES_DIR = "vipalina_courses"

# API Configuration for Telethon
API_ID = int(os.getenv('API_ID', '21020399'))
API_HASH = os.getenv('API_HASH', '')

# Aliases for main.py compatibility
TELEGRAM_API_ID = API_ID
TELEGRAM_API_HASH = API_HASH
TELETHON_SESSION_NAME = 'vipalina_session'
VIPALINA_2FA_PASSWORD = os.getenv('VIPALINA_2FA_PASSWORD', '')
VIPALINA_2FA_PASSWORD = os.getenv('VIPALINA_2FA_PASSWORD', '')

# VIP Manager Chat IDs - список ID чатов, где работают VIP-менеджеры
VIP_MANAGER_CHAT_IDS = [
    -1001755644531,  # Чат VIP-отдела
    5169675294,      # Марина Иванова
    6327692209,      # Оля Антипанова
    7089851957,      # Кристина Махмудян
    6467441345,      # Лиза Виноградова
    6468860203,      # Катя Чайка
    7814751891,      # Оля Тихонова
    8026625530,      # Катя Пилипенко
    268400185,       # Ксюша Уланова (руководитель)
    6323266269,      # Черный Дежурный
    6490807977,      # Синий Дежурный
    7692022284       # Изумрудный Дежурный (@vip_zerocoder)
]

# Авторизованные VIP-пользователи (студенты)
AUTHORIZED_VIP_USERS = [
    268400185,       # Ксюша Уланова (руководитель)
    5169675294,      # Марина Иванова
    6327692209,      # Оля Антипанова
    7089851957,      # Кристина Махмудян
    6467441345,      # Лиза Виноградова
    6468860203,      # Катя Чайка
    7814751891,      # Оля Тихонова
    8026625530,      # Катя Пилипенко
    6323266269,      # Черный Дежурный
    6490807977,      # Синий Дежурный
    7692022284       # Изумрудный Дежурный (@vip_zerocoder)
]

# VIP Department Chat
VIP_DEPARTMENT_CHAT_ID = -1001755644531  # Чат для новых студентов и уведомлений
VIP_ZEROCODER_BOT_USERNAME = "vip_zerocode_bot"  # Бот для CSI/SLA (Salebot, сторонний)
ULTRALINA_BOT_USERNAME = "zerocoder_ultralina_bot"  # Classic bot для мониторинга групповых чатов

# GigaChat API Configuration
GIGACHAT_CLIENT_ID = os.getenv('GIGACHAT_CLIENT_ID', '')
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
GIGACHAT_AUTH_KEY = os.getenv('GIGACHAT_AUTH_KEY', '')

# === AIRTABLE CONFIGURATION (DEPRECATED - use NocoDB) ===
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY', '')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID', 'appOhutNTkJfXRZYr')
AIRTABLE_TABLE_ID = os.getenv('AIRTABLE_TABLE_ID', 'tbleAfY4LbQWL68m6')  # Table ID вместо названия (из-за кириллицы)
AIRTABLE_TABLE_NAME = "Новые"  # Человекочитаемое название

# Названия полей в Airtable
AIRTABLE_FIELD_STUDENT_NAME = "Студент"
AIRTABLE_FIELD_GETCOURSE_ID = "ID пользователя"
AIRTABLE_FIELD_MANAGER = "Менеджер"
AIRTABLE_FIELD_COURSE = "Курс"
AIRTABLE_FIELD_TELEGRAM = "Telegram"
AIRTABLE_FIELD_EMAIL = "Email"
AIRTABLE_FIELD_PHONE = "tgram (Телеги нет, но вот телефон:)"
AIRTABLE_FIELD_STATUS = "Статус студента"

# === NOCODB CONFIGURATION ===
# NocoDB заменяет Airtable как основную базу данных студентов
NOCODB_API_URL = os.getenv('NOCODB_API_URL', 'https://form.zerocoder.ru')
NOCODB_API_TOKEN = os.getenv('NOCODB_API_TOKEN', '')
NOCODB_BASE_ID = os.getenv('NOCODB_BASE_ID', 'p6h5n9hamzoh2on')  # Workspace ID
NOCODB_TABLE_ID = os.getenv('NOCODB_TABLE_ID', 'mxt42rku2ufjmbx')  # Таблица "Ученики все"
NOCODB_VIEW_ID = os.getenv('NOCODB_VIEW_ID', 'vwq982oyajpi1zfx')  # Вьюшка "Новенькие"
NOCODB_TABLE_NAME = "Ученики все"  # Человекочитаемое название
NOCODB_VIEW_NAME = "Новенькие"  # Вьюшка для новых студентов

# Названия полей в NocoDB (совместимы с Airtable для обратной совместимости)
NOCODB_FIELD_STUDENT_NAME = "Студент"
NOCODB_FIELD_GETCOURSE_ID = "ID пользователя"
NOCODB_FIELD_MANAGER = "Менеджер"
NOCODB_FIELD_COURSE = "Курс"
NOCODB_FIELD_TELEGRAM = "Telegram"
NOCODB_FIELD_EMAIL = "Email"
NOCODB_FIELD_PHONE = "Телефон"
NOCODB_FIELD_STATUS = "Статус студента"
NOCODB_FIELD_NEXT_CONTACT = "Следующее общение"  # Дата следующего касания (формат YYYY-MM-DD)
NOCODB_FIELD_LAST_CONTACT = "Дата последнего контакта"  # Дата фактического касания (формат YYYY-MM-DD)

# VIP Manager Team - участвуют в round-robin распределении студентов (6 человек)
# Очередь для VIP студентов (без [luxury] и [mini-luxury] в теге курса)
VIP_MANAGERS_VIP = [
    {
        "name": "Марина Иванова",
        "telegram_id": 5169675294,
        "email": "yermol1412@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Оля Антипанова",
        "telegram_id": 6327692209,
        "email": "antipanova2020@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Кристина Махмудян",
        "telegram_id": 7089851957,
        "email": "kristina.mahmudyan@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Лиза Виноградова",
        "telegram_id": 6467441345,
        "email": "elizavinogradova14@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Катя Чайка",
        "telegram_id": 6468860203,
        "username": "inna18522",
        "email": "inna18522@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Оля Тихонова",
        "telegram_id": 7814751891,
        "email": "tikhonovaov.ooc@gmail.com",
        "role": "VIP_MANAGER"
    }
]

# Очередь для Luxury студентов (с [luxury] или [mini-luxury] в теге курса)
VIP_MANAGERS_LUXURY = [
    {
        "name": "Кристина Махмудян",
        "telegram_id": 7089851957,
        "email": "kristina.mahmudyan@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Катя Пилипенко",
        "telegram_id": 8026625530,
        "username": "katpil7777",
        "email": "katpil7777@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Марина Иванова",
        "telegram_id": 5169675294,
        "email": "yermol1412@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Лиза Виноградова",
        "telegram_id": 6467441345,
        "email": "elizavinogradova14@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Оля Тихонова",
        "telegram_id": 7814751891,
        "email": "tikhonovaov.ooc@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Катя Чайка",
        "telegram_id": 6468860203,
        "username": "inna18522",
        "email": "inna18522@gmail.com",
        "role": "VIP_MANAGER"
    },
    {
        "name": "Оля Антипанова",
        "telegram_id": 6327692209,
        "email": "antipanova2020@gmail.com",
        "role": "VIP_MANAGER"
    }
]

# Руководитель VIP-отдела - НЕ участвует в round-robin, но имеет все права + особые функции
VIP_HEAD = {
    "name": "Ксюша Уланова",
    "telegram_id": 268400185,
    "email": "ulanovawork@gmail.com",
    "role": "VIP_HEAD"
}

# Разработчик - НЕ участвует в round-robin/чатах, но имеет ВСЕ права как руководитель
VIP_DEVELOPER = {
    "name": "Ден МОК",
    "telegram_id": 138828644,
    "username": "den_mok",
    "role": "DEVELOPER"
}

# Все IDs с правами руководителя (для проверки is_head)
HEAD_IDS = [VIP_HEAD['telegram_id'], VIP_DEVELOPER['telegram_id']]

# Тестовый пользователь - всегда обрабатывается как новый студент (для тестирования)
# ВАЖНО: Telegram ID должен быть ДРУГИМ, чтобы не конфликтовать с VIP_HEAD!
TEST_STUDENT = {
    "name": "Ксения Уланова",
    "getcourse_id": "309200567",
    "email": "ulanovawork@gmail.com",
    "phone": "79818102820",
    "telegram_username": "@Xenia108",
    "telegram_id": 999999999  # Фиктивный ID для тестов, НЕ совпадает с реальным
}

# Дежурные аккаунты - имеют права менеджеров, но НЕ участвуют в round-robin распределении
ON_DUTY_ACCOUNTS = [
    {
        "name": "Черный Дежурный",
        "telegram_id": 6323266269,
        "username": "zero_vip_manager",
        "role": "ON_DUTY"
    },
    {
        "name": "Синий Дежурный",
        "telegram_id": 6490807977,
        "username": "manager_vip_zero",
        "role": "ON_DUTY"
    },
    {
        "name": "Изумрудный Дежурный",
        "telegram_id": 7692022284,
        "username": "vip_zerocoder",
        "role": "ON_DUTY"
    }
]

# Все пользователи с правами менеджера (для проверки доступа к командам)
# 6 VIP + 7 Luxury менеджеров (уникальные) + 1 руководитель + 1 разработчик + 3 дежурных = 18 человек
ALL_MANAGER_IDS = (
    [m['telegram_id'] for m in VIP_MANAGERS_VIP] + 
    [m['telegram_id'] for m in VIP_MANAGERS_LUXURY] + 
    HEAD_IDS + 
    [m['telegram_id'] for m in ON_DUTY_ACCOUNTS]
)

# Google Sheets Tab Names
GOOGLE_SHEETS_VIPALINA_TAB = "Випалина"  # Tracking tab for GetCourse ID, Telegram ID, Chat ID
GOOGLE_SHEETS_KPI_TAB = "Общий список new"  # KPI tracking for all students

# Таблица "Доходимость по ДЗ Випалина" для детализации домашних заданий
HOMEWORK_TRACKING_SPREADSHEET_ID = "1BvRH7-KL5glYXEgRJsa2s49BiHh4m875iQ8nBJDIcu4"
HOMEWORK_TRACKING_TAB = "ВСЕ ДЗ"

# === SLA/CSI CONFIGURATION ===
# SLA рабочее время (МСК)
SLA_WORKING_HOURS = {
    'monday': (10, 18),
    'tuesday': (10, 18),
    'wednesday': (10, 18),
    'thursday': (10, 18),
    'friday': (10, 18),
    'saturday': (10, 16),
    'sunday': None  # Выходной
}

# SLA лимит времени ответа (минуты)
SLA_RESPONSE_TIME_LIMIT = 30

# CSI рассылка
CSI_SURVEY_URL = "https://forms.yandex.ru/u/688cb44c02848f1688f5ea0a"
CSI_SURVEY_DAY = 28  # Число месяца
CSI_SURVEY_HOUR = 18  # Час отправки (МСК)

# Часовой пояс Москвы
MOSCOW_TZ = "Europe/Moscow"

# Message Processing Settings
MESSAGE_GROUP_TIMEOUT = 3
MAX_RETRIES = 10
RETRY_DELAY = 5

# RAG System Settings
RAG_COURSES_DIR = "vipalina_processed_courses"
RAG_INDEX_FILE = "vipalina_course_index/vipalina_index.pkl"
RAG_EMBEDDINGS_FILE = "vipalina_embeddings/vipalina_embeddings.pkl"

# Classification Settings
AUTHORIZED_TOPICS = [
    "курс", "обучение", "программа", "материал", "вебинар",
    "оплата", "стоимость", "рассрочка", "поддержка", "помощь",
    "менеджер", "консультация", "аккаунт", "профиль",
    "course", "program", "material", "webinar", "payment",
    "support", "help", "manager", "consultation", "account"
]

# Security Settings
ALLOWED_USER_ROLES = ["vip_manager", "vip_student"]
MAX_MESSAGE_LENGTH = 4000
RATE_LIMIT_WINDOW = 60  # seconds
MAX_MESSAGES_PER_WINDOW = 10

# Logging Settings
LOG_LEVEL = "INFO"
LOG_FORMAT = "[%(asctime)s] %(levelname)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5