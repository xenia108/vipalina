"""
AI анализатор сообщений студентов для Випалины
Использует GigaChat для интеллектуального анализа
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from gigachat_client import get_gigachat_client
from report_generator import get_report_generator

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """Анализатор сообщений студентов с помощью ИИ"""
    
    def __init__(self):
        self.categories = [
            "course_questions",      # Вопросы по курсу
            "tech_support",          # Техническая поддержка
            "payments",              # Финансовые вопросы
            "motivation",            # Мотивация/поддержка
            "complaints",            # Жалобы/конфликты
            "homework_help",         # Помощь с ДЗ
            "career_guidance",       # Карьерные вопросы
            "feedback",              # Отзывы/предложения
            "access_issues",         # Проблемы с доступом
            "other"                  # Другое
        ]
    
    async def analyze_student_message(self, message_text: str, student_id: str) -> Dict[str, Any]:
        """
        Комплексный анализ сообщения студента
        
        Args:
            message_text: Текст сообщения
            student_id: ID студента в GetCourse
            
        Returns:
            Полный анализ сообщения с рекомендациями
        """
        try:
            # 1. Классификация сообщения
            classification = await self._classify_message(message_text)
            
            # 2. Получение данных студента
            student_data = await self._get_student_context(student_id)
            
            # 3. Анализ контекста
            context_analysis = await self._analyze_context(message_text, student_data)
            
            # 4. Генерация рекомендаций
            recommendations = await self._generate_recommendations(
                message_text, classification, student_data, context_analysis
            )
            
            # 5. Определение приоритета
            priority = await self._assess_priority(message_text, context_analysis)
            
            result = {
                "timestamp": datetime.now().isoformat(),
                "student_id": student_id,
                "original_message": message_text,
                "classification": classification,
                "student_context": student_data,
                "context_analysis": context_analysis,
                "recommendations": recommendations,
                "priority": priority
            }
            
            logger.info(f"✅ AI анализ завершен для студента {student_id}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка AI анализа для студента {student_id}: {e}")
            return {
                "error": str(e),
                "student_id": student_id,
                "original_message": message_text,
                "recommendations": "❌ Не удалось провести анализ. Обратитесь к руководителю."
            }
    
    async def _classify_message(self, message_text: str) -> Dict[str, Any]:
        """Классификация сообщения по категориям"""
        try:
            client = await get_gigachat_client()
            result = await client.classify_message(message_text, self.categories)
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка классификации: {e}")
            return {
                "category": "other",
                "confidence": 0.0,
                "reasoning": "Ошибка классификации"
            }
    
    async def _get_student_context(self, student_id: str) -> Dict[str, Any]:
        """Получение контекста студента из KPI Ultra"""
        try:
            report_gen = get_report_generator()
            
            # Получаем данные студента
            student = await report_gen.get_student_by_id(student_id)
            if not student:
                return {"error": "Студент не найден"}
            
            # Получаем данные из Випалины
            vipalina_data = await report_gen.get_vipalina_data()
            vipalina_info = vipalina_data.get(student_id, {})
            
            context = {
                "name": student.get("name", "Неизвестно"),
                "course": student.get("course", "Неизвестно"),
                "manager": student.get("manager_name", "Не назначен"),
                "hw_count": student.get("hw_count", "0"),
                "last_hw_date": student.get("last_hw_date", "Не сдавал"),
                "status": student.get("status", "Неизвестно"),
                "chat_link": vipalina_info.get("chat_link", ""),
                "last_contact": vipalina_info.get("last_contact", "Никогда"),
                "activity_status": vipalina_info.get("activity_status", "Неизвестно")
            }
            
            return context
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения контекста студента {student_id}: {e}")
            return {"error": f"Ошибка получения данных: {str(e)}"}
    
    async def _analyze_context(self, message_text: str, student_context: Dict[str, Any]) -> Dict[str, Any]:
        """Анализ контекста взаимодействия"""
        try:
            # Определяем риск отсева
            risk_level = "низкий"
            risk_factors = []
            
            # Проверяем активность
            hw_count = int(student_context.get("hw_count", "0"))
            if hw_count == 0:
                risk_level = "высокий"
                risk_factors.append("Нет сданных ДЗ")
            
            # Проверяем контакт
            last_contact = student_context.get("last_contact", "")
            if "никогда" in last_contact.lower() or not last_contact:
                risk_level = max(risk_level, "средний")
                risk_factors.append("Нет контакта")
            
            # Проверяем статус
            status = student_context.get("status", "").lower()
            if "пропал" in status:
                risk_level = "высокий"
                risk_factors.append("Статус 'Пропал'")
            
            return {
                "risk_level": risk_level,
                "risk_factors": risk_factors,
                "activity_score": min(hw_count * 10, 100),  # Простая оценка активности
                "engagement_trend": "stable"  # Можно усложнить анализом истории
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа контекста: {e}")
            return {
                "risk_level": "неизвестно",
                "risk_factors": [],
                "activity_score": 0
            }
    
    async def _generate_recommendations(
        self, 
        message_text: str, 
        classification: Dict[str, Any], 
        student_context: Dict[str, Any], 
        context_analysis: Dict[str, Any]
    ) -> str:
        """Генерация рекомендаций для менеджера"""
        try:
            client = await get_gigachat_client()
            
            context = {
                "student_message": message_text,
                "message_category": classification,
                "student_profile": student_context,
                "context_analysis": context_analysis
            }
            
            recommendation = await client.generate_recommendation(context)
            return recommendation
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации рекомендаций: {e}")
            return "❌ Не удалось сгенерировать рекомендации"
    
    async def _assess_priority(self, message_text: str, context_analysis: Dict[str, Any]) -> str:
        """Оценка приоритетности обращения"""
        try:
            # Ключевые слова для срочных обращений
            urgent_keywords = [
                "деньги", "возврат", "руга", "жалоб", "проблем", "не работает",
                "срочно", "немедленно", "сейчас", " urgently", "money", "refund"
            ]
            
            # Проверяем наличие срочных слов
            message_lower = message_text.lower()
            is_urgent = any(keyword in message_lower for keyword in urgent_keywords)
            
            # Учитываем уровень риска
            risk_level = context_analysis.get("risk_level", "низкий")
            
            if is_urgent:
                return "высокий"
            elif risk_level == "высокий":
                return "средний"
            else:
                return "обычный"
                
        except Exception as e:
            logger.error(f"❌ Ошибка оценки приоритета: {e}")
            return "обычный"


# Глобальный экземпляр анализатора
ai_analyzer: Optional[AIAnalyzer] = None


async def get_ai_analyzer() -> AIAnalyzer:
    """Получение глобального экземпляра AI анализатора"""
    global ai_analyzer
    if ai_analyzer is None:
        ai_analyzer = AIAnalyzer()
    return ai_analyzer
