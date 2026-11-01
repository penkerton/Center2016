"""Рейтинги и признаки: Elo, форма, пуассоновская сила, рейтинг игроков.

Все расчёты делаются только по матчам, сыгранным до момента прогноза.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable

from . import config

OUTCOME_HOME = 0
OUTCOME_DRAW = 1
OUTCOME_AWAY = 2
OUTCOME_LABELS = ("победа хозяев", "ничья", "победа гостей")


@dataclass(slots=True)
class Match:
    id: int
    date: str
    time: str
    season_id: int
    tournament_id: int
    group_id: int
    home_id: int
    away_id: int
    home_name: str
    away_name: str
    home_goals: int
    away_goals: int
    overtime: int = 0
    shootout: int = 0
    technical_defeat: int = 0
    age_year: int | None = None
    format: str | None = None
    group_name: str = ""
    stage_name: str = ""
    season_label: str = ""
    tournament_name: str = ""

    @property
    def sort_key(self) -> tuple[str, str, int]:
        return (self.date, self.time or "00:00", self.id)

    @property
    def kickoff(self) -> datetime:
        clock = self.time or "00:00"
        return datetime.fromisoformat(f"{self.date}T{clock}:00")

    @property
    def outcome(self) -> int:
        if self.home_goals > self.away_goals:
            return OUTCOME_HOME
        if self.home_goals < self.away_goals:
            return OUTCOME_AWAY
        return OUTCOME_DRAW

    @property
    def goal_diff(self) -> int:
        return self.home_goals - self.away_goals

    @property
    def is_playoff(self) -> bool:
        return "плей" in (self.stage_name or "").lower() or "playoff" in (self.stage_name or "").lower()


def load_matches(conn: sqlite3.Connection, *, only_played: bool = True) -> list[Match]:
    query = """
        SELECT m.*, t.age_year, t.format, t.name AS tournament_name,
               g.name AS group_name, s.name AS stage_name, se.label AS season_label
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        JOIN tournament_groups g ON g.id = m.group_id
        JOIN stages s ON s.id = m.stage_id
        JOIN seasons se ON se.id = m.season_id
    """
    if only_played:
        query += " WHERE m.played = 1 AND m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL"
    query += " ORDER BY m.date, m.time, m.id"
    rows = conn.execute(query).fetchall()
    return [
        Match(
            id=row["id"],
            date=row["date"],
            time=row["time"] or "",
            season_id=row["season_id"],
            tournament_id=row["tournament_id"],
            group_id=row["group_id"],
            home_id=row["home_team_id"],
            away_id=row["away_team_id"],
            home_name=row["home_name"],
            away_name=row["away_name"],
            home_goals=row["home_goals"],
            away_goals=row["away_goals"],
            overtime=row["overtime"],
            shootout=row["shootout"],
            technical_defeat=row["technical_defeat"],
            age_year=row["age_year"],
            format=row["format"],
            group_name=row["group_name"] or "",
            stage_name=row["stage_name"] or "",
            season_label=row["season_label"] or "",
            tournament_name=row["tournament_name"] or "",
        )
        for row in rows
    ]


def is_trainable(match: Match) -> bool:
    """Технические поражения и отменённые матчи не используем в обучении."""
    return not match.technical_defeat


class EloEngine:
    """Классический Elo с поправкой на домашнее преимущество и сезонный возврат."""

    def __init__(
        self,
        *,
        start: float = config.ELO_START,
        k: float = config.ELO_K,
        home_advantage: float = config.ELO_HOME_ADVANTAGE,
        season_regression: float = config.ELO_SEASON_REGRESSION,
    ) -> None:
        self.start = start
        self.k = k
        self.home_advantage = home_advantage
        self.season_regression = season_regression
        self.ratings: dict[int, float] = {}
        self.games: dict[int, int] = {}
        self.last_season: dict[int, int] = {}
        self.history: list[dict[str, object]] = []

    def rating(self, team_id: int) -> float:
        return self.ratings.get(team_id, self.start)

    def _regress(self, team_id: int, season_id: int) -> None:
        previous = self.last_season.get(team_id)
        if previous is not None and previous != season_id:
            current = self.rating(team_id)
            self.ratings[team_id] = current + (self.start - current) * self.season_regression
        self.last_season[team_id] = season_id

    def win_probability(self, home_id: int, away_id: int) -> float:
        diff = self.rating(home_id) - self.rating(away_id) + self.home_advantage
        return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))

    def predict(self, home_id: int, away_id: int, draw_rate: float = 0.0) -> tuple[float, float, float]:
        raw = self.win_probability(home_id, away_id)
        closeness = max(0.0, 1.0 - 2.0 * abs(raw - 0.5))
        draw = max(0.0, min(0.35, draw_rate * closeness))
        p_home = raw * (1.0 - draw)
        p_away = (1.0 - raw) * (1.0 - draw)
        return p_home, draw, p_away

    def update(self, match: Match) -> None:
        self._regress(match.home_id, match.season_id)
        self._regress(match.away_id, match.season_id)

        expected_home = self.win_probability(match.home_id, match.away_id)
        if match.outcome == OUTCOME_HOME:
            actual_home = 1.0
        elif match.outcome == OUTCOME_AWAY:
            actual_home = 0.0
        else:
            actual_home = 0.5

        goal_factor = 1.0 + 0.35 * math.log1p(abs(match.goal_diff))
        delta = self.k * goal_factor * (actual_home - expected_home)
        self.ratings[match.home_id] = self.rating(match.home_id) + delta
        self.ratings[match.away_id] = self.rating(match.away_id) - delta
        self.games[match.home_id] = self.games.get(match.home_id, 0) + 1
        self.games[match.away_id] = self.games.get(match.away_id, 0) + 1
        self.history.append(
            {
                "match_id": match.id,
                "date": match.date,
                "home_id": match.home_id,
                "away_id": match.away_id,
                "home_elo": round(self.rating(match.home_id), 2),
                "away_elo": round(self.rating(match.away_id), 2),
            }
        )


@dataclass
class FormEntry:
    date: str
    points: int
    goals_for: int
    goals_against: int


class FormTracker:
    """Последние N матчей команды: очки, забитые и пропущенные."""

    def __init__(self, window: int = 5) -> None:
        self.window = window
        self.entries: dict[int, list[FormEntry]] = {}
        self.last_date: dict[int, str] = {}

    def add(self, match: Match) -> None:
        home_points = 2 if match.outcome == OUTCOME_HOME else (1 if match.outcome == OUTCOME_DRAW else 0)
        away_points = 2 if match.outcome == OUTCOME_AWAY else (1 if match.outcome == OUTCOME_DRAW else 0)
        self._push(match.home_id, FormEntry(match.date, home_points, match.home_goals, match.away_goals))
        self._push(match.away_id, FormEntry(match.date, away_points, match.away_goals, match.home_goals))
        self.last_date[match.home_id] = match.date
        self.last_date[match.away_id] = match.date

    def _push(self, team_id: int, entry: FormEntry) -> None:
        bucket = self.entries.setdefault(team_id, [])
        bucket.append(entry)
        if len(bucket) > self.window:
            del bucket[0]

    def stats(self, team_id: int) -> dict[str, float]:
        bucket = self.entries.get(team_id, [])
        if not bucket:
            return {"ppg": 0.0, "gf": 0.0, "ga": 0.0, "games": 0}
        count = len(bucket)
        return {
            "ppg": sum(entry.points for entry in bucket) / count,
            "gf": sum(entry.goals_for for entry in bucket) / count,
            "ga": sum(entry.goals_against for entry in bucket) / count,
            "games": count,
        }

    def rest_days(self, team_id: int, match_date: str) -> float:
        previous = self.last_date.get(team_id)
        if not previous:
            return 30.0
        try:
            delta = (date.fromisoformat(match_date) - date.fromisoformat(previous)).days
        except ValueError:
            return 30.0
        return float(max(0, min(60, delta)))


class PoissonModel:
    """Пуассоновская модель результативности с поправкой на силу соперника.

    λ_хозяев = avg * attack_home * defense_away * home_factor
    λ_гостей = avg * attack_away * defense_home

    Параметры оцениваются взвешенным МНК/итерациями по прошлым матчам,
    вес матча убывает с давностью (half-life).
    """

    def __init__(self, *, half_life_days: float = 240.0, prior_matches: float = 6.0) -> None:
        self.half_life_days = half_life_days
        self.prior_matches = prior_matches
        self.attack: dict[int, float] = {}
        self.defense: dict[int, float] = {}
        self.home_factor = 1.0
        self.avg_goals = 3.0
        self.fitted_count = 0

    def _weight(self, match_date: str, as_of: date) -> float:
        try:
            days = (as_of - date.fromisoformat(match_date)).days
        except ValueError:
            days = 0
        return math.exp(-math.log(2) * max(0, days) / self.half_life_days)

    def fit(self, matches: Iterable[Match], as_of: date) -> None:
        usable = [m for m in matches if m.date and not m.technical_defeat]
        if not usable:
            return
        weights = [self._weight(m.date, as_of) for m in usable]
        total_weight = sum(weights) or 1.0
        self.avg_goals = max(
            0.5,
            sum(w * (m.home_goals + m.away_goals) / 2 for m, w in zip(usable, weights)) / total_weight,
        )
        teams = {m.home_id for m in usable} | {m.away_id for m in usable}
        attack = {team: 1.0 for team in teams}
        defense = {team: 1.0 for team in teams}
        home_factor = 1.05
        prior = self.prior_matches

        # Для скорости раскладываем матчи по командам один раз:
        # (вес, забито, пропущено, соперник, играла_дома).
        by_team: dict[int, list[tuple[float, int, int, int, bool]]] = {team: [] for team in teams}
        for m, w in zip(usable, weights):
            by_team[m.home_id].append((w, m.home_goals, m.away_goals, m.away_id, True))
            by_team[m.away_id].append((w, m.away_goals, m.home_goals, m.home_id, False))

        for _ in range(8):
            for team, entries in by_team.items():
                numerator = prior * self.avg_goals
                denominator = prior * self.avg_goals
                for w, goals_for, _conceded, opponent, is_home in entries:
                    numerator += w * goals_for
                    denominator += w * defense[opponent] * self.avg_goals * (home_factor if is_home else 1.0)
                attack[team] = numerator / max(denominator, 1e-9)
            mean_attack = sum(attack.values()) / len(attack)
            attack = {team: value / mean_attack for team, value in attack.items()}

            for team, entries in by_team.items():
                numerator = prior * self.avg_goals
                denominator = prior * self.avg_goals
                for w, _goals_for, conceded, opponent, is_home in entries:
                    numerator += w * conceded
                    # Атака соперника — с его домашним коэффициентом, если он был хозяевами.
                    denominator += w * attack[opponent] * self.avg_goals * (home_factor if not is_home else 1.0)
                defense[team] = numerator / max(denominator, 1e-9)
            mean_defense = sum(defense.values()) / len(defense)
            defense = {team: value / mean_defense for team, value in defense.items()}

        home_goals = sum(w * m.home_goals for m, w in zip(usable, weights))
        away_goals = sum(w * m.away_goals for m, w in zip(usable, weights))
        if away_goals > 0:
            home_factor = max(0.8, min(1.25, math.sqrt(home_goals / away_goals)))

        self.attack = attack
        self.defense = defense
        self.home_factor = home_factor
        self.fitted_count = len(usable)

    def expected_goals(self, home_id: int, away_id: int) -> tuple[float, float]:
        attack_home = self.attack.get(home_id, 1.0)
        attack_away = self.attack.get(away_id, 1.0)
        defense_home = self.defense.get(home_id, 1.0)
        defense_away = self.defense.get(away_id, 1.0)
        lambda_home = self.avg_goals * attack_home * defense_away * self.home_factor
        lambda_away = self.avg_goals * attack_away * defense_home
        return max(0.2, lambda_home), max(0.2, lambda_away)

    def predict(self, home_id: int, away_id: int, max_goals: int = 15) -> tuple[float, float, float]:
        lambda_home, lambda_away = self.expected_goals(home_id, away_id)
        home_probs = [math.exp(-lambda_home) * lambda_home**k / math.factorial(k) for k in range(max_goals + 1)]
        away_probs = [math.exp(-lambda_away) * lambda_away**k / math.factorial(k) for k in range(max_goals + 1)]
        p_home = p_draw = p_away = 0.0
        for i, pi in enumerate(home_probs):
            for j, pj in enumerate(away_probs):
                probability = pi * pj
                if i > j:
                    p_home += probability
                elif i == j:
                    p_draw += probability
                else:
                    p_away += probability
        total = p_home + p_draw + p_away
        return p_home / total, p_draw / total, p_away / total


@dataclass
class PlayerImpact:
    player_id: int
    name: str
    team_id: int
    games: int
    goals: int
    assists: int
    impact: float
    participation: float


class PlayerStrength:
    """Оценка силы состава по индивидуальной результативности прошлых сезонов.

    Используются только сезоны строго раньше целевого, чтобы не подглядывать
    в текущий сезон. Голы и передачи сглаживаются байесовским приором.
    """

    def __init__(self, prior_games: float = config.PLAYER_PRIOR_GAMES, prior_rate: float = 0.35) -> None:
        self.prior_games = prior_games
        self.prior_rate = prior_rate
        self.by_team_season: dict[tuple[int, int], dict[int, PlayerImpact]] = {}
        self.team_season_strength: dict[tuple[int, int], float] = {}
        self.league_strength: dict[int, float] = {}

    def build(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT pss.player_id, pss.team_id, pss.season_id, pss.games, pss.goals, pss.assists,
                   p.full_name
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            """
        ).fetchall()
        grouped: dict[tuple[int, int], list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault((row["team_id"], row["season_id"]), []).append(row)

        for key, items in grouped.items():
            team_id, season_id = key
            team_games = max((int(item["games"] or 0) for item in items), default=0)
            impacts: dict[int, PlayerImpact] = {}
            for item in items:
                games = int(item["games"] or 0)
                goals = int(item["goals"] or 0)
                assists = int(item["assists"] or 0)
                if games <= 0:
                    impact = self.prior_rate * 0.5
                    participation = 0.0
                else:
                    impact = (goals + 0.7 * assists + self.prior_games * self.prior_rate) / (games + self.prior_games)
                    participation = min(1.0, games / team_games) if team_games else 0.0
                impacts[int(item["player_id"])] = PlayerImpact(
                    player_id=int(item["player_id"]),
                    name=str(item["full_name"]),
                    team_id=team_id,
                    games=games,
                    goals=goals,
                    assists=assists,
                    impact=impact,
                    participation=participation,
                )
            self.by_team_season[key] = impacts
            ordered = sorted(impacts.values(), key=lambda p: (p.participation * p.impact), reverse=True)[:8]
            if ordered:
                weight = sum(max(0.1, p.participation) for p in ordered)
                strength = sum(max(0.1, p.participation) * p.impact for p in ordered) / weight
            else:
                strength = 0.0
            self.team_season_strength[key] = strength

        by_season: dict[int, list[float]] = {}
        for (team_id, season_id), strength in self.team_season_strength.items():
            by_season.setdefault(season_id, []).append(strength)
        self.league_strength = {
            season: sum(values) / len(values) for season, values in by_season.items() if values
        }

    def league_mean(self, season_id: int) -> float:
        """Средняя сила состава лиги по последнему сезону до целевого."""
        seasons = [season for season in self.league_strength if season < season_id]
        if not seasons:
            return 0.0
        return self.league_strength[max(seasons)]

    def team_strength(
        self,
        team_id: int,
        target_season: int,
        *,
        excluded: set[int] | None = None,
    ) -> float | None:
        excluded = excluded or set()
        candidates = [
            (season, strength)
            for (team, season), strength in self.team_season_strength.items()
            if team == team_id and season < target_season
        ]
        if not candidates:
            return None
        candidates.sort()
        season, strength = candidates[-1]
        if excluded:
            strength = self._recompute_strength(team_id, season, excluded)
        # Устаревшие данные тянем к среднему лиги.
        league = self.league_strength.get(season, 0.0)
        gap = max(0, target_season - season - 1)
        weight = 0.75**gap
        return league + (strength - league) * weight

    def _recompute_strength(self, team_id: int, season_id: int, excluded: set[int]) -> float:
        impacts = self.by_team_season.get((team_id, season_id), {})
        ordered = sorted(
            (player for player in impacts.values() if player.player_id not in excluded),
            key=lambda player: (player.participation * player.impact),
            reverse=True,
        )[:8]
        if not ordered:
            return self.league_strength.get(season_id, 0.0)
        weight = sum(max(0.1, player.participation) for player in ordered)
        return sum(max(0.1, player.participation) * player.impact for player in ordered) / weight

    def lineup(self, team_id: int, target_season: int) -> list[PlayerImpact]:
        candidates = [
            (season, impacts)
            for (team, season), impacts in self.by_team_season.items()
            if team == team_id and season < target_season
        ]
        if not candidates:
            return []
        candidates.sort(key=lambda item: item[0])
        return list(candidates[-1][1].values())


@dataclass
class FeatureRow:
    match_id: int
    date: str
    season_id: int
    home_id: int
    away_id: int
    outcome: int
    features: dict[str, float] = field(default_factory=dict)


def base_rate(history: list[int]) -> dict[int, float]:
    """Доли исходов в истории (сглаженные)."""
    counts = [1.0, 1.0, 1.0]
    for outcome in history:
        counts[outcome] += 1
    total = sum(counts)
    return {index: counts[index] / total for index in range(3)}
