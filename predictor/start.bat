@echo off
chcp 65001 >nul
title FHM Hockey Predictor
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

where python >nul 2>nul
if errorlevel 1 (
  echo Python не найден. Установите Python 3.12+ и повторите.
  pause
  exit /b 1
)

python -c "import streamlit" >nul 2>nul
if errorlevel 1 (
  echo Первый запуск: устанавливаю зависимости...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Не удалось установить зависимости.
    pause
    exit /b 1
  )
)

echo Открываю интерфейс в браузере...
python -m streamlit run app.py

pause
