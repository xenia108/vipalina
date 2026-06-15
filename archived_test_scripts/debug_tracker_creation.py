#!/usr/bin/env python3
"""
Скрипт для отладки создания трекера и анализа ошибок квоты.
"""

from tracker_creator import TrackerCreator
import json
import traceback

def debug_quota_info(creator):
    """Детальная проверка информации о квоте."""
    print("🔍 Детальная проверка квоты...")
    
    try:
        # Получаем разные виды информации о квоте
        about_fields = [
            'storageQuota',
            'user',
            'kind',
            'maxUploadSize',
            'appInstalled'
        ]
        
        about = creator.drive_service.about().get(
            fields=','.join(about_fields)
        ).execute()
        
        print("📊 Информация о квоте:")
        print(json.dumps(about, indent=2, ensure_ascii=False))
        
        # Сохраняем в файл
        with open('debug_about_info.json', 'w', encoding='utf-8') as f:
            json.dump(about, f, indent=2, ensure_ascii=False)
        print("✅ Детальная информация сохранена в debug_about_info.json")
        
    except Exception as e:
        print(f"❌ Ошибка получения информации о квоте: {e}")

def test_template_access(creator):
    """Проверка доступа к шаблону."""
    print("\n🔍 Проверка доступа к шаблону...")
    
    try:
        template = creator.sheets_client.open_by_key(creator.TEMPLATE_ID)
        print(f"✅ Шаблон доступен: {template.title}")
        
        # Проверяем доступ к листам
        worksheets = template.worksheets()
        print(f"✅ Доступно листов: {len(worksheets)}")
        
        for worksheet in worksheets:
            print(f"   - {worksheet.title}")
            
    except Exception as e:
        print(f"❌ Ошибка доступа к шаблону: {e}")

def test_copy_operation(creator):
    """Тест операции копирования."""
    print("\n🔍 Тест операции копирования...")
    
    try:
        # Пробуем скопировать шаблон
        copy_metadata = {
            'name': 'DEBUG_TEST_COPY_' + creator.TEMPLATE_ID[:8]
        }
        
        print(f"📋 Попытка копирования шаблона {creator.TEMPLATE_ID}")
        print(f"   Новое имя: {copy_metadata['name']}")
        
        # Выполняем копирование
        copied_file = creator.drive_service.files().copy(
            fileId=creator.TEMPLATE_ID,
            body=copy_metadata,
            supportsAllDrives=True
        ).execute()
        
        print(f"✅ Копирование успешно!")
        print(f"   ID нового файла: {copied_file['id']}")
        print(f"   Имя нового файла: {copied_file['name']}")
        
        # Пытаемся удалить тестовый файл
        try:
            creator.drive_service.files().delete(
                fileId=copied_file['id']
            ).execute()
            print(f"✅ Тестовый файл удален")
        except Exception as delete_error:
            print(f"⚠️ Ошибка удаления тестового файла: {delete_error}")
            
        return copied_file['id']
        
    except Exception as e:
        print(f"❌ Ошибка копирования: {e}")
        print("Подробности ошибки:")
        traceback.print_exc()
        return None

def main():
    """Основная функция."""
    print("Отладка создания трекера")
    print("=" * 40)
    
    try:
        # Создаем TrackerCreator
        creator = TrackerCreator()
        print(f"✅ Аутентификация: {creator.auth_mode}")
        
        # Детальная проверка квоты
        debug_quota_info(creator)
        
        # Проверка доступа к шаблону
        test_template_access(creator)
        
        # Тест копирования
        copied_file_id = test_copy_operation(creator)
        
        if copied_file_id:
            print(f"\n🎉 Тест пройден успешно!")
        else:
            print(f"\n💥 Тест провален - проблема с копированием")
            
    except Exception as e:
        print(f"❌ Общая ошибка: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    main()