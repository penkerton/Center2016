"""Прогноз матча: сборка признаков, вероятности и объяснение.

Прогноз строится только по матчам, сыгранным до времени начала встречи.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from . import config, db
from .backtest import ENSEMBLE_WEIGHTS, ensemble
from .engine import (
    OUTCOME_AWAY,
    OUTCOME_DRAW,
    OUTCOME_HOME,
    Match,
    PlayerStrength,
    load_matches,
)
from .features import FEATURE_NAMES, FeatureState, Observation, build_observations, matrix
from .models import SoftmaxRegression, normalize


@dataclass
class Prediction:
    match_id: int
    home_name: str
    away_name: str
    date: str
    time: str
    tournament: str
    group: str
    format: str | None
    cutoff: str
    probabilities: dict[str, tuple[float, float, float]]
    ensemble: tuple[float, float, float]
    features: dict[str, float]
    reasons: list[str] = field(default_factory=list)
    confidence: str = "низкая"
    data_quality: dict[str, Any] = field(default_factory=dict)
    features_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "home": self.home_name,
            "away": self.away_name,
            "date": self.date,
            "time": self.time,
            "tournament": self.tournament,
            "group": self.group,
            "format": self.format,
            "cutoff": self.cutoff,
            "probabilities": {
                name: {"home": round(value[0], 4), "draw": round(value[1], 4), "away": round(value[2], 4)}
                for name, value in self.probabilities.items()
            },
            "ensemble": {
                "home": round(self.ensemble[0], 4),
                "draw": round(self.ensemble[1], 4),
                "away": round(self.ensemble[2], 4),
            },
            "features": {key: round(value, 4) for key, value in self.features.items()},
            "reasons": self.reasons,
            "confidence": self.confidence,
            "data_quality": self.data_quality,
            "features_hash": self.features_hash,
        }


def _find_match(conn, match_id: int) -> Match:
    matches = load_matches(conn, only_played=False)
    for match in matches:
        if match.id == match_id:
            return match
    raise KeyError(f"Матч {match_id} не найден в базе")


def _history_before(matches: list[Match], cutoff: datetime) -> list[Match]:
    return [match for match in matches if match.home_goals is not None and match.kickoff < cutoff]


def _ensemble_probs(
    observation: Observation,
    logistic_probs: tuple[float, float, float],
) -> tuple[float, float, float]:
    return ensemble(observation, logistic_probs)


def _feature_contributions(
    observation: Observation,
    logistic: SoftmaxRegression | None,
) -> dict[str, float]:
    """Грубая оценка вклада признаков в разницу «хозяева — гости»."""
    contributions: dict[str, float] = {}
    if logistic is None or logistic.weights is None or logistic.mean is None or logistic.scale is None:
        return contributions
    for index, name in enumerate(FEATURE_NAMES):
        value = (observation.features[name] - float(logistic.mean[index])) / float(logistic.scale[index])
        contributions[name] = float(value * (logistic.weights[index][0] - logistic.weights[index][2]))
    return contributions


def _normalize_cutoff(value: datetime) -> datetime:
    """Приводит отсечку к московскому наивному времени (так хранятся даты матчей)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)


