#!/bin/bash

echo "════════════════════════════════════════════════════════════"
echo "  Запуск ТОЛЬКО Telethon аккаунта (@ultralina_zerocoder)"
echo "════════════════════════════════════════════════════════════"
echo ""

# Проверка на запущенные процессы
if pgrep -f "vip_automation_main.py" > /dev/null; then
    echo "⚠️  Telethon уже запущен!"
    echo "Для остановки: pkill -f vip_automation_main.py"
    exit 1
fi

# Создание директорий
mkdir -p vipalina_logs

# Удаление старых lock файлов
if [ -f "vipalina_session.session-journal" ]; then
    echo "🔧 Удаление старых lock файлов..."
    rm -f vipalina_session.session-journal
fi

echo "🚀 Запуск Telethon в фоновом режиме..."
echo ""

# Запуск в фоне
nohup python3 vip_automation_main.py > vipalina_logs/telethon.log 2>&1 &
TELETHON_PID=$!

echo "✅ Telethon запущен с PID: $TELETHON_PID"
echo "$TELETHON_PID" > vipalina_logs/telethon.pid
echo ""

# Ждём 5 секунд для инициализации
sleep 5

# Проверка статуса
if ps -p $TELETHON_PID > /dev/null; then
    echo "✅ Telethon успешно запущен!"
    echo ""
    echo "📊 СТАТУС:"
    echo "────────────────────────────────────────────────────────────"
    echo "PID: $TELETHON_PID"
    echo "Лог: vipalina_logs/telethon.log"
    echo ""
    echo "ФУНКЦИИ:"
    echo "  ✅ Мониторинг VIP-чата"
    echo "  ✅ Онбординг новых студентов"
    echo "  ✅ Создание учебных чатов"
    echo "  ✅ Распределение между менеджерами"
    echo "  ✅ Команды /принять, /пропустить, /addnew"
    echo ""
    echo "ПРОСМОТР ЛОГОВ:"
    echo "  tail -f vipalina_logs/telethon.log"
    echo ""
    echo "ОСТАНОВКА:"
    echo "  pkill -f vip_automation_main.py"
    echo "  или"
    echo "  kill -TERM $TELETHON_PID"
    echo "────────────────────────────────────────────────────────────"
else
    echo "❌ Ошибка запуска! Проверьте логи:"
    echo "  cat vipalina_logs/telethon.log"
fi

echo ""
