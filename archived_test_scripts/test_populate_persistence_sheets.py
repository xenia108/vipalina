#!/usr/bin/env python3
"""
Скрипт для заполнения тестовыми данными листов Active_SLA_Requests,
Onboarding_Progress и Student_Messages в таблице "Логи Випалина".

Используется для тестирования и проверки работоспособности системы логирования.
"""

import logging
from datetime import datetime, timedelta
from vipalina_persistence import get_persistence
import json

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('test_populate')


def create_test_sla_requests(persistence):
    """Создает тестовые SLA-запросы"""
    logger.info("\n📋 Создание тестовых SLA-запросов...")
    
    test_requests = [
        {
            'chat_id': -1001234567890,
            'student_id': 123456789,
            'request_data': {
                'student_name': 'Иван Тестовый',
                'request_text': 'Добрый день! Подскажите, когда будет следующий созвон?',
                'request_time': datetime.now() - timedelta(minutes=5),
                'is_working_hours': True
            }
        },
        {
            'chat_id': -1001234567891,
            'student_id': 987654321,
            'request_data': {
                'student_name': 'Мария Петрова',
                'request_text': 'У меня вопрос по домашнему заданию в уроке 3.2',
                'request_time': datetime.now() - timedelta(minutes=12),
                'is_working_hours': True
            }
        },
        {
            'chat_id': -1001234567892,
            'student_id': 555666777,
            'request_data': {
                'student_name': 'Александр Сидоров',
                'request_text': 'Не могу войти в личный кабинет GetCourse',
                'request_time': datetime.now() - timedelta(hours=1),
                'is_working_hours': False
            }
        }
    ]
    
    created_count = 0
    for req in test_requests:
        try:
            result = persistence.save_sla_request(
                chat_id=req['chat_id'],
                student_id=req['student_id'],
                request_data=req['request_data']
            )
            if result:
                created_count += 1
                logger.info(f"   ✅ Создан SLA-запрос от {req['request_data']['student_name']}")
            else:
                logger.error(f"   ❌ Не удалось создать SLA-запрос от {req['request_data']['student_name']}")
        except Exception as e:
            logger.error(f"   ❌ Ошибка при создании SLA-запроса: {e}")
    
    logger.info(f"\n📊 Создано {created_count} из {len(test_requests)} SLA-запросов")
    return created_count


def create_test_onboarding_progress(persistence):
    """Создает тестовые записи онбординга"""
    logger.info("\n🎓 Создание тестовых записей онбординга...")
    
    test_onboardings = [
        {
            'getcourse_id': 'TEST_ONBOARD_001',
            'progress_data': {
                'student_name': 'Елена Новикова',
                'manager_name': 'Лиза Виноградова',
                'telegram_id': 111222333,
                'telegram_username': '@elena_novikova',
                'start_time': datetime.now() - timedelta(minutes=3),
                'message_id': 12345,
                'steps': {
                    'chat_creation': {'status': 'success', 'details': 'Чат создан', 'error': ''},
                    'welcome_message': {'status': 'success', 'details': 'Приветствие отправлено', 'error': ''},
                    'airtable': {'status': 'success', 'details': 'Добавлен в Airtable', 'error': ''},
                    'kpi_sheets': {'status': 'in_progress', 'details': 'Добавление в KPI Ultra...', 'error': ''},
                    'tracker_creation': {'status': 'pending', 'details': '', 'error': ''}
                },
                'overall_status': 'in_progress',
                'errors': []
            }
        },
        {
            'getcourse_id': 'TEST_ONBOARD_002',
            'progress_data': {
                'student_name': 'Дмитрий Козлов',
                'manager_name': 'Юля Колганова',
                'telegram_id': 444555666,
                'telegram_username': '@dmitry_kozlov',
                'start_time': datetime.now() - timedelta(minutes=10),
                'message_id': 12346,
                'steps': {
                    'chat_creation': {'status': 'success', 'details': 'Чат создан', 'error': ''},
                    'welcome_message': {'status': 'error', 'details': '', 'error': 'Студент запретил добавление в группы'},
                    'airtable': {'status': 'pending', 'details': '', 'error': ''},
                    'kpi_sheets': {'status': 'pending', 'details': '', 'error': ''},
                    'tracker_creation': {'status': 'pending', 'details': '', 'error': ''}
                },
                'overall_status': 'failed',
                'errors': [
                    {'step': 'welcome_message', 'error': 'UserPrivacyRestrictedError: Студент запретил добавление в группы'}
                ]
            }
        }
    ]
    
    created_count = 0
    for onb in test_onboardings:
        try:
            result = persistence.save_onboarding_progress(
                getcourse_id=onb['getcourse_id'],
                progress_data=onb['progress_data']
            )
            if result:
                created_count += 1
                status = onb['progress_data']['overall_status']
                logger.info(f"   ✅ Создан онбординг для {onb['progress_data']['student_name']} (статус: {status})")
            else:
                logger.error(f"   ❌ Не удалось создать онбординг для {onb['progress_data']['student_name']}")
        except Exception as e:
            logger.error(f"   ❌ Ошибка при создании онбординга: {e}")
    
    logger.info(f"\n📊 Создано {created_count} из {len(test_onboardings)} онбордингов")
    return created_count


