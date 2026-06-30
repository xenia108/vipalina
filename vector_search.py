#!/usr/bin/env python3
"""
Улучшенная векторная система поиска курсов
Работает с обработанными JSON файлами вместо сырых текстов
"""

import os
import json
import pickle
import numpy as np
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity
import openai

# Настройки OpenAI
openai_client = openai.OpenAI()

class VectorCourseSearchV2:
    def __init__(self, processed_courses_dir="processed_courses"):
        self.processed_dir = Path(processed_courses_dir)
        self.embeddings_cache_file = "course_embeddings_v2.pkl"
        self.courses_data = []
        self.embeddings = None
        
        # Загружаем данные курсов
        self.load_courses_data()
        
        # Загружаем или создаем эмбеддинги
        self.load_or_create_embeddings()
    
    def load_courses_data(self):
        """Загружает обработанные данные курсов из JSON файлов"""
        if not self.processed_dir.exists():
            print(f"❌ Папка {self.processed_dir} не найдена!")
            return
        
        json_files = list(self.processed_dir.glob("*.json"))
        self.courses_data = []
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    course_data = json.load(f)
                    course_data['file_id'] = json_file.stem
                    self.courses_data.append(course_data)
            except Exception as e:
                print(f"⚠️  Ошибка загрузки {json_file.name}: {e}")
        
        print(f"📚 Загружено курсов: {len(self.courses_data)}")
    
    def create_searchable_text(self, course_data):
        """Создает текст для поиска из структурированных данных курса"""
        searchable_parts = []
        
        # Основная информация
        searchable_parts.append(course_data.get('title', ''))
        searchable_parts.append(course_data.get('short_description', ''))
        searchable_parts.append(course_data.get('detailed_description', ''))
        searchable_parts.append(course_data.get('target_audience', ''))
        searchable_parts.append(course_data.get('category', ''))
        searchable_parts.append(course_data.get('level', ''))
        
        # Программа курса
        program = course_data.get('program', [])
        if isinstance(program, list):
            searchable_parts.extend(program)
        
        # Результаты обучения
        outcomes = course_data.get('outcomes', [])
        if isinstance(outcomes, list):
            searchable_parts.extend(outcomes)
        
        # FAQ вопросы и ответы
        faq = course_data.get('faq', [])
        if isinstance(faq, list):
            for item in faq:
                if isinstance(item, dict):
                    searchable_parts.append(item.get('question', ''))
                    searchable_parts.append(item.get('answer', ''))
        
        # Преподаватели
        instructors = course_data.get('instructors', [])
        if isinstance(instructors, list):
            searchable_parts.extend(instructors)
        
        return ' '.join(filter(None, searchable_parts))
    
    def get_embedding(self, text):
        """Получает эмбеддинг для текста через OpenAI API"""
        try:
            response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"❌ Ошибка получения эмбеддинга: {e}")
            return None
    
    def create_embeddings(self):
        """Создает эмбеддинги для всех курсов"""
        print("🔄 Создание эмбеддингов...")
        embeddings = []
        
        for i, course in enumerate(self.courses_data):
            searchable_text = self.create_searchable_text(course)
            embedding = self.get_embedding(searchable_text)
            
            if embedding:
                embeddings.append(embedding)
                print(f"✅ [{i+1}/{len(self.courses_data)}] {course.get('title', 'Неизвестно')}")
            else:
                print(f"❌ [{i+1}/{len(self.courses_data)}] Ошибка для {course.get('title', 'Неизвестно')}")
                embeddings.append([0] * 1536)  # Заглушка
        
        return np.array(embeddings)
    
    def save_embeddings(self, embeddings):
        """Сохраняет эмбеддинги в файл"""
        cache_data = {
            'embeddings': embeddings,
            'courses_data': self.courses_data,
            'version': 'v2'
        }
        
        with open(self.embeddings_cache_file, 'wb') as f:
            pickle.dump(cache_data, f)
        
        print(f"💾 Эмбеддинги сохранены в {self.embeddings_cache_file}")
    
    def load_embeddings(self):
        """Загружает эмбеддинги из файла"""
        try:
            with open(self.embeddings_cache_file, 'rb') as f:
                cache_data = pickle.load(f)
            
            if cache_data.get('version') == 'v2' and len(cache_data['courses_data']) == len(self.courses_data):
                self.embeddings = cache_data['embeddings']
                print(f"📄 Эмбеддинги загружены из кэша ({len(self.embeddings)} курсов)")
                return True
            else:
                print("⚠️  Кэш устарел, создаем новые эмбеддинги")
                return False
                
        except Exception as e:
            print(f"⚠️  Не удалось загрузить кэш: {e}")
            return False
    
    def load_or_create_embeddings(self):
        """Загружает эмбеддинги из кэша или создает новые"""
        if not self.load_embeddings():
            self.embeddings = self.create_embeddings()
            self.save_embeddings(self.embeddings)
    
    def search_courses(self, query, top_k=5):
        """Ищет курсы по запросу"""
        if self.embeddings is None or len(self.courses_data) == 0:
            return []
        
        # Получаем эмбеддинг запроса
        query_embedding = self.get_embedding(query)
        if not query_embedding:
            return []
        
        query_embedding = np.array(query_embedding).reshape(1, -1)
        
        # Вычисляем сходство
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]
        
        # Получаем топ результатов
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if similarities[idx] > 0.2:  # Порог релевантности (понижен для тестирования)
                course = self.courses_data[idx].copy()
                course['similarity_score'] = float(similarities[idx])
                results.append(course)
        
        return results
    
    def format_course_for_prompt(self, course_data):
        """Форматирует данные курса для промпта ИИ"""
        formatted = f"📚 **{course_data.get('title', 'Неизвестно')}**\n"
        
        # Краткое описание
        short_desc = course_data.get('short_description', '')
        if short_desc:
            formatted += f"🎯 {short_desc}\n\n"
        
        # Целевая аудитория  
        target = course_data.get('target_audience', '')
        if target:
            formatted += f"👥 **Для кого:** {target}\n\n"
        
        # Программа
        program = course_data.get('program', [])
        if program and isinstance(program, list):
            formatted += "📋 **Программа:**\n"
            for module in program[:5]:  # Максимум 5 модулей
                formatted += f"• {module}\n"
            formatted += "\n"
        
        # Результаты
        outcomes = course_data.get('outcomes', [])
        if outcomes and isinstance(outcomes, list):
            formatted += "🎓 **Чему научитесь:**\n"
            for outcome in outcomes[:4]:  # Максимум 4 результата
                formatted += f"• {outcome}\n"
            formatted += "\n"
        
        # Детали
        duration = course_data.get('duration', '')
        price = course_data.get('price', '')
        level = course_data.get('level', '')
        
        if duration or price or level:
            formatted += "ℹ️ **Детали:** "
            details = []
            if duration:
                details.append(f"Длительность: {duration}")
            if level:
                details.append(f"Уровень: {level}")
            if price and price != "Не указана":
                details.append(f"Цена: {price}")
            formatted += " | ".join(details) + "\n\n"
        
        # Ссылка на курс
        url = course_data.get('url', '')
        if url:
            formatted += f"🔗 **Ссылка:** {url}\n\n"
        
        # FAQ (только 2-3 самых важных)
        faq = course_data.get('faq', [])
        if faq and isinstance(faq, list):
            formatted += "❓ **Частые вопросы:**\n"
            for qa in faq[:3]:  # Максимум 3 вопроса
                if isinstance(qa, dict):
                    q = qa.get('question', '')
                    a = qa.get('answer', '')
                    if q and a:
                        formatted += f"• **{q}** {a}\n"
            formatted += "\n"
        
        return formatted
    
    def get_statistics(self):
        """Возвращает статистику по курсам"""
        if not self.courses_data:
            return "Нет данных о курсах"
        
        categories = {}
        levels = {}
        
        for course in self.courses_data:
            # Категории
            category = course.get('category', 'Неизвестно')
            categories[category] = categories.get(category, 0) + 1
            
            # Уровни
            level = course.get('level', 'Неизвестно')
            levels[level] = levels.get(level, 0) + 1
        
        stats = f"📊 **СТАТИСТИКА КУРСОВ**\n"
        stats += f"📚 Всего курсов: {len(self.courses_data)}\n\n"
        
        stats += "🏷️ **По категориям:**\n"
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            stats += f"• {cat}: {count}\n"
        
        stats += "\n📈 **По уровням:**\n"
        for level, count in sorted(levels.items(), key=lambda x: x[1], reverse=True):
            stats += f"• {level}: {count}\n"
        
        return stats

    def get_full_course_content(self, course_data):
        """Получает полное содержимое исходного файла курса из parsed_pages/"""
        try:
            # Получаем ID файла из данных курса
            file_id = course_data.get('file_id', '')
            if not file_id:
                return f"⚠️ Не найден ID файла для курса {course_data.get('title', 'Неизвестно')}"
            
            # Ищем исходный файл в parsed_pages/
            parsed_pages_dir = Path("parsed_pages")
            
            # Ищем файл с соответствующим ID
            txt_files = list(parsed_pages_dir.glob("*.txt"))
            matching_file = None
            
            for txt_file in txt_files:
                if txt_file.stem == file_id:
                    matching_file = txt_file
                    break
            
            if not matching_file:
                return f"⚠️ Исходный файл не найден для курса {course_data.get('title', 'Неизвестно')}"
            
            # Читаем полное содержимое
            with open(matching_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Добавляем заголовок для контекста
            title = course_data.get('title', 'Неизвестно')
            url = course_data.get('url', '')
            
            formatted_content = f"📚 ПОЛНАЯ ИНФОРМАЦИЯ О КУРСЕ: {title}\n"
            if url:
                formatted_content += f"🔗 Ссылка: {url}\n"
            formatted_content += "=" * 80 + "\n\n"
            formatted_content += content
            
            return formatted_content
            
        except Exception as e:
            return f"❌ Ошибка чтения файла курса: {e}"


def main():
    """Тестирование системы поиска"""
    print("🚀 ТЕСТИРОВАНИЕ ВЕКТОРНОГО ПОИСКА V2")
    print("=" * 50)
    
    # Создаем систему поиска
    search_system = VectorCourseSearchV2()
    
    if not search_system.courses_data:
        print("❌ Нет обработанных курсов для поиска!")
        print("💡 Сначала запустите course_data_processor.py")
        return
    
    # Статистика
    print(search_system.get_statistics())
    print("\n" + "=" * 50)
    
    # Тестовые запросы
    test_queries = [
        "Python программирование",
        "нейросети для детей", 
        "создание ботов",
        "веб-дизайн",
        "мобильные приложения",
        "инвестиции и торговля"
    ]
    
    for query in test_queries:
        print(f"\n🔍 **Запрос:** {query}")
        print("-" * 30)
        
        results = search_system.search_courses(query, top_k=3)
        
        if not results:
            print("❌ Курсы не найдены")
            continue
        
        for i, course in enumerate(results, 1):
            title = course.get('title', 'Неизвестно')
            score = course.get('similarity_score', 0)
            category = course.get('category', 'Неизвестно')
            print(f"{i}. **{title}** ({category}) - {score:.3f}")


if __name__ == "__main__":
    main() 