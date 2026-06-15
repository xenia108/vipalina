#!/bin/bash

echo "════════════════════════════════════════════════════════════"
echo "  🛑 ПРИНУДИТЕЛЬНАЯ ОСТАНОВКА ВСЕХ ПРОЦЕССОВ БОТА"
echo "════════════════════════════════════════════════════════════"
echo ""

# Останавливаем все Python процессы связанные с ботом
echo "1️⃣ Остановка vip_automation_main.py..."
pkill -9 -f "vip_automation_main.py" 2>/dev/null && echo "   ✅ Остановлен" || echo "   ⚠️  Не найден"

echo "2️⃣ Остановка vipalina_bot.py..."
pkill -9 -f "vipalina_bot.py" 2>/dev/null && echo "   ✅ Остановлен" || echo "   ⚠️  Не найден"

echo "3️⃣ Остановка main.py..."
pkill -9 -f "main.py" 2>/dev/null && echo "   ✅ Остановлен" || echo "   ⚠️  Не найден"

sleep 2

# Удаление PID файлов
echo ""
echo "4️⃣ Очистка PID файлов..."
rm -f vipalina_logs/system.pid
rm -f vipalina_logs/telethon.pid
rm -f vipalina_logs/vip_automation.pid
echo "   ✅ PID файлы удалены"

# Удаление lock файлов сессии
echo ""
echo "5️⃣ Очистка lock файлов сессии..."
rm -f vipalina_session.session-journal
rm -f ultralina_session.session-journal
echo "   ✅ Lock файлы удалены"

# Финальная проверка
echo ""
echo "6️⃣ Финальная проверка процессов..."
PROCS=$(pgrep -f "python.*vipalina|python.*main.py|python.*vip_automation" 2>/dev/null)
if [ -z "$PROCS" ]; then
    echo "   ✅ Все процессы остановлены"
else
    echo "   ⚠️  Найдены процессы: $PROCS"
    echo "   Попытка принудительной остановки..."
    kill -9 $PROCS 2>/dev/null
    sleep 1
    echo "   ✅ Готово"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ✅ ВСЕ ПРОЦЕССЫ ОСТАНОВЛЕНЫ"
echo "════════════════════════════════════════════════════════════"
echo ""
