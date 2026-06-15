#!/bin/bash

# Скрипт запуска системы автоматизации VIP-отдела

echo "🚀 Запуск системы автоматизации VIP-отдела..."

# Проверяем срок действия токена OAuth
echo "🔍 Проверка срока действия токена OAuth..."
python3 check_token_expiry.py

# Запускаем основную систему
echo "🔄 Запуск основной системы..."
python3 vip_automation_main.py

# Переходим в директорию проекта
cd "$(dirname "$0")"

# Проверяем наличие необходимых файлов
echo "Проверка конфигурации..."

if [ ! -f "vipalina_google_credentials.json" ]; then
    echo "❌ ОШИБКА: Файл vipalina_google_credentials.json не найден!"
    echo "   Пожалуйста, добавьте файл с credentials Google Sheets"
    exit 1
fi

if [ ! -f "config.py" ]; then
    echo "❌ ОШИБКА: Файл config.py не найден!"
    exit 1
fi

echo "✅ Конфигурация найдена"
echo ""

# Проверяем Python
if ! command -v python3 &> /dev/null; then
    echo "❌ ОШИБКА: Python 3 не установлен!"
    exit 1
fi

echo "✅ Python версия: $(python3 --version)"
echo ""

# Проверяем зависимости
echo "Проверка зависимостей..."
python3 -c "import telethon" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Telethon не установлен. Устанавливаем зависимости..."
    pip3 install -r requirements.txt
fi

python3 -c "import gspread" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  gspread не установлен. Устанавливаем зависимости..."
    pip3 install -r requirements.txt
fi

echo "✅ Все зависимости установлены"
echo ""

# Создаем директорию для логов если не существует
mkdir -p vipalina_logs
echo "✅ Директория логов готова"
echo ""

# Проверяем наличие сессии
if [ ! -f "vipalina_session.session" ]; then
    echo "⚠️  ВНИМАНИЕ: Сессия Telethon не найдена!"
    echo "   При первом запуске потребуется авторизация"
    echo ""
fi

echo "================================================"
echo "  Запуск VIP Automation System..."
echo "================================================"
echo ""
echo "Мониторинг чата: -1001755644531"
echo "Количество менеджеров: 8"
echo ""
echo "Новые функции системы:"
echo "  ✅ Мониторинг VIP-чата в реальном времени"
echo "  ✅ Реакция на новых студентов сразу при их появлении"
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
echo "Для остановки используйте: ./stop_vipalina.sh"
echo ""
echo "------------------------------------------------"
echo ""

# Запускаем систему в фоне с логированием
nohup python3 vip_automation_main.py > vipalina_logs/vip_automation.log 2>&1 &

# Сохраняем PID процесса
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
    echo "✅ VIP Automation System успешно запущена в фоне!"
else
    echo "❌ Ошибка запуска. Проверьте логи:"
    tail -10 vipalina_logs/vip_automation.log
fi

echo ""
echo "================================================"