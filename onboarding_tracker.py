"""
Модуль для отслеживания и отображения прогресса онбординга студентов в едином сообщении.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from telethon import TelegramClient

from config import VIP_DEPARTMENT_CHAT_ID

# Модуль персистенции
try:
    from vipalina_persistence import get_persistence
except ImportError:
    get_persistence = None

logger = logging.getLogger('onboarding_tracker')


class OnboardingTracker:
    """Класс для отслеживания прогресса онбординга в едином сообщении"""
    
    def __init__(self, client: TelegramClient):
        self.client = client
        self.tracking_messages: Dict[str, int] = {}  # getcourse_id -> message_id
        self.tracking_data: Dict[str, Dict[str, Any]] = {}  # getcourse_id -> data
    
    def _save_to_persistence(self, getcourse_id: str):
        """Сохраняет состояние онбординга в персистенцию."""
        try:
            if get_persistence and getcourse_id in self.tracking_data and getcourse_id in self.tracking_messages:
                persistence = get_persistence()
                if persistence and persistence.is_initialized():
                    # Подготавливаем данные в правильном формате для персистенции
                    progress_data = self.tracking_data[getcourse_id].copy()
                    progress_data['message_id'] = self.tracking_messages[getcourse_id]
                    
                    persistence.save_onboarding_progress(
                        getcourse_id=getcourse_id,
                        progress_data=progress_data
                    )
        except Exception as e:
            logger.error(f"Ошибка сохранения онбординга в персистенцию: {e}")
    
    def _delete_from_persistence(self, getcourse_id: str):
        """Удаляет состояние онбординга из персистенции."""
        try:
            if get_persistence:
                persistence = get_persistence()
                if persistence and persistence.is_initialized():
                    persistence.delete_onboarding_progress(getcourse_id)
        except Exception as e:
            logger.error(f"Ошибка удаления онбординга из персистенции: {e}")
    
    def load_from_persistence(self):
        """Загружает активные онбординги из персистенции."""
        try:
            if get_persistence:
                persistence = get_persistence()
                if persistence and persistence.is_initialized():
                    data = persistence.load_all_onboarding_progress()
                    for getcourse_id, item in data.items():
                        if item.get('message_id'):
                            self.tracking_messages[getcourse_id] = item['message_id']
                        if item.get('tracking_data'):
                            self.tracking_data[getcourse_id] = item['tracking_data']
                    logger.info(f"Загружено {len(data)} активных онбордингов из персистенции")
        except Exception as e:
            logger.error(f"Ошибка загрузки онбордингов из персистенции: {e}")
    
    def _format_duration(self, start_time: datetime, end_time: Optional[datetime] = None) -> str:
        """Форматирует продолжительность в человекочитаемый формат"""
        if not end_time:
            end_time = datetime.now()
        
        duration = end_time - start_time
        minutes = int(duration.total_seconds() // 60)
        seconds = int(duration.total_seconds() % 60)
        
        if minutes > 0:
            return f"{minutes} мин {seconds} сек"
        else:
            return f"{seconds} сек"
    
    def _get_status_emoji(self, status: str) -> str:
        """Возвращает эмодзи для статуса"""
        status_emojis = {
            'pending': '⏸️',
            'in_progress': '⏳',
            'success': '✅',
            'error': '❌',
            'warning': '⚠️'
        }
        return status_emojis.get(status, '⏸️')
    
    def _format_step_status(self, step_name: str, status: str, details: str = "", error: str = "") -> str:
        """Форматирует строку статуса шага"""
        emoji = self._get_status_emoji(status)
        
        if status == 'error' and error:
            return f"{emoji} **{step_name}:** ОШИБКА\n⚠️ {error}"
        elif status == 'success' and details:
            return f"{emoji} **{step_name}:** Успешно\n{details}"
        elif status == 'in_progress':
            return f"{emoji} **{step_name}:** В процессе..."
        elif status == 'pending':
            return f"{emoji} **{step_name}:** Ожидание"
        elif status == 'success':
            return f"{emoji} **{step_name}:** Успешно"
        else:
            return f"{emoji} **{step_name}:** {status.capitalize()}"
    
    async def start_tracking(self, student_name: str, manager_name: str, getcourse_id: str, telegram_id: Optional[int] = None, telegram_username: Optional[str] = None):
        """Начинает отслеживание онбординга и создает начальное сообщение"""
        try:
            start_time = datetime.now()
            
            # Сохраняем данные отслеживания
            self.tracking_data[getcourse_id] = {
                'student_name': student_name,
                'manager_name': manager_name,
                'getcourse_id': getcourse_id,
                'telegram_id': telegram_id,
                'telegram_username': telegram_username,
                'start_time': start_time,
                'steps': {
                    'chat_creation': {'status': 'pending', 'details': '', 'error': ''},
                    'welcome_message': {'status': 'pending', 'details': '', 'error': ''},
                    'airtable': {'status': 'pending', 'details': '', 'error': ''},
                    'kpi_sheets': {'status': 'pending', 'details': '', 'error': ''},
                    'tracker_creation': {'status': 'pending', 'details': '', 'error': ''}
                },
                'overall_status': 'in_progress',
                'errors': []
            }
            
            # Формируем начальное сообщение
            # Подготавливаем строку с Telegram username
            telegram_line = ""
            if telegram_username:
                # Убираем @ в начале, если есть, и добавляем заново
                clean_username = telegram_username.lstrip('@')
                telegram_line = f"\nTelegram: @{clean_username}"
            
            message = f"""🎓 **ОНБОРДИНГ СТУДЕНТА**

