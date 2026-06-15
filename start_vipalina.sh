#!/bin/bash

echo "=== Запуск Vipalina Telegram бота ==="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для логирования
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

# Проверяем что мы в правильной директории
if [ ! -f "vip_automation_main.py" ]; then
    error "Файл vip_automation_main.py не найден в текущей директории!"
    echo "Убедитесь что вы находитесь в директории vipalina/"
    exit 1
fi

# Проверяем что бот уже не запущен
log "Проверяем запущенные процессы..."
EXISTING=$(ps aux | grep "[p]ython.*vip_automation_main.py" || true)
if [ -n "$EXISTING" ]; then
    warning "Обнаружен уже запущенный процесс бота!"
    echo "$EXISTING"
    read -p "Остановить существующий процесс? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ./stop_vipalina.sh
        sleep 3
    else
        error "Невозможно запустить, пока работает другой экземпляр"
        exit 1
    fi
fi

# Создаём директорию для логов если её нет
mkdir -p vipalina_logs

# Обновляем зависимости
log "Обновляем зависимости Python..."
pip install -r requirements.txt --upgrade --quiet

# Выбираем способ запуска
echo
info "Выберите способ запуска:"
echo "1) Запуск в фоне (nohup) - рекомендуется"
echo "2) Запуск в screen сессии"
echo "3) Обычный запуск (с выводом в консоль)"
echo
read -p "Выберите опцию (1-3): " -n 1 -r
echo

case $REPLY in
    1)
        log "Запускаем в фоне с nohup..."
        nohup python3 vip_automation_main.py > vipalina_logs/vipalina.log 2>&1 &
        PID=$!
        echo $PID > vipalina_logs/vip_automation.pid
        log "Бот запущен в фоне с PID: $PID"
        log "Логи записываются в vipalina_logs/vipalina.log"
        log "Для остановки: ./stop_vipalina.sh"
        ;;
    2)
        log "Запускаем в screen сессии..."
        screen -dmS vipalina_bot python3 vip_automation_main.py
        log "Бот запущен в screen сессии 'vipalina_bot'"
        log "Для подключения: screen -r vipalina_bot"
        log "Для отключения без остановки: Ctrl+A, затем D"
        log "Для остановки: ./stop_vipalina.sh"
        ;;
    3)
        log "Запускаем в обычном режиме..."
        warning "Бот остановится при закрытии терминала!"
        log "Для остановки нажмите Ctrl+C"
        echo
        python3 vip_automation_main.py
        ;;
    *)
        error "Неверный выбор. Запускаем в фоновом режиме..."
        nohup python3 vip_automation_main.py > vipalina_logs/vipalina.log 2>&1 &
        PID=$!
        echo $PID > vipalina_logs/vip_automation.pid
        log "Бот запущен в фоне с PID: $PID"
        ;;
esac

# Проверяем что бот запустился
if [ "$REPLY" != "3" ]; then
    sleep 5
    log "Проверяем статус запуска..."
    PROCESS=$(ps aux | grep "[p]ython.*vip_automation_main.py" || true)
    if [ -n "$PROCESS" ]; then
        log "✅ Бот успешно запущен!"
        echo "$PROCESS"
        info "Следите за логами: tail -f vipalina_logs/vipalina.log"
    else
        error "❌ Бот не запустился. Проверьте логи."
        if [ -f "vipalina_logs/vipalina.log" ]; then
            echo "Последние строки лога:"
            tail -20 vipalina_logs/vipalina.log
        fi
    fi
fi

echo
log "=== Запуск завершен ==="