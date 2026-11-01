"""Walk-forward backtesting: прогноз строго до матча, обновление после.

Для каждого матча признаки считаются по состоянию на момент до встречи.
Логистическая регрессия переобучается только на прошлых матчах.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, db
from .engine import OUTCOME_AWAY, OUTCOME_DRAW, OUTCOME_HOME, EloEngine, Match, PlayerStrength, load_matches
from .features import FEATURE_NAMES, Observation, build_observations, matrix
from .models import Metrics, SoftmaxRegression, bootstrap_accuracy, calibration_table, evaluate, normalize

MODEL_NAMES = ("elo", "poisson", "player", "logistic", "ensemble")
MODEL_LABELS = {
    "elo": "Elo",
    "poisson": "Пуассон",
    "player": "Elo + игроки",
    "logistic": "Логистическая регрессия",
    "ensemble": "Ансамбль",
}
ENSEMBLE_WEIGHTS = {"logistic": 0.60, "poisson": 0.40, "player": 0.0, "elo": 0.0}


@dataclass
class SliceKey:
    name: str
    predicate: Any


def _group_letter(match: Match) -> str:
    text = (match.group_name or "").strip().lower()
    for letter in ("а", "б", "в", "г", "д", "ж"):
        if text.endswith(letter):
            return letter.upper()
    return "?"


def _slices(observations: list[Observation]) -> dict[str, list[int]]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, observation in enumerate(observations):
        match = observation.match
        if match.age_year:
            buckets[f"age_{match.age_year}"].append(index)
        letter = _group_letter(match)
        if letter != "?":
            buckets[f"group_{letter}"].append(index)
        if match.format:
            buckets[f"format_{match.format.replace('×', 'x')}"].append(index)
        buckets[f"season_{match.season_label.replace('/', '_')}"].append(index)
    return dict(buckets)


def ensemble(observation: Observation, logistic_probs: tuple[float, float, float]) -> tuple[float, float, float]:
    parts = {
        "elo": observation.elo_probs,
        "poisson": observation.poisson_probs,
        "player": observation.player_probs,
        "logistic": logistic_probs,
    }
    total = sum(ENSEMBLE_WEIGHTS.values())
    return normalize(
        tuple(  # type: ignore[arg-type]
            sum(ENSEMBLE_WEIGHTS[name] * parts[name][index] for name in ENSEMBLE_WEIGHTS) / total
            for index in range(3)
        )
    )


def _metrics_for(
    predictions: dict[str, list[tuple[float, float, float]]],
    observations: list[Observation],
    indices: list[int],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    outcomes = [observations[index].outcome for index in indices]
    prior = _prior(outcomes)
    for name in MODEL_NAMES:
        probs = [predictions[name][index] for index in indices]
        metrics = evaluate(probs, outcomes)
        low, high = bootstrap_accuracy(probs, outcomes, rounds=300)
        result[name] = {
            **metrics.as_dict(),
            "accuracy_ci95": [round(low, 4), round(high, 4)],
            "calibration": calibration_table(probs, outcomes),
            "blended": evaluate([_blend(p, prior) for p in probs], outcomes).as_dict(),
        }
    return result


def _prior(outcomes: list[int]) -> tuple[float, float, float]:
    counts = [1.0, 1.0, 1.0]
    for outcome in outcomes:
        counts[outcome] += 1
    total = sum(counts)
    return (counts[0] / total, counts[1] / total, counts[2] / total)


def _blend(probs: tuple[float, float, float], prior: tuple[float, float, float], weight: float = 0.05):
    return normalize(
        tuple(probs[index] * (1 - weight) + prior[index] * weight for index in range(3))  # type: ignore[arg-type]
    )


def run_backtest(
    conn,
    *,
    warmup: int = 120,
    retrain_every: int = 30,
    save: bool = True,
) -> dict[str, Any]:
    matches = [match for match in load_matches(conn) if not match.technical_defeat]
    if len(matches) < warmup + 20:
        raise RuntimeError(f"Слишком мало матчей для backtest: {len(matches)}")

    player_strength = PlayerStrength()
    player_strength.build(conn)
    observations = build_observations(matches, player_strength=player_strength, poisson_every=40)
    if len(observations) != len(matches):
        # Технические поражения отфильтрованы, но не должно расходиться.
        matches = [observation.match for observation in observations]

    X, y = matrix(observations)
    predictions: dict[str, list[tuple[float, float, float]]] = {name: [] for name in MODEL_NAMES}
    logistic = None
    last_fit = -1

    for index, observation in enumerate(observations):
        if index < warmup:
            # Тёплый участок: модели ещё не оцениваются, но прогнозы заполняем.
            logistic_probs = observation.elo_probs
        else:
            if logistic is None or index - last_fit >= retrain_every:
                train_X = X[:index]
                train_y = y[:index]
                if len(set(train_y)) >= 2 and len(train_X) >= 60:
                    logistic = SoftmaxRegression(l2=0.05, learning_rate=0.08, epochs=500).fit(train_X, train_y)
                last_fit = index
            if logistic is not None:
                logistic_probs = logistic.predict_proba([X[index]])[0]
            else:
                logistic_probs = observation.elo_probs

        predictions["elo"].append(observation.elo_probs)
        predictions["poisson"].append(observation.poisson_probs)
        predictions["player"].append(observation.player_probs)
        predictions["logistic"].append(logistic_probs)
        predictions["ensemble"].append(ensemble(observation, logistic_probs))

    evaluated_indices = list(range(warmup, len(observations)))
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "matches_total": len(matches),
        "evaluated": len(evaluated_indices),
        "warmup": warmup,
        "retrain_every": retrain_every,
        "date_from": observations[evaluated_indices[0]].match.date,
        "date_to": observations[evaluated_indices[-1]].match.date,
        "models": _metrics_for(predictions, observations, evaluated_indices),
        "ensemble_weights": ENSEMBLE_WEIGHTS,
        "slices": {},
        "outcome_distribution": {
            "home": sum(1 for o in observations if o.outcome == OUTCOME_HOME),
            "draw": sum(1 for o in observations if o.outcome == OUTCOME_DRAW),
            "away": sum(1 for o in observations if o.outcome == OUTCOME_AWAY),
        },
        "draws_in_data": any(o.outcome == OUTCOME_DRAW for o in observations),
        "goal_dispersion": _goal_dispersion(matches),
    }
    for name, indices in sorted(_slices(observations).items()):
        selected = [index for index in indices if index >= warmup]
        if len(selected) < 10:
            continue
        report["slices"][name] = _metrics_for(predictions, observations, selected)

    # Веса ансамбля подбирались по первым 70% проверочных матчей. Метрики на
    # оставшихся 30% — честная проверка выбора, их и стоит смотреть в первую очередь.
    holdout_start = warmup + int(len(evaluated_indices) * 0.7)
    holdout_indices = list(range(holdout_start, len(observations)))
    report["holdout"] = {
        "n": len(holdout_indices),
        "from": observations[holdout_start].match.date if holdout_indices else None,
        "to": observations[holdout_indices[-1]].match.date if holdout_indices else None,
        "models": _metrics_for(predictions, observations, holdout_indices),
        "note": "Веса ансамбля выбраны по первым 70% проверочных матчей, здесь — отложенные 30%.",
    }

    if save:
        save_rating_snapshots(conn, matches, player_strength)
        save_report(report, predictions, observations)

    return report


def _goal_dispersion(matches: list[Match]) -> dict[str, float | int]:
    """Проверка применимости Пуассона: дисперсия голов на команду против среднего."""
    goals = [match.home_goals for match in matches] + [match.away_goals for match in matches]
    count = len(goals)
    if count < 2:
        return {"n": count, "mean": 0.0, "variance": 0.0, "ratio": 0.0}
    mean = sum(goals) / count
    variance = sum((value - mean) ** 2 for value in goals) / (count - 1)
    return {
        "n": count,
        "mean": round(mean, 3),
        "variance": round(variance, 3),
        "ratio": round(variance / mean, 3) if mean else 0.0,
    }


def save_rating_snapshots(conn, matches: list[Match], player_strength: PlayerStrength) -> None:
    """Сохраняет итоговые рейтинги команд и игроков на последнюю дату."""
    if not matches:
        return
    as_of = matches[-1].kickoff.date().isoformat()
    engine = EloEngine()
    for match in matches:
        engine.update(match)
    team_rows = [
        {
            "team_id": team_id,
            "as_of": as_of,
            "elo": round(rating, 2),
            "matches": engine.games.get(team_id, 0),
            "attack": None,
            "defense": None,
        }
        for team_id, rating in engine.ratings.items()
    ]
    db.upsert(conn, "team_ratings_history", team_rows, ["team_id", "as_of"])

    latest_by_player: dict[int, tuple[int, float, int, int, int]] = {}
    for (team_id, season_id), impacts in player_strength.by_team_season.items():
        for impact in impacts.values():
            current = latest_by_player.get(impact.player_id)
            if current is None or season_id > current[0]:
                latest_by_player[impact.player_id] = (
                    season_id,
                    impact.impact,
                    impact.games,
                    impact.goals,
                    impact.assists,
                )
    player_rows = [
        {
            "player_id": player_id,
            "as_of": as_of,
            "rating": round(values[1], 4),
            "games": values[2],
            "goals": values[3],
            "assists": values[4],
        }
        for player_id, values in latest_by_player.items()
    ]
    db.upsert(conn, "player_ratings_history", player_rows, ["player_id", "as_of"])
    conn.commit()


def save_report(
    report: dict[str, Any],
    predictions: dict[str, list[tuple[float, float, float]]],
    observations: list[Observation],
) -> None:
    reports_dir = config.PROJECT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "backtest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with open(reports_dir / "backtest_predictions.csv", "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(
            [
                "match_id",
                "date",
                "season",
                "age",
                "format",
                "group",
                "home",
                "away",
                "home_goals",
                "away_goals",
                "outcome",
                *[f"{name}_p_home" for name in MODEL_NAMES],
                *[f"{name}_p_draw" for name in MODEL_NAMES],
                *[f"{name}_p_away" for name in MODEL_NAMES],
            ]
        )
        for index, observation in enumerate(observations):
            match = observation.match
            writer.writerow(
                [
                    match.id,
                    match.date,
                    match.season_label,
                    match.age_year,
                    match.format,
                    match.group_name,
                    match.home_name,
                    match.away_name,
                    match.home_goals,
                    match.away_goals,
                    match.outcome,
                    *[round(predictions[name][index][0], 4) for name in MODEL_NAMES],
                    *[round(predictions[name][index][1], 4) for name in MODEL_NAMES],
                    *[round(predictions[name][index][2], 4) for name in MODEL_NAMES],
                ]
            )


def save_model_version(conn, *, model_id: str, params: dict[str, Any], metrics: dict[str, Any], notes: str = "") -> None:
    db.upsert(
        conn,
        "model_versions",
        [
            {
                "id": model_id,
                "created_at": db.utc_now(),
                "kind": "ensemble",
                "params_json": json.dumps(params, ensure_ascii=False),
                "metrics_json": json.dumps(metrics, ensure_ascii=False),
                "is_active": 1,
                "notes": notes,
            }
        ],
        ["id"],
    )
    conn.execute("UPDATE model_versions SET is_active = 0 WHERE id <> ?", (model_id,))
    conn.commit()
