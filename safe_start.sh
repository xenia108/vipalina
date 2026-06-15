#!/bin/bash
# Безопасный запуск Vipalina бота без SQLite проблем

cd /Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina

echo "🔍 Проверка существующих процессов..."
if pgrep -f "python.*vip_automation_main" > /dev/null; then
    echo "⚠️  Найдены запущенные процессы бота. Останавливаю..."
    pkill -9 -f "python.*vip_automation_main"
    sleep 3
    echo "✅ Процессы остановлены"
fi

echo "🧹 Очистка старых SQLite файлов..."
rm -f bot_session.session bot_session.session-journal ultralina_session.session-journal
echo "✅ SQLite файлы удалены"

echo "🔍 Проверка .env конфигурации..."
if ! grep -q "BOT_SESSION_STRING=" .env; then
    echo "❌ ОШИБКА: BOT_SESSION_STRING не найден в .env"
    echo "Запустите: python3 generate_bot_session.py"
    exit 1
fi

if ! grep -q "TELETHON_SESSION_STRING=" .env; then
    echo "❌ ОШИБКА: TELETHON_SESSION_STRING не найден в .env"
    exit 1
fi

echo "✅ Конфигурация проверена"

echo "🚀 Запуск бота..."
nohup python3 vip_automation_main.py > vipalina_bot.log 2>&1 &
BOT_PID=$!

sleep 3

if ps -p $BOT_PID > /dev/null; then
    echo "✅ Бот успешно запущен (PID: $BOT_PID)"
    echo "📋 Лог: tail -f vipalina_bot.log"
else
    echo "❌ Ошибка запуска. Проверьте лог:"
    tail -50 vipalina_bot.log
    exit 1
fi
