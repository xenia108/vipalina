#!/usr/bin/env python3
"""
Модуль для обработки OAuth авторизации Google через Telegram бота.
Позволяет обновить OAuth токен без доступа к серверу.
"""

import os
import json
import logging
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger('vipalina_telethon')

# Области доступа для Google API
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'token_vipzerocoder.json')
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vipalina_google_oauth_client.json')

# Redirect URI для ручного ввода кода (OOB flow)
REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'


class OAuthHandler:
    """Обработчик OAuth авторизации через Telegram бота."""
    
    def __init__(self):
        self.flow = None
        self.pending_auth = {}  # user_id -> flow state
        self.last_state = None  # Сохраняем последний state для проверки после рестарта
    
    def generate_auth_url(self, user_id: int) -> str:
        """
        Генерирует URL для авторизации Google.
        
        Args:
            user_id: Telegram ID пользователя
            
        Returns:
            URL для авторизации или сообщение об ошибке
        """
        try:
            if not os.path.exists(CREDENTIALS_FILE):
                return None, f"❌ Файл {CREDENTIALS_FILE} не найден"
            
            # Создаём flow для OOB авторизации
            flow = Flow.from_client_secrets_file(
                CREDENTIALS_FILE,
                scopes=SCOPES,
                redirect_uri=REDIRECT_URI
            )
            
            # Генерируем URL авторизации
            auth_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'  # Всегда запрашиваем refresh_token
            )
            
            # Сохраняем flow для этого пользователя
            self.pending_auth[user_id] = {
                'flow': flow,
                'state': state
            }
            self.last_state = state  # Сохраняем state для восстановления после рестарта
            
            logger.info(f"✅ Сгенерирован URL авторизации для пользователя {user_id}")
            return auth_url, None
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации URL авторизации: {e}")
            return None, f"❌ Ошибка: {e}"
    
    def exchange_code(self, user_id: int, code: str) -> tuple[bool, str]:
        """
        Обменивает код авторизации на токен.
        
        Args:
            user_id: Telegram ID пользователя
            code: Код авторизации от Google
            
        Returns:
            (success, message)
        """
        try:
            # Проверяем наличие сессии или последнего state (для восстановления после рестарта)
            if user_id not in self.pending_auth:
                logger.warning(f"⚠️ Нет активной сессии для {user_id}, проверяем last_state={self.last_state}")
                if not self.last_state:
                    return False, "❌ Нет активной сессии авторизации. Сначала вызовите /oauth"
                # Сессия потеряна при рестарте, но state есть — создаём flow заново
                logger.info(f"🔄 Восстанавливаем сессию для пользователя {user_id}")
                self.flow = Flow.from_client_secrets_file(
                    CREDENTIALS_FILE,
                    scopes=SCOPES,
                    redirect_uri=REDIRECT_URI
                )
            elif self.pending_auth[user_id]['flow'] is None:
                return False, "❌ Нет активной сессии авторизации. Сначала вызовите /oauth"
            
            flow = self.pending_auth[user_id]['flow']
            
            # Обмениваем код на токен
            flow.fetch_token(code=code.strip())
            creds = flow.credentials
            
            # Сохраняем токен
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
            
            # Проверяем работу токена
            service = build('drive', 'v3', credentials=creds)
            about = service.about().get(fields='user').execute()
            user_email = about['user']['emailAddress']
            
            # Очищаем pending auth
            del self.pending_auth[user_id]
            
            logger.info(f"✅ OAuth токен успешно обновлён для {user_email}")
            return True, f"✅ Токен успешно обновлён!\nАккаунт: {user_email}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка обмена кода на токен: {e}")
            return False, f"❌ Ошибка: {e}"
    
    def check_token_status(self) -> dict:
        """
        Проверяет статус текущего токена.
        
        Returns:
            dict с информацией о токене
        """
        try:
            if not os.path.exists(TOKEN_FILE):
                return {'valid': False, 'error': 'Токен не найден'}
            
            with open(TOKEN_FILE, 'r') as f:
                token_data = json.load(f)
            
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            
            if creds.expired:
                if creds.refresh_token:
                    return {'valid': False, 'error': 'Токен истёк, требуется обновление'}
                else:
                    return {'valid': False, 'error': 'Токен истёк, refresh_token отсутствует'}
            
            # Проверяем реальную работу
            service = build('drive', 'v3', credentials=creds)
            about = service.about().get(fields='user').execute()
            
            return {
                'valid': True,
                'email': about['user']['emailAddress'],
                'expiry': token_data.get('expiry', 'unknown')
            }
            
        except Exception as e:
            return {'valid': False, 'error': str(e)}


# Глобальный экземпляр
oauth_handler = OAuthHandler()
