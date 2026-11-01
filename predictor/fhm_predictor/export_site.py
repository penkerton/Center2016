"""Выгрузка данных и параметров модели для статической страницы прогноза.

Страница на GitHub Pages не может запускать Python, поэтому все данные и
коэффициенты модели выгружаются в компактный JS-файл, а расчёт вероятностей
повторяется на JavaScript (site/app.js).

Запуск: python main.py export-site
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import config, db
from .backtest import ENSEMBLE_WEIGHTS
from .engine import Match, PlayerStrength, load_matches
from .features import FEATURE_NAMES, build_observations, final_state, matrix
from .models import SoftmaxRegression

SITE_DIR = config.PROJECT_DIR / "site"


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _team_groups(conn: sqlite3.Connection, season_id: int) -> dict[int, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ts.team_id, g.name AS group_name, t.id AS tournament_id, t.name AS tournament_name,
               t.format, t.age_year
        FROM team_seasons ts
        JOIN tournament_groups g ON g.id = ts.group_id
        JOIN tournaments t ON t.id = ts.tournament_id
        WHERE ts.season_id = ?
        ORDER BY t.id
        """,
        (season_id,),
    ).fetchall()
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        # У команды может быть несколько турниров; для подписи берём первый.
        result.setdefault(
            int(row["team_id"]),
            {
                "group": row["group_name"],
                "tournament_id": int(row["tournament_id"]),
                "tournament_name": row["tournament_name"],
                "format": row["format"],
                "age_year": row["age_year"],
            },
        )
    return result


def _compact_matches(matches: list[Match], *, played: bool) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for match in matches:
        if played:
            rows.append(
                [
                    match.id,
                    match.date,
                    match.home_id,
                    match.away_id,
                    match.home_goals,
                    match.away_goals,
                    match.tournament_id,
                    match.group_id,
                ]
            )
        else:
            rows.append(
                [
                    match.id,
                    match.date,
                    match.time,
                    match.tournament_id,
                    match.group_id,
                    match.home_id,
                    match.away_id,
                ]
            )
    return rows


