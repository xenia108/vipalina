#!/bin/bash

echo "=== Остановка Vipalina Telegram бота ==="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# 1. Ищем ВСЕ процессы Python с vip_automation_main.py (включая nohup, screen, и прямые запуски)
log "Ищем процессы Python с vip_automation_main.py..."
# Используем более широкий паттерн для поиска всех процессов
PYTHON_PIDS=$(ps aux | grep -E "[Pp]ython.*vip_automation_main\.py|vip_automation_main\.py" | grep -v grep | awk '{print $2}')

if [ -n "$PYTHON_PIDS" ]; then
    log "Найдены процессы Python: $PYTHON_PIDS"
    for PID in $PYTHON_PIDS; do
        log "Останавливаю процесс $PID gracefully (SIGTERM)..."
        kill -TERM $PID 2>/dev/null
        
        # Ждём 5 секунд для graceful shutdown
        for i in {1..5}; do
            sleep 1
            if ! kill -0 $PID 2>/dev/null; then
                log "✅ Процесс $PID корректно остановлен"
                break
            fi
            echo -n "."
        done
        echo
        
        # Если процесс всё ещё жив - принудительное завершение
        if kill -0 $PID 2>/dev/null; then
            warning "Процесс $PID не завершился gracefully, принудительная остановка (SIGKILL)..."
            kill -KILL $PID 2>/dev/null
            sleep 1
            
            if ! kill -0 $PID 2>/dev/null; then
                log "✅ Процесс $PID принудительно остановлен"
            else
                error "❌ Не удалось остановить процесс $PID"
            fi
        fi
    done
else
    log "Процессы Python с vip_automation_main.py не найдены"
fi

# 2. Проверяем screen сессии
log "Проверяем screen сессии..."
SCREEN_SESSION=$(screen -ls | grep "vipalina_bot" || true)
if [ -n "$SCREEN_SESSION" ]; then
    log "Найдена screen сессия vipalina_bot, останавливаю..."
    screen -X -S vipalina_bot quit 2>/dev/null
    log "✅ Screen сессия остановлена"
else
    log "Screen сессия vipalina_bot не найдена"
fi

# 3. Удаляем PID файлы
log "Удаляю PID файлы..."
rm -f vipalina_logs/vip_automation.pid 2>/dev/null
rm -f vipalina_logs/system.pid 2>/dev/null
log "✅ PID файлы удалены"

# 4. Финальная проверка и ПРИНУДИТЕЛЬНОЕ убийство оставшихся процессов
log "Финальная проверка..."
REMAINING=$(ps aux | grep -E "[Pp]ython.*vip_automation_main\.py|vip_automation_main\.py" | grep -v grep || true)
if [ -n "$REMAINING" ]; then
    warning "⚠️ Обнаружены оставшиеся процессы - убиваю ПРИНУДИТЕЛЬНО:"
    echo "$REMAINING"
    PIDS=$(echo "$REMAINING" | awk '{print $2}')
    for PID in $PIDS; do
        kill -9 $PID 2>/dev/null
        log "🔪 Убит процесс $PID (kill -9)"
    done
    sleep 1
    # Проверка после убийства
    STILL_REMAINING=$(ps aux | grep -E "[Pp]ython.*vip_automation_main\.py|vip_automation_main\.py" | grep -v grep || true)
    if [ -n "$STILL_REMAINING" ]; then
        error "❌ НЕ УДАЛОСЬ УБИТЬ ПРОЦЕССЫ:"
        echo "$STILL_REMAINING"
    else
        log "✅ Все оставшиеся процессы успешно убиты!"
    fi
else
    log "✅ Все процессы бота успешно остановлены!"
fi

echo
log "=== Бот остановлен ==="