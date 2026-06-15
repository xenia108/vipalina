"""
GigaChat клиент для интеграции с Випалиной
"""

import asyncio
import base64
import json
import logging
from typing import Dict, Any, Optional
import httpx
import warnings
from config import GIGACHAT_CLIENT_ID, GIGACHAT_AUTH_KEY, GIGACHAT_SCOPE

# Отключаем предупреждения о SSL для GigaChat (использует самоподписанный сертификат)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

logger = logging.getLogger(__name__)


class GigaChatClient:
    """Клиент для работы с GigaChat API"""
    
    def __init__(self):
        self.client_id = GIGACHAT_CLIENT_ID
        self.auth_key = GIGACHAT_AUTH_KEY
        self.scope = GIGACHAT_SCOPE
        self.access_token = None
        self.token_expires_at = 0
        # ВАЖНО: GigaChat использует самоподписанный сертификат, отключаем проверку SSL
        self.http_client = httpx.AsyncClient(timeout=30.0, verify=False)
    
    async def _get_access_token(self) -> str:
        """Получение access token для авторизации"""
        import time
        
        # Проверяем, не истек ли токен
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token
        
        try:
            # Кодируем авторизационные данные
            auth_string = f"{self.client_id}:{self.auth_key}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()
            
            # Запрашиваем токен
            response = await self.http_client.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={
                    "Authorization": f"Basic {encoded_auth}",
                    "RqUID": "unique_request_id",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={"scope": self.scope}
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get("access_token")
                # Устанавливаем срок действия (минус 60 секунд для запаса)
                expires_in = token_data.get("expires_at", 0) - 60
                self.token_expires_at = expires_in
                logger.info("✅ Получен новый токен доступа для GigaChat")
                return self.access_token
            else:
                logger.error(f"❌ Ошибка получения токена: {response.status_code} - {response.text}")
                raise Exception(f"Failed to get access token: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при получении токена GigaChat: {e}")
            raise
    
    async def chat_completion(self, messages: list, temperature: float = 0.7) -> Dict[str, Any]:
        """
        Выполнение запроса к GigaChat API
        
        Args:
            messages: Список сообщений в формате OpenAI
            temperature: Температура генерации (0.0-1.0)
            
        Returns:
            Ответ от GigaChat API
        """
        try:
            token = await self._get_access_token()
            
            payload = {
                "model": "GigaChat",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1000,
                "stream": False
            }
            
            response = await self.http_client.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ GigaChat запрос выполнен успешно")
                return result
            else:
                logger.error(f"❌ Ошибка GigaChat: {response.status_code} - {response.text}")
                raise Exception(f"GigaChat API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при выполнении запроса к GigaChat: {e}")
            raise
    
    async def classify_message(self, message_text: str, categories: list) -> Dict[str, Any]:
        """
        Классификация сообщения студента по категориям
        
        Args:
            message_text: Текст сообщения студента
            categories: Список возможных категорий
            
        Returns:
            Результат классификации с категорией и уверенностью
        """
        try:
            prompt = f"""
Ты - помощник по классификации сообщений студентов.
Классифицируй следующее сообщение по одной из категорий:

Категории:
{chr(10).join([f"- {cat}" for cat in categories])}

Сообщение студента:
"{message_text}"

Ответь в формате JSON:
{{
    "category": "название категории",
    "confidence": 0.95,
    "reasoning": "краткое объяснение выбора"
}}
"""
            
            messages = [
                {"role": "system", "content": "Ты - эксперт по классификации сообщений. Отвечай только в формате JSON."},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.chat_completion(messages, temperature=0.3)
            result_text = response["choices"][0]["message"]["content"]
            
            # Извлекаем JSON из ответа
            try:
                # Пытаемся найти JSON в ответе
                import re
                json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                if json_match:
                    result_json = json.loads(json_match.group())
                    return result_json
                else:
                    # Если нет JSON, возвращаем базовый результат
                    return {
                        "category": categories[0],
                        "confidence": 0.5,
                        "reasoning": "Не удалось извлечь структурированный ответ"
                    }
            except json.JSONDecodeError:
                return {
                    "category": categories[0],
                    "confidence": 0.5,
                    "reasoning": "Не удалось распарсить ответ"
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка классификации сообщения: {e}")
            return {
                "category": "other",
                "confidence": 0.0,
                "reasoning": f"Ошибка классификации: {str(e)}"
            }
    
    async def generate_recommendation(self, context: Dict[str, Any]) -> str:
        """
        Генерация рекомендаций для менеджера на основе контекста
        
        Args:
            context: Контекст взаимодействия со студентом
            
        Returns:
            Рекомендация для менеджера
        """
        try:
            prompt = f"""
Ты - опытный VIP-менеджер, который помогает коллегам работать со студентами.
На основе предоставленного контекста сформируй рекомендации для менеджера.

Контекст:
{json.dumps(context, ensure_ascii=False, indent=2)}

Ответь в формате:
🚨 ВАЖНОСТЬ: [срочное/обычное/низкое]
💡 КАТЕГОРИЯ: [тип обращения]
📋 РЕКОМЕНДАЦИИ:
- [конкретные действия]
- [приоритеты]
- [возможные риски]

🎯 ПЛАН ДЕЙСТВИЙ:
1. [первый шаг]
2. [второй шаг]
3. [контрольный пункт]
"""
            
            messages = [
                {"role": "system", "content": "Ты - опытный VIP-менеджер. Давай четкие, практичные рекомендации."},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.chat_completion(messages, temperature=0.5)
            recommendation = response["choices"][0]["message"]["content"]
            
            return recommendation
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации рекомендации: {e}")
            return "❌ Не удалось сгенерировать рекомендацию. Обратитесь к руководителю."
    
    async def close(self):
        """Закрытие HTTP клиента"""
        if self.http_client:
            await self.http_client.aclose()


# Глобальный экземпляр клиента
gigachat_client: Optional[GigaChatClient] = None


async def get_gigachat_client() -> GigaChatClient:
    """Получение глобального экземпляра GigaChat клиента"""
    global gigachat_client
    if gigachat_client is None:
        gigachat_client = GigaChatClient()
    return gigachat_client


async def close_gigachat_client():
    """Закрытие глобального клиента"""
    global gigachat_client
    if gigachat_client:
        await gigachat_client.close()
        gigachat_client = None
