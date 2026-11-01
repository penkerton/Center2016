@echo off
chcp 65001 >nul
title FHM Hockey Predictor — обновление и публикация
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

where python >nul 2>nul
if errorlevel 1 (
  echo Python не найден. Установите Python 3.12+ и повторите.
  pause
  exit /b 1
)

echo.
echo Обновление статистики, пересчёт модели и публикация на GitHub Pages.
echo Это может занять 10-20 минут: сайт ФХМ ограничивает частоту запросов.
echo.
set /p ANSWER=Продолжить? (y/n):
if /i not "%ANSWER%"=="y" (
  echo Отменено.
  pause
  exit /b 0
)

python main.py publish --push
echo.
echo Готово. Проверьте https://penkerton.github.io/Center2016/predictor/
pause
