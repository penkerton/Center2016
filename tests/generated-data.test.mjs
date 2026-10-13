import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readSiteData } from "../js/lib/data.js";
import { computeStandings, teamMetrics } from "../js/lib/standings.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function readPayload(file, prefix) {
  const content = fs.readFileSync(path.join(root, file), "utf8");
  assert.ok(content.startsWith(prefix), `${file}: ожидалось начало «${prefix}»`);
  return JSON.parse(content.slice(prefix.length).replace(/;\s*$/, ""));
}

const siteData = readPayload("site_data.js", "window.siteData =");
const playerGoalsData = readPayload("all_2016_players_season5.js", "window.playerGoalsData =");
const tournamentMatchesData = readPayload("all_2016_matches_season5.js", "window.tournamentMatchesData =");

test("статистика игроков: поля и амплуа", () => {
  assert.ok(playerGoalsData.length > 0, "нет строк статистики");
  for (const row of playerGoalsData) {
    assert.equal(typeof row.player, "string");
    assert.ok(row.player.length > 0, "пустое имя игрока");
    assert.ok(row.team.length > 0, `нет команды у игрока ${row.player}`);
    assert.ok(["", "В", "З", "Н"].includes(row.role), `неизвестное амплуа «${row.role}»`);
    assert.ok(Number.isInteger(row.games) && row.games >= 0);
    assert.ok(Number.isInteger(row.goals) && row.goals >= 0);
  }
});

test("матчи: дата, счёт и привязка к группе", () => {
  assert.ok(tournamentMatchesData.length > 0, "нет матчей");
  for (const match of tournamentMatchesData) {
    assert.match(match.date, /^\d{4}-\d{2}-\d{2}$/, `подозрительная дата: ${match.date}`);
    assert.ok(Number(match.groupId) > 0, `у матча ${match.id} не указана группа`);
    for (const goals of [match.homeGoals, match.awayGoals]) {
      assert.ok(goals === null || Number.isInteger(goals), `некорректный счёт у матча ${match.id}`);
    }
  }
});

test("мета: сезон, своя команда и группы", () => {
  assert.match(siteData.generatedAt, /^\d{4}-\d{2}-\d{2}T/, "generatedAt должен быть ISO-временем");
  assert.ok(siteData.ownTeam?.name, "не указана своя команда");
  assert.ok(Number.isInteger(siteData.ownTeam.id) && siteData.ownTeam.id > 0);
  assert.ok(siteData.season?.label && siteData.season.format && siteData.season.yearLabel);
  assert.ok(siteData.competitions.length > 0, "нет описания групп");

  const ownCompetitions = siteData.competitions.filter((competition) => competition.own);
  assert.equal(ownCompetitions.length, 1, "ровно одна группа должна быть помечена как своя");
  assert.ok(ownCompetitions[0].teams.some((team) => team.name === siteData.ownTeam.name));

  for (const competition of siteData.competitions) {
    assert.ok(competition.teams.length > 0, `пустая группа ${competition.groupName}`);
    assert.ok(competition.groupId > 0 && competition.tournamentId > 0);
  }
});

test("состав команды пригоден для дней рождения", () => {
  assert.ok(siteData.roster.length > 0, "пустой состав");
  const withBirthday = siteData.roster.filter((entry) => /^\d{2}\.\d{2}\.\d{4}$/.test(entry.dateOfBirth));
  assert.equal(withBirthday.length, siteData.roster.length, "у части состава нет даты рождения");
  for (const entry of siteData.roster) {
    assert.ok(["", "В", "З", "Н"].includes(entry.role));
  }
});

test("модель страницы и таблица сходятся с выгруженными данными", () => {
  globalThis.window = { siteData, playerGoalsData, tournamentMatchesData };
  const data = readSiteData();

  assert.equal(data.ready, true);
  assert.ok(data.primary?.own, "не найдена своя группа");
  assert.ok(data.ownMatches.length > 0, "нет матчей своей команды");
  assert.ok(data.groupMatches.length > 0, "нет матчей группы");

  const rows = computeStandings(data.primary.teams, data.groupMatches);
  assert.equal(rows.length, data.primary.teams.length, "в таблице должны быть все команды группы");

  const playedMatches = data.groupMatches.filter((match) => match.hasScore).length;
  const totalGames = rows.reduce((sum, row) => sum + row.games, 0);
  assert.equal(totalGames, playedMatches * 2, "каждый сыгранный матч учитывается у двух команд");

  const metrics = teamMetrics(rows, data.ownTeamName);
  assert.ok(metrics, "не посчитаны показатели своей команды");
  assert.ok(metrics.place >= 1 && metrics.place <= rows.length);
  assert.ok(metrics.diffRank >= 1 && metrics.diffRank <= rows.length);
  assert.ok(metrics.ppgRank >= 1 && metrics.ppgRank <= rows.length);

  const ownRow = rows.find((row) => row.name === data.ownTeamName);
  const ownPlayed = data.groupMatches.filter(
    (match) => match.hasScore && (match.home === data.ownTeamName || match.away === data.ownTeamName),
  ).length;
  assert.equal(ownRow.games, ownPlayed, "число игр своей команды не совпадает с матчами");
});
