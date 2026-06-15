#!/usr/bin/env python3
"""
Скрипт для обработки и структурирования данных курсов с помощью GPT
Убирает лишнюю информацию и создает структурированные описания с FAQ
"""

import os
import json
from openai import OpenAI
from pathlib import Path
import time

class CourseDataProcessor:
    def __init__(self):
        self.client = OpenAI()  # Автоматически использует OPENAI_API_KEY из окружения
        self.input_dir = Path("parsed_pages")
        self.output_dir = Path("processed_courses")
        self.processed_count = 0
        self.total_files = 0
        
        # Создаем папку для обработанных курсов
        self.output_dir.mkdir(exist_ok=True)
        
    def get_processing_prompt(self):
        """Промпт для GPT для обработки данных курса"""
        return """
Ты - эксперт по анализу и структурированию информации о курсах. 

ЗАДАЧА: Обработай текст страницы курса, убери всю лишнюю информацию и создай структурированное описание.

ВАЖНО: В начале каждого файла есть URL в формате "URL: https://zerocoder.ru/...". 
Извлеки этот URL и добавь его в поле "url" в JSON.

УБЕРИ:
- Навигационные меню
- Футеры и хедеры сайта
- Общую информацию о платформе/университете
- Кнопки и ссылки на покупку
- Техническую информацию сайта
- Дублированную информацию

ОСТАВЬ И СТРУКТУРИРУЙ:
- URL курса (извлеки из первой строки)
- Название курса
- Краткое описание (1-2 предложения)
- Подробное описание 
- Целевая аудитория
- Что изучается (программа курса)
- Преподаватели (если указаны)
- Длительность
- Формат обучения
- Стоимость (ОСОБОЕ ВНИМАНИЕ К ЦЕНАМ - см. ниже)
- Результаты обучения
- Требования к студентам

ОСОБОЕ ВНИМАНИЕ К ЦЕНАМ:
- Если курс платный, извлеки ВСЕ доступные тарифы в формате: "Название тарифа - Полная цена - Цена при рассрочке"
- Если рассрочка не указана, пиши только "Название тарифа - Полная цена"
- Если есть несколько тарифов, перечисли их все
- Если это бесплатный вебинар/интенсив, напиши "Бесплатный вебинар" или "Бесплатный интенсив"
- Если цена не указана, напиши "Цена не указана"

СОЗДАЙ СТРУКТУРИРОВАННЫЙ JSON:
{
  "title": "Название курса",
  "short_description": "Краткое описание курса",
  "detailed_description": "Подробное описание",
  "target_audience": "Для кого этот курс",
  "program": ["Модуль 1", "Модуль 2", "..."],
  "instructors": ["Имя преподавателя 1", "..."],
  "duration": "Длительность курса",
  "format": "Формат обучения",
  "pricing": {
    "type": "paid/free",
    "details": "Детальная информация о ценах в формате: Тариф - Полная цена - Цена при рассрочке. Для бесплатных: Бесплатный вебинар/интенсив",
    "tariffs": [
      {
        "name": "Название тарифа",
        "full_price": "Полная цена",
        "installment_price": "Цена при рассрочке (если есть)"
      }
    ]
  },
  "outcomes": ["Результат 1", "Результат 2", "..."],
  "requirements": "Требования к студентам",
  "category": "Категория курса (Python, AI, Дизайн, etc)",
  "level": "Уровень (Новичок/Средний/Продвинутый)",
  "url": "Ссылка на курс",
  "faq": [
    {
      "question": "Часто задаваемый вопрос 1?",
      "answer": "Ответ на вопрос 1"
    },
    {
      "question": "Часто задаваемый вопрос 2?", 
      "answer": "Ответ на вопрос 2"
    }
  ]
}

СОЗДАЙ 5-7 РЕЛЕВАНТНЫХ FAQ основываясь на содержании курса.

Отвечай ТОЛЬКО валидным JSON без дополнительного текста.
"""

    def extract_json_from_response(self, response_text):
        """Извлекает JSON из ответа GPT, убирая markdown разметку"""
        # Убираем возможные markdown блоки
        if "```json" in response_text:
            # Ищем JSON блок между ```json и ```
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end != -1:
                return response_text[start:end].strip()
        elif "```" in response_text:
            # Ищем любой блок кода между ```
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end != -1:
                return response_text[start:end].strip()
        
        # Ищем JSON объект по фигурным скобкам
        start = response_text.find("{")
        if start != -1:
            # Находим закрывающую скобку, учитывая вложенность
            brace_count = 0
            for i, char in enumerate(response_text[start:], start):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return response_text[start:i+1]
        
        # Если ничего не найдено, возвращаем как есть
        return response_text.strip()

    def process_course_file(self, file_path):
        """Обрабатывает один файл курса"""
        try:
            # Читаем исходный файл
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not content.strip():
                print(f"⚠️  Пустой файл: {file_path.name}")
                return False
                
            print(f"🔄 Обрабатываю: {file_path.name}")
            
            # Отправляем в GPT
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.get_processing_prompt()},
                    {"role": "user", "content": f"Обработай данные курса:\n\n{content}"}
                ],
                temperature=0.1,
                max_tokens=4000
            )
            
            raw_response = response.choices[0].message.content.strip()
            
            # Извлекаем JSON из ответа (убираем markdown разметку если есть)
            processed_data = self.extract_json_from_response(raw_response)
            
            # Проверяем что получили валидный JSON
            try:
                json.loads(processed_data)
            except json.JSONDecodeError:
                print(f"❌ Ошибка парсинга JSON для {file_path.name}")
                print(f"🔍 Ответ GPT: {raw_response[:200]}...")
                return False
            
            # Сохраняем обработанный файл
            output_file = self.output_dir / f"{file_path.stem}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(processed_data)
            
            print(f"✅ Сохранен: {output_file.name}")
            self.processed_count += 1
            
            # Небольшая пауза чтобы не превышать rate limits
            time.sleep(1)
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при обработке {file_path.name}: {e}")
            return False
    
    def process_all_courses(self):
        """Обрабатывает все файлы курсов"""
        if not self.input_dir.exists():
            print(f"❌ Папка {self.input_dir} не найдена!")
            return
        
        # Получаем все txt файлы
        txt_files = list(self.input_dir.glob("*.txt"))
        self.total_files = len(txt_files)
        
        if self.total_files == 0:
            print("❌ Не найдено файлов для обработки!")
            return
        
        print(f"📂 Найдено файлов: {self.total_files}")
        print(f"📁 Папка для результатов: {self.output_dir}")
        
        # Для тестирования ограничиваем количество файлов
        test_mode = input("🧪 Тестовый режим (только 3 файла)? (y/n): ").lower() == 'y'
        if test_mode:
            txt_files = txt_files[:3]
            print(f"🧪 Тестовый режим: обрабатываем {len(txt_files)} файлов")
        
        print("-" * 50)
        
        # Обрабатываем каждый файл
        for i, file_path in enumerate(txt_files, 1):
            print(f"📄 [{i}/{len(txt_files)}] {file_path.name}")
            self.process_course_file(file_path)
        
        print("-" * 50)
        print(f"🎉 Обработка завершена!")
        print(f"✅ Успешно обработано: {self.processed_count}/{self.total_files}")
        print(f"📁 Результаты сохранены в: {self.output_dir}")
    
    def create_summary_report(self):
        """Создает сводный отчет по обработанным курсам"""
        if not self.output_dir.exists():
            print("❌ Папка с обработанными курсами не найдена!")
            return
        
        json_files = list(self.output_dir.glob("*.json"))
        if not json_files:
            print("❌ Нет обработанных файлов для анализа!")
            return
        
        categories = {}
        levels = {}
        total_courses = 0
        
        print("\n📊 АНАЛИЗ ОБРАБОТАННЫХ КУРСОВ:")
        print("-" * 50)
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                total_courses += 1
                
                # Подсчет по категориям
                category = data.get('category', 'Неизвестно')
                categories[category] = categories.get(category, 0) + 1
                
                # Подсчет по уровням
                level = data.get('level', 'Неизвестно')
                levels[level] = levels.get(level, 0) + 1
                
            except Exception as e:
                print(f"⚠️  Ошибка чтения {json_file.name}: {e}")
        
        print(f"📚 Всего курсов: {total_courses}")
        
        print(f"\n🏷️  Категории:")
        for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            print(f"   • {category}: {count}")
        
        print(f"\n📈 Уровни сложности:")
        for level, count in sorted(levels.items(), key=lambda x: x[1], reverse=True):
            print(f"   • {level}: {count}")


def main():
    """Основная функция"""
    print("🚀 ОБРАБОТЧИК ДАННЫХ КУРСОВ")
    print("=" * 50)
    
    # Проверяем наличие API ключа в переменных окружения
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY не найден в переменных окружения!")
        print("💡 Установите переменную окружения: export OPENAI_API_KEY='your-key'")
        return
    
    print("✅ OpenAI API ключ найден")
    
    # Создаем обработчик
    processor = CourseDataProcessor()
    
    # Спрашиваем подтверждение
    print(f"📂 Исходная папка: {processor.input_dir}")
    print(f"📁 Папка результатов: {processor.output_dir}")
    
    confirm = input("\n❓ Начать обработку? (y/n): ").lower()
    if confirm != 'y':
        print("❌ Обработка отменена")
        return
    
    # Обрабатываем курсы
    processor.process_all_courses()
    
    # Создаем отчет
    processor.create_summary_report()


if __name__ == "__main__":
    main() 