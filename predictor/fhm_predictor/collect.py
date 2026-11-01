"""Сбор данных ФХМ в локальную базу.

Порядок: сезоны → турниры → этапы → группы → команды → матчи → заявки игроков.
Повторный запуск обновляет существующие записи и не создаёт дубликатов:
ключи — официальные ID ФХМ.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from . import api as fhm_api
from . import config, db
from .api import FhmApi, as_list, normalize_game, parse_age_year, parse_format
from .http import FhmHttp

Progress = Callable[[str], None]

_NAME_YEAR_RE = re.compile(r"^(?P<club>.+?)\s*(?P<year>20\d{2})(?:\s*-\s*\d+)?$")
_PLAYER_ID_RE = re.compile(r"/player/(\d+)")


def _noop(message: str) -> None:  # pragma: no cover - используется как заглушка
    del message


def parse_team_name(name: str) -> tuple[str, int | None]:
    """«Центр 2016 - 1» → («Центр», 2016)."""
    text = (name or "").strip()
    match = _NAME_YEAR_RE.match(text)
    if match:
        return match.group("club").strip(), int(match.group("year"))
    return text, None


def iso_birth_date(value: str) -> str | None:
    text = (value or "").strip()
    match = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", text)
    if not match:
        return None
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"


def collect(
    seasons: tuple[int, ...] = config.TARGET_SEASONS,
    *,
    refresh: bool = False,
    with_rosters: bool = True,
    progress: Progress = _noop,
) -> dict[str, Any]:
    """Собирает справочники, матчи и заявки. Возвращает статистику запуска."""
    http = FhmHttp(logger=progress)
    api = FhmApi(http)
    conn = db.connect()
    db.init_db(conn)
    run_id = db.start_run(conn, {"seasons": list(seasons), "refresh": refresh, "rosters": with_rosters})
    done_rosters: set[tuple[int, int]] = set()

    stats: dict[str, Any] = {
        "run_id": run_id,
        "seasons": {},
        "teams": 0,
        "matches": 0,
        "played_matches": 0,
        "players": 0,
        "roster_rows": 0,
        "issues": 0,
        "http": {},
    }

    try:
        season_index = {int(row["id"]): row for row in api.seasons(refresh=refresh)}
        for season_id in seasons:
            season_info = season_index.get(season_id, {})
            label = str(season_info.get("name") or "")
            years = fhm_api.parse_season_label(label)
            db.upsert(
                conn,
                "seasons",
                [
                    {
                        "id": season_id,
                        "label": label,
                        "start_year": years[0] if years else None,
                        "end_year": years[1] if years else None,
                        "is_current": 1 if season_info.get("current") else 0,
                    }
                ],
                ["id"],
            )
            conn.commit()

            tournament_rows = {int(row["id"]): row for row in api.tournaments(season_id, refresh=refresh)}
            season_start = years[0] if years else None
            season_end = years[1] if years else None
            season_stats = {"tournaments": 0, "groups": 0, "teams": 0, "matches": 0, "played": 0, "roster_rows": 0}
            stats["seasons"][season_id] = season_stats

            for tournament_id in config.TARGET_TOURNAMENTS.get(season_id, ()):
                tournament = tournament_rows.get(tournament_id)
                if tournament is None:
                    db.add_issue(
                        conn,
                        run_id=run_id,
                        kind="missing_tournament",
                        severity="error",
                        entity=str(tournament_id),
                        message=f"Турнир {tournament_id} не найден в сезоне {season_id}",
                    )
                    stats["issues"] += 1
                    continue

                tournament_name = str(tournament.get("name") or "")
                age_year = parse_age_year(tournament_name) or None
                db.upsert(
                    conn,
                    "tournaments",
                    [
                        {
                            "id": tournament_id,
                            "season_id": season_id,
                            "name": tournament_name,
                            "age_year": age_year,
                            "format": parse_format(tournament_name),
                            "play_off": 1 if tournament.get("playOff") else 0,
                            "transition": 1 if tournament.get("transition") else 0,
                            "is_current": 1 if tournament.get("current") else 0,
                        }
                    ],
                    ["id"],
                )
                conn.commit()
                season_stats["tournaments"] += 1
                progress(f"Сезон {label}: турнир {tournament_id} «{tournament_name}»")

                stages = api.stages(tournament_id, refresh=refresh)
                for stage in stages:
                    stage_id = int(stage["id"])
                    db.upsert(
                        conn,
                        "stages",
                        [
                            {
                                "id": stage_id,
                                "tournament_id": tournament_id,
                                "name": str(stage.get("name") or ""),
                                "is_current": 1 if stage.get("current") else 0,
                                "is_transition": 1 if stage.get("transition") else 0,
                            }
                        ],
                        ["id"],
                    )
                    conn.commit()

                    groups = api.groups(stage_id, refresh=refresh)
                    for group in groups:
                        group_id = int(group["id"])
                        db.upsert(
                            conn,
                            "tournament_groups",
                            [
                                {
                                    "id": group_id,
                                    "stage_id": stage_id,
                                    "tournament_id": tournament_id,
                                    "name": str(group.get("name") or ""),
                                }
                            ],
                            ["id"],
                        )
                        conn.commit()
                        season_stats["groups"] += 1

                        teams = api.teams(group_id, refresh=refresh)
                        team_rows: list[dict[str, Any]] = []
                        team_season_rows: list[dict[str, Any]] = []
                        name_to_id: dict[str, int] = {}
                        for team in teams:
                            team_id = int(team["id"])
                            # API иногда отдаёт name/shortName в разном порядке.
                            name = str(team.get("name") or team.get("shortName") or "").strip()
                            short_name = str(team.get("shortName") or "").strip()
                            club, team_age = parse_team_name(name or short_name)
                            team_rows.append(
                                {
                                    "id": team_id,
                                    "name": name or short_name,
                                    "short_name": short_name,
                                    "age_year": team_age or age_year,
                                    "club": club,
                                }
                            )
                            team_season_rows.append(
                                {
                                    "team_id": team_id,
                                    "season_id": season_id,
                                    "tournament_id": tournament_id,
                                    "group_id": group_id,
                                }
                            )
                            for alias in {name, short_name, name.replace("  ", " ")}:
                                alias = (alias or "").strip()
                                if alias:
                                    name_to_id[alias] = team_id
                        db.upsert(conn, "teams", team_rows, ["id"])
                        db.upsert(conn, "team_seasons", team_season_rows, ["team_id", "season_id", "tournament_id", "group_id"])
                        conn.commit()
                        stats["teams"] += len(team_rows)
                        season_stats["teams"] += len(team_rows)

                        games = api.all_games(
                            season_id,
                            tournament=tournament_id,
                            stage=stage_id,
                            group=group_id,
                            refresh=refresh,
                        )
                        match_rows: list[dict[str, Any]] = []
                        for item in games:
                            normalized = normalize_game(
                                item,
                                season=season_id,
                                tournament_id=tournament_id,
                                stage_id=stage_id,
                                group_id=group_id,
                                season_start=season_start,
                                season_end=season_end,
                            )
                            if normalized is None:
                                db.add_issue(
                                    conn,
                                    run_id=run_id,
                                    kind="bad_game_payload",
                                    severity="warning",
                                    entity=str(item.get("id")),
                                    message="Не удалось разобрать дату матча",
                                )
                                stats["issues"] += 1
                                continue
                            home_id = name_to_id.get(normalized.home_name)
                            away_id = name_to_id.get(normalized.away_name)
                            if home_id is None or away_id is None:
                                db.add_issue(
                                    conn,
                                    run_id=run_id,
                                    kind="unknown_team",
                                    severity="warning",
                                    entity=str(normalized.id),
                                    message=(
                                        f"Команда не найдена в группе {group_id}: "
                                        f"{normalized.home_name!r} — {normalized.away_name!r}"
                                    ),
                                )
                                stats["issues"] += 1
                                continue
                            now = db.utc_now()
                            match_rows.append(
                                {
                                    "id": normalized.id,
                                    "season_id": season_id,
                                    "tournament_id": tournament_id,
                                    "stage_id": stage_id,
                                    "group_id": group_id,
                                    "tour_name": normalized.tour_name,
                                    "date": normalized.date_iso,
                                    "time": normalized.time,
                                    "home_team_id": home_id,
                                    "away_team_id": away_id,
                                    "home_name": normalized.home_name,
                                    "away_name": normalized.away_name,
                                    "home_goals": normalized.home_goals,
                                    "away_goals": normalized.away_goals,
                                    "status": normalized.status,
                                    "overtime": int(normalized.overtime),
                                    "shootout": int(normalized.shootout),
                                    "technical_defeat": int(normalized.technical_defeat),
                                    "cancel_status": str(normalized.cancel_status) if normalized.cancel_status else None,
                                    "played": int(normalized.played),
                                    "source_url": normalized.url,
                                    "fetched_at": now,
                                    "updated_at": now,
                                }
                            )
                        db.upsert(conn, "matches", match_rows, ["id"])
                        conn.commit()
                        stats["matches"] += len(match_rows)
                        stats["played_matches"] += sum(1 for row in match_rows if row["played"])
                        season_stats["matches"] += len(match_rows)
                        season_stats["played"] += sum(1 for row in match_rows if row["played"])

                        if with_rosters and season_id in config.ROSTER_SEASONS:
                            for team_id in sorted({row["team_id"] for row in team_season_rows}):
                                if (team_id, season_id) in done_rosters:
                                    continue
                                done_rosters.add((team_id, season_id))
                                roster_rows = collect_roster(
                                    api, conn, run_id, team_id=team_id, season_id=season_id, tournament_id=tournament_id,
                                    refresh=refresh,
                                )
                                stats["roster_rows"] += roster_rows
                                season_stats["roster_rows"] += roster_rows

        rebuild_player_history(conn)
        stats["players"] = int(conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"])
        db.finish_run(conn, run_id, status="ok", stats=stats)
        stats["http"] = http.stats.as_dict()
        stats["db_counts"] = db.counts(conn)
        return stats
    except Exception as exc:  # noqa: BLE001
        db.finish_run(conn, run_id, status="failed", stats=stats, error=str(exc))
        raise
    finally:
        conn.close()


def collect_roster(
    api: FhmApi,
    conn,
    run_id: int,
    *,
    team_id: int,
    season_id: int,
    tournament_id: int,
    refresh: bool = False,
) -> int:
    """Заявка команды на сезон: игроки, роли, номера и агрегаты."""
    players = api.roster(team_id, season_id, refresh=refresh)
    now = db.utc_now()
    existing_first_seen = {
        int(row["id"]): row["first_seen"]
        for row in conn.execute("SELECT id, first_seen FROM players")
    }
    player_rows: list[dict[str, Any]] = []
    roster_rows: list[dict[str, Any]] = []
    stat_rows: list[dict[str, Any]] = []

    for player in players:
        url = str(player.get("url") or "")
        match = _PLAYER_ID_RE.search(url)
        if not match:
            db.add_issue(
                conn,
                run_id=run_id,
                kind="player_without_id",
                severity="warning",
                entity=str(team_id),
                message=f"Игрок без официального ID: {player.get('fullName')!r}",
            )
            continue
        player_id = int(match.group(1))
        statistics = player.get("statistics") or {}
        number = player.get("number")
        player_rows.append(
            {
                "id": player_id,
                "full_name": str(player.get("fullName") or "").strip(),
                "birth_date": iso_birth_date(str(player.get("dateOfBirth") or "")),
                "role": str(player.get("role") or "").strip(),
                "url": f"{config.BASE_URL}{url}",
                "first_seen": existing_first_seen.get(player_id, now),
                "last_seen": now,
            }
        )
        roster_rows.append(
            {
                "team_id": team_id,
                "season_id": season_id,
                "player_id": player_id,
                "number": int(number) if isinstance(number, int) else None,
                "role": str(player.get("role") or "").strip(),
                "source": f"{config.BASE_URL}/team/{team_id}?season={season_id}",
                "fetched_at": now,
            }
        )
        stat_rows.append(
            {
                "player_id": player_id,
                "team_id": team_id,
                "season_id": season_id,
                "tournament_id": tournament_id,
                "games": int(statistics.get("gamesCount") or 0),
                "goals": int(statistics.get("totalGoals") or 0),
                "assists": int(statistics.get("totalAssists") or 0),
                "points": int(statistics.get("totalGoalPasses") or 0),
                "penalties": int(statistics.get("totalPenalties") or 0),
                "missed": int(statistics.get("totalMissed") or 0),
                "time_seconds": int(statistics.get("totalTime") or 0),
                "source": f"{config.BASE_URL}/team/{team_id}/player?season={season_id}",
                "fetched_at": now,
            }
        )

    if player_rows:
        # first_seen не должен перезаписываться при обновлении.
        db.upsert(conn, "players", player_rows, ["id"])
        db.upsert(conn, "team_rosters", roster_rows, ["team_id", "season_id", "player_id"])
        db.upsert(
            conn,
            "player_season_stats",
            stat_rows,
            ["player_id", "team_id", "season_id", "tournament_id"],
        )
        conn.commit()
    return len(roster_rows)


def rebuild_player_history(conn) -> None:
    """Строит историю принадлежности игрока к командам по сезонным агрегатам."""
    rows = conn.execute(
        """
        SELECT player_id,
               team_id,
               season_id,
               SUM(games) AS games,
               SUM(goals) AS goals,
               SUM(assists) AS assists,
               MIN(source) AS source
        FROM player_season_stats
        GROUP BY player_id, team_id, season_id
        """
    ).fetchall()
    history = [
        {
            "player_id": row["player_id"],
            "team_id": row["team_id"],
            "season_id": row["season_id"],
            "first_match_date": None,
            "last_match_date": None,
            "games": int(row["games"] or 0),
            "goals": int(row["goals"] or 0),
            "assists": int(row["assists"] or 0),
            "source": row["source"],
        }
        for row in rows
    ]
    db.upsert(conn, "player_team_history", history, ["player_id", "team_id", "season_id"])
    conn.commit()
