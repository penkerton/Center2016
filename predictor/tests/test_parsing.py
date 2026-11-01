"""Тесты разбора дат и HTML-протокола."""

from __future__ import annotations

import unittest

from fhm_predictor.api import (
    normalize_game,
    parse_age_year,
    parse_format,
    parse_game_datetime,
    parse_season_label,
)
from fhm_predictor.protocols import parse_game_page


class DateTimeTests(unittest.TestCase):
    def test_year_from_season(self) -> None:
        iso, clock = parse_game_datetime("31 октября, суббота | 09:45", "Сб, 31.10, 09:45", season_start=2026, season_end=2027)
        self.assertEqual(iso, "2026-10-31")
        self.assertEqual(clock, "09:45")

    def test_january_belongs_to_second_year(self) -> None:
        iso, _ = parse_game_datetime("8 января, среда", "Ср, 08.01, 10:00", season_start=2026, season_end=2027)
        self.assertEqual(iso, "2027-01-08")

    def test_explicit_year_wins(self) -> None:
        iso, clock = parse_game_datetime("24 апреля 2027, суббота", "Сб, 24.04, 00:00")
        self.assertEqual(iso, "2027-04-24")
        self.assertEqual(clock, "")

    def test_season_label_uses_four_digit_years(self) -> None:
        # Регрессия: раньше «2025/2026» разбирался как 2025/2020, и январские
        # матчи получали 2020 год.
        self.assertEqual(parse_season_label("2025/2026"), (2025, 2026))
        iso, _ = parse_game_datetime(
            "6 января, вторник | 10:00", "Вт, 06.01, 10:00", season_start=2025, season_end=2026
        )
        self.assertEqual(iso, "2026-01-06")


class TournamentNameTests(unittest.TestCase):
    def test_age_and_format(self) -> None:
        name = "2016 г.р. 26/27 (формат 4х4)"
        self.assertEqual(parse_age_year(name), 2016)
        self.assertEqual(parse_format(name), "4×4")

    def test_no_format(self) -> None:
        self.assertIsNone(parse_format("Кубок 2016 г.р. 25/26"))


class ProtocolTests(unittest.TestCase):
    HTML = """
    <html><head><title>Созвездие 2016 - Центр 2016</title></head><body>
      <h1>Кубок г. Москвы 2016 г.р. 26/27 (формат 4х4)</h1>
      <div class="match-scores"><div class="row team"><a class="name h3">Созвездие 2016</a></div>
        <div class="row team"><a class="name h3">Центр 2016</a></div>
        <div class="row scores"><div class="scores-table">
          <div class="score-team"><p class="h2">13</p></div>
          <div class="score-team"><p class="h2">18</p></div>
        </div>
        <ul class="period"><li aria-label="1 период">5:3</li><li aria-label="2 период">2:7</li>
        <li aria-label="3 период">6:8</li></ul></div></div>
      <p class="match-date"><time datetime="2026-10-31T09:45:00+03:00">31 октября</time></p>
      <p class="match-place">Москва, стадион «ЛЦ Созвездие»</p>
      <section class="events__period"><h3 class="events__period-title">1 период</h3>
        <div class="events__period-list">
          <div class="events__row events__row--goal"><div class="timestamp">05:12</div>
            <div class="events__team">Созвездие 2016</div>
            <span class="events__player"><span class="events__number">№ 95</span>
              <a href="/player/12113">Кияненко Сергей</a></span>
            <span class="events__goal-label">Гол</span>
            <div class="events__count" aria-label="Счёт 1 : 0"><span>1</span>:<span>0</span></div>
          </div>
        </div>
      </section>
    </body></html>
    """

    def test_parse(self) -> None:
        game = parse_game_page(self.HTML, match_id=1)
        self.assertEqual(game.home_name, "Созвездие 2016")
        self.assertEqual(game.away_name, "Центр 2016")
        self.assertEqual((game.home_goals, game.away_goals), (13, 18))
        self.assertEqual(game.periods, [(1, 5, 3), (2, 2, 7), (3, 6, 8)])
        self.assertEqual(game.date_iso, "2026-10-31")
        self.assertEqual(game.time, "09:45")
        self.assertEqual(len(game.events), 1)
        self.assertEqual(game.events[0].player_id, 12113)
        self.assertEqual(game.goals_by_player, {12113: 1})


class NormalizeGameTests(unittest.TestCase):
    def test_normalizes_scores(self) -> None:
        item = {
            "id": 22449,
            "date": "Сб, 31.10, 09:45",
            "displayDate": "31 октября, суббота | 09:45",
            "status": 2,
            "tournament": "2016 г.р. 26/27 (формат 4х4)",
            "group": "Группа В",
            "tour": "9 тур",
            "url": "/game/22449",
            "team1": {"name": "Созвездие 2016", "score": 13},
            "team2": {"name": "Центр 2016", "score": 18},
        }
        game = normalize_game(
            item, season=5, tournament_id=51, stage_id=1, group_id=2, season_start=2026, season_end=2027
        )
        assert game is not None
        self.assertEqual(game.date_iso, "2026-10-31")
        self.assertEqual(game.home_goals, 13)
        self.assertTrue(game.played)


if __name__ == "__main__":
    unittest.main()
