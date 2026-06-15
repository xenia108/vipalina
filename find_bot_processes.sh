#!/bin/bash

echo "════════════════════════════════════════════════════════════"
echo "  ПОИСК ЗАПУЩЕННЫХ ПРОЦЕССОВ БОТА"
echo "════════════════════════════════════════════════════════════"
echo ""

echo "1️⃣ ЛОКАЛЬНЫЕ PYTHON ПРОЦЕССЫ:"
echo "────────────────────────────────────────────────────────────"
ps aux | grep -E "python.*vipalina|python.*main.py|python.*bot" | grep -v grep
if [ $? -ne 0 ]; then
    echo "   ✅ Локальных Python процессов не найдено"
fi
echo ""

echo "2️⃣ ПРОВЕРКА АКТИВНОСТИ БОТА ЧЕРЕЗ API:"
echo "────────────────────────────────────────────────────────────"
python3 << 'PYTHON'
import requests
import json
from datetime import datetime

TOKEN = "8464962139:AAEx6DO3LbfeAQq-i0y7bgfl1PR6re9KyT8"

print("Проверка @Vipalina_zerocoder_bot...")
try:
    # Получаем информацию о боте
    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=5)
    if r.status_code == 200:
        bot_info = r.json()
        if bot_info['ok']:
            print(f"✅ Бот найден: @{bot_info['result']['username']}")
            print(f"   ID: {bot_info['result']['id']}")
            print(f"   Имя: {bot_info['result']['first_name']}")
    
    # Проверяем webhook
    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo", timeout=5)
    if r.status_code == 200:
        webhook_info = r.json()['result']
        if webhook_info.get('url'):
            print(f"⚠️  WEBHOOK УСТАНОВЛЕН: {webhook_info['url']}")
            print(f"   Последняя ошибка: {webhook_info.get('last_error_message', 'Нет')}")
        else:
            print("✅ Webhook не установлен (polling режим)")
    
    # Пытаемся получить обновления
    print("\nПопытка получить обновления (getUpdates)...")
    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?limit=1&timeout=1", timeout=3)
    if r.status_code == 200:
        result = r.json()
        if result['ok']:
            print("✅ getUpdates работает - бот НЕ запущен в другом месте")
        else:
            print(f"⚠️  Ошибка: {result.get('description', 'Unknown')}")
    elif r.status_code == 409:
        print("❌ КОНФЛИКТ 409 - БОТ ЗАПУЩЕН В ДРУГОМ МЕСТЕ!")
        print("   Telegram API говорит, что уже идёт активный getUpdates запрос")
    else:
        print(f"⚠️  HTTP {r.status_code}: {r.text}")

except requests.exceptions.Timeout:
    print("⚠️  Timeout - API Telegram не отвечает")
except Exception as e:
    print(f"❌ Ошибка: {e}")
PYTHON
echo ""

echo "3️⃣ ПРОЦЕССЫ ПО PID ФАЙЛАМ:"
echo "────────────────────────────────────────────────────────────"
if [ -f "vipalina_logs/system.pid" ]; then
    PID=$(cat vipalina_logs/system.pid)
    echo "PID из system.pid: $PID"
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ Процесс $PID ЗАПУЩЕН"
        ps -p $PID -o pid,ppid,user,comm,stat,etime,cmd
    else
        echo "⚠️  Процесс $PID НЕ найден (мёртвый PID файл)"
    fi
else
    echo "✅ Файл system.pid не найден"
fi
echo ""

echo "4️⃣ СЕТЕВЫЕ ПОДКЛЮЧЕНИЯ (ПОРТЫ):"
echo "────────────────────────────────────────────────────────────"
echo "Проверка портов 8443, 443, 80..."
lsof -i :8443,443,80 2>/dev/null | grep python || echo "✅ Порты свободны от Python процессов"
echo ""

echo "5️⃣ НЕДАВНИЕ ЛОГИ (последние 20 строк):"
echo "────────────────────────────────────────────────────────────"
if [ -f "vipalina_logs/system.log" ]; then
    tail -20 vipalina_logs/system.log | grep -E "запущен|ERROR|409|Conflict" || echo "Нет ошибок в последних логах"
else
    echo "✅ Лог файл не найден"
fi
echo ""

echo "════════════════════════════════════════════════════════════"
echo "  РЕКОМЕНДАЦИИ:"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Если getUpdates вернул КОНФЛИКТ 409:"
echo "  → Бот запущен на другом сервере/компьютере"
echo "  → Проверьте другие машины, где может быть запущен бот"
echo "  → Или используйте команду для сброса webhook:"
echo "     curl -X POST 'https://api.telegram.org/bot8464962139:AAEx6DO3LbfeAQq-i0y7bgfl1PR6re9KyT8/deleteWebhook?drop_pending_updates=true'"
echo ""
echo "Если процессы найдены локально:"
echo "  → Используйте ./stop_vipalina.sh"
echo "  → Или kill -TERM <PID>"
echo ""

