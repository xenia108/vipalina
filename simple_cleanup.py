#!/usr/bin/env python3
"""
Простой скрипт для очистки Google Drive сервисного аккаунта.
"""

from tracker_creator import TrackerCreator
import sys

def main():
    """Основная функция."""
    print("Простая очистка Google Drive сервисного аккаунта")
    print()
    
    try:
        # Создаем TrackerCreator для доступа к Drive API
        creator = TrackerCreator()
        
        if creator.auth_mode != 'service_account':
            print("⚠️ Этот скрипт должен запускаться с сервисным аккаунтом")
            return
        
        print(f"✅ Аутентификация успешна: {creator.auth_mode}")
        
        # Получаем список файлов
        print("🔍 Получение списка файлов...")
        results = creator.drive_service.files().list(
            fields="files(id, name, createdTime)",
            orderBy="createdTime desc"
        ).execute()
        
        files = results.get('files', [])
        print(f"📊 Найдено файлов: {len(files)}")
        
        if not files:
            print("⚠️ Файлы не найдены")
            return
        
        # Показываем последние 20 файлов
        print("\n📂 Последние 20 файлов:")
        for i, file in enumerate(files[:20], 1):
            print(f"   {i:2d}. {file['name']}")
        
        # Спрашиваем, сколько файлов удалить
        print(f"\n❓ Сколько самых старых файлов удалить? (0 для выхода)")
        try:
            count = int(input("Введите число: "))
        except ValueError:
            print("❌ Неверный ввод")
            return
        
        if count <= 0:
            print("Выход")
            return
        
        if count > len(files):
            count = len(files)
        
        # Удаляем файлы
        print(f"\n🗑️ Удаление {count} самых старых файлов...")
        deleted = 0
        
        # Файлы отсортированы по дате создания (новые первые), 
        # поэтому берем последние count файлов (самые старые)
        files_to_delete = files[-count:] if count < len(files) else files
        
        for file in files_to_delete:
            try:
                creator.drive_service.files().delete(fileId=file['id']).execute()
                print(f"✅ Удален: {file['name']}")
                deleted += 1
            except Exception as e:
                print(f"❌ Ошибка удаления {file['name']}: {e}")
        
        print(f"\n📊 Результаты: удалено {deleted} из {count} файлов")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()