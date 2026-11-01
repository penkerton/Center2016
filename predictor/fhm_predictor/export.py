"""Экспорт таблиц в CSV/Excel и резервное копирование базы."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from . import config

EXPORT_TABLES = [
    "seasons",
    "tournaments",
    "stages",
    "tournament_groups",
    "teams",
    "team_seasons",
    "matches",
    "match_periods",
    "match_events",
    "players",
    "team_rosters",
    "player_season_stats",
    "player_match_statistics",
    "player_team_history",
    "team_ratings_history",
    "player_ratings_history",
    "predictions",
    "model_versions",
    "collection_runs",
    "data_quality_issues",
]


def export_tables(conn: sqlite3.Connection, output_dir: Path | None = None) -> dict[str, Path]:
    output_dir = Path(output_dir or config.EXPORT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    result: dict[str, Path] = {}

    frames: dict[str, pd.DataFrame] = {}
    for table in EXPORT_TABLES:
        try:
            frame = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        except Exception:  # noqa: BLE001 - таблицы может не быть в старой базе
            continue
        frames[table] = frame
        csv_path = output_dir / f"{table}.csv"
        frame.to_csv(csv_path, index=False, encoding="utf-8-sig", sep=";")
        result[table] = csv_path

    excel_path = output_dir / f"fhm_export_{stamp}.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for table, frame in frames.items():
            sheet = table[:31]
            frame.to_excel(writer, sheet_name=sheet, index=False)
    result["excel"] = excel_path
    return result


def backup_database(db_path: Path | None = None, backup_dir: Path | None = None) -> Path:
    db_path = Path(db_path or config.DB_PATH)
    backup_dir = Path(backup_dir or (config.PROJECT_DIR / "backups"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    destination = backup_dir / f"fhm-{stamp}.db"
    # Онлайн-копия через SQLite backup API — база остаётся консистентной.
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


def database_info(conn: sqlite3.Connection) -> dict[str, Any]:
    size = Path(config.DB_PATH).stat().st_size if Path(config.DB_PATH).exists() else 0
    last = conn.execute("SELECT MAX(fetched_at) AS value FROM matches").fetchone()
    return {
        "path": str(config.DB_PATH),
        "size_bytes": size,
        "last_match_update": last["value"] if last else None,
    }


def copy_site_data(target_dir: Path | None = None) -> Path:
    """Копирует агрегированные данные для статического сайта (экспериментально)."""
    target_dir = Path(target_dir or (config.PROJECT_DIR / "site_export"))
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir
