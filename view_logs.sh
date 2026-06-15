#!/bin/bash

# Скрипт для просмотра логов VIP Automation System
# Usage: ./view_logs.sh [опции]

echo "================================================"
echo "  Просмотр логов VIP Automation System"
echo "================================================"
echo ""

# Переходим в директорию проекта
cd "$(dirname "$0")"

# Проверяем наличие директории логов
if [ ! -d "vipalina_logs" ]; then
    echo "❌ Директория логов не найдена!"
    exit 1
fi

# Проверяем наличие логов
if [ ! -f "vipalina_logs/vip_automation.log" ]; then
    echo "❌ Файл логов не найден!"
    echo "Возможно, система еще не запущена."
    exit 1
fi

# Определяем опции
FOLLOW=false
LINES=50

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -n|--lines)
            LINES="$2"
            shift 2
            ;;
        -h|--help)
            echo "Использование: $0 [опции]"
            echo ""
            echo "Опции:"
            echo "  -f, --follow    Непрерывный просмотр логов (tail -f)"
            echo "  -n, --lines N   Количество строк для отображения (по умолчанию 50)"
            echo "  -h, --help      Показать эту справку"
            echo ""
            exit 0
            ;;
        *)
            echo "Неизвестная опция: $1"
            echo "Используйте -h для получения справки"
            exit 1
            ;;
    esac
done

echo "Файл логов: vipalina_logs/vip_automation.log"
echo "------------------------------------------------"

if [ "$FOLLOW" = true ]; then
    echo "Непрерывный просмотр логов (Ctrl+C для остановки):"
    echo "------------------------------------------------"
    tail -n $LINES -f vipalina_logs/vip_automation.log
else
    echo "Последние $LINES строк логов:"
    echo "------------------------------------------------"
    tail -n $LINES vipalina_logs/vip_automation.log
fi

echo ""
echo "================================================"