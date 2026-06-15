#!/bin/bash

# Скрипт перезапуска VIP Automation System с новыми функциями
# Usage: ./restart_vip_automation.sh

echo "================================================"
echo "  Перезапуск VIP Automation System"
echo "================================================"
echo ""

# Переходим в директорию проекта
cd "$(dirname "$0")"

# Останавливаем текущую версию системы
echo "Остановка текущей версии системы..."
./stop_vipalina.sh

# Ждем немного чтобы процессы завершились
sleep 3

# Проверяем что все процессы остановлены
echo "Проверка оставшихся процессов..."
REMAINING=$(ps aux | grep -E "[p]ython.*vip_automation_main.py|[p]ython.*vipalina" || true)
if [ -n "$REMAINING" ]; then
    echo "⚠️  Найдены оставшиеся процессы:"
    echo "$REMAINING"
    echo "Принудительная остановка..."
    pkill -f "python.*vip_automation_main.py" 2>/dev/null || true
    pkill -f "python.*vipalina" 2>/dev/null || true
    sleep 2
fi

# Создаем директорию для логов если не существует
mkdir -p vipalina_logs
echo "✅ Директория логов готова"

# Проверяем наличие сессии
if [ ! -f "vipalina_session.session" ]; then
    echo "⚠️  ВНИМАНИЕ: Сессия Telethon не найдена!"
    echo "   При первом запуске потребуется авторизация"
    echo ""
fi

echo "================================================"
echo "  Запуск новой версии VIP Automation System..."
echo "================================================"
echo ""
echo "Новые функции:"
echo "  ✅ Анализ истории чата при запуске (с 31.10.2025)"
echo "  ✅ Обработка студентов, появившихся во время отсутствия бота"
echo "  ✅ Улучшенная система уведомлений"
echo "  ✅ Обработка проблем приватности студентов"
echo ""
echo "Система будет:"
echo "  1. Отслеживать новых VIP-студентов"
echo "  2. Распределять их между менеджерами"
echo "  3. Создавать учебные чаты автоматически"
echo "  4. Сохранять данные в Google Sheets"
echo "  5. Анализировать историю чата при запуске"
echo ""
echo "Для остановки нажмите Ctrl+C"
echo ""
echo "------------------------------------------------"
echo ""

# Запускаем систему в фоне
nohup python3 vip_automation_main.py > vipalina_logs/vip_automation.log 2>&1 &
PID=$!
echo $PID > vipalina_logs/vip_automation.pid

echo "✅ Система запущена в фоне с PID: $PID"
echo "✅ Логи записываются в vipalina_logs/vip_automation.log"
echo "✅ PID сохранен в vipalina_logs/vip_automation.pid"
echo ""
echo "Для просмотра логов в реальном времени:"
echo "  tail -f vipalina_logs/vip_automation.log"
echo ""
echo "Для остановки системы:"
echo "  kill $PID"
echo "  или"
echo "  ./stop_vipalina.sh"
echo ""

# Проверяем что система запустилась
sleep 3
echo "Проверка статуса запуска..."
PROCESS=$(ps -p $PID -o pid= 2>/dev/null)
if [ -n "$PROCESS" ]; then
    echo "✅ VIP Automation System успешно запущена!"
else
    echo "❌ Ошибка запуска. Проверьте логи:"
    tail -10 vipalina_logs/vip_automation.log
fi

echo ""
echo "================================================"
echo "  Перезапуск завершен"
echo "================================================"