#!/bin/bash

# =====================================================
# Единый скрипт запуска системы VipAlina
# Запускает оба бота одновременно через main.py
# =====================================================

echo "=================================================="
echo "  VipAlina System - Запуск всех компонентов"
echo "=================================================="
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции логирования
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ОШИБКА]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[ПРЕДУПРЕЖДЕНИЕ]${NC} $1"
}

info() {
    echo -e "${BLUE}[ИНФО]${NC} $1"
}

# Переходим в директорию скрипта
cd "$(dirname "$0")"

# 1. Проверка наличия необходимых файлов
log "Проверка конфигурации..."

if [ ! -f "config.py" ]; then
    error "Файл config.py не найден!"
    exit 1
fi

if [ ! -f ".env" ]; then
    error "Файл .env не найден! Создайте из .env.example"
    exit 1
fi

if [ ! -f "vipalina_google_credentials.json" ]; then
    warning "Файл vipalina_google_credentials.json не найден!"
    warning "Google Sheets интеграция может не работать"
fi

echo "✅ Конфигурация найдена"
echo ""

# 2. Проверка Python
if ! command -v python3 &> /dev/null; then
    error "Python 3 не установлен!"
    exit 1
fi

log "Python версия: $(python3 --version)"
echo ""

# 3. Проверка и установка зависимостей
log "Проверка зависимостей..."
pip3 install -r requirements.txt --quiet

echo "✅ Все зависимости установлены"
echo ""

# 4. Создание необходимых директорий
log "Создание директорий..."
mkdir -p vipalina_logs
mkdir -p vipalina_history
mkdir -p vipalina_processed_courses
echo "✅ Директории готовы"
echo ""

# 5. Проверка запущенных процессов
log "Проверка запущенных процессов..."
EXISTING=$(ps aux | grep "[p]ython.*main.py\|[p]ython.*vip_automation_main.py\|[p]ython.*vipalina_bot.py" || true)

if [ -n "$EXISTING" ]; then
    warning "Обнаружены уже запущенные процессы бота!"
    echo "$EXISTING"
    read -p "Остановить существующие процессы? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "Останавливаем существующие процессы..."
        ./stop_vipalina.sh
        sleep 3
    else
        error "Невозможно запустить, пока работают другие экземпляры"
        exit 1
    fi
fi

# 6. Запуск системы
echo "=================================================="
echo "  Запуск VipAlina System..."
echo "=================================================="
echo ""
echo "Запускается:"
echo "  ✅ Telethon UserClient (токен: 8412841722...)"
echo "  ✅ @Vipalina_zerocoder_bot (токен: 8464962139...)"
echo "  ✅ System Monitor"
echo "  ✅ State Manager"
echo ""
echo "Функции:"
echo "  • Онбординг новых студентов"
echo "  • Мониторинг VIP-чата"
echo "  • Распределение студентов между менеджерами"
echo "  • Создание учебных чатов"
echo "  • Интеграция с Google Sheets, Airtable, KPI"
echo "  • Ответы на вопросы студентов"
echo ""
echo "Для остановки используйте: ./stop_vipalina.sh"
echo ""
echo "------------------------------------------------"
echo ""

# Запуск в фоне с логированием
nohup python3 main.py > vipalina_logs/system.log 2>&1 &

# Сохраняем PID
PID=$!
echo $PID > vipalina_logs/system.pid

log "✅ Система запущена в фоне с PID: $PID"
log "✅ Логи записываются в vipalina_logs/system.log"
log "✅ PID сохранен в vipalina_logs/system.pid"
echo ""

# Проверяем что система запустилась
sleep 3
echo "Проверка статуса запуска..."
PROCESS=$(ps -p $PID -o pid= 2>/dev/null)

if [ -n "$PROCESS" ]; then
    log "✅ VipAlina System успешно запущена!"
    echo ""
    echo "Просмотр логов в реальном времени:"
    echo "  tail -f vipalina_logs/system.log"
    echo ""
    echo "Остановка системы:"
    echo "  ./stop_vipalina.sh"
    echo "  или"
    echo "  kill -TERM $PID"
else
    error "❌ Ошибка запуска. Проверьте логи:"
    tail -20 vipalina_logs/system.log
fi

echo ""
echo "=================================================="
