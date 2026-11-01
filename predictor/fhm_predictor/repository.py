"""Запросы к базе для интерфейса и отчётов."""

from __future__ import annotations

import sqlite3
from typing import Any

from .engine import EloEngine, Match, load_matches


def seasons(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM seasons ORDER BY id").fetchall()


def tournaments(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT t.*, s.label AS season_label
        FROM tournaments t JOIN seasons s ON s.id = t.season_id
        ORDER BY t.season_id, t.name
        """
    ).fetchall()


def groups(conn: sqlite3.Connection, tournament_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM tournament_groups WHERE tournament_id = ? ORDER BY name",
        (tournament_id,),
    ).fetchall()


def teams(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM teams ORDER BY name COLLATE NOCASE").fetchall()


def team_rows(conn: sqlite3.Connection, season_id: int | None = None) -> list[sqlite3.Row]:
    query = """
        SELECT DISTINCT t.*
        FROM teams t
        JOIN team_seasons ts ON ts.team_id = t.id
    """
    params: tuple[Any, ...] = ()
    if season_id is not None:
        query += " WHERE ts.season_id = ?"
        params = (season_id,)
    query += " ORDER BY t.name COLLATE NOCASE"
    return conn.execute(query, params).fetchall()


def roster(conn: sqlite3.Connection, team_id: int, season_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT p.id, p.full_name, p.birth_date, p.role, r.number,
               COALESCE(s.games, 0) AS games,
               COALESCE(s.goals, 0) AS goals,
               COALESCE(s.assists, 0) AS assists,
               COALESCE(s.points, 0) AS points,
               COALESCE(s.penalties, 0) AS penalties
        FROM team_rosters r
        JOIN players p ON p.id = r.player_id
        LEFT JOIN player_season_stats s
               ON s.player_id = r.player_id AND s.team_id = r.team_id AND s.season_id = r.season_id
        WHERE r.team_id = ? AND r.season_id = ?
        ORDER BY COALESCE(s.goals, 0) DESC, p.full_name
        """,
        (team_id, season_id),
    ).fetchall()


def player_history(conn: sqlite3.Connection, player_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT th.season_id, se.label AS season_label, th.team_id, t.name AS team_name,
               th.games, th.goals, th.assists
        FROM player_team_history th
        JOIN seasons se ON se.id = th.season_id
        JOIN teams t ON t.id = th.team_id
        WHERE th.player_id = ?
        ORDER BY th.season_id, t.name
        """,
        (player_id,),
    ).fetchall()


def player_row(conn: sqlite3.Connection, player_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()


def team_matches(conn: sqlite3.Connection, team_id: int, limit: int = 10, before: str | None = None) -> list[sqlite3.Row]:
    query = """
        SELECT m.*, g.name AS group_name, tr.name AS tournament_name, s.label AS season_label
        FROM matches m
        JOIN tournament_groups g ON g.id = m.group_id
        JOIN tournaments tr ON tr.id = m.tournament_id
        JOIN seasons s ON s.id = m.season_id
        WHERE (m.home_team_id = ? OR m.away_team_id = ?) AND m.played = 1
    """
    params: list[Any] = [team_id, team_id]
    if before:
        query += " AND m.date < ?"
        params.append(before)
    query += " ORDER BY m.date DESC, m.id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def h2h(conn: sqlite3.Connection, team_a: int, team_b: int, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT m.* FROM matches m
        WHERE m.played = 1
          AND ((m.home_team_id = ? AND m.away_team_id = ?) OR (m.home_team_id = ? AND m.away_team_id = ?))
        ORDER BY m.date DESC
        LIMIT ?
        """,
        (team_a, team_b, team_b, team_a, limit),
    ).fetchall()


def upcoming_matches(conn: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT m.*, tr.name AS tournament_name, tr.age_year, tr.format, g.name AS group_name
        FROM matches m
        JOIN tournaments tr ON tr.id = m.tournament_id
        JOIN tournament_groups g ON g.id = m.group_id
        WHERE m.played = 0 AND m.date >= date('now')
        ORDER BY m.date, m.time
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def match_row(conn: sqlite3.Connection, match_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT m.*, tr.name AS tournament_name, tr.age_year, tr.format, g.name AS group_name
        FROM matches m
        JOIN tournaments tr ON tr.id = m.tournament_id
        JOIN tournament_groups g ON g.id = m.group_id
        WHERE m.id = ?
        """,
        (match_id,),
    ).fetchone()


def elo_snapshot(conn: sqlite3.Connection) -> dict[int, dict[str, float]]:
    engine = EloEngine()
    for match in load_matches(conn):
        engine.update(match)
    return {
        team_id: {"elo": round(rating, 1), "games": engine.games.get(team_id, 0)}
        for team_id, rating in engine.ratings.items()
    }


def collection_runs(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM collection_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def quality_issues(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM data_quality_issues ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


def last_matches_all(conn: sqlite3.Connection) -> list[Match]:
    return load_matches(conn)
