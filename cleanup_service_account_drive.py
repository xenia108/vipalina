#!/usr/bin/env python3
"""
Скрипт для очистки Google Drive сервисного аккаунта.
Удаляет старые трекеры студентов для освобождения места.
"""

import os
from tracker_creator import TrackerCreator
from datetime import datetime, timedelta
import re

def list_trackers(creator, folder_id=None):
    """Получить список всех трекеров в папке."""
    try:
        if folder_id:
            # Получаем файлы из конкретной папки
            query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.spreadsheet'"
            results = creator.drive_service.files().list(
                q=query,
                fields="files(id, name, createdTime, owners)",
                orderBy="createdTime desc"
            ).execute()
        else:
            # Получаем все spreadsheet файлы
            query = "mimeType = 'application/vnd.google-apps.spreadsheet'"
            results = creator.drive_service.files().list(
                q=query,
                fields="files(id, name, createdTime, owners)",
                orderBy="createdTime desc"
            ).execute()
        
        files = results.get('files', [])
        return files
    except Exception as e:
        print(f"❌ Ошибка получения списка файлов: {e}")
        return []

def is_student_tracker(filename):
    """Проверить, является ли файл трекером студента."""
    # Типичные шаблоны названий трекеров:
    # "Имя - Название курса, GetCourse ID"
    patterns = [
        r'.* - .*, \d+',  # Стандартный формат
        r'.*Трекер.*',    # Содержит слово "Трекер"
        r'.*Student.*',   # Содержит слово "Student"
    ]
    
    for pattern in patterns:
        if re.match(pattern, filename, re.IGNORECASE):
            return True
    return False

