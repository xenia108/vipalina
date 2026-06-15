# Vipalina — Система автоматизации VIP-отдела Zerocoder University

**Vipalina** — комплексный Telegram-бот для автоматизации работы VIP-отдела онлайн-университета Zerocoder. Система охватывает весь жизненный цикл студента: от первичного онбординга до завершения обучения, автоматизируя рутинные задачи менеджеров и обеспечивая контроль качества 24/7.

---

## Проблема

VIP-отдел университета ежедневно принимает десятки новых студентов. Каждый требует:
- Персонального менеджера (распределение вручную)
- Создания учебного чата в Telegram
- Подготовки индивидуального Google-трекера
- Занесения данных в несколько таблиц одновременно
- Регулярного контакта и отслеживания прогресса

Весь этот процесс занимал часы ручного труда ежедневно, часть студентов терялась, а контроль SLA был невозможен.

---

## Решение

Двойная архитектура клиентов Telegram:

- **User Client** (`@ultralina_zerocoder`) — создаёт групповые чаты, добавляет участников, отправляет личные сообщения от имени пользователя
- **Bot Client** (`@zerocoder_ultralina_bot`) — отправляет inline-кнопки, обрабатывает команды, управляет потоком взаимодействия

---

## Ключевые возможности

### Автоматический онбординг студентов
1. Бот мониторит чат VIP-отдела и реагирует на новых студентов от `@zerocoder_vipgetcourse_bot`
2. Автоматически распределяет студента между менеджерами (round-robin: 6 для VIP, 7 для Luxury)
3. Менеджер получает карточку студента с кнопками **[Принять]** / **[Пропустить]**
4. После принятия запускается полный онбординг:
   - Поиск студента в NocoDB
   - Чтение данных из KPI Ultra (Google Sheets)
   - Создание персонального трекера (Google Sheet) с формулами и dropdown
   - Создание группового чата, добавление студента и менеджера
   - Запись всех данных в таблицу "Випалина"

### Отчётность и аналитика
| Команда | Описание |
|---|---|
| `/bigreport` | Комплексный отчёт: статистика отдела, сравнение менеджеров, SLA |
| `/reportmonth` | Месячный отчёт по статусам, динамике, конверсии |
| `/reportweek` | Недельный отчёт по активности и задачам |
| `/forecast` | Прогноз доходимости студентов (риски, критично) |
| `/report <ID>` | Детальная карточка студента |

### SLA и контроль качества
- Автоматическое отслеживание времени ответа менеджера на запросы студентов
- Лимит: 60 минут в рабочее время (Пн–Пт 10:00–19:00 МСК)
- Ежедневные SLA-отчёты в 20:00 МСК в чат VIP-отдела
- Ежедневные напоминания о студентах без контакта ≥7 дней (11:00 МСК, Пн–Пт)
- CSI-опрос студента через 7 дней после начала работы с менеджером

### Управление чатами
- Рассылка с сегментацией: `/broadcast [#тег] текст` (с превью и подтверждением)
- Подключение существующих чатов: `/activate <ID>`
- Мониторинг всех сообщений студентов + обновление даты последнего контакта

---

## Архитектура

```
vipalina/
├── vip_automation_main.py     # Точка входа — оркестратор всей системы
├── vipalina_bot.py            # Bot Client (pyTelegramBotAPI)
├── vipalina_telethon.py       # User Client (Telethon)
├── config.py                  # Конфигурация (секреты через .env)
│
├── onboarding_tracker.py      # Онбординг: создание трекера
├── student_onboarding.py      # Онбординг: создание чата
├── onboarding_notifications.py # Уведомления на каждом шаге
│
├── vipalina_sheets.py         # Google Sheets: таблица "Випалина"
├── vipalina_kpi_sheets.py     # Google Sheets: KPI Ultra
├── vipalina_persistence.py    # Персистенция состояния в Google Sheets
├── vipalina_nocodb.py         # Интеграция с NocoDB
│
├── sla_tracker.py             # Трекинг SLA-запросов
├── sla_reporter.py            # Генерация SLA-отчётов
├── report_generator.py        # Генерация всех отчётов
│
├── manager_queue.py           # Round-robin очередь менеджеров
├── message_classifier.py      # AI-классификация сообщений
├── state_manager.py           # Управление состоянием диалогов
│
├── course_config.py           # Конфигурация курсов
├── course_config_v2.py        # v2 маппинг курсов
├── dynamic_course_config.py   # Динамическое обновление маппинга
├── unknown_course_handler.py  # Обработка неизвестных курсов
│
├── gigachat_client.py         # GigaChat AI интеграция
├── ai_analyzer.py             # OpenAI интеграция
│
├── system_monitor.py          # Мониторинг здоровья системы
├── centralized_logger.py      # Централизованное логирование
├── pid_lock.py                # Защита от двойного запуска
│
├── safe_start.sh              # Рекомендуемый запуск
├── stop_vipalina.sh           # Остановка системы
├── view_logs.sh               # Просмотр логов
└── requirements.txt           # Зависимости Python
```

