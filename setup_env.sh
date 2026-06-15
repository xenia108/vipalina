#!/bin/bash

echo "=== Настройка виртуального окружения для Vipalina ==="

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

# Проверяем, установлен ли Python
if ! command -v python3 &> /dev/null; then
    error "Python 3 не найден. Пожалуйста, установите Python 3."
    exit 1
fi

# Проверяем, установлен ли pip
if ! command -v pip3 &> /dev/null; then
    warning "pip3 не найден. Устанавливаем..."
    python3 -m ensurepip --upgrade
fi

# Создаем виртуальное окружение
log "Создаем виртуальное окружение..."
python3 -m venv vipalina_env

if [ $? -ne 0 ]; then
    error "Не удалось создать виртуальное окружение"
    exit 1
fi

# Активируем виртуальное окружение
log "Активируем виртуальное окружение..."
source vipalina_env/bin/activate

if [ $? -ne 0 ]; then
    error "Не удалось активировать виртуальное окружение"
    exit 1
fi

# Обновляем pip
log "Обновляем pip..."
pip install --upgrade pip

# Устанавливаем зависимости
log "Устанавливаем зависимости..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    error "Не удалось установить зависимости"
    exit 1
fi

# Проверяем установку
log "Проверяем установку основных пакетов..."
python -c "import telebot; print('pyTelegramBotAPI: OK')"
python -c "import openai; print('OpenAI: OK')"
python -c "import gspread; print('gspread: OK')"

log "Виртуальное окружение успешно настроено!"

echo
info "Для активации виртуального окружения в будущем используйте:"
echo "  source vipalina_env/bin/activate"
echo
info "Для деактивации виртуального окружения используйте:"
echo "  deactivate"
echo
info "Для запуска бота после активации окружения:"
echo "  python vipalina_bot.py"