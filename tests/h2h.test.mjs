import test from "node:test";
import assert from "node:assert/strict";

import { buildH2hLookup, h2hResult } from "../js/lib/h2h.js";

const teams = ["А", "Б", "В"];
const matches = [
  { home: "А", away: "Б", homeGoals: 3, awayGoals: 1, hasScore: true, date: "2026-09-01" },
  { home: "В", away: "А", homeGoals: 2, awayGoals: 2, hasScore: true, date: "2026-09-02" },
];

test("результат считается с точки зрения строки матрицы", () => {
  const lookup = buildH2hLookup(matches, teams);
  assert.deepEqual(h2hResult(lookup, "А", "Б"), {
    kind: "played",
    state: "win",
    goalsFor: 3,
    goalsAgainst: 1,
    score: "3:1",
  });
  assert.equal(h2hResult(lookup, "Б", "А").state, "loss");
  assert.equal(h2hResult(lookup, "Б", "А").score, "1:3");
  assert.equal(h2hResult(lookup, "А", "В").state, "draw");
  assert.equal(h2hResult(lookup, "А", "В").score, "2:2");
});

test("диагональ и несыгранные пары", () => {
  const lookup = buildH2hLookup(matches, teams);
  assert.deepEqual(h2hResult(lookup, "А", "А"), { kind: "self" });
  assert.deepEqual(h2hResult(lookup, "Б", "В"), { kind: "empty" });
});

test("чужие команды и матчи без счёта в матрицу не попадают", () => {
  const lookup = buildH2hLookup(
    [...matches, { home: "А", away: "Чужая", homeGoals: 1, awayGoals: 0, hasScore: true, date: "2026-09-03" },
      { home: "Б", away: "В", homeGoals: null, awayGoals: null, hasScore: false, date: "2026-09-04" }],
    teams,
  );
  assert.deepEqual(h2hResult(lookup, "А", "Чужая"), { kind: "empty" });
  assert.deepEqual(h2hResult(lookup, "Б", "В"), { kind: "empty" });
});