👤 Студент: {student_name}
ID GetCourse: {getcourse_id}
ID Telegram: {telegram_id if telegram_id else 'Не указан'}{telegram_line}

👩‍💼 Менеджер: {manager_name}
🕐 Начало: {start_time.strftime('%d.%m.%Y %H:%M')}

{self._format_step_status('Создание чата', 'pending')}

{self._format_step_status('Отправка приветствия', 'pending')}

{self._format_step_status('NocoDB', 'pending')}

{self._format_step_status('KPI Ultra', 'pending')}

{self._format_step_status('Создание трекера', 'pending')}

🔄 Статус: В процессе
⏱️ Продолжительность: 0 сек
"""
            
            # Отправляем сообщение
            sent_message = await self.client.send_message(
                entity=VIP_DEPARTMENT_CHAT_ID,
                message=message,
                parse_mode='md',
                link_preview=False
            )
            
            # Сохраняем ID сообщения для последующих обновлений
            self.tracking_messages[getcourse_id] = sent_message.id
            logger.info(f"Начато отслеживание онбординга для студента {student_name} (ID: {sent_message.id})")
            
            # Сохраняем в персистенцию
            self._save_to_persistence(getcourse_id)
            
        except Exception as e:
            logger.error(f"Ошибка при создании сообщения отслеживания онбординга: {e}", exc_info=True)
    
    async def update_step(self, getcourse_id: str, step_name: str, status: str, details: str = "", error: str = ""):
        """Обновляет статус шага онбординга"""
        try:
            if getcourse_id not in self.tracking_data:
                logger.warning(f"Нет данных отслеживания для студента {getcourse_id}")
                return
            
            # Обновляем данные шага
            if step_name in self.tracking_data[getcourse_id]['steps']:
                self.tracking_data[getcourse_id]['steps'][step_name] = {
                    'status': status,
                    'details': details,
                    'error': error
                }
            
            # Если есть ошибка, добавляем в список ошибок
            if status == 'error' and error:
                self.tracking_data[getcourse_id]['errors'].append({
                    'step': step_name,
                    'error': error,
                    'timestamp': datetime.now()
                })
            
            # Обновляем сообщение
            await self._update_tracking_message(getcourse_id)
            
            # Сохраняем в персистенцию
            self._save_to_persistence(getcourse_id)
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении шага онбординга: {e}", exc_info=True)
    
    async def _update_tracking_message(self, getcourse_id: str):
        """Обновляет сообщение отслеживания онбординга"""
        try:
            if getcourse_id not in self.tracking_data or getcourse_id not in self.tracking_messages:
                return
            
            data = self.tracking_data[getcourse_id]
            message_id = self.tracking_messages[getcourse_id]
            
            # Определяем общий статус
            error_steps = [step for step in data['steps'].values() if step['status'] == 'error']
            pending_steps = [step for step in data['steps'].values() if step['status'] == 'pending']
            in_progress_steps = [step for step in data['steps'].values() if step['status'] == 'in_progress']
            
            if error_steps:
                overall_status = "Ошибки в процессе"
                overall_emoji = "❌"
            elif not pending_steps and not in_progress_steps:
                overall_status = "Завершен успешно"
                overall_emoji = "🎉"
            else:
                overall_status = "В процессе"
                overall_emoji = "🔄"
            
            # Формируем информацию о студенте
            telegram_line = ""
            if data['telegram_username']:
                # Убираем @ в начале, если есть, и добавляем заново
                clean_username = data['telegram_username'].lstrip('@')
                telegram_line = f"\nTelegram: @{clean_username}"
            
            student_info = f"👤 Студент: {data['student_name']}\nID GetCourse: {data['getcourse_id']}\nID Telegram: {data['telegram_id'] if data['telegram_id'] else 'Не указан'}{telegram_line}"
            
            # Формируем сообщение
            steps_text = "\n\n".join([
                self._format_step_status(
                    "Создание чата", 
                    data['steps']['chat_creation']['status'],
                    data['steps']['chat_creation']['details'],
                    data['steps']['chat_creation']['error']
                ),
                self._format_step_status(
                    "Отправка приветствия", 
                    data['steps']['welcome_message']['status'],
                    data['steps']['welcome_message']['details'],
                    data['steps']['welcome_message']['error']
                ),
                self._format_step_status(
                    "NocoDB", 
                    data['steps']['airtable']['status'],
                    data['steps']['airtable']['details'],
                    data['steps']['airtable']['error']
                ),
                self._format_step_status(
                    "KPI Ultra", 
                    data['steps']['kpi_sheets']['status'],
                    data['steps']['kpi_sheets']['details'],
                    data['steps']['kpi_sheets']['error']
                ),
                self._format_step_status(
                    "Создание трекера", 
                    data['steps']['tracker_creation']['status'],
                    data['steps']['tracker_creation']['details'],
                    data['steps']['tracker_creation']['error']
                )
            ])
            
            # Добавляем блок ошибок, если есть
            errors_block = ""
            if data['errors']:
                errors_text = "\n".join([
                    f"• {error['step']}: {error['error']}" 
                    for error in data['errors'][-3:]  # Показываем только последние 3 ошибки
                ])
                errors_block = f"\n\n⚠️ Ошибки и проблемы:\n{errors_text}"
            
            # Формируем финальное сообщение
            message = f"""🎓 **ОНБОРДИНГ СТУДЕНТА**

