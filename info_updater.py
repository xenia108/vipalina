"""
Модуль для обновления информации о процессах и курсах через команду #обновитьинфу
Доступен только для руководителя VIP-отдела (Ксения Уланова)
"""

import logging
import os
import re
from datetime import datetime
from typing import Optional, Dict, Any
from telethon import events, TelegramClient

from datetime_utils import format_moscow_time, get_moscow_timestamp_str

logger = logging.getLogger('vipalina_telethon')

# ID руководителя VIP-отдела
VIP_HEAD_ID = 268400185  # Ксения Уланова


class InfoUpdater:
    """
    Класс для обновления информационных файлов бота через команды в чате.
    Только для руководителя VIP-отдела.
    """
    
    def __init__(self, client: TelegramClient):
        self.client = client
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        
        # Файлы, которые можно обновлять
        self.updatable_files = {
            'prompt': 'vipalina_prompt.txt',
            'courses': 'course_list_for_alina.txt',
            'processes': 'vip_processes_info.txt',
            'faq': 'vip_faq.txt'
        }
        
        logger.info("InfoUpdater инициализирован")
    
    def register_handlers(self):
        """Регистрирует обработчики команд обновления информации"""
        
        @self.client.on(events.NewMessage(pattern=r'^#обновитьинфу'))
        async def handle_info_update(event):
            """Обрабатывает команду #обновитьинфу от руководителя"""
            
            sender_id = event.sender_id
            
            # Проверка прав доступа - только руководитель VIP-отдела
            if sender_id != VIP_HEAD_ID:
                logger.warning(f"Попытка обновления информации от неавторизованного пользователя {sender_id}")
                await event.reply(
                    "❌ У вас нет прав для обновления информации бота.\n"
                    "Эта функция доступна только руководителю VIP-отдела."
                )
                return
            
            # Парсим команду
            message_text = event.message.text
            
            # Формат: #обновитьинфу <тип> <содержимое>
            # Или: #обновитьинфу <содержимое> (по умолчанию тип = prompt)
            
            try:
                await self._process_update(event, message_text)
            except Exception as e:
                logger.error(f"Ошибка при обновлении информации: {e}", exc_info=True)
                await event.reply(f"❌ Ошибка при обновлении: {e}")
        
        logger.info("Обработчики команд обновления информации зарегистрированы")
    
    async def _process_update(self, event, message_text: str):
        """Обрабатывает обновление информации"""
        
        # Убираем команду #обновитьинфу
        content = message_text.replace('#обновитьинфу', '', 1).strip()
        
        if not content:
            await self._send_help(event)
            return
        
        # Определяем тип обновления
        file_type = 'prompt'  # По умолчанию
        update_content = content
        
        # Проверяем, указан ли тип явно
        for ftype in self.updatable_files.keys():
            if content.startswith(ftype + ' '):
                file_type = ftype
                update_content = content[len(ftype):].strip()
                break
        
        # Выполняем обновление
        result = await self._update_file(file_type, update_content)
        
        if result['success']:
            await event.reply(result['message'])
        else:
            await event.reply(f"❌ {result['message']}")
    
    async def _update_file(self, file_type: str, content: str) -> Dict[str, Any]:
        """Обновляет указанный файл"""
        
        if file_type not in self.updatable_files:
            return {
                'success': False,
                'message': f"Неизвестный тип файла: {file_type}"
            }
        
        filename = self.updatable_files[file_type]
        filepath = os.path.join(self.base_path, filename)
        
        try:
            # Создаем резервную копию
            backup_path = self._create_backup(filepath)
            
            # Определяем режим обновления
            mode = self._get_update_mode(content)
            
            if mode == 'append':
                # Добавление к существующему содержимому
                clean_content = content.replace('+', '', 1).strip()
                with open(filepath, 'a', encoding='utf-8') as f:
                    f.write('\n\n' + clean_content)
                
                message = f"""✅ **ИНФОРМАЦИЯ ДОБАВЛЕНА**

📁 **Файл:** {filename}
📝 **Режим:** Добавление
🕐 **Время:** {format_moscow_time()}
💾 **Резервная копия:** {os.path.basename(backup_path)}

**Добавленный текст:**
{clean_content[:200]}{'...' if len(clean_content) > 200 else ''}
"""
            
            elif mode == 'replace':
                # Замена всего содержимого
                clean_content = content.replace('!', '', 1).strip()
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(clean_content)
                
                message = f"""✅ **ИНФОРМАЦИЯ ЗАМЕНЕНА**

📁 **Файл:** {filename}
📝 **Режим:** Полная замена
🕐 **Время:** {format_moscow_time()}
💾 **Резервная копия:** {os.path.basename(backup_path)}

**Размер нового содержимого:** {len(clean_content)} символов
"""
            
            else:
                # По умолчанию - перезапись
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                message = f"""✅ **ИНФОРМАЦИЯ ОБНОВЛЕНА**

📁 **Файл:** {filename}
📝 **Режим:** Перезапись
🕐 **Время:** {format_moscow_time()}
💾 **Резервная копия:** {os.path.basename(backup_path)}

**Размер нового содержимого:** {len(content)} символов
"""
            
            logger.info(f"Файл {filename} обновлен руководителем VIP-отдела")
            
            return {
                'success': True,
                'message': message
            }
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении файла {filename}: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Не удалось обновить файл {filename}: {e}"
            }
    
    def _get_update_mode(self, content: str) -> str:
        """Определяет режим обновления по префиксу"""
        if content.startswith('+'):
            return 'append'  # Добавление
        elif content.startswith('!'):
            return 'replace'  # Полная замена
        else:
            return 'overwrite'  # Перезапись (по умолчанию)
    
    def _create_backup(self, filepath: str) -> str:
        """Создает резервную копию файла"""
        
        if not os.path.exists(filepath):
            # Если файл не существует, создаем пустой
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('')
            return filepath
        
        # Создаем директорию для бэкапов
        backup_dir = os.path.join(self.base_path, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        # Формируем имя бэкапа с временной меткой
        filename = os.path.basename(filepath)
        timestamp = get_moscow_timestamp_str()
        backup_filename = f"{filename}.backup_{timestamp}"
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # Копируем файл
        with open(filepath, 'r', encoding='utf-8') as source:
            content = source.read()
        
        with open(backup_path, 'w', encoding='utf-8') as backup:
            backup.write(content)
        
        logger.info(f"Создана резервная копия: {backup_path}")
        return backup_path
    
    async def _send_help(self, event):
        """Отправляет справку по использованию команды"""
        
        help_text = """📚 **СПРАВКА: ОБНОВЛЕНИЕ ИНФОРМАЦИИ**

**Формат команды:**
```
#обновитьинфу [тип] <содержимое>
```

**Доступные типы:**
• `prompt` - системный промпт бота (по умолчанию)
• `courses` - список курсов
• `processes` - информация о процессах
• `faq` - часто задаваемые вопросы

**Режимы обновления:**
• Без префикса - перезаписать файл
• `+` в начале - добавить к существующему
• `!` в начале - полная замена

**Примеры:**

1. Обновить промпт (перезапись):
```
#обновитьинфу Ты - ВипАлина, помощник для VIP-студентов...
```

2. Добавить информацию о курсе:
```
#обновитьинфу courses +Новый курс "AI Консалтинг" - обучение работе с нейросетями для бизнеса
```

3. Полностью заменить FAQ:
```
#обновитьинфу faq !Вопрос: Как получить доступ?
Ответ: Обратитесь к менеджеру...
```

4. Обновить процессы:
```
#обновитьинфу processes При онбординге студента необходимо...
```

**Важно:**
✅ Автоматически создаются резервные копии
✅ Доступно только вам (руководитель VIP-отдела)
✅ Изменения применяются немедленно

**Текущие файлы:**
"""
        
        # Добавляем информацию о существующих файлах
        for ftype, filename in self.updatable_files.items():
            filepath = os.path.join(self.base_path, filename)
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                help_text += f"\n• `{ftype}` → {filename} ({size} байт)"
            else:
                help_text += f"\n• `{ftype}` → {filename} (не создан)"
        
        await event.reply(help_text)
    
    async def list_backups(self, event):
        """Показывает список резервных копий"""
        
        sender_id = event.sender_id
        if sender_id != VIP_HEAD_ID:
            return
        
        backup_dir = os.path.join(self.base_path, 'backups')
        
        if not os.path.exists(backup_dir):
            await event.reply("📦 Резервных копий пока нет")
            return
        
        backups = sorted(os.listdir(backup_dir), reverse=True)
        
        if not backups:
            await event.reply("📦 Резервных копий пока нет")
            return
        
        message = "📦 **РЕЗЕРВНЫЕ КОПИИ**\n\n"
        
        for backup in backups[:20]:  # Показываем последние 20
            filepath = os.path.join(backup_dir, backup)
            size = os.path.getsize(filepath)
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            message += f"• `{backup}` ({size} байт, {mtime.strftime('%Y-%m-%d %H:%M')})\n"
        
        if len(backups) > 20:
            message += f"\n... и еще {len(backups) - 20} копий"
        
        await event.reply(message)


# Функция для интеграции с основным ботом
def setup_info_updater(client: TelegramClient) -> InfoUpdater:
    """
    Настраивает модуль обновления информации
    
    Args:
        client: Экземпляр Telethon клиента
        
    Returns:
        InfoUpdater: Настроенный экземпляр модуля
    """
    updater = InfoUpdater(client)
    updater.register_handlers()
    logger.info("Модуль обновления информации настроен")
    return updater
