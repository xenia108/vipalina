#!/usr/bin/env python3
"""
Скрипт для проверки квоты Google Drive сервисного аккаунта.
"""

from tracker_creator import TrackerCreator
import json

def main():
    """Основная функция."""
    print("Проверка квоты Google Drive сервисного аккаунта")
    print("=" * 50)
    
    try:
        # Создаем TrackerCreator для доступа к Drive API
        creator = TrackerCreator()
        
        if creator.auth_mode != 'service_account':
            print("⚠️ Этот скрипт должен запускаться с сервисным аккаунтом")
            return
        
        print(f"✅ Аутентификация успешна: {creator.auth_mode}")
        
        # Получаем подробную информацию о квоте
        print("🔍 Получение информации о квоте...")
        about = creator.drive_service.about().get(fields='*').execute()
        
        # Сохраняем полную информацию для анализа
        with open('drive_about_info.json', 'w', encoding='utf-8') as f:
            json.dump(about, f, indent=2, ensure_ascii=False)
        
        print("✅ Полная информация сохранена в drive_about_info.json")
        
        # Показываем ключевую информацию
        print("\n📊 Ключевая информация:")
        
        # Информация о пользователе
        user_info = about.get('user', {})
        print(f"   Аккаунт: {user_info.get('emailAddress', 'Неизвестно')}")
        print(f"   Имя: {user_info.get('displayName', 'Неизвестно')}")
        
        # Информация о квоте
        storage_quota = about.get('storageQuota', {})
        print(f"\n💾 Информация о хранилище:")
        
        limit = storage_quota.get('limit')
        usage = storage_quota.get('usage')
        usage_in_drive = storage_quota.get('usageInDrive')
        usage_in_drive_trash = storage_quota.get('usageInDriveTrash')
        
        print(f"   Лимит: {limit if limit else 'Не ограничен'}")
        print(f"   Использовано всего: {usage if usage else 0}")
        print(f"   Использовано в Drive: {usage_in_drive if usage_in_drive else 0}")
        print(f"   Использовано в корзине: {usage_in_drive_trash if usage_in_drive_trash else 0}")
        
        # Преобразуем в ГБ для удобства
        if limit:
            limit_gb = int(limit) / (1024**3)
            usage_gb = int(usage) / (1024**3) if usage else 0
            usage_drive_gb = int(usage_in_drive) / (1024**3) if usage_in_drive else 0
            
            print(f"\n📈 В Гигабайтах:")
            print(f"   Лимит: {limit_gb:.2f} ГБ")
            print(f"   Использовано всего: {usage_gb:.2f} ГБ ({(usage_gb/limit_gb)*100:.1f}%)")
            print(f"   Использовано в Drive: {usage_drive_gb:.2f} ГБ ({(usage_drive_gb/limit_gb)*100:.1f}%)")
        
        # Проверяем, есть ли ограничения
        if limit and usage:
            usage_percent = (int(usage) / int(limit)) * 100
            if usage_percent > 90:
                print(f"\n⚠️ ВНИМАНИЕ: Использовано {usage_percent:.1f}% квоты!")
            else:
                print(f"\n✅ Квота используется на {usage_percent:.1f}%")
        
        # Получаем информацию о файлах
        print(f"\n📂 Получение информации о файлах...")
        results = creator.drive_service.files().list(
            fields="files(id, name, mimeType, size)",
            pageSize=100
        ).execute()
        
        files = results.get('files', [])
        print(f"   Найдено файлов: {len(files)}")
        
        # Считаем общий размер файлов
        total_size = 0
        spreadsheet_count = 0
        other_count = 0
        
        for file in files:
            mime_type = file.get('mimeType', '')
            size_str = file.get('size', '0')
            
            if size_str and size_str.isdigit():
                size = int(size_str)
                total_size += size
            
            if 'spreadsheet' in mime_type:
                spreadsheet_count += 1
            else:
                other_count += 1
        
        total_size_mb = total_size / (1024**2)
        total_size_gb = total_size / (1024**3)
        
        print(f"   Таблиц: {spreadsheet_count}")
        print(f"   Других файлов: {other_count}")
        print(f"   Общий размер: {total_size_mb:.2f} МБ ({total_size_gb:.2f} ГБ)")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()