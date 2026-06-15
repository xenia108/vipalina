#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для поиска релевантных курсов по ключевым словам
"""

import os
import re
from typing import List, Dict, Tuple

# Директория с файлами курсов
COURSES_DIR = 'parsed_pages'

# Словарь ключевых слов и соответствующих им частей имен файлов
COURSE_KEYWORDS = {
    # Программирование
    'python': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers', 'python-and-chatgpt-course-for-kids', 'python-ai-for-kids', 'analytics-python-chatgpt', 'int-python', 'freelance-and-project-work-python'],
    'питон': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers', 'python-and-chatgpt-course-for-kids', 'python-ai-for-kids', 'analytics-python-chatgpt', 'int-python', 'freelance-and-project-work-python'],
    'пайтон': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers', 'python-and-chatgpt-course-for-kids', 'python-ai-for-kids', 'analytics-python-chatgpt', 'int-python', 'freelance-and-project-work-python'],
    'изучить python': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers', 'python-and-chatgpt-course-for-kids'],
    'изучить питон': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers', 'python-and-chatgpt-course-for-kids'],
    'программирование': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers', 'scratch-programming-course-for-kids'],
    'программирование на python': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers'],
    'программирование на питоне': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers'],
    'разработка': ['python-from-scratch-with-chatgpt', 'mobile-app-developer-online-course', 'chatbot-developer', 'web-design-course'],
    'разработка на python': ['python-from-scratch-with-chatgpt', 'freelance-and-project-work-python'],
    'разработка на питоне': ['python-from-scratch-with-chatgpt', 'freelance-and-project-work-python'],
    'код': ['vibe-coding', 'practicum-vibe-coding-in-cursor'],
    'программист': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers'],
    'python разработчик': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers', 'freelance-and-project-work-python'],
    'питон разработчик': ['python-from-scratch-with-chatgpt', 'python-developer-for-teenagers', 'freelance-and-project-work-python'],
    
    # Вайб-кодинг и AI-разработка
    'вайб': ['vibe-coding', 'practicum-vibe-coding-in-cursor', 'vibe-marketing'],
    'вайб-кодинг': ['vibe-coding', 'practicum-vibe-coding-in-cursor'],
    'вайб кодинг': ['vibe-coding', 'practicum-vibe-coding-in-cursor'],
    'cursor': ['vibe-coding', 'practicum-vibe-coding-in-cursor'],
    'ai-агент': ['vibe-coding', 'practicum-creating-ai-agents', 'open-lesson-on-creating-ai-assistants'],
    'ии-агент': ['vibe-coding', 'practicum-creating-ai-agents', 'open-lesson-on-creating-ai-assistants'],
    'автономный агент': ['vibe-coding', 'practicum-creating-ai-agents'],
    
    # Нейросети и AI
    'нейросети': ['neural-networks-for-life', 'designer-course-neural-networks-for-life', 'neural-networks-from-principles-to-practice', 'russian-neural-networks', 'neuro-for-life'],
    'нейросеть': ['neural-networks-for-life', 'designer-course-neural-networks-for-life', 'neural-networks-from-principles-to-practice', 'russian-neural-networks'],
    'нейронные сети': ['neural-networks-for-life', 'designer-course-neural-networks-for-life', 'neural-networks-from-principles-to-practice', 'russian-neural-networks'],
    'нейронка': ['neural-networks-for-life', 'designer-course-neural-networks-for-life', 'neural-networks-from-principles-to-practice', 'russian-neural-networks'],
    'нейронки': ['neural-networks-for-life', 'designer-course-neural-networks-for-life', 'neural-networks-from-principles-to-practice', 'russian-neural-networks'],
    'изучить нейросети': ['neural-networks-for-life', 'neural-networks-from-principles-to-practice'],
    'искусственный интеллект': ['neural-networks-for-life', 'start-your-business-with-ai', 'couese-ai-for-investment'],
    'ии': ['neural-networks-for-life', 'start-your-business-with-ai', 'couese-ai-for-investment'],
    'ai': ['neural-networks-for-life', 'start-your-business-with-ai', 'couese-ai-for-investment', 'visual-content-with-ai-course'],
    'машинное обучение': ['neural-networks-for-life', 'neural-networks-from-principles-to-practice'],
    'chatgpt': ['python-from-scratch-with-chatgpt', 'python-and-chatgpt-course-for-kids', 'data-analysis-from-scratch-with-chatgpt-course', 'analytics-python-chatgpt'],
    'чатгпт': ['python-from-scratch-with-chatgpt', 'python-and-chatgpt-course-for-kids', 'data-analysis-from-scratch-with-chatgpt-course', 'analytics-python-chatgpt'],
    'российские нейросети': ['russian-neural-networks', 'russian-neural-networks-the-bestupdates', 'russian-neural-networks-course'],
    'китайские нейросети': ['chinese-neural-networks-course'],
    'deepseek': ['deepseek-r1-lesson'],
    
    # Промпт-инжиниринг
    'промпт': ['prompt-engineer-with-ai-course', 'prompt-engineer-ai', 'first-intensive-prompt-engineering', 'practikum-prompt-engineering'],
    'промпт-инжиниринг': ['prompt-engineer-with-ai-course', 'first-intensive-prompt-engineering', 'practikum-prompt-engineering'],
    'промпт инжиниринг': ['prompt-engineer-with-ai-course', 'first-intensive-prompt-engineering'],
    
    # Чат-боты
    'бот': ['chatbot-developer', 'chatbot-workshop', 'int-python', 'practicum-online-store-in-a-bot-using-ai'],
    'боты': ['chatbot-developer', 'chatbot-workshop', 'int-python', 'practicum-online-store-in-a-bot-using-ai'],
    'чат-бот': ['chatbot-developer', 'chatbot-workshop'],
    'чатбот': ['chatbot-developer', 'chatbot-workshop'],
    'создать бота': ['chatbot-developer', 'int-python'],
    'разработка ботов': ['chatbot-developer', 'int-python'],
    'телеграм бот': ['chatbot-developer', 'int-python'],
    'телеграм боты': ['chatbot-developer', 'int-python'],
    'telegram': ['chatbot-developer', 'int-python'],
    'telegram бот': ['chatbot-developer', 'int-python'],
    'изучить боты': ['chatbot-developer', 'int-python'],
    'как создать бота': ['chatbot-developer', 'int-python'],
    
    # Мобильная разработка
    'мобильное приложение': ['mobile-app-developer-online-course', 'mobile-app-in-flutter-flow-course', 'new-int-mob-flutterflow'],
    'мобильная разработка': ['mobile-app-developer-online-course', 'mobile-app-in-flutter-flow-course'],
    'flutter': ['mobile-app-in-flutter-flow-course', 'new-int-mob-flutterflow'],
    'flutterflow': ['mobile-app-in-flutter-flow-course', 'new-int-mob-flutterflow'],
    'приложение': ['mobile-app-developer-online-course', 'mobile-app-in-flutter-flow-course'],
    
    # Веб-дизайн
    'веб-дизайн': ['web-design-course', 'intensive-web-design', 'web-successful-career-in-web-design'],
    'дизайн': ['web-design-course', 'intensive-web-design', 'visual-content-with-ai-course'],
    'сайт': ['web-design-course', 'zerocoding-on-bubble-online-course'],
    
    # No-code платформы
    'bubble': ['zerocoding-on-bubble-online-course'],
    'directual': ['directual-online-course-from-zero-to-pro'],
    'airtable': ['shopify-course'],
    'no-code': ['zerocoding-on-bubble-online-course', 'directual-online-course-from-zero-to-pro'],
    'ноукод': ['zerocoding-on-bubble-online-course', 'directual-online-course-from-zero-to-pro'],
    'зерокод': ['zerocoding-on-bubble-online-course', 'directual-online-course-from-zero-to-pro'],
    
    # 1С разработка
    '1с': ['course-profession-1c-developer', '1c-intensiv'],
    '1c': ['course-profession-1c-developer', '1c-intensiv'],
    
    # Анализ данных
    'анализ данных': ['data-analysis-from-scratch-with-chatgpt-course', 'analytics-python-chatgpt'],
    'аналитик': ['data-analysis-from-scratch-with-chatgpt-course', 'analytics-python-chatgpt'],
    'данные': ['data-analysis-from-scratch-with-chatgpt-course', 'analytics-python-chatgpt'],
    
    # Инвестиции и финансы
    'инвестиции': ['couese-ai-for-investment', 'neural-networks-for-investments', 'online-investment-workshop', 'algo-trading-with-ai'],
    'инвестировать': ['couese-ai-for-investment', 'neural-networks-for-investments', 'online-investment-workshop'],
    'трейдинг': ['algo-trading-with-ai'],
    'алготрейдинг': ['algo-trading-with-ai'],
    'портфель': ['online-investment-workshop'],
    
    # Бизнес и предпринимательство
    'бизнес': ['start-your-business-with-ai', 'zerocoder-mentorship-for-ai-studio', 'zerocoder-premium-mentorship-for-luxury-studio'],
    'заработок': ['start-your-business-with-ai', 'neuromoney-2'],
    'нейроденьги': ['neuromoney-2'],
    'студия': ['zerocoder-mentorship-for-ai-studio', 'zerocoder-premium-mentorship-for-luxury-studio'],
    
    # Маркетинг
    'маркетинг': ['vibe-marketing', 'open-lesson-on-vibe-marketing-with-ai'],
    'вайб-маркетинг': ['vibe-marketing', 'open-lesson-on-vibe-marketing-with-ai'],
    'контент': ['visual-content-with-ai-course', 'neural-networks-for-visual-content'],
    
    # Для детей и подростков
    'дети': ['proficamp-online-summer-camp-for-kids', 'python-and-chatgpt-course-for-kids', 'scratch-programming-course-for-kids', 'python-ai-for-kids'],
    'детей': ['proficamp-online-summer-camp-for-kids', 'python-and-chatgpt-course-for-kids', 'scratch-programming-course-for-kids', 'python-ai-for-kids'],
    'детские': ['proficamp-online-summer-camp-for-kids', 'python-and-chatgpt-course-for-kids', 'scratch-programming-course-for-kids', 'python-ai-for-kids'],
    'детские курсы': ['proficamp-online-summer-camp-for-kids', 'python-and-chatgpt-course-for-kids', 'scratch-programming-course-for-kids', 'python-ai-for-kids'],
    'обучение детей': ['proficamp-online-summer-camp-for-kids', 'python-and-chatgpt-course-for-kids', 'scratch-programming-course-for-kids', 'python-ai-for-kids'],
    'подростки': ['python-developer-for-teenagers', 'neuroteen-program-for-teens', 'nteen-demo-2'],
    'школьники': ['python-developer-for-teenagers', 'python-and-chatgpt-course-for-kids'],
    'нейро teens': ['neuroteen-program-for-teens', 'nteen-demo-2'],
    'лагерь': ['proficamp-online-summer-camp-for-kids'],
    
    # Преподавание
    'преподаватель': ['neuro-for-teachers-course', 'workshop-on-neural-networks-for-teachers'],
    'учитель': ['neuro-for-teachers-course', 'workshop-on-neural-networks-for-teachers'],
    'образование': ['neuro-for-teachers-course'],
    
    # Карьера и консультации
    'карьера': ['career-consultation', 'web-successful-career-in-web-design', 'it-careers-without-borders'],
    'консультация': ['career-consultation'],
    'фриланс': ['freelance-and-project-work-python'],
    
    # Старшее поколение
    'пожилые': ['new-technology-for-older-adults-course'],
    'старшее поколение': ['new-technology-for-older-adults-course'],
    'возраст': ['new-technology-for-older-adults-course'],
    
    # Абонементы и общее
    'абонемент': ['subscription'],
    'подписка': ['subscription'],
    'все курсы': ['subscription'],
    'менторство': ['premium-mentorship-in-it-with-zerocoding-and-ai', 'zerocoder-mentorship-for-ai-studio'],
}

def normalize_text(text: str) -> str:
    """Нормализация текста для поиска"""
    # Приводим к нижнему регистру
    text = text.lower()
    # Убираем лишние символы, оставляем только буквы, цифры и пробелы
    text = re.sub(r'[^\w\s\-]', ' ', text)
    # Убираем множественные пробелы
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def find_file_by_pattern(pattern: str) -> str:
    """
    Ищет файл в директории по частичному совпадению имени
    
    Args:
        pattern: Часть имени файла для поиска
        
    Returns:
        Полное имя найденного файла или пустую строку
    """
    if not os.path.exists(COURSES_DIR):
        return ""
    
    files = os.listdir(COURSES_DIR)
    for file in files:
        if pattern in file.lower():
            return file
    
    return ""

def find_relevant_courses(user_message: str) -> List[str]:
    """
    Находит релевантные курсы по сообщению пользователя
    
    Args:
        user_message: Сообщение пользователя
        
    Returns:
        Список файлов курсов, релевантных запросу
    """
    normalized_message = normalize_text(user_message)
    found_patterns = set()
    
    # Ищем прямые совпадения ключевых слов
    for keyword, course_patterns in COURSE_KEYWORDS.items():
        if keyword in normalized_message:
            found_patterns.update(course_patterns)
    
    # Дополнительные проверки для составных фраз
    if any(word in normalized_message for word in ['создать', 'разработать', 'сделать']):
        if any(word in normalized_message for word in ['бот', 'telegram', 'телеграм']):
            found_patterns.update(['chatbot-developer', 'int-python'])
        if any(word in normalized_message for word in ['сайт', 'веб', 'интернет-магазин']):
            found_patterns.update(['web-design-course', 'zerocoding-on-bubble-online-course'])
        if any(word in normalized_message for word in ['приложение', 'мобильное']):
            found_patterns.update(['mobile-app-developer-online-course', 'mobile-app-in-flutter-flow-course'])
    
    if any(word in normalized_message for word in ['заработать', 'деньги', 'доход']):
        found_patterns.update(['start-your-business-with-ai', 'neuromoney-2'])
    
    if any(word in normalized_message for word in ['ребенок', 'сын', 'дочь', 'детям']):
        found_patterns.update(['proficamp-online-summer-camp-for-kids', 'python-and-chatgpt-course-for-kids'])
    
    # Ищем реальные файлы по паттернам
    found_files = []
    for pattern in found_patterns:
        real_file = find_file_by_pattern(pattern)
        if real_file:
            found_files.append(real_file)
    
    return found_files

def load_course_content(course_file: str) -> Dict[str, str]:
    """
    Загружает содержимое файла курса
    
    Args:
        course_file: Имя файла курса
        
    Returns:
        Словарь с информацией о курсе (title, url, content)
    """
    file_path = os.path.join(COURSES_DIR, course_file)
    
    if not os.path.exists(file_path):
        return {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Парсим структуру файла
        lines = content.split('\n')
        url = ""
        title = ""
        main_content = ""
        
        for i, line in enumerate(lines):
            if line.startswith('URL:'):
                url = line.replace('URL:', '').strip()
            elif line.startswith('ЗАГОЛОВОК:'):
                title = line.replace('ЗАГОЛОВОК:', '').strip()
            elif line.startswith('СОДЕРЖИМОЕ:'):
                # Берем все содержимое после этой строки
                main_content = '\n'.join(lines[i+1:])
                break
        
        return {
            'title': title,
            'url': url,
            'content': main_content,
            'file': course_file
        }
    
    except Exception as e:
        print(f"Ошибка при загрузке курса {course_file}: {e}")
        return {}

def search_courses(user_message: str, max_courses: int = 3) -> List[Dict[str, str]]:
    """
    Основная функция поиска курсов
    
    Args:
        user_message: Сообщение пользователя
        max_courses: Максимальное количество курсов для возврата
        
    Returns:
        Список словарей с информацией о найденных курсах
    """
    relevant_files = find_relevant_courses(user_message)
    
    if not relevant_files:
        return []
    
    courses = []
    for course_file in relevant_files[:max_courses]:
        course_info = load_course_content(course_file)
        if course_info:
            courses.append(course_info)
    
    return courses

def format_course_for_prompt(courses: List[Dict[str, str]]) -> str:
    """
    Форматирует информацию о курсах для добавления в промпт
    
    Args:
        courses: Список словарей с информацией о курсах
        
    Returns:
        Отформатированная строка для промпта
    """
    if not courses:
        return ""
    
    formatted = "\n\nИНФОРМАЦИЯ О РЕЛЕВАНТНЫХ КУРСАХ ZEROCODER:\n"
    formatted += "=" * 50 + "\n"
    
    for i, course in enumerate(courses, 1):
        formatted += f"\n{i}. {course['title']}\n"
        formatted += f"URL: {course['url']}\n"
        
        # Теперь добавляем ПОЛНОЕ содержимое курса
        formatted += f"ПОЛНОЕ ОПИСАНИЕ:\n{course['content']}\n"
        formatted += "-" * 50 + "\n"
    
    formatted += "\nИспользуй эту информацию для ответа пользователю. Информация о курсах будет сохранена в истории диалога. Если курс релевантен запросу - расскажи о нем подробно, включая стоимость, длительность и другие детали, и дай ссылку."
    
    return formatted

# Функция для тестирования
if __name__ == "__main__":
    # Тестовые запросы
    test_queries = [
        "Хочу изучить Python",
        "Как создать Telegram бота?",
        "Расскажи про нейросети",
        "Хочу заработать с помощью ИИ",
        "Курсы для детей",
        "Вайб-кодинг это что?"
    ]
    
    for query in test_queries:
        print(f"\n🔍 Запрос: {query}")
        courses = search_courses(query, max_courses=2)
        if courses:
            print(f"✅ Найдено курсов: {len(courses)}")
            for course in courses:
                print(f"  - {course['title']}")
        else:
            print("❌ Курсы не найдены") 