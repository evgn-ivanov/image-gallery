#!/bin/bash
cd telegram-bot
python3 bot.py &
# Держим процесс живым для Render
wait
