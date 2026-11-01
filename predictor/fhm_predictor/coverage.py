"""Отчёт покрытия: сколько турниров, команд, матчей и игроков собрано."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from . import config


def build_coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    tournaments = conn.execute(
        """
        SELECT t.id, t.name, t.age_year, t.format, s.label AS season_label,
               (SELECT COUNT(*) FROM tournament_groups g WHERE g.tournament_id = t.id) AS groups,
               (SELECT COUNT(DISTINCT ts.team_id) FROM team_seasons ts WHERE ts.tournament_id = t.id) AS teams,
               (SELECT COUNT(*) FROM matches m WHERE m.tournament_id = t.id) AS matches,
               (SELECT COUNT(*) FROM matches m WHERE m.tournament_id = t.id AND m.played = 1) AS played,
               (SELECT COUNT(*) FROM matches m WHERE m.tournament_id = t.id AND m.played = 0) AS scheduled,
               (SELECT COUNT(*) FROM matches m WHERE m.tournament_id = t.id AND m.source_url LIKE '%/game/%') AS with_url
        FROM tournaments t
        JOIN seasons s ON s.id = t.season_id
        ORDER BY t.season_id, t.id
        """
    ).fetchall()

    players = conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
    rosters = conn.execute("SELECT COUNT(*) AS n FROM team_rosters").fetchone()["n"]
    with_birth = conn.execute("SELECT COUNT(*) AS n FROM players WHERE birth_date IS NOT NULL").fetchone()["n"]
    seasons = conn.execute("SELECT COUNT(*) AS n FROM seasons").fetchone()["n"]
    groups = conn.execute("SELECT COUNT(*) AS n FROM tournament_groups").fetchone()["n"]
    teams = conn.execute("SELECT COUNT(*) AS n FROM teams").fetchone()["n"]
    matches = conn.execute("SELECT COUNT(*) AS n FROM matches").fetchone()["n"]
    played = conn.execute("SELECT COUNT(*) AS n FROM matches WHERE played = 1").fetchone()["n"]
    events = conn.execute("SELECT COUNT(*) AS n FROM match_events").fetchone()["n"]
    periods = conn.execute("SELECT COUNT(*) AS n FROM match_periods").fetchone()["n"]
    issues = conn.execute("SELECT COUNT(*) AS n FROM data_quality_issues").fetchone()["n"]

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "totals": {
            "seasons": seasons,
            "tournaments": len(tournaments),
            "groups": groups,
            "teams": teams,
            "matches": matches,
            "played": played,
            "scheduled": matches - played,
            "players": players,
            "players_with_birthdate": with_birth,
            "roster_rows": rosters,
            "match_events": events,
            "match_periods": periods,
            "quality_issues": issues,
        },
        "tournaments": [dict(row) for row in tournaments],
        "notes": [
            "Матчи без счёта — будущие игры сезона 2026/2027, они не считаются пропусками.",
            "Заявки игроков собраны для сезонов 2025/2026 и 2026/2027 (сезон 2024/2025 — частично).",
            "Построчные составы на странице матча подгружаются JS и в HTML отсутствуют.",
        ],
    }


def save_coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    coverage = build_coverage(conn)
    directory = config.PROJECT_DIR / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Покрытие данных",
        "",
        f"Сформировано: {coverage['generated_at']}",
        "",
        "| Сезон | Турнир | Групп | Команд | Матчей | Сыграно | Игр впереди |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in coverage["tournaments"]:
        lines.append(
            f"| {row['season_label']} | {row['name']} | {row['groups']} | {row['teams']} | "
            f"{row['matches']} | {row['played']} | {row['scheduled']} |"
        )
    lines += ["", "## Итого", ""]
    for key, value in coverage["totals"].items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    (directory / "coverage.md").write_text("\n".join(lines), encoding="utf-8")
    return coverage
