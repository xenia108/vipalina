#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Классификатор сообщений для Vipalina
"""

import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger('vipalina_telethon')

class MessageClassifier:
    """Классификатор сообщений для определения типа запроса от пользователей"""
    
    def __init__(self):
        # Определяем категории сообщений
        self.categories = {
            "course_inquiry": {
                "keywords": [
                    "курс", "программ", "обучени", "заняти", "материал", 
                    "урок", "вебинар", "интенсив", "професси", "навык",
                    "course", "program", "learn", "class", "material",
                    "lesson", "webinar", "intensive", "profession", "skill"
                ],
                "priority": 1
            },
            "technical_support": {
                "keywords": [
                    "не работ", "ошибк", "проблем", "техподдержк", "помогит",
                    "не открывает", "завис", "bug", "error", "problem", 
                    "support", "help", "stuck", "freeze"
                ],
                "priority": 2
            },
            "payment_inquiry": {
                "keywords": [
                    "оплат", "денег", "стоимост", "деньг", "чек", "счет",
                    "рассрочк", "подписк", "тариф", "price", "payment",
                    "cost", "money", "installment", "subscription", "bill"
                ],
                "priority": 1
            },
            "account_issue": {
                "keywords": [
                    "аккаунт", "профил", "логин", "парол", "вход", "регистр",
                    "account", "profile", "login", "password", "sign in", "register"
                ],
                "priority": 2
            },
            "general_inquiry": {
                "keywords": [
                    "здравствуй", "привет", "добрый", "пока", "спасибо",
                    "hello", "hi", "good", "bye", "thank", "прекрасно"
                ],
                "priority": 3
            },
            "vip_manager_request": {
                "keywords": [
                    "менеджер", "консультаци", "совет", "помощь", "вопрос",
                    "manager", "consult", "advice", "question", "support"
                ],
                "priority": 1
            }
        }
    
    def classify_message(self, message: str) -> Tuple[str, float]:
        """
        Классифицирует сообщение и возвращает категорию и уровень уверенности
        
        Args:
            message (str): Текст сообщения
            
        Returns:
            Tuple[str, float]: Категория и уровень уверенности (0-1)
        """
        if not message:
            logger.info("Пустое сообщение, возвращаем general_inquiry")
            return "general_inquiry", 0.0
        
        message_lower = message.lower().strip()
        logger.info(f"Классификация сообщения: '{message_lower}'")
        
        max_score = 0
        best_category = "general_inquiry"
        total_matches = 0
        
        for category, data in self.categories.items():
            score = 0
            keywords = data["keywords"]
            
            # Подсчитываем количество совпадений ключевых слов
            matched_keywords = []
            for keyword in keywords:
                if keyword in message_lower:
                    score += 1
                    total_matches += 1
                    matched_keywords.append(keyword)
            
            # Нормализуем оценку
            normalized_score = score / len(keywords) if keywords else 0
            
            logger.info(f"Категория '{category}': совпадений={score}, норм. оценка={normalized_score:.2f}, ключевые слова={matched_keywords}")
            
            # Обновляем лучшую категорию, если текущая оценка выше
            if normalized_score > max_score:
                max_score = normalized_score
                best_category = category
        
        # If no matches at all, return general_inquiry with 0 confidence
        if total_matches == 0:
            logger.info("Не найдено совпадений, возвращаем general_inquiry с уверенностью 0.0")
            return "general_inquiry", 0.0
            
        logger.info(f"Лучшая категория: '{best_category}' с оценкой {max_score:.2f}")
        return best_category, min(max_score, 1.0)
    
    def is_authorized_topic(self, message: str) -> bool:
        """
        Проверяет, относится ли сообщение к авторизованным темам
        
        Args:
            message (str): Текст сообщения
            
        Returns:
            bool: True, если тема авторизована
        """
        authorized_keywords = [
            "курс", "обучение", "программа", "материал", "вебинар",
            "оплата", "стоимость", "рассрочка", "поддержка", "помощь",
            "менеджер", "консультация", "аккаунт", "профиль",
            "course", "program", "material", "webinar", "payment",
            "support", "help", "manager", "consultation", "account"
        ]
        
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in authorized_keywords)
    
    def should_forward_to_manager(self, message: str, user_role: str) -> bool:
        """
        Определяет, нужно ли переслать сообщение VIP-менеджеру
        
        Args:
            message (str): Текст сообщения
            user_role (str): Роль пользователя ("vip_student" или "vip_manager")
            
        Returns:
            bool: True, если нужно переслать менеджеру
        """
        # Если пользователь уже является менеджером, не пересылаем
        if user_role == "vip_manager":
            return False
        
        # Категории, которые требуют участия менеджера
        manager_required_categories = [
            "payment_inquiry",
            "account_issue",
            "vip_manager_request",
            "technical_support"
        ]
        
        category, confidence = self.classify_message(message)
        result = category in manager_required_categories and confidence > 0.0
        logger.info(f"Нужно ли переслать менеджеру: {result} (категория={category}, уверенность={confidence:.2f})")
        return result