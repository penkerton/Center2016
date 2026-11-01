"""Прогноз турнирной таблицы по предстоящим матчам.

Текущие очки считаются по сыгранным матчам (2 за победу, 1 за ничью), к ним
добавляется математическое ожидание очков за оставшиеся игры. Ожидаемая разница
шайб — по λ пуассоновской модели.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .backtest import ENSEMBLE_WEIGHTS
from .engine import Match, PlayerStrength, load_matches
from .features import FEATURE_NAMES, build_observations, final_state, matrix
from .models import SoftmaxRegression, normalize


@dataclass
class ProjectedTeam:
    team_id: int
    name: str
    played: int = 0
    points: int = 0
    goals_for: int = 0
    goals_against: int = 0
    expected_points: float = 0.0
    expected_goal_diff: float = 0.0
    remaining: int = 0
    current_rank: int = 0
    projected_rank: int = 0

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def projected_points(self) -> float:
        return self.points + self.expected_points

    @property
    def projected_goal_diff(self) -> float:
        return self.goal_diff + self.expected_goal_diff


@dataclass
class ProjectedGroup:
    group_id: int
    group_name: str
    tournament_id: int
    tournament_name: str
    season_label: str
    teams: list[ProjectedTeam] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "group": self.group_name,
            "tournament": self.tournament_name,
            "season": self.season_label,
            "matches": len(self.matches),
            "teams": [
                {
                    "team_id": team.team_id,
                    "name": team.name,
                    "played": team.played,
                    "points": team.points,
                    "expected_points": round(team.expected_points, 2),
                    "projected_points": round(team.projected_points, 2),
                    "goal_diff": team.goal_diff,
                    "expected_goal_diff": round(team.expected_goal_diff, 2),
                    "projected_goal_diff": round(team.projected_goal_diff, 2),
                    "remaining": team.remaining,
                    "current_rank": team.current_rank,
                    "projected_rank": team.projected_rank,
                }
                for team in self.teams
            ],
        }


class Projector:
    """Один раз обученное состояние для быстрых прогнозов многих матчей."""

    def __init__(self, conn: sqlite3.Connection, *, as_of: date | None = None) -> None:
        self.conn = conn
        self.as_of = as_of or date.today()
        self.matches = load_matches(conn, only_played=False)
        self.played = [match for match in self.matches if match.home_goals is not None]
        self.player_strength = PlayerStrength()
        self.player_strength.build(conn)
        observations = build_observations(self.played, player_strength=self.player_strength, poisson_every=40)
        X, y = matrix(observations)
        self.logistic = SoftmaxRegression(l2=0.05, learning_rate=0.08, epochs=500).fit(X, y)
        self.state = final_state(self.played, self.player_strength)
        self.state.poisson.fit(
            [match for match in self.played if not match.technical_defeat],
            self.as_of,
        )
        self.draw_rate = self.state.draw_rate()

    def predict(self, match: Match) -> dict[str, Any]:
        features = self.state.features(match)
        elo = self.state.elo.predict(match.home_id, match.away_id, self.draw_rate)
        poisson = self.state.poisson.predict(match.home_id, match.away_id)
        player, _, _ = self.state.player_adjusted_probs(match)
        logistic = self.logistic.predict_proba([[features[name] for name in FEATURE_NAMES]])[0]
        models = {"elo": elo, "poisson": poisson, "player": player, "logistic": logistic}
        total = sum(ENSEMBLE_WEIGHTS.values()) or 1.0
        ensemble = normalize(
            tuple(  # type: ignore[arg-type]
                sum(ENSEMBLE_WEIGHTS[name] * models[name][index] for name in ENSEMBLE_WEIGHTS) / total
                for index in range(3)
            )
        )
        lambda_home, lambda_away = self.state.poisson.expected_goals(match.home_id, match.away_id)
        return {
            "probabilities": models,
            "ensemble": ensemble,
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
        }

    def projected_group(self, group_id: int) -> ProjectedGroup:
        group_row = self.conn.execute(
            """
            SELECT g.id, g.name, t.id AS tournament_id, t.name AS tournament_name, s.label AS season_label
            FROM tournament_groups g
            JOIN tournaments t ON t.id = g.tournament_id
            JOIN seasons s ON s.id = t.season_id
            WHERE g.id = ?
            """,
            (group_id,),
        ).fetchone()
        if group_row is None:
            raise KeyError(f"Группа {group_id} не найдена")
        group = ProjectedGroup(
            group_id=int(group_row["id"]),
            group_name=group_row["name"],
            tournament_id=int(group_row["tournament_id"]),
            tournament_name=group_row["tournament_name"],
            season_label=group_row["season_label"],
        )

        names = {
            int(row["id"]): row["name"] for row in self.conn.execute("SELECT id, name FROM teams")
        }
        teams: dict[int, ProjectedTeam] = {}
        for row in self.conn.execute(
            "SELECT team_id FROM team_seasons WHERE group_id = ?", (group_id,)
        ):
            team_id = int(row["team_id"])
            teams[team_id] = ProjectedTeam(team_id=team_id, name=names.get(team_id, f"#{team_id}"))

        for match in self.played:
            if match.group_id != group_id:
                continue
            home = teams.setdefault(match.home_id, ProjectedTeam(match.home_id, match.home_name))
            away = teams.setdefault(match.away_id, ProjectedTeam(match.away_id, match.away_name))
            home.played += 1
            away.played += 1
            home.goals_for += match.home_goals
            home.goals_against += match.away_goals
            away.goals_for += match.away_goals
            away.goals_against += match.home_goals
            if match.outcome == 0:
                home.points += 2
            elif match.outcome == 2:
                away.points += 2
            else:
                home.points += 1
                away.points += 1

        upcoming = [
            match
            for match in self.matches
            if match.group_id == group_id and match.home_goals is None and match.date >= self.as_of.isoformat()
        ]
        for match in upcoming:
            prediction = self.predict(match)
            home = teams.setdefault(match.home_id, ProjectedTeam(match.home_id, match.home_name))
            away = teams.setdefault(match.away_id, ProjectedTeam(match.away_id, match.away_name))
            home.expected_points += prediction["ensemble"][0] * 2 + prediction["ensemble"][1]
            away.expected_points += prediction["ensemble"][2] * 2 + prediction["ensemble"][1]
            diff = prediction["lambda_home"] - prediction["lambda_away"]
            home.expected_goal_diff += diff
            away.expected_goal_diff -= diff
            home.remaining += 1
            away.remaining += 1
            group.matches.append(match)

        ordered = list(teams.values())
        current = sorted(ordered, key=lambda team: (-team.points, -team.goal_diff, -team.goals_for, team.name))
        for index, team in enumerate(current, start=1):
            team.current_rank = index
        projected = sorted(
            ordered,
            key=lambda team: (
                -team.projected_points,
                -team.projected_goal_diff,
                -team.points,
                team.name,
            ),
        )
        for index, team in enumerate(projected, start=1):
            team.projected_rank = index
        group.teams = projected
        return group


def projected_groups(
    conn: sqlite3.Connection,
    *,
    season_id: int = 5,
    age_year: int = 2016,
) -> list[ProjectedGroup]:
    rows = conn.execute(
        """
        SELECT g.id
        FROM tournament_groups g
        JOIN tournaments t ON t.id = g.tournament_id
        WHERE t.season_id = ? AND t.age_year = ?
        ORDER BY t.id, g.name
        """,
        (season_id, age_year),
    ).fetchall()
    projector = Projector(conn)
    groups: list[ProjectedGroup] = []
    for row in rows:
        group = projector.projected_group(int(row["id"]))
        if group.teams and group.matches:
            groups.append(group)
    return groups