def delete_old_trackers(creator, days_old=30, dry_run=True):
    """Удалить старые трекеры."""
    print(f"🔍 Поиск трекеров старше {days_old} дней...")
    
    # Получаем все файлы
    files = list_trackers(creator)
    
    if not files:
        print("⚠️ Файлы не найдены")
        return
    
    print(f"📊 Найдено файлов: {len(files)}")
    
    # Определяем пороговую дату
    cutoff_date = datetime.utcnow() - timedelta(days=days_old)
    print(f"📅 Удаляем файлы старше: {cutoff_date.strftime('%Y-%m-%d')}")
    
    deleted_count = 0
    skipped_count = 0
    
    for file in files:
        try:
            filename = file['name']
            file_id = file['id']
            created_time = datetime.strptime(file['createdTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
            
            # Проверяем, является ли файл трекером студента
            if not is_student_tracker(filename):
                print(f"⏭️ Пропущен (не трекер): {filename}")
                skipped_count += 1
                continue
            
            # Проверяем возраст файла
            if created_time > cutoff_date:
                print(f"⏭️ Пропущен (слишком новый): {filename} ({created_time.strftime('%Y-%m-%d')})")
                skipped_count += 1
                continue
            
            # Удаляем файл
            if dry_run:
                print(f"📋 [DRY RUN] Будет удален: {filename} ({created_time.strftime('%Y-%m-%d')})")
            else:
                creator.drive_service.files().delete(fileId=file_id).execute()
                print(f"✅ Удален: {filename} ({created_time.strftime('%Y-%m-%d')})")
            
            deleted_count += 1
            
        except Exception as e:
            print(f"❌ Ошибка обработки файла {file.get('name', 'Unknown')}: {e}")
            skipped_count += 1
    
    print(f"\n📊 Результаты:")
    print(f"   Удалено: {deleted_count}")
    print(f"   Пропущено: {skipped_count}")
    
    if dry_run:
        print(f"\n💡 Это был тестовый запуск. Для реального удаления используйте --delete")

def delete_by_keyword(creator, keyword, dry_run=True):
    """Удалить файлы по ключевому слову."""
    print(f"🔍 Поиск файлов содержащих: '{keyword}'")
    
    # Получаем все файлы
    files = list_trackers(creator)
    
    if not files:
        print("⚠️ Файлы не найдены")
        return
    
    print(f"📊 Найдено файлов: {len(files)}")
    
    deleted_count = 0
    skipped_count = 0
    
    for file in files:
        try:
            filename = file['name']
            file_id = file['id']
            
            # Проверяем, содержит ли имя ключевое слово
            if keyword.lower() not in filename.lower():
                continue
            
            # Удаляем файл
            if dry_run:
                print(f"📋 [DRY RUN] Будет удален: {filename}")
            else:
                creator.drive_service.files().delete(fileId=file_id).execute()
                print(f"✅ Удален: {filename}")
            
            deleted_count += 1
            
        except Exception as e:
            print(f"❌ Ошибка обработки файла {file.get('name', 'Unknown')}: {e}")
            skipped_count += 1
    
    print(f"\n📊 Результаты:")
    print(f"   Удалено: {deleted_count}")
    print(f"   Пропущено: {skipped_count}")
    
    if dry_run:
        print(f"\n💡 Это был тестовый запуск. Для реального удаления используйте --delete")

def show_storage_info(creator):
    """Показать информацию о хранилище."""
    try:
        about = creator.drive_service.about().get(fields='*').execute()
        
        # Получаем информацию о квоте
        storage_quota = about.get('storageQuota', {})
        limit = int(storage_quota.get('limit', 0)) if storage_quota.get('limit') else 0
        usage = int(storage_quota.get('usage', 0)) if storage_quota.get('usage') else 0
        usage_in_drive = int(storage_quota.get('usageInDrive', 0)) if storage_quota.get('usageInDrive') else 0
        
        print("💾 Информация о хранилище:")
        if limit > 0:
            limit_gb = limit / (1024**3)
            usage_gb = usage / (1024**3)
            usage_drive_gb = usage_in_drive / (1024**3)
            usage_percent = (usage / limit) * 100
            usage_drive_percent = (usage_in_drive / limit) * 100
            
            print(f"   Всего доступно: {limit_gb:.2f} ГБ")
            print(f"   Использовано всего: {usage_gb:.2f} ГБ ({usage_percent:.1f}%)")
            print(f"   Использовано в Drive: {usage_drive_gb:.2f} ГБ ({usage_drive_percent:.1f}%)")
        else:
            print("   Квота не ограничена (неограниченное хранилище)")
            
    except Exception as e:
        print(f"❌ Ошибка получения информации о хранилище: {e}")

def main():
    """Основная функция."""
    print("=" * 60)
    print("ОЧИСТКА GOOGLE DRIVE СЕРВИСНОГО АККАУНТА")
    print("=" * 60)
    print()
    
    try:
        # Создаем TrackerCreator для доступа к Drive API
        creator = TrackerCreator()
        
        if creator.auth_mode != 'service_account':
            print("⚠️ Этот скрипт должен запускаться с сервисным аккаунтом")
            print(f"   Текущий режим: {creator.auth_mode}")
            return
        
        print(f"✅ Аутентификация успешна: {creator.auth_mode}")
        print()
        
        # Показываем информацию о хранилище
        show_storage_info(creator)
        print()
        
        # Показываем последние 10 файлов
        print("📂 Последние 10 файлов:")
        files = list_trackers(creator)[:10]
        for i, file in enumerate(files, 1):
            created_time = datetime.strptime(file['createdTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
            print(f"   {i:2d}. {file['name']} ({created_time.strftime('%Y-%m-%d')})")
        print()
        
        # Спрашиваем пользователя, что делать
        print("Выберите действие:")
        print("1. Удалить старые трекеры (тестовый запуск)")
        print("2. Удалить трекеры старше 30 дней (реальное удаление)")
        print("3. Удалить файлы по ключевому слову (тестовый запуск)")
        print("4. Удалить файлы по ключевому слову (реальное удаление)")
        print("5. Показать информацию о хранилище")
        print("0. Выход")
        print()
        
        choice = input("Введите номер действия: ").strip()
        
        if choice == '1':
            delete_old_trackers(creator, days_old=30, dry_run=True)
        elif choice == '2':
            confirm = input("⚠️ ВНИМАНИЕ! Это реальное удаление файлов. Продолжить? (y/N): ").strip().lower()
            if confirm == 'y':
                delete_old_trackers(creator, days_old=30, dry_run=False)
            else:
                print("Отменено")
        elif choice == '3':
            keyword = input("Введите ключевое слово: ").strip()
            if keyword:
                delete_by_keyword(creator, keyword, dry_run=True)
        elif choice == '4':
            keyword = input("Введите ключевое слово: ").strip()
            if keyword:
                confirm = input("⚠️ ВНИМАНИЕ! Это реальное удаление файлов. Продолжить? (y/N): ").strip().lower()
                if confirm == 'y':
                    delete_by_keyword(creator, keyword, dry_run=False)
                else:
                    print("Отменено")
        elif choice == '5':
            show_storage_info(creator)
        elif choice == '0':
            print("Выход")
        else:
            print("Неверный выбор")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    main()