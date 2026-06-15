#!/usr/bin/env python3
"""Проверка использования Google Drive сервис-аккаунта"""

import json
from googleapiclient.discovery import build
from google.oauth2 import service_account

SERVICE_ACCOUNT_FILE = 'vipalina_google_service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive']

def check_drive_usage():
    """Проверяет квоту и использование Drive"""
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    
    service = build('drive', 'v3', credentials=credentials)
    
    # Получаем информацию о хранилище
    about = service.about().get(fields='storageQuota,user').execute()
    
    quota = about.get('storageQuota', {})
    user = about.get('user', {})
    
    print(f"\n📧 Сервис-аккаунт: {user.get('emailAddress', 'N/A')}")
    print(f"\n💾 Квота Drive:")
    
    limit = int(quota.get('limit', 0))
    usage = int(quota.get('usage', 0))
    usage_in_drive = int(quota.get('usageInDrive', 0))
    
    if limit > 0:
        limit_gb = limit / (1024**3)
        usage_gb = usage / (1024**3)
        usage_drive_gb = usage_in_drive / (1024**3)
        percent = (usage / limit) * 100
        
        print(f"  Лимит: {limit_gb:.2f} GB")
        print(f"  Использовано: {usage_gb:.2f} GB ({percent:.1f}%)")
        print(f"  В Drive: {usage_drive_gb:.2f} GB")
        print(f"  Доступно: {(limit - usage) / (1024**3):.2f} GB")
        
        if percent > 95:
            print(f"\n⚠️ КРИТИЧНО: Квота заполнена на {percent:.1f}%!")
    else:
        print(f"  ⚠️ Unlimited storage или организационный аккаунт")
        print(f"  Использовано: {usage / (1024**3):.2f} GB")
    
    # Список файлов (последние 50)
    print(f"\n📁 Последние файлы:")
    results = service.files().list(
        pageSize=50,
        fields="files(id, name, mimeType, size, createdTime)",
        orderBy="createdTime desc"
    ).execute()
    
    files = results.get('files', [])
    total_size = 0
    
    for f in files[:10]:
        size = int(f.get('size', 0))
        total_size += size
        size_mb = size / (1024**2)
        mime = f.get('mimeType', '')
        name = f.get('name', 'N/A')[:50]
        
        if 'spreadsheet' in mime:
            icon = '📊'
        elif 'folder' in mime:
            icon = '📁'
        else:
            icon = '📄'
        
        print(f"  {icon} {name[:40]}: {size_mb:.2f} MB")
    
    print(f"\n💾 Всего файлов: {len(files)}")
    print(f"💾 Размер последних 50: {total_size / (1024**3):.2f} GB")

if __name__ == '__main__':
    check_drive_usage()
