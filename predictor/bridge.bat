@echo off
chcp 65001 >nul
title FHM Hockey Predictor — локальный сервер
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

where python >nul 2>nul
if errorlevel 1 (
  echo Python не найден. Установите Python 3.12+ и повторите.
  pause
  exit /b 1
)

echo Открываю страницу прогноза: http://127.0.0.1:8765/
echo Обновление данных и пересчёт модели — по паролю refresh.
python main.py serve --open

pause