def build_prediction(
    conn,
    match_id: int,
    *,
    cutoff: datetime | None = None,
    excluded_players: set[int] | None = None,
) -> Prediction:
    target = _find_match(conn, match_id)
    cutoff = _normalize_cutoff(cutoff) if cutoff else target.kickoff
    all_matches = load_matches(conn, only_played=False)
    history = _history_before(all_matches, cutoff)
    if not history:
        raise RuntimeError("Нет ни одного матча до отсечки — прогноз невозможен")

    player_strength = PlayerStrength()
    player_strength.build(conn)
    observations = build_observations(history, player_strength=player_strength)
    if len(observations) < 60:
        raise RuntimeError("Недостаточно матчей для обучения")

    logistic = SoftmaxRegression(l2=0.05, learning_rate=0.08, epochs=500)
    X, y = matrix(observations)
    logistic.fit(X, y)

    state = FeatureState(player_strength=player_strength)
    for match in history:
        state.observe(match)
    state.refit_poisson(cutoff.date())

    features = state.features(target)
    elo_probs = state.elo.predict(target.home_id, target.away_id, state.draw_rate())
    poisson_probs = state.poisson.predict(target.home_id, target.away_id)
    player_probs, psi_home, psi_away = state.player_adjusted_probs(target)

    if excluded_players:
        strength_home = player_strength.team_strength(target.home_id, target.season_id, excluded=excluded_players)
        strength_away = player_strength.team_strength(target.away_id, target.season_id, excluded=excluded_players)
        if strength_home is None:
            strength_home = player_strength.league_mean(target.season_id)
        if strength_away is None:
            strength_away = player_strength.league_mean(target.season_id)
        bonus = max(-120.0, min(120.0, 220.0 * (strength_home - strength_away)))
        diff = (
            state.elo.rating(target.home_id)
            - state.elo.rating(target.away_id)
            + state.elo.home_advantage
            + bonus
        )
        raw = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
        closeness = max(0.0, 1.0 - 2.0 * abs(raw - 0.5))
        draw = max(0.0, min(0.35, state.draw_rate() * closeness))
        player_probs = (raw * (1.0 - draw), draw, (1.0 - raw) * (1.0 - draw))
        features = dict(features)
        features["player_diff"] = strength_home - strength_away
        psi_home, psi_away = strength_home, strength_away

    observation = Observation(
        match=target,
        features=features,
        elo_probs=elo_probs,
        poisson_probs=poisson_probs,
        player_probs=player_probs,
        elo_home=state.elo.rating(target.home_id),
        elo_away=state.elo.rating(target.away_id),
        player_strength_home=psi_home,
        player_strength_away=psi_away,
        outcome=-1,
    )
    logistic_probs = logistic.predict_proba([[features[name] for name in FEATURE_NAMES]])[0]
    probabilities = {
        "elo": elo_probs,
        "poisson": poisson_probs,
        "player": player_probs,
        "logistic": logistic_probs,
        "ensemble": _ensemble_probs(observation, logistic_probs),
    }

    games_home = state.elo.games.get(target.home_id, 0)
    games_away = state.elo.games.get(target.away_id, 0)
    roster_rows = conn.execute(
        "SELECT COUNT(*) AS n FROM player_season_stats WHERE season_id = ? AND team_id IN (?, ?)",
        (target.season_id, target.home_id, target.away_id),
    ).fetchone()["n"]
    confidence = "высокая" if min(games_home, games_away) >= 10 and roster_rows >= 20 else (
        "средняя" if min(games_home, games_away) >= 5 else "низкая"
    )

    reasons = _reasons(target, state, psi_home, psi_away, poisson_probs)
    features_hash = hashlib.sha256(
        json.dumps(
            {
                "match_id": target.id,
                "cutoff": cutoff.isoformat(),
                "features": {key: round(float(value), 6) for key, value in sorted(features.items())},
                "ensemble_weights": ENSEMBLE_WEIGHTS,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    return Prediction(
        match_id=target.id,
        home_name=target.home_name,
        away_name=target.away_name,
        date=target.date,
        time=target.time,
        tournament=target.tournament_name,
        group=target.group_name,
        format=target.format,
        cutoff=cutoff.isoformat(),
        probabilities=probabilities,
        ensemble=probabilities["ensemble"],
        features=features,
        reasons=reasons,
        confidence=confidence,
        data_quality={
            "history_matches": len(history),
            "home_games": games_home,
            "away_games": games_away,
            "roster_stat_rows": roster_rows,
        },
        features_hash=features_hash,
    )


def _reasons(
    target: Match,
    state: FeatureState,
    psi_home: float,
    psi_away: float,
    poisson_probs: tuple[float, float, float],
) -> list[str]:
    reasons: list[str] = []
    elo_home = state.elo.rating(target.home_id)
    elo_away = state.elo.rating(target.away_id)
    diff = elo_home - elo_away
    if abs(diff) < 25:
        reasons.append(f"Рейтинги команд практически равны ({elo_home:.0f} против {elo_away:.0f}).")
    else:
        leader = target.home_name if diff > 0 else target.away_name
        reasons.append(
            f"По рейтингу Elo сильнее {leader}: {elo_home:.0f} против {elo_away:.0f} "
            f"(разница {abs(diff):.0f})."
        )

    lambda_home, lambda_away = state.poisson.expected_goals(target.home_id, target.away_id)
    reasons.append(
        f"Ожидаемая результативность: {lambda_home:.1f} шайбы у хозяев и {lambda_away:.1f} у гостей."
    )

    home_form = state.form.stats(target.home_id)
    away_form = state.form.stats(target.away_id)
    if home_form["games"] and away_form["games"]:
        reasons.append(
            f"Форма последних матчей: {home_form['ppg']:.1f} очка за игру у {target.home_name}, "
            f"{away_form['ppg']:.1f} у {target.away_name}."
        )

    if abs(psi_home - psi_away) > 0.02:
        better = target.home_name if psi_home > psi_away else target.away_name
        reasons.append(
            f"Оценка состава по прошлым сезонам выше у {better} "
            f"({psi_home:.2f} против {psi_away:.2f} условных шайб на игрока)."
        )

    if target.format:
        reasons.append(f"Формат встречи: {target.format}.")
    return reasons


def save_prediction(conn, prediction: Prediction, *, immutable: bool = False) -> None:
    payload = prediction.as_dict()
    directory = config.PREDICTIONS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"match_{prediction.match_id}.json"
    if immutable and path.exists():
        raise FileExistsError(f"Неизменяемый прогноз уже существует: {path}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    conn.execute(
        """
        INSERT INTO predictions(match_id, model_version, model_kind, created_at, cutoff,
                                prob_home, prob_draw, prob_away, features_json, features_hash)
        VALUES(?, ?, 'ensemble', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prediction.match_id,
            "ensemble-v1",
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            prediction.cutoff,
            prediction.ensemble[0],
            prediction.ensemble[1],
            prediction.ensemble[2],
            json.dumps(prediction.features, ensure_ascii=False),
            prediction.features_hash,
        ),
    )
    conn.commit()


def verify_prediction(conn, match_id: int) -> dict[str, Any]:
    """Сравнивает сохранённый прогноз с фактическим результатом."""
    path = config.PREDICTIONS_DIR / f"match_{match_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Сначала сохраните прогноз: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    row = conn.execute(
        "SELECT home_goals, away_goals FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if row is None or row["home_goals"] is None:
        raise RuntimeError("Фактический результат ещё не опубликован")
    home_goals, away_goals = int(row["home_goals"]), int(row["away_goals"])
    actual = OUTCOME_HOME if home_goals > away_goals else (OUTCOME_AWAY if away_goals > home_goals else OUTCOME_DRAW)
    probs = payload["ensemble"]
    probabilities = (probs["home"], probs["draw"], probs["away"])
    predicted = max(range(3), key=lambda index: probabilities[index])
    comparison = {
        "match_id": match_id,
        "predicted": probabilities,
        "predicted_outcome": predicted,
        "actual_score": f"{home_goals}:{away_goals}",
        "actual_outcome": actual,
        "correct": predicted == actual,
        "brier": sum((probabilities[index] - (1.0 if index == actual else 0.0)) ** 2 for index in range(3)),
        "features_hash": payload.get("features_hash"),
        "cutoff": payload.get("cutoff"),
    }
    conn.execute(
        "UPDATE predictions SET actual_home = ?, actual_away = ?, actual_outcome = ?, correct = ? "
        "WHERE match_id = ? AND cutoff = ?",
        (home_goals, away_goals, str(actual), int(predicted == actual), match_id, payload.get("cutoff")),
    )
    conn.commit()
    return comparison


def describe_probabilities(probabilities: tuple[float, float, float]) -> str:
    home, draw, away = normalize(probabilities)
    return f"хозяева {home * 100:.1f}%, ничья {draw * 100:.1f}%, гости {away * 100:.1f}%"
