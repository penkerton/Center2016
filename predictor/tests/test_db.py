"""Тесты базы: схема, идемпотентность upsert, отсутствие дублей."""

from __future__ import annotations

import sqlite3
import unittest

from fhm_predictor import db


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        db.init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_schema_created(self) -> None:
        tables = {
            row["name"]
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        for expected in (
            "matches",
            "players",
            "player_match_statistics",
            "player_team_history",
            "predictions",
            "model_versions",
            "collection_runs",
            "data_quality_issues",
        ):
            self.assertIn(expected, tables)

    def test_upsert_is_idempotent(self) -> None:
        team = {"id": 1, "name": "Центр 2016", "short_name": "Центр", "age_year": 2016, "club": "Центр"}
        db.upsert(self.conn, "teams", [team], ["id"])
        db.upsert(self.conn, "teams", [dict(team, name="Центр 2016 (обн.)")], ["id"])
        rows = self.conn.execute("SELECT * FROM teams").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Центр 2016 (обн.)")

    def test_match_unique(self) -> None:
        self.conn.executemany(
            "INSERT INTO seasons(id, label) VALUES(?, ?)", [(5, "2026/2027")]
        )
        self.conn.execute(
            "INSERT INTO tournaments(id, season_id, name) VALUES(1, 5, '2016 г.р. 26/27 (формат 4х4)')"
        )
        self.conn.execute("INSERT INTO stages(id, tournament_id, name) VALUES(1, 1, 'Групповой этап')")
        self.conn.execute("INSERT INTO tournament_groups(id, stage_id, tournament_id, name) VALUES(1, 1, 1, 'Группа В')")
        self.conn.executemany(
            "INSERT INTO teams(id, name) VALUES(?, ?)", [(1, "Созвездие 2016"), (2, "Центр 2016")]
        )
        row = {
            "id": 22449,
            "season_id": 5,
            "tournament_id": 1,
            "stage_id": 1,
            "group_id": 1,
            "date": "2026-10-31",
            "home_team_id": 1,
            "away_team_id": 2,
            "home_name": "Созвездие 2016",
            "away_name": "Центр 2016",
            "home_goals": 13,
            "away_goals": 18,
            "played": 1,
            "fetched_at": "2026-11-01T00:00:00+00:00",
            "updated_at": "2026-11-01T00:00:00+00:00",
        }
        db.upsert(self.conn, "matches", [row], ["id"])
        db.upsert(self.conn, "matches", [dict(row, home_goals=14)], ["id"])
        rows = self.conn.execute("SELECT * FROM matches").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["home_goals"], 14)


if __name__ == "__main__":
    unittest.main()
