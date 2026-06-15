#!/usr/bin/env python3
"""
Тестовый скрипт для проверки правильности подтягивания TEMPLATE_TARIFF_TRACKER_ID
"""

import os
from dotenv import load_dotenv
from tracker_creator import TrackerCreator

def test_env_variable():
    """Проверка переменной окружения"""
    print("Проверка переменной окружения TEMPLATE_TARIFF_TRACKER_ID")
    print("=" * 60)
    
    # Загружаем переменные окружения
    load_dotenv()
    
    # Проверяем переменную окружения
    tariff_id = os.getenv('TEMPLATE_TARIFF_TRACKER_ID')
    print(f"Значение из .env файла: {tariff_id}")
    
    # Проверяем значение по умолчанию в классе
    creator = TrackerCreator()
    print(f"Значение в TrackerCreator.TEMPLATE_TARIFF_ID: {creator.TEMPLATE_TARIFF_ID}")
    
    # Сравниваем значения
    if tariff_id == creator.TEMPLATE_TARIFF_ID:
        print("✅ Переменная подтягивается правильно")
    else:
        print("❌ Переменная подтягивается неправильно")
    
    print()

def test_template_selection():
    """Проверка выбора шаблона в зависимости от типа программы"""
    print("Проверка выбора шаблона")
    print("=" * 60)
    
    creator = TrackerCreator()
    print(f"Шаблон для обычных курсов: {creator.TEMPLATE_ID}")
    print(f"Шаблон для тарифов: {creator.TEMPLATE_TARIFF_ID}")
    
    # Проверим несколько примеров курсов
    test_cases = [
        ("[python-ai-2.0] Тариф \"VIP\"", "Обычный курс"),
        ("[club] Тариф VIP", "Абонемент"),
        ("[neuro-3.0][neuro-russian] [neuro-china] Бандл \"VIP\"", "Бандл"),
        ("[luxury] IT-КАРЬЕРА БЕЗ ГРАНИЦ", "Премиум курс")
    ]
    
    from course_config_v2 import CourseConfig
    
    for course_tag, description in test_cases:
        is_tariff = CourseConfig.is_tariff_program(course_tag)
        template_id = creator.TEMPLATE_TARIFF_ID if is_tariff else creator.TEMPLATE_ID
        template_type = "Тариф" if is_tariff else "Обычный курс"
        
        print(f"\nКурс: {course_tag}")
        print(f"  Тип: {description}")
        print(f"  Определен как тариф: {is_tariff}")
        print(f"  Используемый шаблон: {template_type} ({template_id})")

if __name__ == "__main__":
    test_env_variable()
    test_template_selection()