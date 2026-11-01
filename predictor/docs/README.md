# FHM Hockey Predictor — спецификация

Этот каталог — набор проектной документации FHM Hockey Predictor. Он описывает
фактическое состояние системы, а не первоначальный план.

| Документ | О чём |
|---|---|
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | назначение, готовность, ключевые числа |
| [ARCHITECTURE.md](ARCHITECTURE.md) | модули, поток данных, обновление, тесты |
| [DATA_SOURCES.md](DATA_SOURCES.md) | устройство сайта ФХМ, API, robots.txt, ограничения |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | таблицы, ключи, происхождение, примеры SQL |
| [PLAYER_TRACKING.md](PLAYER_TRACKING.md) | ID игроков, заявки, переходы, рейтинг |
| [MODEL_METHODOLOGY.md](MODEL_METHODOLOGY.md) | Elo, Пуассон, признаки, логистика, ансамбль |
| [BACKTEST_RESULTS.md](BACKTEST_RESULTS.md) | метрики, калибровка, контрольный матч |
| [DATA_QUALITY.md](DATA_QUALITY.md) | проверки, найденные и исправленные дефекты |
| [USER_GUIDE.md](USER_GUIDE.md) | установка, интерфейс, команды, проблемы |
| [DEVELOPMENT_PROGRESS.md](DEVELOPMENT_PROGRESS.md) | журнал этапов и решений |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | честные границы применимости |

Быстрый старт и структура кода — в [../README.md](../README.md).

## Правила поддержки

1. Числа в документах должны совпадать с `reports/backtest.json`,
   `reports/coverage.md` и `data/fhm.db`.
2. После изменения моделей пересчитайте backtest и обновите
   `BACKTEST_RESULTS.md`.
3. После изменения сбора обновите `DATA_SOURCES.md` и `DATA_QUALITY.md`.
4. Ограничения не удаляются задним числом: если проблема решена, она переезжает
   в раздел «найденные и исправленные».
