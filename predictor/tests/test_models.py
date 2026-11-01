"""Тесты рейтингов, моделей и метрик."""

from __future__ import annotations

import unittest

from fhm_predictor.engine import EloEngine, Match, PoissonModel
from fhm_predictor.models import SoftmaxRegression, evaluate


def match(match_id: int, home: int, away: int, home_goals: int, away_goals: int, date: str = "2026-09-01") -> Match:
    return Match(
        id=match_id,
        date=date,
        time="10:00",
        season_id=5,
        tournament_id=51,
        group_id=1,
        home_id=home,
        away_id=away,
        home_name=f"Команда {home}",
        away_name=f"Команда {away}",
        home_goals=home_goals,
        away_goals=away_goals,
        format="4×4",
        age_year=2016,
    )


class EloTests(unittest.TestCase):
    def test_home_advantage(self) -> None:
        engine = EloEngine()
        probability = engine.win_probability(1, 2)
        self.assertGreater(probability, 0.5)

    def test_winner_gains_rating(self) -> None:
        engine = EloEngine()
        before = engine.rating(1)
        engine.update(match(1, 1, 2, 5, 1))
        self.assertGreater(engine.rating(1), before)
        self.assertLess(engine.rating(2), before)

    def test_season_regression(self) -> None:
        engine = EloEngine()
        engine.ratings[1] = 1700.0
        engine.last_season[1] = 4
        engine._regress(1, 5)
        self.assertLess(engine.rating(1), 1700.0)
        self.assertGreater(engine.rating(1), 1500.0)


class PoissonTests(unittest.TestCase):
    def test_probabilities_sum_to_one(self) -> None:
        model = PoissonModel()
        matches = [
            match(1, 1, 2, 5, 2),
            match(2, 1, 3, 3, 3),
            match(3, 2, 3, 4, 1),
            match(4, 2, 1, 2, 2),
        ]
        model.fit(matches, __import__("datetime").date(2026, 9, 30))
        home, draw, away = model.predict(1, 2)
        self.assertAlmostEqual(home + draw + away, 1.0, places=6)

    def test_stronger_attack_scores_more(self) -> None:
        model = PoissonModel()
        model.attack = {1: 2.0, 2: 0.5}
        model.defense = {1: 1.0, 2: 1.0}
        model.avg_goals = 3.0
        lambda_home, _ = model.expected_goals(1, 2)
        lambda_weak, _ = model.expected_goals(2, 1)
        self.assertGreater(lambda_home, lambda_weak)


class ModelTests(unittest.TestCase):
    def test_softmax_sums_to_one(self) -> None:
        X = [[0.0, 0.0], [1.0, 1.0], [-1.0, 0.5], [0.3, -0.2]]
        y = [0, 2, 1, 0]
        model = SoftmaxRegression(epochs=50).fit(X, y)
        probabilities = model.predict_proba(X)
        for triple in probabilities:
            self.assertAlmostEqual(sum(triple), 1.0, places=6)

    def test_metrics_perfect_prediction(self) -> None:
        probs = [(0.9, 0.05, 0.05), (0.05, 0.9, 0.05), (0.05, 0.05, 0.9)]
        metrics = evaluate(probs, [0, 1, 2])
        self.assertEqual(metrics.accuracy, 1.0)
        self.assertLess(metrics.log_loss, 0.2)

    def test_metrics_never_negative(self) -> None:
        metrics = evaluate([(0.4, 0.3, 0.3)], [2])
        self.assertGreater(metrics.brier, 0.0)
        self.assertGreater(metrics.log_loss, 0.0)


if __name__ == "__main__":
    unittest.main()
