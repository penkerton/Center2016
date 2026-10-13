import test from "node:test";
import assert from "node:assert/strict";

import { computeStandings, teamMetrics } from "../js/lib/standings.js";

const teams = [
  { id: 1, name: "А" },
  { id: 2, name: "Б" },
  { id: 3, name: "В" },
  { id: 4, name: "Г" },
];

const played = (home, away, homeGoals, awayGoals) => ({ home, away, homeGoals, awayGoals, hasScore: true });

const matches = [
  played("А", "Б", 5, 2),
  played("В", "Г", 3, 3),
  played("А", "В", 1, 4),
  played("Б", "Г", 2, 2),
];

test("таблица считается по регламенту: 2 очка за победу, 1 за ничью", () => {
  const rows = computeStandings(teams, matches);
  const byName = Object.fromEntries(rows.map((row) => [row.name, row]));

  assert.deepEqual(
    [byName["А"].games, byName["А"].wins, byName["А"].losses, byName["А"].points, byName["А"].diff],
    [2, 1, 1, 2, 0],
  );
  assert.deepEqual(
    [byName["В"].games, byName["В"].wins, byName["В"].draws, byName["В"].points, byName["В"].diff],
    [2, 1, 1, 3, 3],
  );
  assert.equal(byName["Б"].points, 1);
  assert.equal(byName["Г"].points, 2);
});

test("порядок: очки → разница → заброшенные шайбы", () => {
  const rows = computeStandings(teams, matches);
  assert.deepEqual(
    rows.map((row) => row.name),
    ["В", "А", "Г", "Б"],
  );
});

test("команды без игр попадают в таблицу с нулями", () => {
  const rows = computeStandings([...teams, { id: 5, name: "Д" }], matches);
  const last = rows.find((row) => row.name === "Д");
  assert.equal(last.games, 0);
  assert.equal(last.points, 0);
  assert.equal(rows.length, 5);
});

test("матчи без счёта не влияют на таблицу", () => {
  const rows = computeStandings(teams, [...matches, { home: "А", away: "Г", homeGoals: null, awayGoals: null, hasScore: false }]);
  const teamA = rows.find((row) => row.name === "А");
  assert.equal(teamA.games, 2);
});

test("показатели команды для обзора сезона", () => {
  const rows = computeStandings(teams, matches);
  const metrics = teamMetrics(rows, "А");

  assert.equal(metrics.place, 2);
  assert.equal(metrics.total, 4);
  assert.equal(metrics.points, 2);
  assert.equal(metrics.diffRank, 2);
  assert.equal(metrics.ppgRank, 2);
  assert.deepEqual(metrics.tiedTeams, ["Г"]);
  assert.equal(teamMetrics(rows, "Нет такой"), null);
});
