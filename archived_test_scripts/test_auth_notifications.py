#!/usr/bin/env python3
"""
Тестовый скрипт для проверки системы уведомлений об ошибках аутентификации.
"""

import asyncio
from auth_error_notifier import notify_oauth_error, notify_token_expiring_soon

async def test_notifications():
    """Тестирует систему уведомлений"""
    print("🧪 Тестирование системы уведомлений об ошибках аутентификации...")
    
    # Тест 1: Уведомление об ошибке OAuth
    print("\n1️⃣ Тест уведомления об ошибке OAuth:")
    await notify_oauth_error("invalid_grant: Token has been expired or revoked.")
    
    # Тест 2: Уведомление о скором истечении токена
    print("\n2️⃣ Тест уведомления о скором истечении токена (3 дня):")
    await notify_token_expiring_soon(3)
    
    # Тест 3: Уведомление об истекшем токене
    print("\n3️⃣ Тест уведомления об истекшем токене:")
    await notify_token_expiring_soon(0)
    
    print("\n✅ Все тесты завершены!")

if __name__ == "__main__":
    asyncio.run(test_notifications())