---
name: vipalina-dev
description: >
  Используй этот скилл для работы с проектом Vipalina — Telegram-ботом автоматизации
  VIP-отдела Zerocoder University. Триггеры: "запусти бота", "проверь ошибки",
  "обнови README", "опубликуй изменения", "что сломалось", "добавь функцию",
  "как устроен проект", "подготовь к публикации", "виправь баг".
---

# Скилл: Разработка и сопровождение Vipalina

## Контекст проекта

**Vipalina** — система автоматизации VIP-отдела Zerocoder University.
Рабочая директория: `/Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/`

**Двойная архитектура:**
- `@zerocoder_ultralina_bot` (Bot Client, pyTelegramBotAPI) — команды, inline-кнопки
- `@ultralina_zerocoder` (User Client, Telethon) — создание чатов, добавление участников

**Точка входа:** `vip_automation_main.py`

---

## Структура проекта

```
vipalina/
├── vip_automation_main.py        # Оркестратор — запускает оба клиента
├── vipalina_bot.py               # Bot Client (pyTelegramBotAPI)
├── vipalina_telethon.py          # User Client (Telethon)
├── ultralina_telethon.py         # Расширенный Telethon клиент
├── config.py                     # Конфигурация (секреты через .env!)
├── requirements.txt              # Зависимости
│
├── student_onboarding.py         # Создание чата + онбординг
├── onboarding_tracker.py         # Создание трекера в Google Sheets
├── onboarding_notifications.py   # Уведомления на каждом шаге
│
├── vipalina_sheets.py            # Google Sheets: таблица "Випалина"
├── vipalina_kpi_sheets.py        # Google Sheets: KPI Ultra
├── vipalina_persistence.py       # Персистенция состояния
├── vipalina_nocodb.py            # NocoDB API
│
├── sla_tracker.py                # Трекинг SLA-запросов
├── sla_reporter.py               # SLA-отчёты
├── report_generator.py           # Все отчёты (/bigreport, /reportmonth и др.)
│
├── manager_queue.py              # Round-robin очередь менеджеров
├── state_manager.py              # Состояние диалогов
├── message_classifier.py         # AI-классификация сообщений
│
├── course_config.py              # Конфигурация курсов
├── course_config_v2.py           # v2 маппинг
├── dynamic_course_config.py      # Динамическое обновление маппинга
├── unknown_course_handler.py     # Обработка неизвестных курсов
│
├── safe_start.sh                 # Рекомендуемый запуск
├── stop_vipalina.sh              # Остановка
├── view_logs.sh                  # Просмотр логов
│
└── .env                          # Секреты (НЕ в git!)
```

---

## Задача 1: Понять структуру проекта

Когда просят объяснить как устроен проект:

1. Прочитай `CLAUDE.md` (корень проекта) — основной контекст
2. Прочитай `config.py` — все интеграции и параметры
3. Прочитай `vip_automation_main.py` — как запускаются компоненты
4. Объясни архитектуру коротко: что делает каждый модуль, как они связаны

---

## Задача 2: Запустить сервис

```bash
# Проверить, запущен ли уже
ps aux | grep "python.*vip_automation" | grep -v grep

# Безопасный запуск (рекомендуется)
cd /Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina
./safe_start.sh

# Проверить успешный запуск
sleep 3 && grep "✅.*запущен" vipalina_bot.log | tail -5

# Остановка
./stop_vipalina.sh
```

**Частые проблемы при запуске:**
- `database is locked` → добавь `BOT_SESSION_STRING` в `.env`, удали `*.session` файлы
- `unpack requires a buffer` → перегенерируй сессию: `python3 generate_bot_session.py`
- `No module named X` → активируй venv: `source vipalina_env/bin/activate`

---

## Задача 3: Проверить ошибки в логах

```bash
cd /Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina

# Последние ошибки
grep -i "error\|exception\|traceback\|failed" vipalina_bot.log | tail -30

# Критические ошибки
grep -i "critical\|CRITICAL" vipalina_bot.log | tail -10

# Ошибки онбординга
grep -i "onboarding.*error\|error.*onboarding" vipalina_bot.log | tail -20

# Живой лог
tail -f vipalina_bot.log
```

После анализа ошибок:
1. Определи модуль, в котором ошибка (имя файла в traceback)
2. Прочитай соответствующий файл
3. Предложи исправление
4. Покажи diff перед применением — жди подтверждения

---

## Задача 4: Внести изменения в код

Перед любым изменением:
1. Прочитай целевой файл полностью
2. Покажи что именно изменишь (старый → новый фрагмент)
3. Жди явного подтверждения
4. Применяй изменение через Edit (не Write, если файл уже существует)

**Ключевые файлы по задачам:**
- Добавить команду боту → `vipalina_bot.py`
- Изменить онбординг → `student_onboarding.py` + `onboarding_tracker.py`
- Изменить отчёты → `report_generator.py`
- Изменить распределение менеджеров → `manager_queue.py` + `config.py`
- Изменить SLA → `sla_tracker.py` + `config.py`
- Добавить курс → `course_config_v2.py`

**Правило безопасности:** никогда не трогай `.env`, `*.session`, JSON-credentials.

---

## Задача 5: Обновить README

README находится в корне: `README.md`

Структура README:
1. Заголовок + описание проекта (1 абзац)
2. Проблема → Решение
3. Ключевые возможности (таблица или список)
4. Архитектура (дерево папок)
5. Интеграции (таблица)
6. Установка (пошагово)
7. Запуск
8. Уровни доступа
9. Технологии

При обновлении README:
- Отражай реальное текущее состояние кода, не планы
- Не раскрывай ID чатов, email менеджеров, внутренние ссылки
- Язык README — русский

---

## Задача 6: Подготовить проект к публикации на GitHub

```bash
cd /Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina

# 1. Проверить что нет секретов в staged файлах
git diff --cached | grep -E "token|password|secret|key|hash" | grep -v "os.getenv\|your_"

# 2. Проверить статус
git status

# 3. Добавить изменения
git add <конкретные файлы>

# 4. Создать коммит
git commit -m "описание изменений"

# 5. Запушить
git push origin main
```

**Чеклист безопасности перед push:**
- [ ] `.env` не в staging (он в `.gitignore`)
- [ ] `*.session` не в staging
- [ ] JSON-credentials не в staging
- [ ] В `config.py` нет реальных токенов (только `os.getenv('VAR', '')`)
- [ ] В `_archived_cleanup_2026/` нет `.env.backup` файлов

---

## Правила работы с проектом

- Показывай план → жди подтверждения → действуй
- После действия — коротко сообщи что сделано
- Не удаляй файлы без явного запроса
- Не отправляй сообщения от имени бота
- Секреты — только в `.env`, никогда в код
- Если что-то не получилось — написать «не получилось, потому что...» и предложить решение
