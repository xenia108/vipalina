"""
Конфигурация курсов для VipAlina.
Маппинг тегов GetCourse на внутренние названия курсов для Airtable, KPI и трекеров.
"""

from typing import Dict, Any, Optional
import logging
import re

logger = logging.getLogger('vipalina_telethon')


class CourseConfig:
    """
    Конфигурация курсов с маппингом тегов и параметрами для трекеров.
    """
    
    # Маппинг: тег из GetCourse → данные курса
    COURSE_MAPPING = {
        # Нейросети
        "[neuro-law] Тариф \"Стратегический\"": {
            "internal_name": "Нейросети для юристов (корпоративный)",
            "airtable_name": "neuro-law",
            "kpi_name": "neuro-law",
            "tracker_name": "Нейросети для юристов",
            "lesson_count": 40,
            "access_days": 365,  # 0 = навсегда
            "support_days": 180,
            "monthly_target": 7,  # Целевое количество уроков в месяц
            "monthly_minimum": 7  # Минимум уроков в месяц
        },
        "[neuro-law] Тариф \"Базовый\"": {
            "internal_name": "Нейросети для юристов",
            "airtable_name": "neuro-law",
            "kpi_name": "neuro-law",
            "tracker_name": "Нейросети для юристов",
            "lesson_count": 40,
            "access_days": 180,
            "support_days": 90,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        
        # Python
        "[python-pro] Тариф \"VIP\"": {
            "internal_name": "Python PRO",
            "airtable_name": "Питон",
            "kpi_name": "Питон",
            "tracker_name": "Python PRO",
            "lesson_count": 120,
            "access_days": 0,  # Навсегда
            "support_days": 365,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        "[python-pro] Тариф \"Базовый\"": {
            "internal_name": "Python Базовый",
            "airtable_name": "Питон",
            "kpi_name": "Питон",
            "tracker_name": "Python Базовый",
            "lesson_count": 60,
            "access_days": 180,
            "support_days": 90,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        
        # Мобильная разработка
        "[mobile-dev] Тариф \"VIP+\"": {
            "internal_name": "Мобильная разработка VIP+",
            "airtable_name": "VIP+ мобилка",
            "kpi_name": "VIP+ мобилка",
            "tracker_name": "Мобильная разработка",
            "lesson_count": 100,
            "access_days": 0,
            "support_days": 365,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        
        # Аналитика данных
        "[data-analytics] Тариф \"VIP+\"": {
            "internal_name": "Аналитика данных VIP+",
            "airtable_name": "VIP+ аналитик",
            "kpi_name": "VIP+ аналитик",
            "tracker_name": "Аналитика данных",
            "lesson_count": 80,
            "access_days": 0,
            "support_days": 365,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        
        # Промпт-инженер
        "[prompt-engineer] Тариф \"Корпоративный\"": {
            "internal_name": "Промпт-инженер (корпоративный)",
            "airtable_name": "Промпт Корпоратив",
            "kpi_name": "Промпт Корпоратив",
            "tracker_name": "Промпт-инженер",
            "lesson_count": 50,
            "access_days": 365,
            "support_days": 180,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        "[prompt-engineer] Тариф \"Базовый\"": {
            "internal_name": "Промпт-инженер",
            "airtable_name": "Промпт-инженер",
            "kpi_name": "Промпт-инженер",
            "tracker_name": "Промпт-инженер",
            "lesson_count": 30,
            "access_days": 180,
            "support_days": 90,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        
        # Веб-разработка
        "[web-dev] Тариф \"VIP+\"": {
            "internal_name": "Веб-разработка VIP+",
            "airtable_name": "VIP+ веб",
            "kpi_name": "VIP+ веб",
            "tracker_name": "Веб-разработка",
            "lesson_count": 110,
            "access_days": 0,
            "support_days": 365,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        
        # Чат-боты
        "[chatbot] Тариф VIP": {
            "internal_name": "Чат-боты VIP",
            "airtable_name": "Чат-боты",
            "kpi_name": "Чат-боты, VIP",
            "tracker_name": "Чат-боты",
            "lesson_count": 70,
            "access_days": 0,  # Навсегда
            "support_days": 365,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        "[chatbot] VIP с гарантией": {
            "internal_name": "Чат-боты VIP с гарантией",
            "airtable_name": "Чат-боты",
            "kpi_name": "Чат-боты, VIP",
            "tracker_name": "Чат-боты",
            "lesson_count": 70,
            "access_days": 0,  # Навсегда
            "support_days": 365,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        
        # AI-консалтинг
        "[ai-consulting] Тариф \"Корпоративный\"": {
            "internal_name": "AI-Консалтинг (корпоративный)",
            "airtable_name": "Al-Консалтинг \"Корп\"",
            "kpi_name": "Al-Консалтинг \"Корп\"",
            "tracker_name": "AI-Консалтинг",
            "lesson_count": 45,
            "access_days": 365,
            "support_days": 180,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        
        # Вайб-маркетинг
        "[vibe-marketing] Тариф \"Корпоративный\"": {
            "internal_name": "Вайб-маркетинг (корпоративный)",
            "airtable_name": "Вайб маркетинг Корп",
            "kpi_name": "Вайб маркетинг Корп",
            "tracker_name": "Вайб-маркетинг",
            "lesson_count": 30,
            "access_days": 365,
            "support_days": 180,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        
        # Лухари
        "[luhari-career]": {
            "internal_name": "Лухари Карьера",
            "airtable_name": "Лухари Карьера",
            "kpi_name": "Лухари Карьера",
            "tracker_name": "Лухари Карьера",
            "lesson_count": 25,
            "access_days": 180,
            "support_days": 90,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
        "[luhari-startup]": {
            "internal_name": "Лухари Стартап",
            "airtable_name": "Лухари Стартап",
            "kpi_name": "Лухари Стартап",
            "tracker_name": "Лухари Стартап",
            "lesson_count": 30,
            "access_days": 180,
            "support_days": 90,
            "monthly_target": 7,
            "monthly_minimum": 7
        },
    }
    
    @classmethod
    def get_course_by_tag(cls, getcourse_tag: str) -> Optional[Dict[str, Any]]:
        """
        Получает данные курса по тегу из GetCourse.
        
        Args:
            getcourse_tag: Тег курса из GetCourse (например, "[neuro-law] Тариф \"Стратегический\"")
            
        Returns:
            Dict с данными курса или None если не найдено
        """
        # Игнорируем внутренние приписки (Первый платеж, Вн. Рассрочка и т.д.)
        cleaned_tag = cls._clean_course_tag(getcourse_tag)
        
        # Прямое совпадение
        if cleaned_tag in cls.COURSE_MAPPING:
            course_data = cls.COURSE_MAPPING[cleaned_tag].copy()
            course_data['getcourse_tag'] = cleaned_tag
            return course_data
        
        # Пытаемся найти точное совпадение по основной части тега
        # (без внутренних приписок)
        base_tag = cls._extract_base_tag(cleaned_tag)
        for tag, data in cls.COURSE_MAPPING.items():
            base_mapped_tag = cls._extract_base_tag(tag)
            if base_mapped_tag == base_tag:
                logger.info(f"Найдено точное совпадение по основной части курса: '{cleaned_tag}' -> '{tag}'")
                course_data = data.copy()
                course_data['getcourse_tag'] = cleaned_tag
                return course_data
        
        logger.warning(f"Курс не найден в маппинге: '{cleaned_tag}'")
        return None
    
    @classmethod
    def get_airtable_course_name(cls, getcourse_tag: str) -> str:
        """Получает название курса для Airtable по тегу GetCourse"""
        course = cls.get_course_by_tag(getcourse_tag)
        return course['airtable_name'] if course else getcourse_tag
    
    @classmethod
    def get_kpi_course_name(cls, getcourse_tag: str) -> str:
        """Получает название курса для KPI Sheets по тегу GetCourse"""
        course = cls.get_course_by_tag(getcourse_tag)
        return course['kpi_name'] if course else getcourse_tag
    
    @classmethod
    def get_tracker_course_name(cls, getcourse_tag: str) -> str:
        """Получает название курса для трекера по тегу GetCourse"""
        course = cls.get_course_by_tag(getcourse_tag)
        return course['tracker_name'] if course else getcourse_tag
    
    @classmethod
    def get_course_params(cls, getcourse_tag: str) -> Dict[str, Any]:
        """
        Получает параметры курса для создания трекера.
        
        Returns:
            Dict с параметрами: lesson_count, access_days, support_days, monthly_target, monthly_minimum
        """
        course = cls.get_course_by_tag(getcourse_tag)
        if not course:
            # Дефолтные значения если курс не найден
            return {
                'lesson_count': 50,
                'access_days': 180,
                'support_days': 90,
                "monthly_target": 7,
                'monthly_minimum': 7
            }
        
        return {
            'lesson_count': course['lesson_count'],
            'access_days': course['access_days'],
            'support_days': course['support_days'],
            'monthly_target': course['monthly_target'],
            'monthly_minimum': course['monthly_minimum']
        }
    
    @classmethod
    def _clean_course_tag(cls, getcourse_tag: str) -> str:
        """
        Очищает тег курса от внутренних приписок.
        
        Args:
            getcourse_tag: Исходный тег курса
            
        Returns:
            Очищенный тег курса
        """
        # Список внутренних приписок для игнорирования (в любом регистре)
        internal_additions = [
            'первый платеж',
            'вн. рассрочка',
            'внутренняя рассрочка',
            'рассрочка'
        ]
        
        # Очищаем тег от внутренних приписок
        cleaned_tag = getcourse_tag
        for addition in internal_additions:
            # Удаляем приписку в любом регистре
            pattern = r'[.\s]*' + re.escape(addition) + r'[.\s]*'
            cleaned_tag = re.sub(pattern, '', cleaned_tag, flags=re.IGNORECASE)
        
        # Убираем лишние точки и пробелы в конце
        cleaned_tag = re.sub(r'[.\s]+$', '', cleaned_tag)
        
        return cleaned_tag.strip()
    
    @classmethod
    def _extract_base_tag(cls, getcourse_tag: str) -> str:
        """
        Извлекает основную часть тега курса (без тарифа).
        
        Args:
            getcourse_tag: Тег курса
            
        Returns:
            Основная часть тега курса
        """
        # Извлекаем основную часть тега (все квадратные скобки в начале)
        match = re.match(r'^(\[.*?\]\s*)+', getcourse_tag)
        if match:
            return match.group(0).strip()
        # Если нет квадратных скобок, возвращаем всё до первого пробела
        match = re.match(r'^([^\s]+)', getcourse_tag)
        if match:
            return match.group(1)
        return getcourse_tag
    
    @classmethod
    def list_all_courses(cls) -> list:
        """Возвращает список всех доступных курсов"""
        return list(cls.COURSE_MAPPING.keys())
    
    @classmethod
    def add_custom_course(cls, getcourse_tag: str, course_data: Dict[str, Any]):
        """
        Добавляет кастомный курс в маппинг (для динамического добавления).
        
        Args:
            getcourse_tag: Тег из GetCourse
            course_data: Данные курса
        """
        cls.COURSE_MAPPING[getcourse_tag] = course_data
        logger.info(f"✅ Добавлен кастомный курс: {getcourse_tag}")

# Функция для быстрого доступа
def get_course_config(getcourse_tag: str) -> Optional[Dict[str, Any]]:
    """Быстрый доступ к конфигурации курса"""
    return CourseConfig.get_course_by_tag(getcourse_tag)
