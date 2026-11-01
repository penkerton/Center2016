"""Проверки качества данных: дубли, пропуски, аномалии."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any


def run_checks(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(kind: str, severity: str, message: str, count: int) -> None:
        checks.append({"kind": kind, "severity": severity, "message": message, "count": count})

    duplicates = conn.execute(
        """
        SELECT date, home_team_id, away_team_id, COUNT(*) AS n
        FROM matches
        GROUP BY date, home_team_id, away_team_id
        HAVING n > 1
        """
    ).fetchall()
    add("duplicate_matches", "error", "Матчи-дубликаты (одна дата и пара команд)", len(duplicates))

    missing_scores = conn.execute(
        "SELECT COUNT(*) AS n FROM matches WHERE played = 0 AND date < ?", (date.today().isoformat(),)
    ).fetchone()["n"]
    add("past_without_score", "warning", "Прошедшие матчи без счёта", int(missing_scores))

    unknown_teams = conn.execute(
        "SELECT COUNT(*) AS n FROM matches WHERE home_team_id IS NULL OR away_team_id IS NULL"
    ).fetchone()["n"]
    add("unknown_team", "error", "Матчи без сопоставленной команды", int(unknown_teams))

    empty_rosters = conn.execute(
        """
        SELECT COUNT(*) AS n FROM teams t
        WHERE EXISTS (SELECT 1 FROM team_seasons ts WHERE ts.team_id = t.id AND ts.season_id IN (4, 5))
          AND NOT EXISTS (SELECT 1 FROM team_rosters r WHERE r.team_id = t.id)
        """
    ).fetchone()["n"]
    add("team_without_roster", "warning", "Команды без заявки игроков", int(empty_rosters))

    no_birth = conn.execute("SELECT COUNT(*) AS n FROM players WHERE birth_date IS NULL").fetchone()["n"]
    add("player_without_birthdate", "info", "Игроки без даты рождения", int(no_birth))

    outliers = conn.execute(
        "SELECT COUNT(*) AS n FROM matches WHERE played = 1 AND ABS(home_goals - away_goals) > 25"
    ).fetchone()["n"]
    add("score_outlier", "info", "Матчи с разницей больше 25 шайб", int(outliers))

    event_mismatch = conn.execute(
        """
        SELECT COUNT(*) AS n FROM (
            SELECT m.id,
                   (m.home_goals + m.away_goals) AS goals,
                   (SELECT COUNT(*) FROM match_events e WHERE e.match_id = m.id AND e.event_type = 'goal') AS events
            FROM matches m
            WHERE m.played = 1
        ) WHERE goals <> events AND events > 0
        """
    ).fetchone()["n"]
    add("events_score_mismatch", "warning", "Число голов в событиях не совпадает со счётом", int(event_mismatch))

    stale = conn.execute("SELECT MAX(fetched_at) AS value FROM matches").fetchone()["value"]
    add("data_freshness", "info", f"Последнее обновление матчей: {stale or 'нет данных'}", 0)
    return checks
