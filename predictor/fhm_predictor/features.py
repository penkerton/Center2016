"""Признаки матча, рассчитанные только по прошлым данным.

Один проход по хронологии: перед матчем считаем признаки из текущего состояния,
после матча обновляем Elo, форму и пуассоновскую модель. Такой проход исключает
утечку будущих результатов.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from .engine import (
    OUTCOME_AWAY,
    OUTCOME_DRAW,
    OUTCOME_HOME,
    EloEngine,
    FormTracker,
    Match,
    PoissonModel,
    PlayerStrength,
    is_trainable,
)

FEATURE_NAMES = (
    "elo_diff",
    "elo_home",
    "elo_away",
    "form_ppg_diff",
    "form_gf_diff",
    "form_ga_diff",
    "rest_diff",
    "experience_diff",
    "poisson_log_ratio",
    "player_diff",
    "is_4x4",
    "is_5x5",
    "is_2016",
    "is_group_a",
    "is_group_b",
    "is_group_v",
)


@dataclass
class Observation:
    match: Match
    features: dict[str, float]
    elo_probs: tuple[float, float, float]
    poisson_probs: tuple[float, float, float]
    player_probs: tuple[float, float, float]
    elo_home: float
    elo_away: float
    player_strength_home: float
    player_strength_away: float
    outcome: int


@dataclass
class FeatureState:
    player_strength: PlayerStrength | None = None
    elo: EloEngine = field(default_factory=EloEngine)
    form: FormTracker = field(default_factory=FormTracker)
    poisson: PoissonModel = field(default_factory=PoissonModel)
    poisson_every: int = 40
    history: list[Match] = field(default_factory=list)
    outcomes: list[int] = field(default_factory=list)

    def draw_rate(self) -> float:
        if not self.outcomes:
            return 0.02
        draws = sum(1 for outcome in self.outcomes if outcome == OUTCOME_DRAW)
        return (draws + 1.0) / (len(self.outcomes) + 50.0)

    def _player_strength(self, team_id: int, season_id: int) -> float:
        if self.player_strength is None:
            return 0.0
        value = self.player_strength.team_strength(team_id, season_id)
        # Нет данных о прошлом составе — считаем команду средней по лиге,
        # а не «нулевой» (иначе новые команды получают необоснованный штраф).
        return self.player_strength.league_mean(season_id) if value is None else value

    def features(self, match: Match) -> dict[str, float]:
        home_form = self.form.stats(match.home_id)
        away_form = self.form.stats(match.away_id)
        elo_home = self.elo.rating(match.home_id)
        elo_away = self.elo.rating(match.away_id)
        lambda_home, lambda_away = self.poisson.expected_goals(match.home_id, match.away_id)
        psi_home = self._player_strength(match.home_id, match.season_id)
        psi_away = self._player_strength(match.away_id, match.season_id)
        group_name = (match.group_name or "").lower()
        format_name = (match.format or "").lower()
        return {
            "elo_diff": (elo_home - elo_away) / 100.0,
            "elo_home": (elo_home - 1500.0) / 100.0,
            "elo_away": (elo_away - 1500.0) / 100.0,
            "form_ppg_diff": home_form["ppg"] - away_form["ppg"],
            "form_gf_diff": home_form["gf"] - away_form["gf"],
            "form_ga_diff": home_form["ga"] - away_form["ga"],
            "rest_diff": self.form.rest_days(match.home_id, match.date)
            - self.form.rest_days(match.away_id, match.date),
            "experience_diff": math.log1p(self.elo.games.get(match.home_id, 0))
            - math.log1p(self.elo.games.get(match.away_id, 0)),
            "poisson_log_ratio": math.log(max(lambda_home, 1e-6) / max(lambda_away, 1e-6)),
            "player_diff": psi_home - psi_away,
            "is_4x4": 1.0 if "4" in format_name else 0.0,
            "is_5x5": 1.0 if "5" in format_name else 0.0,
            "is_2016": 1.0 if match.age_year == 2016 else 0.0,
            "is_group_a": 1.0 if group_name.endswith("а") else 0.0,
            "is_group_b": 1.0 if group_name.endswith("б") else 0.0,
            "is_group_v": 1.0 if group_name.endswith("в") else 0.0,
        }

    def player_adjusted_probs(self, match: Match) -> tuple[tuple[float, float, float], float, float]:
        psi_home = self._player_strength(match.home_id, match.season_id)
        psi_away = self._player_strength(match.away_id, match.season_id)
        bonus = max(-120.0, min(120.0, 220.0 * (psi_home - psi_away)))
        diff = self.elo.rating(match.home_id) - self.elo.rating(match.away_id) + self.elo.home_advantage + bonus
        raw = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
        draw_rate = self.draw_rate()
        closeness = max(0.0, 1.0 - 2.0 * abs(raw - 0.5))
        draw = max(0.0, min(0.35, draw_rate * closeness))
        return (raw * (1.0 - draw), draw, (1.0 - raw) * (1.0 - draw)), psi_home, psi_away

    def observe(self, match: Match) -> None:
        self.elo.update(match)
        self.form.add(match)
        self.history.append(match)
        if is_trainable(match):
            self.outcomes.append(match.outcome)

    def refit_poisson(self, as_of: date) -> None:
        usable = [m for m in self.history if is_trainable(m)]
        if len(usable) >= 20:
            self.poisson.fit(usable, as_of)


def build_observations(
    matches: list[Match],
    *,
    player_strength: PlayerStrength | None = None,
    poisson_every: int = 40,
) -> list[Observation]:
    """Идёт по хронологии и сохраняет признаки до обновления состояния."""
    state = FeatureState(player_strength=player_strength, poisson_every=poisson_every)
    observations: list[Observation] = []
    for match in matches:
        if not is_trainable(match):
            # Технические поражения не обучают модель, но фиксируются в истории.
            state.observe(match)
            continue
        if len(state.history) >= 20 and len(state.history) % poisson_every == 0:
            state.refit_poisson(match.kickoff.date())
        features = state.features(match)
        elo_probs = state.elo.predict(match.home_id, match.away_id, state.draw_rate())
        poisson_probs = state.poisson.predict(match.home_id, match.away_id)
        player_probs, psi_home, psi_away = state.player_adjusted_probs(match)
        observations.append(
            Observation(
                match=match,
                features=features,
                elo_probs=elo_probs,
                poisson_probs=poisson_probs,
                player_probs=player_probs,
                elo_home=state.elo.rating(match.home_id),
                elo_away=state.elo.rating(match.away_id),
                player_strength_home=psi_home,
                player_strength_away=psi_away,
                outcome=match.outcome,
            )
        )
        state.observe(match)
    return observations


def matrix(observations: list[Observation]) -> tuple[list[list[float]], list[int]]:
    rows: list[list[float]] = []
    labels: list[int] = []
    for observation in observations:
        rows.append([observation.features[name] for name in FEATURE_NAMES])
        labels.append(observation.outcome)
    return rows, labels


def final_state(matches: list[Match], player_strength: PlayerStrength | None = None) -> FeatureState:
    state = FeatureState(player_strength=player_strength)
    for match in matches:
        state.observe(match)
    if matches:
        state.refit_poisson(matches[-1].kickoff.date())
    return state
