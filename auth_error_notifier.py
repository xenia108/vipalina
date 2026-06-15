#!/usr/bin/env python3
"""
Модуль для уведомления руководителя VIP-отдела о проблемах с OAuth аутентификацией.
"""

import logging
import asyncio
from telethon import TelegramClient
from config import TELETHON_BOT_TOKEN, TELETHON_SESSION_NAME, VIP_HEAD, API_ID, API_HASH
import os
from datetime import datetime

logger = logging.getLogger('vipalina_telethon')

class AuthErrorNotifier:
    """Класс для уведомления о проблемах с аутентификацией"""
    
    def __init__(self):
        self.telethon_token = TELETHON_BOT_TOKEN
        # Используем отдельную сессию для уведомлений, чтобы избежать конфликтов
        self.session_name = f"{TELETHON_SESSION_NAME}_notifications"
        self.api_id = API_ID
        self.api_hash = API_HASH
        self.vip_head_id = VIP_HEAD['telegram_id']
        self.client = None
        self.log_file = "vipalina_logs/auth_errors.log"
        self.proxy = self._detect_proxy()
        
        # Создаем директорию для логов, если она не существует
        os.makedirs("vipalina_logs", exist_ok=True)
    
    @staticmethod
    def _detect_proxy():
        """Определяет доступность Tor-прокси."""
        try:
            import socks
            import socket
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(2)
            result = test_sock.connect_ex(('127.0.0.1', 9050))
            test_sock.close()
            if result == 0:
                return (socks.SOCKS5, '127.0.0.1', 9050)
        except (ImportError, Exception):
            pass
        return None
    
    async def _initialize_client(self):
        """Инициализирует Telethon клиент асинхронно"""
        if self.client is None:
            try:
                # Создаем клиент Telethon с отдельной сессией
                self.client = TelegramClient(self.session_name, self.api_id, self.api_hash, proxy=self.proxy)
                await self.client.start(bot_token=self.telethon_token)
                
                # Проверяем, что клиент авторизован
                me = await self.client.get_me()
                logger.info(f"✅ Telethon клиент инициализирован: {me.username}")
            except Exception as e:
                logger.warning(f"⚠️ Telethon клиент не инициализирован: {e}")
                # Не прекращаем выполнение, просто будем писать в лог
    
    def _write_to_log(self, message: str):
        """Записывает сообщение в лог-файл"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message = f"[{timestamp}] {message}\n"
            
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_message)
                
            logger.info(f"✅ Сообщение записано в лог: {self.log_file}")
        except Exception as e:
            logger.error(f"❌ Ошибка записи в лог: {e}")
    
    async def notify_oauth_error(self, error_message: str):
        """
        Отправляет уведомление руководителю VIP-отдела о проблеме с OAuth.
        Уведомляет обо ВСЕХ ошибках, связанных с авторизацией (не только invalid_grant).
        
        Args:
            error_message: Сообщение об ошибке
        """
            
        client = None
        try:
            # Создаем отдельный клиент для каждого уведомления
            client = TelegramClient(self.session_name, self.api_id, self.api_hash, proxy=self.proxy)
            await client.start(bot_token=self.telethon_token)
            
            message = self._format_oauth_error_message(error_message)
            
            # Отправляем сообщение
            await client.send_message(self.vip_head_id, message)
            logger.info("✅ Уведомление о проблеме с OAuth отправлено руководителю VIP-отдела")
            
            # Закрываем клиент
            await client.disconnect()
                
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке уведомления: {e}")
            # Логируем детали ошибки для диагностики
            logger.error(f"Детали ошибки: {type(e).__name__}: {str(e)}")
            # Записываем в лог как резервный способ
            self._write_to_log(f"OAuth Error: {error_message}")
            
            # Закрываем клиент, если он был создан
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
    
    def _format_oauth_error_message(self, error_message: str) -> str:
        """
        Форматирует сообщение об ошибке OAuth/авторизации.
        
        Args:
            error_message: Сообщение об ошибке
            
        Returns:
            Отформатированное сообщение
        """
        # Определяем тип ошибки для заголовка
        if 'invalid_grant' in error_message or 'Token has been expired' in error_message:
            title = "🚨 **ВНИМАНИЕ: Токен OAuth истёк!**"
            action = "**Для обновления токена:**\nОтправьте мне команду `/oauth` в личные сообщения."
        elif 'OpenSSL' in error_message or 'crypto' in error_message:
            title = "🚨 **ВНИМАНИЕ: Ошибка библиотеки OpenSSL!**"
            action = "**Для исправления:**\nНужно переустановить пакеты:\n`pip3 install pyOpenSSL==24.3.0 cryptography==43.0.3`"
        else:
            title = "🚨 **ВНИМАНИЕ: Ошибка авторизации Google!**"
            action = "**Для обновления токена:**\nОтправьте мне команду `/oauth` в личные сообщения."

        message = f"""{title}

Ошибка: `{error_message}`

{action}"""

        return message
    
    async def notify_token_expiring_soon(self, days_left: int):
        """
        Отправляет уведомление о скором истечении срока действия токена.
        
        Args:
            days_left: Количество дней до истечения срока действия
        """
        client = None
        try:
            # Создаем отдельный клиент для каждого уведомления
            client = TelegramClient(self.session_name, self.api_id, self.api_hash, proxy=self.proxy)
            await client.start(bot_token=self.telethon_token)
            
            message = self._format_token_expiring_message(days_left)
            
            # Отправляем сообщение
            await client.send_message(self.vip_head_id, message)
            logger.info("✅ Уведомление о скором истечении токена отправлено руководителю VIP-отдела")
            
            # Закрываем клиент
            await client.disconnect()
                
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке уведомления: {e}")
            # Логируем детали ошибки для диагностики
            logger.error(f"Детали ошибки: {type(e).__name__}: {str(e)}")
            # Записываем в лог как резервный способ
            self._write_to_log(f"Token Expiring Warning: {days_left} days left")
            
            # Закрываем клиент, если он был создан
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
    
    def _format_token_expiring_message(self, days_left: int) -> str:
        """
        Форматирует сообщение о скором истечении срока действия токена.
        
        Args:
            days_left: Количество дней до истечения срока действия
            
        Returns:
            Отформатированное сообщение
        """
        if days_left <= 0:
            message = """🚨 **ВНИМАНИЕ: Токен OAuth ИСТЕК!**

Система автоматически переключилась на сервисный аккаунт.

**Для обновления токена:**
Отправьте мне команду `/oauth` в личные сообщения."""
        else:
            message = f"""⚠️ **ВНИМАНИЕ: Токен OAuth скоро истечёт**

До истечения осталось: **{days_left} дней**

**Рекомендую обновить токен:**
Отправьте мне команду `/oauth` в личные сообщения."""

        return message

# Глобальный экземпляр нотификатора
notifier = AuthErrorNotifier()

async def notify_oauth_error(error_message: str):
    """
    Асинхронная функция для отправки уведомления о проблеме с OAuth.
    
    Args:
        error_message: Сообщение об ошибке
    """
    await notifier.notify_oauth_error(error_message)

async def notify_token_expiring_soon(days_left: int):
    """
    Асинхронная функция для отправки уведомления о скором истечении токена.
    
    Args:
        days_left: Количество дней до истечения срока действия
    """
    await notifier.notify_token_expiring_soon(days_left)

if __name__ == "__main__":
    # Тестовое уведомление
    import asyncio
    
    async def test_notification():
        await notify_oauth_error("invalid_grant: Token has been expired or revoked.")
    
    asyncio.run(test_notification())