def create_test_student_messages(persistence):
    """Создает тестовые сообщения студентов"""
    logger.info("\n💬 Создание тестовых сообщений студентов...")
    
    test_messages = [
        {
            'chat_id': -1001234567890,
            'student_id': 123456789,
            'getcourse_id': 'TEST_STUDENT_001',
            'student_name': 'Иван Тестовый',
            'manager_name': 'Лиза Виноградова',
            'message_text': 'Здравствуйте! Начал изучать первый урок, всё очень интересно!',
            'message_type': 'text',
            'course': 'Чат-боты, VIP'
        },
        {
            'chat_id': -1001234567891,
            'student_id': 987654321,
            'getcourse_id': 'TEST_STUDENT_002',
            'student_name': 'Мария Петрова',
            'manager_name': 'Юля Колганова',
            'message_text': 'Прикрепляю скриншот ошибки, которая возникла при выполнении ДЗ',
            'message_type': 'photo',
            'course': 'Python-разработчик, VIP'
        },
        {
            'chat_id': -1001234567892,
            'student_id': 555666777,
            'getcourse_id': 'TEST_STUDENT_003',
            'student_name': 'Александр Сидоров',
            'manager_name': 'Лиза Виноградова',
            'message_text': 'Завершил урок 2.3, когда можно созвониться для разбора?',
            'message_type': 'text',
            'course': 'Веб-разработка, VIP'
        },
        {
            'chat_id': -1001234567890,
            'student_id': 123456789,
            'getcourse_id': 'TEST_STUDENT_001',
            'student_name': 'Иван Тестовый',
            'manager_name': 'Лиза Виноградова',
            'message_text': 'Отправляю выполненное домашнее задание по уроку 1.1',
            'message_type': 'document',
            'course': 'Чат-боты, VIP'
        },
        {
            'chat_id': -1001234567893,
            'student_id': 777888999,
            'getcourse_id': 'TEST_STUDENT_004',
            'student_name': 'Ольга Смирнова',
            'manager_name': 'Юля Колганова',
            'message_text': 'Не получается настроить окружение, записал голосовое сообщение с описанием проблемы',
            'message_type': 'voice',
            'course': 'Python-разработчик, VIP'
        }
    ]
    
    created_count = 0
    for msg in test_messages:
        try:
            result = persistence.save_student_message(
                chat_id=msg['chat_id'],
                student_id=msg['student_id'],
                getcourse_id=msg['getcourse_id'],
                student_name=msg['student_name'],
                manager_name=msg['manager_name'],
                message_text=msg['message_text'],
                message_type=msg['message_type'],
                course=msg['course']
            )
            if result:
                created_count += 1
                msg_preview = msg['message_text'][:50] + "..." if len(msg['message_text']) > 50 else msg['message_text']
                logger.info(f"   ✅ Создано сообщение от {msg['student_name']}: {msg_preview}")
            else:
                logger.error(f"   ❌ Не удалось создать сообщение от {msg['student_name']}")
        except Exception as e:
            logger.error(f"   ❌ Ошибка при создании сообщения: {e}")
    
    logger.info(f"\n📊 Создано {created_count} из {len(test_messages)} сообщений")
    return created_count


def main():
    """Главная функция"""
    logger.info("=" * 80)
    logger.info("🧪 ЗАПОЛНЕНИЕ ТЕСТОВЫМИ ДАННЫМИ ЛИСТОВ ПЕРСИСТЕНЦИИ")
    logger.info("=" * 80)
    
    # Получаем экземпляр persistence
    try:
        persistence = get_persistence()
        
        if not persistence or not persistence.is_initialized():
            logger.error("❌ ОШИБКА: Модуль персистенции не инициализирован!")
            logger.error("   Проверьте:")
            logger.error("   1. Файл vipalina_google_service_account.json существует")
            logger.error("   2. Сервисный аккаунт имеет доступ к таблице")
            logger.error("   3. ID таблицы правильный в config.py")
            return 1
        
        logger.info("✅ Модуль персистенции инициализирован успешно\n")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при инициализации: {e}")
        return 1
    
    # Создаем тестовые данные
    try:
        total_created = 0
        
        # 1. SLA-запросы
        total_created += create_test_sla_requests(persistence)
        
        # 2. Онбординги
        total_created += create_test_onboarding_progress(persistence)
        
        # 3. Сообщения студентов
        total_created += create_test_student_messages(persistence)
        
        # Итого
        logger.info("\n" + "=" * 80)
        logger.info(f"✅ ЗАПОЛНЕНИЕ ЗАВЕРШЕНО")
        logger.info(f"   Всего создано записей: {total_created}")
        logger.info("=" * 80)
        
        logger.info("\n📋 Проверьте таблицу:")
        logger.info("   https://docs.google.com/spreadsheets/d/1wWbgAq92qehpTO0lm4AQJzTQ8RvpA9fX_vORYBqkHCE")
        logger.info("\n   Листы для проверки:")
        logger.info("   • Active_SLA_Requests - должно быть 3 записи")
        logger.info("   • Onboarding_Progress - должно быть 2 записи")
        logger.info("   • Student_Messages - должно быть 5 записей")
        
        return 0
        
    except Exception as e:
        logger.error(f"\n❌ Ошибка при создании тестовых данных: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
