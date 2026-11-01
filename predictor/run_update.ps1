# Обновление данных ФХМ (то же, что кнопка «Обновить статистику»).
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
python main.py collect
