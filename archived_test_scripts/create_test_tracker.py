#!/usr/bin/env python3
"""
Скрипт для создания тестового трекера.
"""

import sys
import logging
from tracker_creator import create_student_tracker

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def create_test_tracker(course_tag):
    """
    Создает тестовый трекер для указанного курса.
    
    Args:
        course_tag (str): Тег курса из GetCourse
    """
    try:
        print(f"🚀 Создание тестового трекера для курса: {course_tag}")
        
        result = create_student_tracker(
            student_name="Тестовый Студент",
            course_tag=course_tag,
            manager_name="Лиза Виноградова",
            getcourse_id="TEST12345"
        )
        
        print("\n" + "="*60)
        print("✅ ТЕСТОВЫЙ ТРЕКЕР УСПЕШНО СОЗДАН!")
        print("="*60)
        print(f"\n📊 URL: {result['url']}")
        print(f"Идентификатор: {result['spreadsheet_id']}")
        print(f"Название: {result['title']}")
        print("\n" + "="*60 + "\n")
        
        return result
        
    except Exception as e:
        print(f"\n❌ Ошибка при создании тестового трекера: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Использование: python3 create_test_tracker.py \"[название курса] Тариф VIP\"")
        sys.exit(1)
    
    course_tag = sys.argv[1]
    create_test_tracker(course_tag)