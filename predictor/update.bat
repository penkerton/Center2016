@echo off
chcp 65001 >nul
title FHM Hockey Predictor — обновление данных
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

where python >nul 2>nul
if errorlevel 1 (
  echo Python не найден. Установите Python 3.12+ и повторите.
  pause
  exit /b 1
)

python main.py collect
echo.
echo Готово. Лог выше. Окно можно закрыть.
pause
