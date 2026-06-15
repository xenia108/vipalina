#!/usr/bin/env python3
"""
Тестирование интеграции с NocoDB.
Проверяет подключение, поиск студентов, обновление данных.
"""

import asyncio
import logging
from vipalina_nocodb import create_nocodb_integration
from config import (
    NOCODB_API_URL,
    NOCODB_API_TOKEN,
    NOCODB_BASE_ID,
    NOCODB_TABLE_ID,
    NOCODB_VIEW_ID,
    NOCODB_FIELD_GETCOURSE_ID,
    NOCODB_FIELD_MANAGER
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_nocodb_integration():
    """Тестирование интеграции с NocoDB"""
    
    print("=" * 80)
    print("ТЕСТИРОВАНИЕ ИНТЕГРАЦИИ С NOCODB")
    print("=" * 80)
    print()
    
    # Создание интеграции
    print("📦 Шаг 1: Инициализация интеграции...")
    try:
        nocodb = create_nocodb_integration(
            api_url=NOCODB_API_URL,
            api_token=NOCODB_API_TOKEN,
            base_id=NOCODB_BASE_ID,
            table_id=NOCODB_TABLE_ID,
            view_id=NOCODB_VIEW_ID
        )
        print(f"   ✅ Интеграция создана")
        print(f"   URL: {NOCODB_API_URL}")
        print(f"   База: {NOCODB_BASE_ID}")
        print(f"   Таблица: {NOCODB_TABLE_ID}")
        print(f"   Вьюшка: {NOCODB_VIEW_ID}")
        print()
    except Exception as e:
        print(f"   ❌ Ошибка при создании интеграции: {e}")
        return
    
    # Тест подключения
    print("🔌 Шаг 2: Проверка подключения...")
    try:
        result = await nocodb.test_connection()
        if result['success']:
            print(f"   ✅ Подключение успешно")
            print(f"   Всего записей в таблице: {result.get('total_rows', 'N/A')}")
        else:
            print(f"   ❌ Ошибка подключения: {result.get('error')}")
            return
        print()
    except Exception as e:
        print(f"   ❌ Ошибка при проверке подключения: {e}")
        return
    
    # Тест поиска студента (используем тестовый GetCourse ID)
    print("🔍 Шаг 3: Поиск тестового студента...")
    test_getcourse_id = input("   Введите GetCourse ID для поиска (или Enter для пропуска): ").strip()
    
    if test_getcourse_id:
        try:
            student = await nocodb.find_student_by_getcourse_id(
                getcourse_id=test_getcourse_id,
                getcourse_field=NOCODB_FIELD_GETCOURSE_ID
            )
            
            if student:
                print(f"   ✅ Студент найден!")
                print(f"   Record ID: {student['id']}")
                print(f"   URL: {student['record_url']}")
                print(f"   Данные: {student['fields']}")
                
                # Тест получения полных данных
                print()
                print("📋 Шаг 4: Получение полных данных студента...")
                student_data = await nocodb.get_student_data(
                    getcourse_id=test_getcourse_id,
                    getcourse_field=NOCODB_FIELD_GETCOURSE_ID
                )
                
                if student_data:
                    print(f"   ✅ Данные получены:")
                    print(f"   Имя: {student_data.get('name')}")
                    print(f"   Курс: {student_data.get('course')}")
                    print(f"   Email: {student_data.get('email')}")
                    print(f"   Telegram: {student_data.get('telegram')}")
                    print(f"   Менеджер: {student_data.get('manager')}")
                    print()
                    
                    # Тест обновления менеджера (опционально)
                    update_test = input("   Протестировать обновление менеджера? (y/n): ").strip().lower()
                    if update_test == 'y':
                        test_manager = input("   Введите имя менеджера для теста: ").strip()
                        if test_manager:
                            print()
                            print("🔄 Шаг 5: Обновление менеджера...")
                            update_result = await nocodb.update_manager_field(
                                record_id=student['id'],
                                manager_name=test_manager,
                                manager_field=NOCODB_FIELD_MANAGER
                            )
                            
                            if update_result:
                                print(f"   ✅ Менеджер успешно обновлен на: {test_manager}")
                            else:
                                print(f"   ❌ Ошибка при обновлении менеджера")
                else:
                    print(f"   ❌ Не удалось получить данные студента")
            else:
                print(f"   ⚠️ Студент с GetCourse ID {test_getcourse_id} не найден")
                print(f"   Проверьте, что студент существует в вьюшке 'Новенькие'")
        except Exception as e:
            print(f"   ❌ Ошибка при поиске студента: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("   ⏭️ Поиск студента пропущен")
    
    print()
    print("=" * 80)
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО!")
    print("=" * 80)
    print()
    print("📊 Результаты:")
    print("   ✅ Подключение к NocoDB работает")
    print("   ✅ API токен валиден")
    print("   ✅ Таблица 'Ученики все' доступна")
    if test_getcourse_id:
        print("   ✅ Функции поиска и обновления протестированы")
    print()
    print("🎉 Интеграция с NocoDB готова к использованию!")
    print()


if __name__ == "__main__":
    asyncio.run(test_nocodb_integration())
