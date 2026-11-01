# FHM Hockey Predictor

Локальная система прогнозирования матчей детских хоккейных команд Федерации
хоккея Москвы (2016 и 2017 г.р.). Работает на данных `fhmoscow.com`, хранит всё
в SQLite и не требует облачных сервисов.

Это часть проекта [«Центр»](../README.md): статический сайт команды остаётся в
корне `Other/center`, а аналитика и прогнозы живут в этой папке.

## Что уже работает

- Сбор турниров, групп, команд, матчей и заявок игроков за сезоны
  2024/2025, 2025/2026 и 2026/2027 (2 914 матчей, 3 299 игроков).
- Хронологический walk-forward backtest: 2 313 проверочных матчей, ансамбль
  Elo/Пуассон/логистическая регрессия, точность 0,767 (Brier 0,336).
- Прогноз конкретного матча с вероятностями, объяснением и ручной правкой
  состава.
- Контрольный матч «Созвездие 2016» — «Центр 2016» (31.10.2026): прогноз
  сохранён с отсечкой до начала, проверен по факту.
- Русскоязычный интерфейс Streamlit и CLI.

## Быстрый старт (Windows)

Самый простой путь — двойной щелчок по `start.bat` в папке `predictor`:
он сам проверит Python, при необходимости поставит зависимости и откроет
интерфейс в браузере.

Или из PowerShell:

```powershell
cd Other\center\predictor
python -m pip install -r requirements.txt
python main.py collect          # первый сбор данных, 10–20 минут
python main.py backtest         # проверка моделей
.\start.bat                     # интерфейс: http://localhost:8501
```

Если PowerShell не даёт запустить `run_ui.ps1` из-за политики выполнения, используйте
`start.bat` (он не требует подписи) либо:
`powershell -ExecutionPolicy Bypass -File .\run_ui.ps1`.

## Команды

| Команда | Что делает |
|---|---|
| `python main.py init` | создаёт базу и схему |
| `python main.py collect [--season 5]` | обновляет данные ФХМ (инкрементально) |
| `python main.py status` | количество записей и дата обновления |
| `python main.py backtest` | walk-forward проверка, отчёт в `reports/` |
| `python main.py predict --match 22449 [--save]` | прогноз матча (ID виден в интерфейсе) |
| `python main.py verify --match 22449` | сверка сохранённого прогноза с фактом |
| `python main.py protocols --season 5` | разбор HTML-протоколов (счёт по периодам, голы) |
| `python main.py report` | отчёт покрытия `reports/coverage.md` |
| `python main.py check` | проверки качества данных |
| `python main.py export-site` | данные и коэффициенты для статической страницы (`site/data.js`) |
| `python main.py serve [--open]` | локальный сервер страницы + API обновления (`bridge.bat`) |
| `python main.py publish [--push]` | collect → backtest → export-site → git commit (+ push) |
| `python main.py export` | CSV + Excel в `data/exports/` |
| `python main.py backup` | резервная копия базы в `backups/` |

## Страница на сайте

`predictor/index.html` — самостоятельная страница прогноза, которая работает на
GitHub Pages без Python: модели Elo, Пуассона и логистической регрессии
повторены на JavaScript, данные выгружаются в `site/data.js`.

- Публичный адрес: `https://penkerton.github.io/Center2016/predictor/`
  (страница нигде не linked с основным сайтом, `noindex`).
- Обновить данные страницы: `python main.py export-site`, затем закоммитить
  `site/data.js`.
- Локально с кнопками сбора статистики и пересчёта модели: `bridge.bat` →
  `http://127.0.0.1:8765/`. Пароль для кнопок — `refresh`; сервер проверяет его
  сам, а не только браузер.

На GitHub Pages кнопки обновления не работают (там нет Python) — страница
показывает последний выгруженный снимок и честно об этом сообщает.

Обновление и публикация выполняются вручную на локальном компьютере:

```powershell
.\publish.bat        # подтверждение → collect → backtest → export-site → git push
```

Скрипт сам коммитит изменения и публикует их; GitHub Actions пересобирает
страницу через 1–2 минуты.

## Структура

```
fhm_predictor/
  config.py      настройки, целевые сезоны и турниры
  http.py        клиент ФХМ: кеш, пауза, повторы после 429
  api.py         обёртка JSON API и нормализация матчей
  collect.py     сбор данных в SQLite
  db.py          схема и upsert
  protocols.py   разбор HTML-протокола матча
  engine.py      Elo, форма, Пуассон, рейтинг игроков
  features.py    признаки без утечки будущего
  models.py      softmax-регрессия и метрики
  backtest.py    walk-forward и отчёты
  predict.py     прогноз, объяснение, сохранение, сверка
  projections.py прогноз турнирной таблицы по оставшимся матчам
  export_site.py выгрузка данных и коэффициентов для страницы
  bridge.py      локальный сервер: статика + API обновления
  coverage.py    отчёт покрытия
  quality.py     проверки данных
  export.py      экспорт и резервные копии
  repository.py  запросы для интерфейса
main.py          CLI
app.py           Streamlit
site/            data.js, model.js, app.js, style.css (статические данные и UI)
index.html       страница /predictor/
tests/           unittest, включая тест отсутствия утечки
docs/            документация проекта
```

## Документация

- [Обзор проекта](docs/PROJECT_OVERVIEW.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [Источники данных](docs/DATA_SOURCES.md)
- [Схема базы](docs/DATABASE_SCHEMA.md)
- [История игроков и переходы](docs/PLAYER_TRACKING.md)
- [Методика моделей](docs/MODEL_METHODOLOGY.md)
- [Результаты backtest](docs/BACKTEST_RESULTS.md)
- [Качество данных](docs/DATA_QUALITY.md)
- [Руководство пользователя](docs/USER_GUIDE.md)
- [Журнал разработки](docs/DEVELOPMENT_PROGRESS.md)
- [Ограничения](docs/KNOWN_LIMITATIONS.md)

## Приватность

Проект локальный. В нём нет контактов, адресов и фотографий: только публичные
спортивные данные (имя, год рождения, амплуа, игровая статистика). Папки
`data/`, `predictions/`, `backups/` и `reports/` исключены из git — в
публичный репозиторий сайта они не попадают.
