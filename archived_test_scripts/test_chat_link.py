#!/usr/bin/env python3
"""
Тестовый скрипт для проверки формирования ссылки на чат
"""

def test_chat_link_formatting():
    """Тест формирования ссылки на чат"""
    print("Тест формирования ссылки на чат")
    print("=" * 50)
    
    # Тестовые значения chat_id
    test_cases = [
        -1001234567890,  # Стандартный формат супергруппы
        -1009876543210,  # Другой формат супергруппы
        1234567890,      # Обычный ID (без префикса)
        -1234567890      # Отрицательный ID без префикса -100
    ]
    
    for chat_id in test_cases:
        # Формируем ссылку как в коде
        chat_link_id = str(chat_id).replace('-100', '') if str(chat_id).startswith('-100') else str(chat_id)
        link = f"https://t.me/c/{chat_link_id}"
        
        print(f"chat_id: {chat_id}")
        print(f"chat_link_id: {chat_link_id}")
        print(f"Ссылка: {link}")
        print("-" * 30)

if __name__ == "__main__":
    test_chat_link_formatting()