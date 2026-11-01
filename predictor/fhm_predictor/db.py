"""SQLite-хранилище FHM Hockey Predictor.

Схема повторяет обязательный минимум из технического задания: справочники,
матчи, игроки, история принадлежности, рейтинги, прогнозы, версии моделей,
журналы сбора и качества данных. Для каждой записи, пришедшей извне, хранится
происхождение (URL/ID источника и время загрузки).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config

SCHEMA_VERSION = "1"

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    params_json TEXT,
    stats_json TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES collection_runs(id),
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    entity TEXT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seasons (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    start_year INTEGER,
    end_year INTEGER,
    is_current INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES seasons(id),
    name TEXT NOT NULL,
    age_year INTEGER,
    format TEXT,
    play_off INTEGER,
    transition INTEGER,
    is_current INTEGER
);

CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
    name TEXT,
    is_current INTEGER,
    is_transition INTEGER
);

CREATE TABLE IF NOT EXISTS tournament_groups (
    id INTEGER PRIMARY KEY,
    stage_id INTEGER NOT NULL REFERENCES stages(id),
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
    name TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT,
    age_year INTEGER,
    club TEXT
);

CREATE TABLE IF NOT EXISTS team_seasons (
    team_id INTEGER NOT NULL REFERENCES teams(id),
    season_id INTEGER NOT NULL REFERENCES seasons(id),
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
    group_id INTEGER NOT NULL REFERENCES tournament_groups(id),
    PRIMARY KEY (team_id, season_id, tournament_id, group_id)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES seasons(id),
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
    stage_id INTEGER NOT NULL REFERENCES stages(id),
    group_id INTEGER NOT NULL REFERENCES tournament_groups(id),
    tour_name TEXT,
    date TEXT NOT NULL,
    time TEXT,
    home_team_id INTEGER NOT NULL REFERENCES teams(id),
    away_team_id INTEGER NOT NULL REFERENCES teams(id),
    home_name TEXT NOT NULL,
    away_name TEXT NOT NULL,
    home_goals INTEGER,
    away_goals INTEGER,
    status INTEGER,
    overtime INTEGER NOT NULL DEFAULT 0,
    shootout INTEGER NOT NULL DEFAULT 0,
    technical_defeat INTEGER NOT NULL DEFAULT 0,
    cancel_status TEXT,
    played INTEGER NOT NULL DEFAULT 0,
    source_url TEXT,
    fetched_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_home ON matches(home_team_id);
CREATE INDEX IF NOT EXISTS idx_matches_away ON matches(away_team_id);
CREATE INDEX IF NOT EXISTS idx_matches_season ON matches(season_id);
CREATE INDEX IF NOT EXISTS idx_matches_group ON matches(group_id);

CREATE TABLE IF NOT EXISTS match_periods (
    match_id INTEGER NOT NULL REFERENCES matches(id),
    period INTEGER NOT NULL,
    home_goals INTEGER,
    away_goals INTEGER,
    PRIMARY KEY (match_id, period)
);

CREATE TABLE IF NOT EXISTS match_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    period INTEGER,
    minute TEXT,
    team_id INTEGER,
    player_id INTEGER,
    event_type TEXT NOT NULL,
    detail TEXT,
    score_home INTEGER,
    score_away INTEGER,
    source TEXT,
    UNIQUE (match_id, period, minute, player_id, event_type)
);

CREATE INDEX IF NOT EXISTS idx_events_match ON match_events(match_id);
CREATE INDEX IF NOT EXISTS idx_events_player ON match_events(player_id);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    birth_date TEXT,
    role TEXT,
    url TEXT,
    first_seen TEXT,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS team_rosters (
    team_id INTEGER NOT NULL REFERENCES teams(id),
    season_id INTEGER NOT NULL REFERENCES seasons(id),
    player_id INTEGER NOT NULL REFERENCES players(id),
    number INTEGER,
    role TEXT,
    source TEXT,
    fetched_at TEXT,
    PRIMARY KEY (team_id, season_id, player_id)
);

CREATE TABLE IF NOT EXISTS player_season_stats (
    player_id INTEGER NOT NULL REFERENCES players(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    season_id INTEGER NOT NULL REFERENCES seasons(id),
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
    games INTEGER NOT NULL DEFAULT 0,
    goals INTEGER NOT NULL DEFAULT 0,
    assists INTEGER NOT NULL DEFAULT 0,
    points INTEGER NOT NULL DEFAULT 0,
    penalties INTEGER NOT NULL DEFAULT 0,
    missed INTEGER NOT NULL DEFAULT 0,
    time_seconds INTEGER NOT NULL DEFAULT 0,
    source TEXT,
    fetched_at TEXT,
    PRIMARY KEY (player_id, team_id, season_id, tournament_id)
);

CREATE TABLE IF NOT EXISTS player_team_history (
    player_id INTEGER NOT NULL REFERENCES players(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    season_id INTEGER NOT NULL REFERENCES seasons(id),
    first_match_date TEXT,
    last_match_date TEXT,
    games INTEGER NOT NULL DEFAULT 0,
    goals INTEGER NOT NULL DEFAULT 0,
    assists INTEGER NOT NULL DEFAULT 0,
    source TEXT,
    PRIMARY KEY (player_id, team_id, season_id)
);

CREATE TABLE IF NOT EXISTS player_match_statistics (
    player_id INTEGER NOT NULL REFERENCES players(id),
    match_id INTEGER NOT NULL REFERENCES matches(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    goals INTEGER NOT NULL DEFAULT 0,
    assists INTEGER NOT NULL DEFAULT 0,
    participated INTEGER,
    source TEXT,
    PRIMARY KEY (player_id, match_id)
);

CREATE TABLE IF NOT EXISTS team_ratings_history (
    team_id INTEGER NOT NULL REFERENCES teams(id),
    as_of TEXT NOT NULL,
    elo REAL,
    matches INTEGER NOT NULL DEFAULT 0,
    attack REAL,
    defense REAL,
    PRIMARY KEY (team_id, as_of)
);

CREATE TABLE IF NOT EXISTS player_ratings_history (
    player_id INTEGER NOT NULL REFERENCES players(id),
    as_of TEXT NOT NULL,
    rating REAL NOT NULL,
    games INTEGER NOT NULL DEFAULT 0,
    goals INTEGER NOT NULL DEFAULT 0,
    assists INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, as_of)
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER,
    model_version TEXT,
    model_kind TEXT,
    created_at TEXT NOT NULL,
    cutoff TEXT,
    prob_home REAL NOT NULL,
    prob_draw REAL NOT NULL,
    prob_away REAL NOT NULL,
    features_json TEXT,
    features_hash TEXT,
    actual_home INTEGER,
    actual_away INTEGER,
    actual_outcome TEXT,
    correct INTEGER
);

CREATE INDEX IF NOT EXISTS idx_predictions_match ON predictions(match_id);

CREATE TABLE IF NOT EXISTS model_versions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    params_json TEXT,
    metrics_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS model_training_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    model_version TEXT,
    params_json TEXT,
    metrics_json TEXT,
    error TEXT
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: Path | str = config.DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Streamlit запускает скрипт в разных потоках — соединение должно это допускать.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SCHEMA_VERSION,),
    )
    conn.commit()


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def upsert(
    conn: sqlite3.Connection,
    table: str,
    rows: Iterable[dict[str, Any]],
    pk: Iterable[str],
) -> int:
    """INSERT ... ON CONFLICT DO UPDATE по списку первичных ключей."""
    rows = list(rows)
    if not rows:
        return 0
    pk = list(pk)
    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    update_columns = [column for column in columns if column not in pk]
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    if update_columns:
        assignments = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
        sql += f" ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {assignments}"
    else:
        sql += f" ON CONFLICT ({', '.join(pk)}) DO NOTHING"
    conn.executemany(sql, [tuple(row.get(column) for column in columns) for row in rows])
    return len(rows)


def start_run(conn: sqlite3.Connection, params: dict[str, Any]) -> int:
    cursor = conn.execute(
        "INSERT INTO collection_runs(started_at, status, params_json) VALUES(?, 'running', ?)",
        (utc_now(), json.dumps(params, ensure_ascii=False)),
    )
    conn.commit()
    return int(cursor.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    stats: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE collection_runs SET finished_at = ?, status = ?, stats_json = ?, error = ? WHERE id = ?",
        (utc_now(), status, json.dumps(stats or {}, ensure_ascii=False), error, run_id),
    )
    conn.commit()


def add_issue(
    conn: sqlite3.Connection,
    *,
    run_id: int | None,
    kind: str,
    severity: str,
    entity: str | None,
    message: str,
) -> None:
    conn.execute(
        "INSERT INTO data_quality_issues(run_id, kind, severity, entity, message, created_at) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        (run_id, kind, severity, entity, message, utc_now()),
    )


def latest_update(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(fetched_at) AS fetched FROM matches").fetchone()
    return row["fetched"] if row else None


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        "seasons",
        "tournaments",
        "stages",
        "tournament_groups",
        "teams",
        "matches",
        "match_events",
        "players",
        "team_rosters",
        "player_season_stats",
        "player_ratings_history",
        "team_ratings_history",
        "predictions",
        "model_versions",
        "collection_runs",
        "data_quality_issues",
    ]
    result: dict[str, int] = {}
    for table in tables:
        try:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            result[table] = int(row["n"])
        except sqlite3.Error:
            result[table] = -1
    return result
