#!/usr/bin/env python3
"""
Скрипт для проверки срока действия OAuth токена и отправки уведомлений заранее.
"""

import json
import os
from datetime import datetime, timedelta
import asyncio
from auth_error_notifier import notify_token_expiring_soon

TOKEN_FILE = 'token_vipzerocoder.json'

def check_token_expiry():
    """
    Проверяет срок действия токена и отправляет уведомление, если он скоро истечет.
    """
    if not os.path.exists(TOKEN_FILE):
        print(f"❌ Файл токена {TOKEN_FILE} не найден")
        return
    
    try:
        with open(TOKEN_FILE, 'r') as f:
            token_data = json.load(f)
        
        # Парсим дату истечения срока действия
        expiry_str = token_data.get('expiry')
        if not expiry_str:
            print("❌ Не найдена информация о сроке действия токена")
            return
        
        # Преобразуем строку в объект datetime
        expiry_date = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
        
        # Получаем текущую дату
        now = datetime.now(expiry_date.tzinfo)
        
        # Вычисляем разницу
        diff = expiry_date - now
        days_left = diff.days
        seconds_left = diff.total_seconds()
        
        print(f"📅 Срок действия токена истекает: {expiry_date}")
        print(f"⏰ Текущее время: {now}")
        print(f"⏳ До истечения срока: {days_left} дней ({seconds_left} секунд)")
        
        # Если до истечения осталось меньше 7 дней, отправляем уведомление
        if 0 <= days_left <= 7:
            print(f"⚠️ Токен скоро истечет! Отправляем уведомление...")
            asyncio.run(notify_token_expiring_soon(days_left))
        elif days_left < 0:
            print("❌ Токен уже истек!")
            # Отправляем уведомление о том, что токен истек
            asyncio.run(notify_token_expiring_soon(0))
        else:
            print("✅ Токен действует нормально")
            
    except Exception as e:
        print(f"❌ Ошибка при проверке срока действия токена: {e}")

if __name__ == "__main__":
    check_token_expiry()