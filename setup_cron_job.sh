#!/bin/bash

# Скрипт для установки cron-задачи для проверки срока действия токена OAuth

echo "🔧 Установка cron-задачи для проверки срока действия токена OAuth..."

# Получаем абсолютный путь к директории проекта
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Создаем временный файл для crontab
CRON_TEMP=$(mktemp)

# Получаем текущий crontab
crontab -l > "$CRON_TEMP" 2>/dev/null || true

# Проверяем, существует ли уже задача
if grep -q "check_token_expiry.py" "$CRON_TEMP"; then
    echo "⚠️ Задача уже существует в crontab"
else
    # Добавляем задачу на ежедневный запуск в 9:00 утра
    echo "0 9 * * * cd $PROJECT_DIR && python3 check_token_expiry.py >> $PROJECT_DIR/vipalina_logs/token_check.log 2>&1" >> "$CRON_TEMP"
    echo "✅ Задача добавлена: ежедневная проверка токена в 9:00"
fi

# Устанавливаем обновленный crontab
crontab "$CRON_TEMP"

# Удаляем временный файл
rm "$CRON_TEMP"

echo "✅ Cron-задача успешно установлена"

# Показываем текущие задачи
echo ""
echo "📅 Текущие cron-задачи:"
crontab -l