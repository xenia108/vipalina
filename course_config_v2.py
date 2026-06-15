"""
Конфигурация курсов для VipAlina v2.
Маппинг тегов GetCourse на внутренние названия курсов для Airtable, KPI и трекеров.
Данные импортируются из автоматически сгенерированного файла.
"""

from typing import Dict, Any, Optional, List
import logging
import re
from datetime import datetime

# Импортируем сгенерированный маппинг
from course_mapping_generated import COURSE_MAPPING

logger = logging.getLogger('vipalina_telethon')


class CourseConfig:
    """
    Конфигурация курсов с маппингом тегов и параметрами для трекеров.
    Использует данные из листа 'Условия курсов' шаблона трекера.
    """
    
    # Маппинг импортируется из course_mapping_generated.py
    COURSE_MAPPING = COURSE_MAPPING
    
    # Словарь для хранения неизвестных курсов, ожидающих маппинга
    UNKNOWN_COURSES = {}
    
    # Состояние для неоднозначных курсов (когда найдено несколько кандидатов)
    _ambiguous_course_tag: Optional[str] = None
    _ambiguous_candidates: Optional[List[Dict[str, Any]]] = None
    
    @classmethod
    def register_unknown_course(cls, getcourse_tag: str, student_data: Dict[str, Any] = None) -> str:
        """
        Регистрирует неизвестный курс для последующего маппинга.
        
        Args:
            getcourse_tag: Тег курса из GetCourse
            student_data: Данные студента (опционально)
            
        Returns:
            request_id для отслеживания запроса
        """
        import uuid
        request_id = str(uuid.uuid4())
        
        cls.UNKNOWN_COURSES[request_id] = {
            'getcourse_tag': getcourse_tag,
            'student_data': student_data,
            'status': 'pending'
        }
        
        logger.info(f"📝 Зарегистрирован неизвестный курс: {getcourse_tag} (request_id: {request_id[:8]}...)")
        return request_id
    
    @classmethod
    def _load_from_sheets_cache(cls) -> bool:
        """
        Загружает маппинг курсов напрямую из Google Sheets (с кэшированием).
        Обновляет COURSE_MAPPING из листа "Условия курсов" шаблона трекера.
        
        Returns:
            True если успешно загружено
        """
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            import time
            
            # Проверяем кэш (5 минут)
            current_time = time.time()
            cache_ttl = 300  # 5 минут
            
            if hasattr(cls, '_cache_timestamp'):
                if current_time - cls._cache_timestamp < cache_ttl:
                    logger.debug("ℹ️ Используем кэшированный маппинг курсов")
                    return True
            
            logger.info("🔄 Загрузка маппинга курсов из Google Sheets...")
            
            # Подключение к Google Sheets
            scopes = ['https://www.googleapis.com/auth/spreadsheets']
            credentials = Credentials.from_service_account_file(
                'vipalina_google_service_account.json',
                scopes=scopes
            )
            gc = gspread.authorize(credentials)
            
            # Шаблон трекера
            template_id = '1gH1Sd7BCeUFBqufXUy63nVjWPcNmGNq312iL8-_Y_rQ'
            template = gc.open_by_key(template_id)
            conditions_sheet = template.worksheet('Условия курсов')
            
            # Читаем все данные
            all_data = conditions_sheet.get_all_values()
            
            if len(all_data) < 2:
                logger.warning("⚠️ Нет данных в листе 'Условия курсов'")
                return False
            
            # Заголовки
            headers = [h.strip() for h in all_data[0]]
            col_indices = {h: i for i, h in enumerate(headers)}
            
            # Обновляем маппинг
            new_mapping = {}
            
            for row in all_data[1:]:
                if not row or not row[0].strip():
                    continue
                
                course_tag = row[0].strip()
                
                def get_cell(col_name, default=""):
                    idx = col_indices.get(col_name, -1)
                    if idx >= 0 and idx < len(row):
                        return row[idx].strip()
                    return default
                
                internal_name = get_cell('Название для AT, KPI Ultra, трекера и группы в телеграм', course_tag)
                
                def safe_int(value, default=0):
                    """Безопасное преобразование в int, обрабатывает 'Навсегда' и другие текстовые значения"""
                    if not value or value == '':
                        return default
                    value_lower = value.lower().strip()
                    if any(text in value_lower for text in ['навсегда', 'бессрочно', 'forever', 'unlimited']):
                        return 999  # Представляем "навсегда" как 999 месяцев
                    try:
                        return int(float(value))
                    except ValueError:
                        return default
                
                new_mapping[course_tag] = {
                    'internal_name': internal_name,
                    'tracker_name': internal_name,
                    'kpi_name': internal_name,
                    'airtable_name': internal_name,
                    'gant_sheet': get_cell('Название листа в таблице ГАНТ', ''),
                    'lesson_count': safe_int(get_cell('Количество уроков', '0')),
                    'access_months': safe_int(get_cell('Доступ к платформе (мес)', '0')),
                    'curator_support_months': safe_int(get_cell('Поддержка куратора (мес)', '0')),
                    'vip_support_months': safe_int(get_cell('Поддержка VIP, обучение+окупаемость (мес)', '0')),
                    'program_type': get_cell('Тип программы', 'regular')
                }
                
                # Отладка для VIP Навсегда
                if 'навсегда' in course_tag.lower() or 'навсегда' in internal_name.lower():
                    logger.info(f"📊 DEBUG LOAD: {course_tag} -> program_type={get_cell('Тип программы', 'regular')}")
            
            # Сохраняем временные соответствия перед обновлением
            temp_mapping = {}
            for tag, data in cls.COURSE_MAPPING.items():
                # Временные соответствия не имеют всех полей
                if 'getcourse_tag' in data or 'internal_name' in data:
                    temp_mapping[tag] = data
            
            # Обновляем маппинг
            cls.COURSE_MAPPING = new_mapping
            # Восстанавливаем временные соответствия
            cls.COURSE_MAPPING.update(temp_mapping)
            cls._cache_timestamp = current_time
            
            logger.info(f"✅ Загружено {len(new_mapping)} курсов из Google Sheets")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки маппинга из Google Sheets: {e}")
            # Используем статичный маппинг как fallback
            return False
    
    @classmethod
    def _extract_course_ids(cls, getcourse_tag: str) -> List[str]:
        """
        Извлекает все идентификаторы курса из тега GetCourse.
        
        Args:
            getcourse_tag: Тег курса из GetCourse
            
        Returns:
            List[str] список идентификаторов курса
        """
        # Ищем все идентификаторы в квадратных скобках
        course_ids = re.findall(r'\[([^\]]+)\]', getcourse_tag.lower())
        return course_ids
    
    @classmethod
    def _normalize_course_tag(cls, getcourse_tag: str) -> str:
        """
        Нормализует тег курса для сравнения.
        Убирает лишние пробелы и точки в конце, приводит к нижнему регистру.
        
        Args:
            getcourse_tag: Тег курса из GetCourse
            
        Returns:
            Нормализованный тег курса
        """
        # Приводим к нижнему регистру
        normalized = getcourse_tag.lower().strip()
        
        # Убираем точки в конце (важно для [club] Тариф VIP Навсегда.)
        normalized = normalized.rstrip('.')
        
        return normalized
    
    @classmethod
    def _normalize_name_for_exact_match(cls, name: str) -> str:
        """Нормализация полного названия курса для точного сравнения.
        Не удаляет VIP / корпоративные маркеры, только приводит к нижнему регистру
        и схлопывает пробелы / точки на конце."""
        if not name:
            return ""
        text = name.strip()
        # Схлопываем повторяющиеся пробелы
        text = re.sub(r"\s+", " ", text)
        # Приводим к нижнему регистру и убираем точку в конце
        text = text.lower().rstrip('.')
        return text
    
    @classmethod
    def _strip_noise_phrases(cls, name: str) -> str:
        """Удаляет из строки курсa шумовые слова (подарок/рассрочка/первый платеж и т.п.),
        сохраняя при этом VIP / VIP Плюс / VIP с гарантией / корпоративный.
        Используется для повторного поиска, когда в названии есть дополнительные пометки.
        """
        if not name:
            return ""
        text = name.lower()
        # Убираем кавычки, оставляем скобки и слова VIP
        text = re.sub(r'["]', ' ', text)
        # Список шумовых фраз, которые можно игнорировать
        noise_phrases = [
            'курс в подарок',
            'в подарок',
            'подарок',
            'первый платеж',
            'первый платёж',
            'рассрочка',
            'вн. рассрочка',
            'вн рассрочка',
            'внутренняя рассрочка',
        ]
        for phrase in noise_phrases:
            if phrase in text:
                text = text.replace(phrase, ' ')
        # Схлопываем пробелы и убираем точки/запятые в конце
        text = re.sub(r'[,.]+', ' ', text)
        text = re.sub(r"\s+", " ", text).strip().rstrip('.')
        return text
    
    @classmethod
    def _match_course_by_name(cls, getcourse_tag: str) -> Optional[Dict[str, Any]]:
        """Пытается найти курс по полному названию из GetCourse в колонке A листа
        "Условия курсов" с учётом шумовых слов (подарок, первый платеж, рассрочка).
        
        Логика:
        1. Пытаемся найти точное совпадение по полной строке (после лёгкой нормализации).
        2. Если не нашли, пробуем сравнить строку без шумовых фраз.
        3. Если найден уникальный кандидат — возвращаем его.
        4. Если кандидатов несколько или ничего не найдено — возвращаем None,
           чтобы дальше сработал поиск по тегу [] и стандартный unknown_course handler.
        """
        if not cls.COURSE_MAPPING:
            return None
        
        # 1. Точное совпадение (с нормализацией пробелов/регистра)
        normalized_input = cls._normalize_name_for_exact_match(getcourse_tag)
        normalized_mapping: Dict[str, Dict[str, Any]] = {}
        for key, data in cls.COURSE_MAPPING.items():
            norm_key = cls._normalize_name_for_exact_match(key)
            if norm_key not in normalized_mapping:
                normalized_mapping[norm_key] = data
            else:
                # Если есть дубликаты, логируем, но продолжаем
                logger.debug(f"⚠️ Дубликат названия курса в маппинге: '{key}'")
        if normalized_input in normalized_mapping:
            course_data = normalized_mapping[normalized_input].copy()
            course_data['getcourse_tag'] = getcourse_tag
            logger.info(f"✅ Найден курс по точному совпадению названия: {getcourse_tag} -> {course_data['internal_name']}")
            return course_data
        
        # 2. Повторный поиск без шумовых слов (подарок, рассрочка, первый платеж)
        cleaned_input = cls._strip_noise_phrases(getcourse_tag)
        if not cleaned_input or cleaned_input == normalized_input:
            return None
        
        cleaned_mapping: Dict[str, list[tuple[str, Dict[str, Any]]]] = {}
        for key, data in cls.COURSE_MAPPING.items():
            cleaned_key = cls._strip_noise_phrases(key)
            if not cleaned_key:
                continue
            cleaned_mapping.setdefault(cleaned_key, []).append((key, data))
        
        if cleaned_input in cleaned_mapping:
            candidates = cleaned_mapping[cleaned_input]
            if len(candidates) > 1:
                # Несколько вариантов с одинаковым "очищенным" названием — ситуация неоднозначная
                # Дальше пусть отработает логика по тегу [] или unknown_course_handler
                logger.warning(
                    f"⚠️ Найдено несколько курсов с одинаковым очищенным названием '{cleaned_input}',"\
                    f" невозможно однозначно выбрать курс для '{getcourse_tag}'"
                )
                return None
            # Единственный кандидат — используем его
            key, data = candidates[0]
            course_data = data.copy()
            course_data['getcourse_tag'] = getcourse_tag
            logger.info(
                f"✅ Найден курс по названию без шумовых слов: {getcourse_tag} -> {course_data['internal_name']} (строка '{key}')"
            )
            return course_data
        
        return None
    
    @classmethod
    def get_name_candidates_for_unknown(cls, getcourse_tag: str) -> List[str]:
        """Возвращает список возможных внутренних названий курса (internal_name)
        для случая, когда курс не был однозначно найден.

        Логика:
        - Берём строку из GetCourse и очищаем её от шумовых фраз (подарок/рассрочка/первый платеж).
        - Ищем все строки в маппинге, у которых очищенное название совпадает.
        - Возвращаем список внутренних названий (без дубликатов).
        """
        # Гарантируем, что маппинг загружен
        cls._load_from_sheets_cache()

        cleaned_input = cls._strip_noise_phrases(getcourse_tag)
        if not cleaned_input:
            return []

        candidates: List[str] = []
        seen: set[str] = set()

        for key, data in cls.COURSE_MAPPING.items():
            cleaned_key = cls._strip_noise_phrases(key)
            if not cleaned_key:
                continue
            if cleaned_key == cleaned_input:
                internal_name = data.get('internal_name') or data.get('kpi_name') or key
                if internal_name not in seen:
                    seen.add(internal_name)
                    candidates.append(internal_name)

        return candidates
    
    @classmethod
    def has_ambiguous_course(cls) -> bool:
        """Проверяет, есть ли неоднозначно определённый курс"""
        return cls._ambiguous_candidates is not None and len(cls._ambiguous_candidates) > 0
    
    @classmethod
    def get_ambiguous_candidates(cls) -> List[Dict[str, Any]]:
        """Возвращает список кандидатов для неоднозначного курса"""
        return cls._ambiguous_candidates or []
    
    @classmethod
    def get_ambiguous_course_tag(cls) -> Optional[str]:
        """Возвращает тег неоднозначного курса"""
        return cls._ambiguous_course_tag
    
    @classmethod
    def clear_ambiguous_course(cls):
        """Очищает данные о неоднозначном курсе"""
        cls._ambiguous_course_tag = None
        cls._ambiguous_candidates = None
        logger.debug("Состояние неоднозначного курса очищено")
    
    @classmethod
    def get_course_by_tag(cls, getcourse_tag: str) -> Optional[Dict[str, Any]]:
        """
        Получает данные курса по тегу из GetCourse.
        Автоматически загружает маппинг из Google Sheets при необходимости.
        
        Новая логика с обработкой неоднозначных курсов:
        1. Точное совпадение с колонкой A
        2. Совпадение без шумовых слов  
        3. Поиск по тегу [] с проверкой вариантов
        4. Если несколько кандидатов → сохраняет для уточнения в чате VIP-отдела
        
        Args:
            getcourse_tag: Тег курса из GetCourse (например, "[neuro-law] Тариф \"Стратегический\"")
            
        Returns:
            Dict с данными курса или None если не найдено / неоднозначно
        """
        # Загружаем маппинг из Google Sheets (с кэшированием)
        cls._load_from_sheets_cache()
        
        # Очищаем предыдущее состояние неоднозначности
        cls.clear_ambiguous_course()
        
        # 1. Пытаемся найти курс по полному названию (колонка A) с учётом шумовых слов
        name_match = cls._match_course_by_name(getcourse_tag)
        if name_match:
            return name_match
        
        # 2. Прямое совпадение по тегу (с нормализацией)
        normalized_tag = cls._normalize_course_tag(getcourse_tag)
        normalized_mapping = {cls._normalize_course_tag(k): v for k, v in cls.COURSE_MAPPING.items()}
        
        if normalized_tag in normalized_mapping:
            course_data = normalized_mapping[normalized_tag].copy()
            course_data['getcourse_tag'] = getcourse_tag
            logger.info(f"✅ Найден курс: {getcourse_tag} -> {course_data['internal_name']}")
            return course_data
        
        # 3. Пытаемся найти совпадение по идентификаторам внутри []
        # Новая логика: если найдено несколько кандидатов с одинаковым тегом [], 
        # сохраняем их для уточнения
        getcourse_tag_lower = getcourse_tag.lower()
        
        # Извлекаем все идентификаторы курса из тега
        course_ids = cls._extract_course_ids(getcourse_tag)
        
        if course_ids:
            # Ищем точное совпадение по всем идентификаторам курса
            exact_matches = []
            partial_matches = []
            primary_course_id = course_ids[0]  # Первый ID = основной курс
            
            for tag, data in cls.COURSE_MAPPING.items():
                # Извлекаем идентификаторы из тега в маппинге
                mapping_course_ids = cls._extract_course_ids(tag)
                
                # Проверяем точное совпадение по всем идентификаторам
                if set(course_ids) == set(mapping_course_ids):
                    exact_matches.append((tag, data))
                # Частичное совпадение: ПРИОРИТЕТ ПЕРВОМУ ID
                elif set(mapping_course_ids).issubset(set(course_ids)):
                    # Проверяем, есть ли первый (основной) ID в маппинге
                    if mapping_course_ids and mapping_course_ids[0] == primary_course_id:
                        # Основной курс совпадает - высокий приоритет
                        match_quality = 1000 + len(set(mapping_course_ids))
                        partial_matches.append((match_quality, tag, data))
                    else:
                        # Дополнительный курс (подарок) - низкий приоритет
                        match_quality = len(set(mapping_course_ids))
                        partial_matches.append((match_quality, tag, data))
            
            # Если найдены точные совпадения
            if exact_matches:
                if len(exact_matches) == 1:
                    # Единственный точный кандидат - используем его
                    tag, data = exact_matches[0]
                    logger.info(f"✅ Найдено точное совпадение по всем ID курса: '{getcourse_tag}' -> '{tag}'")
                    course_data = data.copy()
                    course_data['getcourse_tag'] = getcourse_tag
                    return course_data
                else:
                    # Несколько точных кандидатов - неоднозначная ситуация
                    logger.warning(
                        f"⚠️ Найдено {len(exact_matches)} курсов с одинаковым тегом для '{getcourse_tag}': "
                        f"{[tag for tag, _ in exact_matches]}"
                    )
                    cls._ambiguous_course_tag = getcourse_tag
                    cls._ambiguous_candidates = [
                        {'getcourse_tag': tag, **data} for tag, data in exact_matches
                    ]
                    return None  # Требуется уточнение
            
            # Если есть частичные совпадения, возвращаем лучшее
            if partial_matches:
                partial_matches.sort(key=lambda x: x[0], reverse=True)
                best_match = partial_matches[0]
                logger.info(f"✅ Найдено лучшее частичное совпадение по ID курса: '{getcourse_tag}' -> '{best_match[1]}'")
                course_data = best_match[2].copy()
                course_data['getcourse_tag'] = getcourse_tag
                return course_data
        
        logger.error(f"❌ Курс не найден в маппинге: '{getcourse_tag}'")
        return None    
    @classmethod
    def get_airtable_course_name(cls, getcourse_tag: str) -> str:
        """Получает название курса для Airtable по тегу GetCourse"""
        course = cls.get_course_by_tag(getcourse_tag)
        return course['airtable_name'] if course else getcourse_tag
    
    @classmethod
    def get_kpi_course_name(cls, getcourse_tag: str) -> str:
        """Получает название курса для KPI Sheets по тегу GetCourse или resolved названию"""
        course = cls.get_course_by_tag(getcourse_tag)
        
        # Если не нашли по тегу, ищем по internal_name/kpi_name (для resolved названий из KPI)
        if not course:
            cls._load_from_sheets_cache()
            search_normalized = getcourse_tag.lower().strip()
            for tag, data in cls.COURSE_MAPPING.items():
                internal_name = data.get('internal_name', '')
                kpi_name = data.get('kpi_name', '')
                if getcourse_tag == internal_name or getcourse_tag == kpi_name:
                    course = data
                    break
                if search_normalized == internal_name.lower().strip() or search_normalized == kpi_name.lower().strip():
                    course = data
                    break
                if (search_normalized in internal_name.lower() or search_normalized in kpi_name.lower() or
                    internal_name.lower() in search_normalized or kpi_name.lower() in search_normalized):
                    if internal_name or kpi_name:
                        course = data
                        break
        
        return course['kpi_name'] if course else getcourse_tag
    
    @classmethod
    def get_tracker_course_name(cls, getcourse_tag: str) -> str:
        """Получает название курса для трекера по тегу GetCourse или resolved названию из KPI"""
        course = cls.get_course_by_tag(getcourse_tag)
        
        # Если не нашли по тегу, ищем по internal_name/kpi_name (для resolved названий из KPI)
        if not course:
            cls._load_from_sheets_cache()
            search_normalized = getcourse_tag.lower().strip()
            for tag, data in cls.COURSE_MAPPING.items():
                internal_name = data.get('internal_name', '')
                kpi_name = data.get('kpi_name', '')
                if getcourse_tag == internal_name or getcourse_tag == kpi_name:
                    course = data
                    break
                if search_normalized == internal_name.lower().strip() or search_normalized == kpi_name.lower().strip():
                    course = data
                    break
                if (search_normalized in internal_name.lower() or search_normalized in kpi_name.lower() or
                    internal_name.lower() in search_normalized or kpi_name.lower() in search_normalized):
                    if internal_name or kpi_name:
                        course = data
                        break
        
        return course['tracker_name'] if course else getcourse_tag
    
    @classmethod
    def get_gant_sheet_name(cls, getcourse_tag: str) -> str:
        """Получает название листа в таблице ГАНТ (для загрузки ДЗ)"""
        course = cls.get_course_by_tag(getcourse_tag)
        return course.get('gant_sheet', '') if course else ''
    
    @classmethod
    def get_course_params(cls, getcourse_tag: str) -> Dict[str, Any]:
        """
        Получает параметры курса для создания трекера.
        
        Returns:
            Dict с параметрами: lesson_count, access_days, curator_support_days, 
                               vip_support_days, monthly_target, monthly_minimum, program_type
        """
        course = cls.get_course_by_tag(getcourse_tag)
        
        # Если не нашли по тегу, ищем по internal_name/kpi_name (для resolved названий из KPI)
        if not course:
            cls._load_from_sheets_cache()
            search_normalized = getcourse_tag.lower().strip()
            for tag, data in cls.COURSE_MAPPING.items():
                internal_name = data.get('internal_name', '')
                kpi_name = data.get('kpi_name', '')
                if getcourse_tag == internal_name or getcourse_tag == kpi_name:
                    course = data
                    logger.info(f"✅ get_course_params: найден курс по названию '{getcourse_tag}' -> tag='{tag}'")
                    break
                if search_normalized == internal_name.lower().strip() or search_normalized == kpi_name.lower().strip():
                    course = data
                    logger.info(f"✅ get_course_params: найден курс по названию (case-insensitive) '{getcourse_tag}' -> tag='{tag}'")
                    break
                if (search_normalized in internal_name.lower() or search_normalized in kpi_name.lower() or
                    internal_name.lower() in search_normalized or kpi_name.lower() in search_normalized):
                    if internal_name or kpi_name:
                        course = data
                        logger.info(f"✅ get_course_params: найден курс по частичному совпадению '{getcourse_tag}' -> tag='{tag}'")
                        break
        
        if not course:
            # Дефолтные значения если курс не найден
            logger.warning(f"⚠️ Используются дефолтные параметры для курса: {getcourse_tag}")
            return {
                'lesson_count': 50,
                'access_days': 360,  # 12 месяцев
                'curator_support_days': 180,  # 6 месяцев
                'vip_support_days': 360,  # 12 месяцев
                'monthly_target': 7,
                'monthly_minimum': 7,
                'gant_sheet': '',
                'program_type': 'regular'  # По умолчанию обычный курс
            }
        
        # Получаем оригинальные значения (могут быть текстовыми)
        original_access = course.get('access_months', 0)
        original_curator = course.get('curator_support_months', 0)
        original_vip = course.get('vip_support_months', 0)
        
        # Конвертируем месяцы в дни, обрабатывая текстовые значения
        access_days = cls._convert_months_to_days(original_access)
        curator_support_days = cls._convert_months_to_days(original_curator)
        vip_support_days = cls._convert_months_to_days(original_vip)
        
        return {
            'lesson_count': course.get('lesson_count', 50),
            'access_days': access_days,
            'curator_support_days': curator_support_days,
            'vip_support_days': vip_support_days,
            'monthly_target': course.get('monthly_target', 7),
            'monthly_minimum': course.get('monthly_minimum', 7),
            'gant_sheet': course.get('gant_sheet', ''),
            'program_type': course.get('program_type', 'regular'),  # regular, bundle, subscription, premium
            # Сохраняем оригинальные значения для использования в формулах
            'original_access_months': original_access,
            'original_curator_months': original_curator,
            'original_vip_months': original_vip
        }
    
    @classmethod
    def _convert_months_to_days(cls, months_value) -> int:
        """
        Конвертирует месяцы в дни, обрабатывая текстовые значения.
        Для текстовых значений возвращает 0.
        """
        # Если значение текстовое, возвращаем 0
        if isinstance(months_value, str) and not months_value.isdigit():
            return 0
        
        # Конвертируем числовые значения в дни
        try:
            months = int(float(months_value)) if months_value else 0
            return months * 30 if months > 0 else 0
        except (ValueError, TypeError):
            return 0
    
    @classmethod
    def is_tariff_program(cls, getcourse_tag: str) -> bool:
        """
        Определяет, является ли программа тарифом (Бандл, Абонемент, Премиум).
        
        Args:
            getcourse_tag: Тег курса из GetCourse или resolved название из KPI
            
        Returns:
            True если это тариф (не обычный курс)
        """
        course = cls.get_course_by_tag(getcourse_tag)
        
        # Если не нашли по тегу, ищем по internal_name/kpi_name (для resolved названий из KPI)
        if not course:
            cls._load_from_sheets_cache()
            # Нормализуем входное название для поиска
            search_normalized = getcourse_tag.lower().strip()
            for tag, data in cls.COURSE_MAPPING.items():
                internal_name = data.get('internal_name', '')
                kpi_name = data.get('kpi_name', '')
                # Точное совпадение
                if getcourse_tag == internal_name or getcourse_tag == kpi_name:
                    course = data
                    logger.info(f"✅ is_tariff_program: найден курс по названию '{getcourse_tag}' -> tag='{tag}'")
                    break
                # Case-insensitive совпадение
                if search_normalized == internal_name.lower().strip() or search_normalized == kpi_name.lower().strip():
                    course = data
                    logger.info(f"✅ is_tariff_program: найден курс по названию (case-insensitive) '{getcourse_tag}' -> tag='{tag}'")
                    break
                # Частичное совпадение (если входное название содержится в internal_name/kpi_name или наоборот)
                if (search_normalized in internal_name.lower() or search_normalized in kpi_name.lower() or
                    internal_name.lower() in search_normalized or kpi_name.lower() in search_normalized):
                    if internal_name or kpi_name:  # Исключаем пустые строки
                        course = data
                        logger.info(f"✅ is_tariff_program: найден курс по частичному совпадению '{getcourse_tag}' -> tag='{tag}'")
                        break
        
        if not course:
            logger.warning(f"⚠️ is_tariff_program: курс не найден для '{getcourse_tag}'")
            return False
        
        program_type = course.get('program_type', 'regular')
        
        # Fallback: если program_type не указан, но название содержит признаки тарифа
        if program_type == 'regular' or not program_type:
            internal_name = course.get('internal_name', '').lower()
            kpi_name = course.get('kpi_name', '').lower()
            if any(keyword in internal_name or keyword in kpi_name for keyword in ['абонемент', 'бандл', 'премиум', 'vip навсегда']):
                program_type = 'subscription'  # По умолчанию считаем абонементом
                logger.info(f"📚 is_tariff_program: определён как тариф по названию '{getcourse_tag}' -> type={program_type}")
        
        is_tariff = program_type in ['bundle', 'subscription', 'premium']
        logger.info(f"📚 is_tariff_program: '{getcourse_tag}' -> type={program_type}, is_tariff={is_tariff}")
        return is_tariff
    
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
    
    @classmethod
    def list_all_courses(cls) -> list:
        """Возвращает список всех доступных курсов"""
        return list(cls.COURSE_MAPPING.keys())
    
    @classmethod
    def get_total_courses_count(cls) -> int:
        """Возвращает общее количество курсов в маппинге"""
        return len(cls.COURSE_MAPPING)
    
    @classmethod
    def search_courses(cls, search_term: str) -> list:
        """Поиск курсов по ключевому слову"""
        search_lower = search_term.lower()
        results = []
        for tag, data in cls.COURSE_MAPPING.items():
            if (search_lower in tag.lower() or 
                search_lower in data['internal_name'].lower() or
                search_lower in data.get('tracker_name', '').lower()):
                results.append({
                    'tag': tag,
                    'name': data['internal_name'],
                    'tracker_name': data.get('tracker_name', '')
                })
        return results


