#!/bin/bash
cd /Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina
pkill -9 -f "python.*vip_automation_main"
sleep 2
nohup python3 vip_automation_main.py > /dev/null 2>&1 < /dev/null &
sleep 3
ps aux | grep "python.*vip_automation_main" | grep -v grep | awk '{print "✅ Бот запущен! PID: "$2}'
