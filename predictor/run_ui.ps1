# Запуск локального интерфейса FHM Hockey Predictor.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
python -m streamlit run app.py