{student_info}

👩‍💼 Менеджер: {data['manager_name']}
🕐 Начало: {data['start_time'].strftime('%d.%m.%Y %H:%M')}

{steps_text}{errors_block}

{overall_emoji} Статус: {overall_status}
⏱️ Продолжительность: {self._format_duration(data['start_time'])}
"""
            
            # Обновляем сообщение
            await self.client.edit_message(
                entity=VIP_DEPARTMENT_CHAT_ID,
                message=message_id,
                text=message,
                parse_mode='md',
                link_preview=False
            )
            
            logger.info(f"Обновлено сообщение отслеживания онбординга для студента {data['student_name']}")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения отслеживания онбординга: {e}", exc_info=True)
    
    async def finish_tracking(self, getcourse_id: str, success: bool = True):
        """Завершает отслеживание онбординга"""
        try:
            if getcourse_id not in self.tracking_data:
                return
            
            data = self.tracking_data[getcourse_id]
            end_time = datetime.now()
            
            # Обновляем общий статус
            if success:
                overall_status = "Завершен успешно"
                overall_emoji = "🎉"
            else:
                overall_status = "Завершен с ошибками"
                overall_emoji = "❌"
            
            # Формируем информацию о студенте
            telegram_line = ""
            if data['telegram_username']:
                # Убираем @ в начале, если есть, и добавляем заново
                clean_username = data['telegram_username'].lstrip('@')
                telegram_line = f"\nTelegram: @{clean_username}"
            
            student_info = f"👤 Студент: {data['student_name']}\nID GetCourse: {data['getcourse_id']}\nID Telegram: {data['telegram_id'] if data['telegram_id'] else 'Не указан'}{telegram_line}"
            
            # Формируем сообщение с шагами
            steps_text = "\n\n".join([
                self._format_step_status(
                    "Создание чата", 
                    data['steps']['chat_creation']['status'],
                    data['steps']['chat_creation']['details']
                ),
                self._format_step_status(
                    "Отправка приветствия", 
                    data['steps']['welcome_message']['status'],
                    data['steps']['welcome_message']['details']
                ),
                self._format_step_status(
                    "NocoDB", 
                    data['steps']['airtable']['status'],
                    data['steps']['airtable']['details']
                ),
                self._format_step_status(
                    "KPI Ultra", 
                    data['steps']['kpi_sheets']['status'],
                    data['steps']['kpi_sheets']['details']
                ),
                self._format_step_status(
                    "Создание трекера", 
                    data['steps']['tracker_creation']['status'],
                    data['steps']['tracker_creation']['details']
                )
            ])
            
            # Добавляем блок ошибок, если есть
            errors_block = ""
            if data['errors']:
                errors_text = "\n".join([
                    f"• {error['step']}: {error['error']}" 
                    for error in data['errors']
                ])
                errors_block = f"\n\n⚠️ Ошибки и проблемы:\n{errors_text}"
            
            message = f"""🎓 **ОНБОРДИНГ СТУДЕНТА**

{student_info}

👩‍💼 Менеджер: {data['manager_name']}
🕐 Начало: {data['start_time'].strftime('%d.%m.%Y %H:%M')}
🏁 Завершение: {end_time.strftime('%d.%m.%Y %H:%M')}

{steps_text}{errors_block}

{overall_emoji} Статус: {overall_status}
⏱️ Продолжительность: {self._format_duration(data['start_time'], end_time)}
"""
            
            # Обновляем сообщение
            if getcourse_id in self.tracking_messages:
                message_id = self.tracking_messages[getcourse_id]
                await self.client.edit_message(
                    entity=VIP_DEPARTMENT_CHAT_ID,
                    message=message_id,
                    text=message,
                    parse_mode='md',
                    link_preview=False
                )
            
            # Очищаем данные отслеживания
            if getcourse_id in self.tracking_messages:
                del self.tracking_messages[getcourse_id]
            if getcourse_id in self.tracking_data:
                del self.tracking_data[getcourse_id]
            
            # Удаляем из персистенции
            self._delete_from_persistence(getcourse_id)
            
            logger.info(f"Завершено отслеживание онбординга для студента {data['student_name']}")
            
        except Exception as e:
            logger.error(f"Ошибка при завершении отслеживания онбординга: {e}", exc_info=True)