# Функции для быстрого доступа
def get_course_config(getcourse_tag: str) -> Optional[Dict[str, Any]]:
    """Быстрый доступ к конфигурации курса"""
    return CourseConfig.get_course_by_tag(getcourse_tag)


def get_course_for_airtable(getcourse_tag: str) -> str:
    """Получить название курса для Airtable"""
    return CourseConfig.get_airtable_course_name(getcourse_tag)


def get_course_for_kpi(getcourse_tag: str) -> str:
    """Получить название курса для KPI Ultra"""
    return CourseConfig.get_kpi_course_name(getcourse_tag)


def get_course_for_tracker(getcourse_tag: str) -> str:
    """Получить название курса для трекера"""
    return CourseConfig.get_tracker_course_name(getcourse_tag)


# Пример использования
if __name__ == "__main__":
    print(f"📚 Всего курсов в базе: {CourseConfig.get_total_courses_count()}")
    print()
    
    # Тест маппинга
    test_tags = [
        "[neuro-law] Тариф \"Корпоративный\"",
        "[python-ai-2.0] Тариф \"VIP\"",
        "[luxury] IT-КАРЬЕРА БЕЗ ГРАНИЦ"
    ]
    
    for tag in test_tags:
        course = get_course_config(tag)
        if course:
            print(f"✅ {tag}")
            print(f"   Airtable: {course['airtable_name']}")
            print(f"   KPI: {course['kpi_name']}")
            print(f"   Трекер: {course['tracker_name']}")
            print(f"   Уроков: {course['lesson_count']}")
            print(f"   Доступ: {course['access_days']} дней")
            print(f"   VIP поддержка: {course['vip_support_days']} дней")
            print()
