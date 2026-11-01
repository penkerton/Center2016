"""Тест отсутствия утечки: признаки матча не зависят от будущих матчей."""

from __future__ import annotations

import unittest
from dataclasses import replace

from fhm_predictor.engine import Match
from fhm_predictor.features import build_observations

TEAMS = [1, 2, 3, 4]


def make_match(index: int, home: int, away: int, home_goals: int, away_goals: int) -> Match:
    day = (index % 28) + 1
    month = 9 + (index // 28)
    return Match(
        id=1000 + index,
        date=f"2026-{month:02d}-{day:02d}",
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
        group_name="Группа В",
    )


def synthetic_matches(count: int = 40) -> list[Match]:
    matches = []
    for index in range(count):
        home = TEAMS[index % len(TEAMS)]
        away = TEAMS[(index + 1 + index // 7) % len(TEAMS)]
        if home == away:
            away = TEAMS[(away + 1) % len(TEAMS)]
        home_goals = (index * 3 + home) % 9
        away_goals = (index * 5 + away) % 7
        matches.append(make_match(index, home, away, home_goals, away_goals))
    return matches


class LeakageTests(unittest.TestCase):
    def test_prefix_features_are_stable(self) -> None:
        matches = synthetic_matches()
        full = build_observations(matches)
        prefix = build_observations(matches[:20])
        self.assertEqual(len(prefix), 20)
        for index in range(20):
            self.assertEqual(full[index].features, prefix[index].features, f"утечка в матче {index}")
            self.assertEqual(full[index].outcome, prefix[index].outcome)

    def test_future_result_does_not_change_past(self) -> None:
        matches = synthetic_matches()
        changed = replace(matches[25], home_goals=99, away_goals=0)
        baseline = build_observations(matches)
        modified_matches = matches[:25] + [changed] + matches[26:]
        modified = build_observations(modified_matches)
        for index in range(25):
            self.assertEqual(baseline[index].features, modified[index].features)


if __name__ == "__main__":
    unittest.main()
