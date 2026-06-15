"""
Модуль формирования ежемесячных отчётов по SLA.
Отправляет отчёт руководителю VIP-отдела в конце месяца.
"""

import logging
from datetime import datetime, timedelta
import asyncio
import pytz
from typing import Dict, Any
from telethon import TelegramClient

from config import (
    VIP_HEAD,
    MOSCOW_TZ,
    SLA_RESPONSE_TIME_LIMIT
)

logger = logging.getLogger('vipalina_sla_reporter')


class SLAReporter:
    """
    Генератор ежемесячных отчётов по SLA.
    """
    
    def __init__(self, client: TelegramClient, sla_sheets):
        """
        Args:
            client: Telethon клиент
            sla_sheets: Интеграция с Google Sheets SLA
        """
        self.client = client
        self.sla_sheets = sla_sheets
        self.moscow_tz = pytz.timezone(MOSCOW_TZ)
        self.vip_head_id = VIP_HEAD['telegram_id']
        self.is_running = False
        logger.info("Инициализирован SLA Reporter")
    
    async def start(self):
        """Запускает планировщик отчётов"""
        self.is_running = True
        logger.info("SLA Reporter запущен")
        
        # Запускаем фоновую задачу
        asyncio.create_task(self._schedule_loop())
    
    async def stop(self):
        """Останавливает планировщик"""
        self.is_running = False
        logger.info("SLA Reporter остановлен")
    
    async def _schedule_loop(self):
        """Основной цикл планировщика отчётов"""
        while self.is_running:
            try:
                now = datetime.now(self.moscow_tz)
                
                # Проверяем, последний ли день месяца
                if self._is_last_day_of_month(now) and now.hour == 20 and now.minute < 10:
                    logger.info(f"Время отправки ежемесячного SLA-отчёта: {now}")
                    await self.send_monthly_report()
                    
                    # Ждём 2 часа, чтобы не отправить повторно
                    await asyncio.sleep(3600 * 2)
                
                # Проверяем каждые 10 минут
                await asyncio.sleep(600)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле SLA Reporter: {e}", exc_info=True)
                await asyncio.sleep(600)
    
    def _is_last_day_of_month(self, dt: datetime) -> bool:
        """Проверяет, является ли день последним в месяце"""
        next_day = dt + timedelta(days=1)
        return next_day.month != dt.month
    
    async def send_monthly_report(self, year: int = None, month: int = None) -> bool:
        """
        Формирует и отправляет ежемесячный отчёт.
        
        Args:
            year: Год (если None - текущий месяц)
            month: Месяц (если None - текущий месяц)
            
        Returns:
            True если отчёт отправлен успешно
        """
        try:
            now = datetime.now(self.moscow_tz)
            
            # Если год и месяц не указаны - берём текущий месяц
            if year is None or month is None:
                year = now.year
                month = now.month
            
            logger.info(f"Формирование SLA-отчёта за {month}/{year}")
            
            # Получаем статистику
            stats = self.sla_sheets.get_monthly_stats(year, month)
            
            # Формируем отчёт
            report = self._format_report(stats, year, month)
            
            # Отправляем руководителю
            await self.client.send_message(self.vip_head_id, report)
            
            logger.info(f"SLA-отчёт за {month}/{year} отправлен руководителю")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке ежемесячного отчёта: {e}", exc_info=True)
            return False
    
    def _format_report(self, stats: Dict[str, Any], year: int, month: int) -> str:
        """
        Форматирует отчёт в текстовом виде.
        
        Args:
            stats: Статистика SLA
            year: Год
            month: Месяц
            
        Returns:
            Отформатированный отчёт
        """
        month_name_ru = {
            1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
            5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
            9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
        }
        
        report = f"""📊 **ЕЖЕМЕСЯЧНЫЙ ОТЧЁТ SLA**
**Период:** {month_name_ru[month]} {year}

━━━━━━━━━━━━━━━━━━━━━━━━━

📈 **ОБЩАЯ СТАТИСТИКА:**

🔹 Всего запросов: {stats['total_requests']}
🔹 Запросов в рабочее время: {stats['working_hours_requests']}
🔹 SLA соблюдён (≤{SLA_RESPONSE_TIME_LIMIT} мин): {stats['sla_met_count']}
🔹 SLA НЕ соблюдён: {stats['sla_not_met_count']}

⏱️ **Среднее время ответа:** {stats['avg_response_time']:.1f} мин
"""
        
        if stats['working_hours_requests'] > 0:
            sla_percentage = round(
                (stats['sla_met_count'] / stats['working_hours_requests']) * 100,
                1
            )
            report += f"✅ **Процент соблюдения SLA:** {sla_percentage}%\n"
        
        # Статистика по менеджерам
        if stats['by_manager']:
            report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            report += "\n👥 **СТАТИСТИКА ПО МЕНЕДЖЕРАМ:**\n\n"
            
            # Сортируем по среднему времени
            managers_sorted = sorted(
                stats['by_manager'].items(),
                key=lambda x: x[1].get('avg_time', 999)
            )
            
            for manager_name, manager_stats in managers_sorted:
                avg_time = manager_stats.get('avg_time', 0)
                sla_perc = manager_stats.get('sla_percentage', 0)
                requests = manager_stats['requests']
                sla_met = manager_stats['sla_met']
                
                # Эмодзи в зависимости от результата
                if avg_time <= SLA_RESPONSE_TIME_LIMIT:
                    emoji = "🟢"
                elif avg_time <= SLA_RESPONSE_TIME_LIMIT * 1.5:
                    emoji = "🟡"
                else:
                    emoji = "🔴"
                
                report += f"{emoji} **{manager_name}**\n"
                report += f"   • Запросов: {requests}\n"
                report += f"   • Среднее время: {avg_time:.1f} мин\n"
                report += f"   • SLA соблюдён: {sla_met}/{requests} ({sla_perc:.1f}%)\n\n"
        
        report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"\n📋 Подробные данные: [Google Sheets](https://docs.google.com/spreadsheets/d/{self.sla_sheets.spreadsheet.id})"
        
        return report
