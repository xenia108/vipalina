# Vipalina — Telegram-бот автоматизации VIP-отдела Zerocoder University

## Что это

Комплексная система для VIP-отдела: онбординг студентов, распределение между менеджерами, SLA-мониторинг, отчётность, управление чатами. Работает 24/7 в автономном режиме.

**Владелец:** Ксения Уланова (руководитель VIP-отдела)  
**Репозиторий:** https://github.com/xenia108/vipalina

---

## Точка входа

```bash
./safe_start.sh          # запуск
./stop_vipalina.sh       # остановка
./view_logs.sh           # логи
```

Главный файл: `vip_automation_main.py`

---

## Архитектура (двойной клиент)

| Клиент | Аккаунт | Технология | Задачи |
|---|---|---|---|
| Bot Client | @zerocoder_ultralina_bot | pyTelegramBotAPI | Команды, inline-кнопки, callback |
| User Client | @ultralina_zerocoder | Telethon | Создание чатов, добавление участников |

---

## Ключевые модули

| Файл | Назначение |
|---|---|
| `vip_automation_main.py` | Оркестратор |
| `student_onboarding.py` | Создание Telegram-чата |
| `onboarding_tracker.py` | Создание Google-трекера |
| `vipalina_sheets.py` | Google Sheets: таблица "Випалина" |
| `vipalina_kpi_sheets.py` | Google Sheets: KPI Ultra |
| `vipalina_nocodb.py` | База данных студентов (NocoDB) |
| `sla_tracker.py` | Трекинг SLA |
| `report_generator.py` | Генерация отчётов |
| `manager_queue.py` | Round-robin очередь менеджеров |
| `config.py` | Все настройки (секреты через .env) |

---

## Переменные окружения

Все секреты — только в `.env` (файл исключён из git).  
Шаблон: `.env.example`

Обязательные переменные:
- `TELEGRAM_BOT_TOKEN` — токен Bot Client
- `TELETHON_BOT_TOKEN` — токен для Telethon
- `BOT_SESSION_STRING` — StringSession (генерируется через `generate_bot_session.py`)
- `API_ID` / `API_HASH` — Telegram API credentials
- `OPENAI_API_KEY` — для AI-классификации сообщений
- `NOCODB_API_TOKEN` — доступ к базе студентов

---

## Безопасность

- Никогда не коммить `.env`, `*.session`, `*_service_account.json`, `token_*.json`
- В `config.py` только `os.getenv('VAR', '')` — без захардкоженных значений
- Бот принимает команды только от авторизованных пользователей (`AUTHORIZED_VIP_USERS` в config.py)

---

## Скилл для Claude Code

Для работы с проектом через Claude Code — используй скилл `/vipalina-dev`:
- понять структуру
- запустить и остановить сервис
- проверить ошибки в логах
- внести изменения в код
- обновить README
- подготовить коммит и запушить на GitHub
