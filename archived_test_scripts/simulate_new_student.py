#!/usr/bin/env python3
"""
Скрипт для ПОЛНОГО тестирования онбординга нового студента.
Выполняет реальную интеграцию со всеми таблицами:
- Создание трекера
- Добавление в KPI Ultra (лист 'Випалина')
- Добавление в Airtable
- Сохранение в модуле персистенции
"""

import asyncio
import logging
from datetime import datetime
from tracker_creator import create_student_tracker
from course_config_v2 import CourseConfig
from vipalina_kpi_sheets import VipalinaKPISheetsIntegration
from vipalina_airtable import VipalinaAirtableIntegration
from vipalina_persistence import VipalinaPersistence
from config import VIP_MANAGERS_VIP, AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def simulate_new_student_onboarding():
    """
    Полное тестирование онбординга нового студента:
    1. Создание трекера
    2. Добавление в KPI Ultra
    3. Добавление в Airtable
    4. Сохранение в модуле персистенции
    5. Проверка всех интеграций
    """
    
    print("=" * 80)
    print("ПОЛНОЕ ТЕСТИРОВАНИЕ ОНБОРДИНГА НОВОГО СТУДЕНТА")
    print("=" * 80)
    print()
    
    # Тестовые данные студента
    test_student = {
        'name': 'Тестовый Студент',
        'getcourse_id': f'TEST{datetime.now().strftime("%Y%m%d%H%M%S")}',
        'course_tag': '[chatbot] Тариф VIP',
        'manager_name': 'Лиза Виноградова',
        'telegram_id': 999999999,
        'telegram_username': 'test_student',
        'phone': '+79999999999',
        'email': 'test@example.com',
        'chat_id': -1001234567890  # Тестовый ID чата
    }
    
    # Находим ID менеджера
    manager_id = None
    for manager in VIP_MANAGERS_VIP:
        if manager['name'] == test_student['manager_name']:
            manager_id = manager['telegram_id']
            break
    
    if not manager_id:
        manager_id = VIP_MANAGERS_VIP[0]['telegram_id']  # Первый из списка
        test_student['manager_name'] = VIP_MANAGERS_VIP[0]['name']
    
    print(f"👤 Студент: {test_student['name']}")
    print(f"🆔 GetCourse ID: {test_student['getcourse_id']}")
    print(f"📚 Курс: {test_student['course_tag']}")
    print(f"👨‍💼 Менеджер: {test_student['manager_name']} (ID: {manager_id})")
    print()
    
    # Шаг 1: Получаем информацию о курсе
    print("📋 Шаг 1: Получение информации о курсе...")
    course_params = CourseConfig.get_course_params(test_student['course_tag'])
    tracker_name = CourseConfig.get_tracker_course_name(test_student['course_tag'])
    
    print(f"   ✅ Курс найден: {tracker_name}")
    print(f"   📊 Уроков: {course_params['lesson_count']}")
    print(f"   ⏰ Доступ: {course_params['access_days']} дней")
    print(f"   💎 VIP поддержка: {course_params['vip_support_days']} дней")
    print()
    
    # Шаг 2: Создание трекера
    print("📝 Шаг 2: Создание персонального трекера студента...")
    tracker_url = "Не создан"
    tracker_id = ""
    
    try:
        result = create_student_tracker(
            student_name=test_student['name'],
            course_tag=test_student['course_tag'],
            manager_name=test_student['manager_name'],
            getcourse_id=test_student['getcourse_id']
        )
        
        print(f"   ✅ Трекер создан успешно!")
        print(f"   🔗 URL: {result['url']}")
        print(f"   🆔 ID: {result['spreadsheet_id']}")
        print()
        
        tracker_url = result['url']
        tracker_id = result['spreadsheet_id']
        
    except Exception as e:
        print(f"   ❌ Ошибка при создании трекера: {e}")
        print()
        return
    
    # Шаг 3: Добавление в KPI Ultra (лист 'Випалина')
    print("📊 Шаг 3: Добавление в KPI Ultra (лист 'Випалина')...")
    kpi_success = False
    
    try:
        kpi_integration = VipalinaKPISheetsIntegration()
        
        student_data_for_kpi = {
            'getcourse_id': test_student['getcourse_id'],
            'getcourse_url': f"https://university.zerocoder.ru/user/control/user/update/id/{test_student['getcourse_id']}",
            'name': test_student['name'],
            'course': tracker_name,
            'airtable_url': '-',
            'manager_name': test_student['manager_name'],
            'telegram_id': test_student['telegram_id']
        }
        
        kpi_success = await kpi_integration.add_student_to_kpi_sheet(
            student_data=student_data_for_kpi,
            invite_link="-"
        )
        
        if kpi_success:
            print(f"   ✅ Студент добавлен в лист 'Випалина' KPI Ultra")
        else:
            print(f"   ⚠️ Студент не добавлен в KPI Ultra (возможно, уже существует)")
        print()
        
    except Exception as e:
        print(f"   ❌ Ошибка при добавлении в KPI Ultra: {e}")
        print()
    
    # Шаг 4: Добавление в Airtable
    print("📇 Шаг 4: Добавление в Airtable...")
    airtable_success = False
    
    try:
        airtable_integration = VipalinaAirtableIntegration(
            api_key=AIRTABLE_API_KEY,
            base_id=AIRTABLE_BASE_ID,
            table_id=AIRTABLE_TABLE_ID
        )
        
        # Пытаемся найти студента и обновить менеджера
        existing_record = await airtable_integration.find_student_by_getcourse_id(
            test_student['getcourse_id']
        )
        
        if existing_record:
            update_success = await airtable_integration.update_manager_field(
                record_id=existing_record['id'],
                manager_name=test_student['manager_name']
            )
            if update_success:
                print(f"   ✅ Студент найден в Airtable, менеджер обновлён")
                print(f"   🆔 Airtable Record ID: {existing_record['id']}")
                airtable_success = True
            else:
                print(f"   ⚠️ Студент найден, но не удалось обновить менеджера")
        else:
            print(f"   ⚠️ Студент не найден в Airtable (запись должна быть создана заранее)")
        print()
        
    except Exception as e:
        print(f"   ❌ Ошибка при работе с Airtable: {e}")
        print()
    
    # Шаг 5: Сохранение в модуле персистенции
    print("💾 Шаг 5: Сохранение в модуле персистенции...")
    persistence_success = False
    
    try:
        persistence = VipalinaPersistence()
        init_success = persistence.initialize()
        
        if init_success and persistence.is_initialized():
            # Chat_To_Student
            persistence.save_chat_to_student_mapping(
                chat_id=test_student['chat_id'],
                getcourse_id=test_student['getcourse_id'],
                student_name=test_student['name'],
                invite_link="-"
            )
            print(f"   ✅ Сохранён маппинг чата (Chat_To_Student)")
            
            # Students_Data
            persistence.save_student_data(
                getcourse_id=test_student['getcourse_id'],
                student_data={
                    'name': test_student['name'],
                    'telegram_id': test_student['telegram_id'],
                    'telegram_username': test_student['telegram_username'],
                    'getcourse_id': test_student['getcourse_id'],
                    'course': tracker_name,
                    'email': test_student['email'],
                    'phone': test_student['phone']
                }
            )
            print(f"   ✅ Сохранены данные студента (Students_Data)")
            
            # Manager_Assignments
            persistence.save_manager_assignment(
                getcourse_id=test_student['getcourse_id'],
                assignment_data={
                    'manager_id': manager_id,
                    'manager_name': test_student['manager_name'],
                    'course_tag': test_student['course_tag'],
                    'status': 'active',
                    'student_name': test_student['name'],
                    'student_telegram': test_student['telegram_username'],
                    'student_telegram_id': test_student['telegram_id']
                }
            )
            print(f"   ✅ Сохранено назначение менеджера (Manager_Assignments)")
            
            # System_Events (опционально)
            try:
                if hasattr(persistence, 'log_system_event'):
                    persistence.log_system_event(
                        event_type="test_student_onboarding",
                        description=f"Тестовый онбординг студента {test_student['getcourse_id']}",
                        data={
                            'chat_id': test_student['chat_id'],
                            'getcourse_id': test_student['getcourse_id'],
                            'student_name': test_student['name'],
                            'manager_id': manager_id,
                            'manager_name': test_student['manager_name'],
                            'tracker_url': tracker_url
                        }
                    )
                    print(f"   ✅ Записано событие в лог (System_Events)")
            except Exception as log_error:
                print(f"   ⚠️ Не удалось записать событие в лог: {log_error}")
            
            persistence_success = True
        else:
            print(f"   ⚠️ Модуль персистенции не инициализирован")
        print()
        
    except Exception as e:
        print(f"   ❌ Ошибка при сохранении в персистенцию: {e}")
        print()
    
    # Итоги
    print("=" * 80)
    print("✅ ПОЛНОЕ ТЕСТИРОВАНИЕ ОНБОРДИНГА ЗАВЕРШЕНО!")
    print("=" * 80)
    print()
    print("📋 Итоговая информация:")
    print(f"   👤 Студент: {test_student['name']}")
    print(f"   🆔 GetCourse ID: {test_student['getcourse_id']}")
    print(f"   📚 Курс: {tracker_name}")
    print(f"   👨‍💼 Менеджер: {test_student['manager_name']}")
    print(f"   🔗 Трекер: {tracker_url}")
    print()
    print("📊 Статус интеграций:")
    print(f"   {'✅' if tracker_url != 'Не создан' else '❌'} Трекер Google Sheets")
    print(f"   {'✅' if kpi_success else '❌'} KPI Ultra (лист 'Випалина')")
    print(f"   {'✅' if airtable_success else '❌'} Airtable")
    print(f"   {'✅' if persistence_success else '❌'} Модуль персистенции")
    print()
    
    if all([tracker_url != "Не создан", kpi_success, airtable_success, persistence_success]):
        print("🎉 ВСЕ ИНТЕГРАЦИИ УСПЕШНЫ! Студент полностью в системе! 🎓")
    else:
        print("⚠️ Некоторые интеграции не выполнены. Проверьте логи выше.")
    print()


if __name__ == "__main__":
    asyncio.run(simulate_new_student_onboarding())
