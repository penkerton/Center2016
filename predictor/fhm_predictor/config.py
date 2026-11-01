"""Настройки проекта FHM Hockey Predictor.

Все пути вычисляются относительно каталога ``predictor/``, поэтому проект
переносим вместе с папкой ``Other/center``.
"""

from __future__ import annotations

from pathlib import Path

# --- Пути -----------------------------------------------------------------

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent  # Other/center/predictor
CENTER_DIR = PROJECT_DIR.parent  # Other/center (статический сайт команды)

DATA_DIR = PROJECT_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
RAW_DIR = DATA_DIR / "raw"
EXPORT_DIR = DATA_DIR / "exports"
PREDICTIONS_DIR = PROJECT_DIR / "predictions"
DB_PATH = DATA_DIR / "fhm.db"

# --- Источник -------------------------------------------------------------

BASE_URL = "https://www.fhmoscow.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 FHM-Hockey-Predictor/0.1"
)

# Сайт отдаёт 429 при частых запросах к /api. Держим паузу между запросами.
API_MIN_INTERVAL_SECONDS = 1.2
REQUEST_TIMEOUT_SECONDS = 45
MAX_RETRIES = 5
API_CACHE_TTL_SECONDS = 6 * 3600
HTML_CACHE_TTL_SECONDS = 24 * 3600

# /api/game/list принимает limit не больше 50 (при 100 отвечает HTTP 400).
GAME_PAGE_SIZE = 50

# --- Предметная область ---------------------------------------------------

# Сезоны ФХМ: 3 = 2024/2025, 4 = 2025/2026, 5 = 2026/2027 (текущий).
TARGET_SEASONS = (3, 4, 5)

# Турниры, которые относятся к командам 2016 и 2017 года рождения.
# 3:  Кубок ФХМ 2016 г.р. (первый и второй этапы) — исторический слой
# 4:  Кубок 2016 г.р. 25/26, Кубок 2017 г.р. (первый и второй этапы)
# 5:  2016 г.р. 26/27 (5х5), 2016 г.р. 26/27 (4х4), 2017 г.р. 26/27 (4х4)
TARGET_TOURNAMENTS: dict[int, tuple[int, ...]] = {
    3: (12, 13),
    4: (22, 23, 24),
    5: (48, 51, 54),
}

# Возрастные категории, которые считаем «своими» для проекта.
TARGET_AGE_YEARS = (2016, 2017)

# Заявки игроков собираем только для актуальных сезонов: история сезона 2024/25
# восстанавливается по карточкам игроков и нужна только для рейтингов.
ROSTER_SEASONS = (4, 5)

# --- Контрольный матч -----------------------------------------------------

CONTROL_MATCH_ID = 22449
CONTROL_MATCH_URL = f"{BASE_URL}/game/{CONTROL_MATCH_ID}"
# Отсечка: всё, что стало известно после начала матча, использовать нельзя.
CONTROL_CUTOFF_ISO = "2026-10-31T09:45:00+03:00"

# --- Модели ---------------------------------------------------------------

RANDOM_SEED = 20261031

# Параметры Elo
ELO_START = 1500.0
ELO_K = 24.0
ELO_HOME_ADVANTAGE = 60.0
ELO_SEASON_REGRESSION = 1.0 / 3.0  # доля возврата к среднему между сезонами

# Параметры сглаживания индивидуальных рейтингов (байесовское сжатие)
PLAYER_PRIOR_GAMES = 8.0
PLAYER_PRIOR_RATE = 1.2  # шайб на матч для «среднего» игрока до данных

# Минимум матчей для честной оценки модели в отчётах
MIN_MATCHES_FOR_METRICS = 30