def build_site_payload(conn: sqlite3.Connection, *, selftest_count: int = 3) -> dict[str, Any]:
    all_matches = load_matches(conn, only_played=False)
    # Как и в predict.py, состояние команд строится по всем сыгранным матчам
    # (технические поражения учитываются в Elo/форме, но не в обучении).
    played_all = [match for match in all_matches if match.home_goals is not None]

    player_strength = PlayerStrength()
    player_strength.build(conn)

    observations = build_observations(played_all, player_strength=player_strength, poisson_every=40)
    X, y = matrix(observations)
    logistic = SoftmaxRegression(l2=0.05, learning_rate=0.08, epochs=500).fit(X, y)

    state = final_state(played_all, player_strength)
    # В predict.py Пуассон пересчитывается на дату отсечки (сегодня).
    state.poisson.fit([match for match in played_all if not match.technical_defeat], date.today())
    last_played_date = played_all[-1].date if played_all else None
    draw_rate = state.draw_rate()

    seasons = {int(row["id"]): row["label"] for row in conn.execute("SELECT id, label FROM seasons")}
    teams_rows = conn.execute("SELECT id, name, age_year FROM teams").fetchall()
    teams: dict[str, Any] = {}
    for row in teams_rows:
        teams[str(row["id"])] = {
            "n": row["name"],
            "a": row["age_year"],
        }

    current_season = max(seasons) if seasons else 5
    groups = _team_groups(conn, current_season)
    league_strength = player_strength.league_mean(current_season)
    s5_team_ids = sorted({int(row["team_id"]) for row in conn.execute(
        "SELECT DISTINCT team_id FROM team_seasons WHERE season_id = ?", (current_season,)
    )})

    for team_id in s5_team_ids:
        info = groups.get(team_id, {})
        form = state.form.stats(team_id)
        strength = player_strength.team_strength(team_id, current_season)
        if strength is None:
            strength = league_strength
        impacts = _team_impacts(player_strength, team_id, current_season)
        teams[str(team_id)].update(
            {
                "g": info.get("group", ""),
                "t": info.get("tournament_id"),
                "f": info.get("format"),
                "e": _round(state.elo.rating(team_id), 6),
                "m": int(state.elo.games.get(team_id, 0)),
                "p": _round(form["ppg"], 6),
                "gf": _round(form["gf"], 6),
                "ga": _round(form["ga"], 6),
                "ld": state.form.last_date.get(team_id),
                "s": _round(strength, 8),
                "imp": [[pid, _round(part, 6), _round(impact, 8)] for pid, part, impact in impacts],
            }
        )

    upcoming = [
        match
        for match in all_matches
        if match.home_goals is None and match.date >= date.today().isoformat()
    ]
    played = [match for match in all_matches if match.home_goals is not None]

    tournaments = {
        str(row["id"]): {
            "n": row["name"],
            "age": row["age_year"],
            "format": row["format"],
            "season": row["season_id"],
        }
        for row in conn.execute("SELECT id, name, age_year, format, season_id FROM tournaments")
    }
    group_names = {
        str(row["id"]): row["name"] for row in conn.execute("SELECT id, name FROM tournament_groups")
    }

    # Подробности по группам 2016 г.р. — для прогноза турнирной таблицы.
    group_info: dict[str, Any] = {}
    group_rows = conn.execute(
        """
        SELECT g.id, g.name, g.tournament_id, t.age_year, t.season_id, t.format
        FROM tournament_groups g
        JOIN tournaments t ON t.id = g.tournament_id
        WHERE t.age_year = 2016 AND t.season_id = ?
        """
        , (current_season,)
    ).fetchall()
    for row in group_rows:
        group_info[str(row["id"])] = {
            "n": row["name"],
            "t": int(row["tournament_id"]),
            "age": row["age_year"],
            "season": int(row["season_id"]),
            "format": row["format"],
            "teams": [],
        }
    team_group_rows = conn.execute(
        "SELECT group_id, team_id FROM team_seasons WHERE season_id = ?",
        (current_season,),
    ).fetchall()
    for row in team_group_rows:
        group = group_info.get(str(row["group_id"]))
        if group is not None:
            group["teams"].append(int(row["team_id"]))
    for group in group_info.values():
        group["teams"] = sorted(set(group["teams"]), key=lambda team_id: teams.get(str(team_id), {}).get("n", ""))
    group_info = {gid: group for gid, group in group_info.items() if group["teams"]}

    rosters: dict[str, list[list[Any]]] = {}
    for team_id in s5_team_ids:
        rows = conn.execute(
            """
            SELECT r.player_id, r.number, r.role,
                   COALESCE(SUM(s.games), 0) AS games,
                   COALESCE(SUM(s.goals), 0) AS goals,
                   COALESCE(SUM(s.assists), 0) AS assists,
                   COALESCE(SUM(s.points), 0) AS points,
                   COALESCE(SUM(s.penalties), 0) AS penalties
            FROM team_rosters r
            LEFT JOIN player_season_stats s
                   ON s.player_id = r.player_id AND s.team_id = r.team_id AND s.season_id = r.season_id
            WHERE r.team_id = ? AND r.season_id = ?
            GROUP BY r.player_id
            ORDER BY goals DESC, games DESC
            """,
            (team_id, current_season),
        ).fetchall()
        rosters[str(team_id)] = [
            [
                int(row["player_id"]),
                row["number"],
                row["role"],
                int(row["games"]),
                int(row["goals"]),
                int(row["assists"]),
                int(row["points"]),
                int(row["penalties"]),
            ]
            for row in rows
        ]

    players: dict[str, Any] = {}
    player_rows = conn.execute("SELECT id, full_name, birth_date, role FROM players").fetchall()
    history_rows = conn.execute(
        """
        SELECT player_id, season_id, team_id, games, goals, assists
        FROM player_team_history
        ORDER BY season_id
        """
    ).fetchall()
    history: dict[int, list[list[Any]]] = {}
    for row in history_rows:
        history.setdefault(int(row["player_id"]), []).append(
            [int(row["season_id"]), int(row["team_id"]), int(row["games"]), int(row["goals"]), int(row["assists"])]
        )
    for row in player_rows:
        birth_year = None
        if row["birth_date"]:
            try:
                birth_year = int(str(row["birth_date"])[:4])
            except ValueError:
                birth_year = None
        players[str(row["id"])] = {
            "n": row["full_name"],
            "b": birth_year,
            "r": row["role"],
            "h": history.get(int(row["id"]), []),
        }

    quality = _load_quality()
    coverage = _load_coverage(conn)

    payload: dict[str, Any] = {
        "meta": {
            "generated_at": _iso_now(),
            "data_as_of": last_played_date,
            "season_id": current_season,
            "season_label": seasons.get(current_season, ""),
            "model_version": "ensemble-v1",
            "draw_rate": _round(draw_rate, 8),
            "league_strength": _round(league_strength, 8),
            "counts": {
                "matches": len(all_matches),
                "played": len(played),
                "upcoming": len(upcoming),
                "teams": len(teams),
                "players": len(players),
            },
            "hash": "",
        },
        "params": {
            "elo": {
                "start": config.ELO_START,
                "k": config.ELO_K,
                "home_advantage": config.ELO_HOME_ADVANTAGE,
            },
            "poisson": {
                "avg": _round(state.poisson.avg_goals, 8),
                "home_factor": _round(state.poisson.home_factor, 8),
                "attack": {str(team): _round(value, 8) for team, value in state.poisson.attack.items()},
                "defense": {str(team): _round(value, 8) for team, value in state.poisson.defense.items()},
            },
            "player_scale": 220.0,
            "player_clip": 120.0,
            "ensemble": ENSEMBLE_WEIGHTS,
        },
        "model": {
            "features": list(FEATURE_NAMES),
            "mean": [_round(value, 8) for value in logistic.mean.tolist()],
            "scale": [_round(value, 8) for value in logistic.scale.tolist()],
            "weights": [[_round(value, 8) for value in row] for row in logistic.weights.tolist()],
            "bias": [_round(value, 8) for value in logistic.bias.tolist()],
            "classes": list(logistic.classes_),
        },
        "teams": teams,
        "tournaments": tournaments,
        "groups": group_names,
        "group_info": group_info,
        "seasons": {str(key): value for key, value in seasons.items()},
        "upcoming": _compact_matches(upcoming, played=False),
        "played": _compact_matches(played, played=True),
        "rosters": rosters,
        "players": players,
        "quality": quality,
        "coverage": coverage,
        "selftest": [],
    }

    payload["meta"]["hash"] = hashlib.sha256(
        json.dumps(
            {"params": payload["params"], "model": payload["model"]},
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    if selftest_count:
        payload["selftest"] = _selftest(conn, upcoming, selftest_count)
    return payload


def _team_impacts(
    player_strength: PlayerStrength, team_id: int, target_season: int
) -> list[tuple[int, float, float]]:
    candidates = [
        (season, impacts)
        for (team, season), impacts in player_strength.by_team_season.items()
        if team == team_id and season < target_season
    ]
    if not candidates:
        return []
    candidates.sort(key=lambda item: item[0])
    impacts = candidates[-1][1]
    return [(player.player_id, player.participation, player.impact) for player in impacts.values()]


def _load_quality() -> dict[str, Any]:
    path = config.PROJECT_DIR / "reports" / "backtest.json"
    if not path.exists():
        return {}
    report = json.loads(path.read_text(encoding="utf-8"))
    keep = ("accuracy", "brier", "log_loss", "n", "accuracy_ci95", "calibration")
    models = {
        name: {key: values[key] for key in keep if key in values}
        for name, values in report.get("models", {}).items()
    }
    holdout = report.get("holdout") or {}
    return {
        "generated_at": report.get("generated_at"),
        "evaluated": report.get("evaluated"),
        "matches_total": report.get("matches_total"),
        "date_from": report.get("date_from"),
        "date_to": report.get("date_to"),
        "models": models,
        "holdout": {
            "n": holdout.get("n"),
            "from": holdout.get("from"),
            "to": holdout.get("to"),
            "models": {
                name: {key: values[key] for key in keep if key in values}
                for name, values in (holdout.get("models") or {}).items()
            },
        },
        "slices": report.get("slices", {}),
        "goal_dispersion": report.get("goal_dispersion"),
        "outcome_distribution": report.get("outcome_distribution"),
        "ensemble_weights": report.get("ensemble_weights"),
    }


def _load_coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        from .coverage import build_coverage

        coverage = build_coverage(conn)
        return {
            "totals": coverage["totals"],
            "tournaments": coverage["tournaments"],
        }
    except Exception:  # noqa: BLE001
        return {}


def _selftest(conn: sqlite3.Connection, upcoming: list[Match], count: int) -> list[dict[str, Any]]:
    """Три эталонных прогноза Python для сверки с JS."""
    from .predict import build_prediction

    picked: list[Match] = []
    # Первым делом — «Центр — Буран», если он есть в расписании.
    for match in upcoming:
        if "Центр" in match.home_name and "Буран" in match.away_name:
            picked.append(match)
            break
    for match in upcoming:
        if all(match.id != item.id for item in picked):
            picked.append(match)
        if len(picked) >= count:
            break

    result: list[dict[str, Any]] = []
    now = datetime.now().astimezone().replace(tzinfo=None)
    for match in picked[:count]:
        prediction = build_prediction(conn, match.id, cutoff=now)
        result.append(
            {
                "match_id": match.id,
                "home": _round(prediction.ensemble[0], 8),
                "draw": _round(prediction.ensemble[1], 8),
                "away": _round(prediction.ensemble[2], 8),
                "hash": prediction.features_hash,
            }
        )
    return result


def export_site(conn: sqlite3.Connection, output_dir: Path | None = None) -> Path:
    output_dir = Path(output_dir or SITE_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_site_payload(conn)
    path = output_dir / "data.js"
    content = "window.PREDICTOR_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    path.write_text(content, encoding="utf-8")
    (output_dir / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return path
