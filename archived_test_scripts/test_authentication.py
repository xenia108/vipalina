#!/usr/bin/env python3
"""
Скрипт для тестирования аутентификации Google API.
Проверяет работоспособность как сервисного аккаунта, так и пользовательского токена.
"""

import os
from tracker_creator import TrackerCreator
from dynamic_course_config import DynamicCourseConfig
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_service_account_auth():
    """Тест аутентификации через сервисный аккаунт."""
    print("=" * 50)
    print("ТЕСТ АУТЕНТИФИКАЦИИ ЧЕРЕЗ СЕРВИСНЫЙ АККАУНТ")
    print("=" * 50)
    
    try:
        # Создаем TrackerCreator с принудительным использованием сервисного аккаунта
        creator = TrackerCreator()
        print(f"✅ TrackerCreator инициализирован")
        print(f"   Режим аутентификации: {creator.auth_mode}")
        
        # Проверяем доступ к Drive API
        about = creator.drive_service.about().get(fields='*').execute()
        print(f"✅ Доступ к Drive API успешен")
        
        # Проверяем доступ к Sheets API
        # Пробуем получить доступ к шаблону
        template = creator.sheets_client.open_by_key(creator.TEMPLATE_ID)
        print(f"✅ Доступ к шаблону успешен: {template.title}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка аутентификации через сервисный аккаунт: {e}")
        return False

def test_user_oauth_auth():
    """Тест аутентификации через пользовательский OAuth токен."""
    print("=" * 50)
    print("ТЕСТ АУТЕНТИФИКАЦИИ ЧЕРЕЗ ПОЛЬЗОВАТЕЛЬСКИЙ OAUTH ТОКЕН")
    print("=" * 50)
    
    try:
        # Проверяем наличие токена
        if not os.path.exists('token_vipzerocoder.json'):
            print("⚠️ Файл токена не найден")
            return False
            
        # Создаем TrackerCreator (он автоматически попытается использовать токен)
        creator = TrackerCreator()
        print(f"✅ TrackerCreator инициализирован")
        print(f"   Режим аутентификации: {creator.auth_mode}")
        
        if creator.auth_mode == 'user_oauth':
            # Проверяем доступ к Drive API
            about = creator.drive_service.about().get(fields='*').execute()
            user_email = about.get('user', {}).get('emailAddress', 'Неизвестно')
            print(f"✅ Доступ к Drive API успешен")
            print(f"   Аккаунт: {user_email}")
            
            # Проверяем доступ к Sheets API
            template = creator.sheets_client.open_by_key(creator.TEMPLATE_ID)
            print(f"✅ Доступ к шаблону успешен: {template.title}")
            
            return True
        else:
            print("⚠️ Пользовательская аутентификация не используется")
            return False
        
    except Exception as e:
        print(f"❌ Ошибка аутентификации через пользовательский токен: {e}")
        return False

def test_course_config():
    """Тест загрузки конфигурации курсов."""
    print("=" * 50)
    print("ТЕСТ ЗАГРУЗКИ КОНФИГУРАЦИИ КУРСОВ")
    print("=" * 50)
    
    try:
        config = DynamicCourseConfig()
        course_count = len(config._course_cache)
        print(f"✅ Загружено курсов: {course_count}")
        
        if course_count > 0:
            # Показываем несколько примеров курсов
            courses = list(config._course_cache.keys())[:3]
            print("Примеры курсов:")
            for course in courses:
                print(f"  - {course}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации курсов: {e}")
        return False

def main():
    """Основная функция."""
    print("ТЕСТИРОВАНИЕ АУТЕНТИФИКАЦИИ GOOGLE API")
    print()
    
    # Тестируем сервисный аккаунт
    service_ok = test_service_account_auth()
    print()
    
    # Тестируем пользовательский токен
    user_ok = test_user_oauth_auth()
    print()
    
    # Тестируем конфигурацию курсов
    config_ok = test_course_config()
    print()
    
    print("=" * 50)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 50)
    print(f"Сервисный аккаунт: {'✅ OK' if service_ok else '❌ ОШИБКА'}")
    print(f"Пользовательский токен: {'✅ OK' if user_ok else '❌ ОШИБКА'}")
    print(f"Конфигурация курсов: {'✅ OK' if config_ok else '❌ ОШИБКА'}")
    
    if service_ok:
        print()
        print("✅ Система готова к работе с сервисным аккаунтом")
    
    if user_ok:
        print()
        print("✅ Система готова к работе с пользовательским токеном")
        print("   Это предпочтительный способ, так как использует квоту пользователя")
    
    if not service_ok and not user_ok:
        print()
        print("❌ Оба метода аутентификации не работают")
        print("   Необходимо проверить учетные данные")

if __name__ == '__main__':
    main()