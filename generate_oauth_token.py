#!/usr/bin/env python3
"""
Скрипт для генерации нового OAuth токена для Google API.
Используется для авторизации в Google Sheets и Drive API от имени пользователя.
"""

import os
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Области доступа (scopes) для Google API
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

# Имя файла для сохранения токена
TOKEN_FILE = 'token_vipzerocoder.json'
CREDENTIALS_FILE = 'vipalina_google_oauth_client.json'

def main():
    """Основная функция для генерации токена OAuth."""
    creds = None
    
    # Проверяем, существует ли файл с токеном
    if os.path.exists(TOKEN_FILE):
        print(f"⚠️ Файл токена {TOKEN_FILE} уже существует")
        response = input("Хотите перезаписать его? (y/N): ")
        if response.lower() != 'y':
            print("Отмена операции")
            return
    
    # Загружаем учетные данные клиента
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ Файл учетных данных {CREDENTIALS_FILE} не найден")
        print("Пожалуйста, убедитесь, что файл существует и содержит корректные данные клиента")
        return
    
    try:
        # Создаем поток OAuth
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE, SCOPES)
        
        # Запускаем локальный сервер для авторизации
        print("🔄 Открывается браузер для авторизации...")
        print("Пожалуйста, войдите в аккаунт Google (vipzerocoder@gmail.com) и разрешите доступ")
        
        creds = flow.run_local_server(port=0)
        
        # Сохраняем токен в файл
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
        
        print(f"✅ Токен успешно сохранен в файл {TOKEN_FILE}")
        
        # Проверяем работу токена
        print("🔍 Проверка токена...")
        service = build('drive', 'v3', credentials=creds)
        about = service.about().get(fields='user').execute()
        user_email = about['user']['emailAddress']
        print(f"✅ Авторизация успешна! Аккаунт: {user_email}")
        
    except Exception as e:
        print(f"❌ Ошибка при генерации токена: {e}")
        return

if __name__ == '__main__':
    print("=" * 60)
    print("ГЕНЕРАЦИЯ НОВОГО OAUTH ТОКЕНА ДЛЯ GOOGLE API")
    print("=" * 60)
    print()
    print("Этот скрипт поможет создать новый токен OAuth для доступа к Google Sheets и Drive")
    print()
    
    main()
    
    print()
    print("=" * 60)
    print("Процесс завершен")
    print("=" * 60)