---

## Интеграции

| Сервис | Назначение |
|---|---|
| **Telegram Bot API** | Команды, inline-кнопки, callback |
| **Telethon** | Создание групп, добавление участников |
| **Google Sheets** | Випалина, KPI Ultra, SLA, Персистенция, Трекеры |
| **Google Drive** | Хранение трекеров студентов |
| **NocoDB** | Основная БД студентов (заменил Airtable) |
| **OpenAI / GigaChat** | Классификация сообщений студентов |

---

## Установка

### 1. Клонировать репозиторий

```bash
git clone https://github.com/xenia108/vipalina.git
cd vipalina
```

### 2. Создать виртуальное окружение

```bash
python3 -m venv vipalina_env
source vipalina_env/bin/activate
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Настроить окружение

Скопируй `.env.example` в `.env` и заполни все переменные:

```bash
cp .env.example .env
```

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELETHON_BOT_TOKEN=your_telethon_bot_token
BOT_SESSION_STRING=your_bot_session_string
API_ID=your_api_id
API_HASH=your_api_hash

# OpenAI
OPENAI_API_KEY=your_openai_key

# NocoDB
NOCODB_API_URL=https://your-nocodb-instance.com
NOCODB_API_TOKEN=your_nocodb_token
NOCODB_BASE_ID=your_base_id
NOCODB_TABLE_ID=your_table_id

# Google Sheets
GOOGLE_SHEETS_ID=your_kpi_sheet_id
SLA_GOOGLE_SHEETS_ID=your_sla_sheet_id
VIPALINA_LOGS_SPREADSHEET_ID=your_logs_sheet_id
```

### 5. Настроить Google API

1. Создай проект в [Google Cloud Console](https://console.cloud.google.com/)
2. Включи Google Sheets API и Google Drive API
3. Создай Service Account, скачай JSON → сохрани как `vipalina_google_service_account.json`
4. Создай OAuth 2.0 Client, скачай JSON → сохрани как `vipalina_google_oauth_client.json`
5. Предоставь сервисному аккаунту доступ к нужным таблицам

### 6. Сгенерировать Telethon-сессию

```bash
python3 generate_bot_session.py
```

Добавь полученную строку в `.env` как `BOT_SESSION_STRING`.

---

## Запуск

### Рекомендуемый способ

```bash
./safe_start.sh
```

Скрипт автоматически: останавливает старые процессы, очищает SQLite-файлы, проверяет `.env`, запускает в фоне.

### Проверка работы

```bash
# Проверить процесс
ps aux | grep "python.*vip_automation" | grep -v grep

# Смотреть лоr в реальном времени
./view_logs.sh

# Убедиться в успешном запуске
grep "✅.*запущен" vipalina_bot.log | tail -5
```

### Остановка

```bash
./stop_vipalina.sh
```

---

## Уровни доступа

| Роль | Возможности |
|---|---|
| **VIP-менеджер** | Онбординг, отчёты по своим студентам, рассылки, управление чатами |
| **Руководитель** | Полный доступ, сравнительная аналитика, настройка маппинга курсов |
| **Дежурный** | Приём студентов, базовые отчёты |
| **Разработчик** | Все права руководителя |

---

## Персистентность

Всё состояние системы сохраняется в Google Sheets (7 листов) и восстанавливается после перезапуска:

- Связи чатов и студентов
- Данные студентов
- Назначения менеджеров
- Индексы очередей (round-robin)
- Активные SLA-запросы
- Прогресс онбординга
- Системные события

---

## Безопасность

- Все секреты хранятся в `.env` (исключён из git)
- JSON-файлы Google credentials исключены из git
- Телеграм-сессии (`.session`) исключены из git
- Бот отвечает только авторизованным пользователям из white-list

---

## Технологии

- **Python 3.10+**
- **Telethon** — Telegram user client
- **pyTelegramBotAPI** — Telegram bot client
- **gspread + google-auth** — Google Sheets / Drive
- **httpx** — NocoDB API
- **OpenAI / GigaChat** — AI-классификация сообщений
- **scikit-learn** — векторный поиск по курсам
- **python-dotenv** — управление окружением

---

## Разработчик

Zerocoder University, VIP-отдел  
Версия: Production | Последнее обновление: 2026
