#!/usr/bin/env python3
"""
Тест поиска студента по ID в KPI Ultra при /activate
"""

import asyncio
import sys
from report_generator import get_report_generator

async def test_student_search():
    """Тестирует поиск студентов по ID"""
    
    test_ids = [
        "483755148",  # ID из предыдущего вопроса
        "489683868",  # Олег Иванов
        "999999999",  # Несуществующий
    ]
    
    print("=" * 60)
    print("ТЕСТ ПОИСКА СТУДЕНТА ПО ID В KPI ULTRA")
    print("=" * 60)
    
    report_gen = get_report_generator()
    
    for test_id in test_ids:
        print(f"\n🔍 Ищу студента: {test_id}")
        print("-" * 60)
        
        student = await report_gen.get_student_by_id(test_id)
        
        if student:
            print(f"✅ НАЙДЕН")
            print(f"   Имя: {student.get('name', 'Н/Д')}")
            print(f"   Курс: {student.get('course', 'Н/Д')}")
            print(f"   Менеджер: {student.get('manager_name', 'Н/Д')}")
            print(f"   Статус: {student.get('status', 'Н/Д')}")
            print(f"   Строка: {student.get('row_idx', 'Н/Д')}")
            print(f"   Chat ID: {student.get('chat_id', 'Н/Д')}")
        else:
            print(f"❌ НЕ НАЙДЕН")
    
    print("\n" + "=" * 60)
    print("ТЕСТ ЗАВЕРШЁН")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_student_search())
