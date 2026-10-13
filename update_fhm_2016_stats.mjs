#!/usr/bin/env node

/*
 * Выгрузка данных ФХМ для сайта команды «Центр» (2016 г.р.).
 *
 * Скрипт формирует три файла, которые лежат рядом с index.html и подключаются
 * к странице как обычные скрипты:
 *
 *   all_2016_players_season5.js  → window.playerGoalsData      (статистика игроков турниров)
 *   all_2016_matches_season5.js  → window.tournamentMatchesData (матчи групп)
 *   site_data.js                 → window.siteData              (мета: сезон, группы, состав, время выгрузки)
 *
 * Страница не содержит собственных данных: таблица, плитки обзора, ближайший
 * матч, матрица встреч и дни рождения собираются из этих файлов.
 *
 * Идентификаторы турниров, групп и команды «Центр» в системе ФХМ зафиксированы
 * в константах ниже (см. UPDATE_STATS.md, раздел «Идентификаторы ФХМ»).
 */

import fs from "node:fs/promises";
import path from "node:path";

const OUTPUT_FILE_DEFAULT = "all_2016_players_season5.js";
const OUTPUT_MATCHES_FILE_DEFAULT = "all_2016_matches_season5.js";
const OUTPUT_META_FILE_DEFAULT = "site_data.js";
const FETCH_TIMEOUT_MS = 12000;
const MIN_VALID_ROWS = 20;
const MIN_VALID_RATIO = 0.6;

/* Идентификаторы ФХМ. Меняются при смене сезона/регламента — см. документацию. */
const TARGET_TOURNAMENT_GROUPS = [
  // «2016 г.р. 26/27 (формат 4х4)»: Группа Б и Группа В (в Группе В играет «Центр»)
  { tournamentId: 51, groupIds: [312, 315] },
  // «2016 г.р. 26/27 (формат 5х5)»: Группа А
  { tournamentId: 48, groupIds: [309] },
];
const OWN_TEAM_ID_DEFAULT = 604; // «Центр 2016»
const SOURCE_SITE = "https://fhmoscow.com";

function parseArgs(argv) {
  const options = {
    seasonId: 5,
    delayMs: 120,
    ownTeamId: OWN_TEAM_ID_DEFAULT,
    outputJs: OUTPUT_FILE_DEFAULT,
    outputMatchesJs: OUTPUT_MATCHES_FILE_DEFAULT,
    outputMetaJs: OUTPUT_META_FILE_DEFAULT,
  };

  const readValue = (flag, index) => {
    const next = argv[index + 1];
    if (next === undefined || next.startsWith("--")) {
      throw new Error(`${flag} requires a value`);
    }
    return next;
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--seasonId") {
      options.seasonId = Number.parseInt(readValue(arg, i), 10);
      i += 1;
      continue;
    }
    if (arg === "--delayMs") {
      options.delayMs = Number.parseInt(readValue(arg, i), 10);
      i += 1;
      continue;
    }
    if (arg === "--ownTeamId") {
      options.ownTeamId = Number.parseInt(readValue(arg, i), 10);
      i += 1;
      continue;
    }
    if (arg === "--outputJs") {
      options.outputJs = readValue(arg, i);
      i += 1;
      continue;
    }
    if (arg === "--outputMatchesJs") {
      options.outputMatchesJs = readValue(arg, i);
      i += 1;
      continue;
    }
    if (arg === "--outputMetaJs") {
      options.outputMetaJs = readValue(arg, i);
      i += 1;
      continue;
    }
    if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    }

    throw new Error(`Unknown argument: ${arg}`);
  }

  if (!Number.isInteger(options.seasonId) || options.seasonId <= 0) {
    throw new Error("seasonId must be a positive integer");
  }
  if (!Number.isInteger(options.delayMs) || options.delayMs < 0) {
    throw new Error("delayMs must be a non-negative integer");
  }
  if (!Number.isInteger(options.ownTeamId) || options.ownTeamId <= 0) {
    throw new Error("ownTeamId must be a positive integer");
  }

  resolveSafeOutputPath(options.outputJs);
  resolveSafeOutputPath(options.outputMatchesJs);
  resolveSafeOutputPath(options.outputMetaJs);

  return options;
}

function printHelp() {
  console.log("Usage: node update_fhm_2016_stats.mjs [options]");
  console.log("");
  console.log("Options:");
  console.log("  --seasonId <number>        Season id (default: 5)");
  console.log("  --delayMs <number>         Delay between requests in ms (default: 120)");
  console.log("  --ownTeamId <number>       FHМ team id of «Центр» (default: 604)");
  console.log("  --outputJs <path>          Players output path");
  console.log("  --outputMatchesJs <path>   Matches output path");
  console.log("  --outputMetaJs <path>      Site meta output path");
}

async function sleep(ms) {
  if (ms <= 0) {
    return;
  }
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function toArray(value) {
  if (value === null || value === undefined) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

async function fetchWithRetry(url, init, retries = 3) {
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      const response = await fetch(url, {
        ...init,
        signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      if (attempt >= retries) {
        throw error;
      }
      await sleep(350 * attempt);
    }
  }

  throw new Error("Unreachable");
}

function invokeFhmPost(uri, body, retries = 3) {
  return fetchWithRetry(
    uri,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    },
    retries,
  );
}

function invokeFhmGet(uri, retries = 3) {
  return fetchWithRetry(
    uri,
    {
      method: "GET",
    },
    retries,
  );
}

const TEAM_YEAR_SUFFIX = /\s*2016$/;

/** «Центр 2016» → «Центр»: единая нормализация имён команд для страницы. */
function normalizeTeamName(value) {
  return String(value ?? "").replace(TEAM_YEAR_SUFFIX, "").trim();
}

/** «2016 г.р. 26/27 (формат 4х4)» → подписи для интерфейса. */
function parseTournamentTitle(value) {
  const title = String(value ?? "");
  const year = title.match(/(\d{4})\s*г\.р\./);
  const code = title.match(/(\d{2})\s*\/\s*(\d{2})/);
  const format = title.match(/формат\s*(\d+)\s*[хx×]\s*(\d+)/i);

  return {
    yearLabel: year ? `${year[1]} г.р.` : "",
    code: code ? `${code[1]}/${code[2]}` : "",
    label: code ? `${2000 + Number(code[1])}/${2000 + Number(code[2])}` : "",
    format: format ? `${format[1]}×${format[2]}` : "",
  };
}

function extractPlayerRows(players, groupName, teamName) {
  const rows = [];

  for (const player of players) {
    const statistics = player?.statistics ?? null;
    const games = Number.isFinite(Number(statistics?.gamesCount)) ? Number(statistics.gamesCount) : 0;
    const goals = Number.isFinite(Number(statistics?.totalGoals)) ? Number(statistics.totalGoals) : 0;

    rows.push({
      player: String(player?.fullName ?? ""),
      group: groupName,
      team: teamName,
      role: String(player?.role ?? "").trim(),
      games,
      goals,
    });
  }

  return rows;
}

function extractRosterEntry(player) {
  const number = Number(player?.number);
  return {
    player: String(player?.fullName ?? "").trim(),
    role: String(player?.role ?? "").trim(),
    number: Number.isInteger(number) ? number : null,
    dateOfBirth: String(player?.dateOfBirth ?? "").trim(),
  };
}

function validateRows(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return false;
  }

  for (const row of rows) {
    if (typeof row !== "object" || row === null) {
      return false;
    }
    if (
      typeof row.player !== "string" ||
      typeof row.group !== "string" ||
      typeof row.team !== "string" ||
      typeof row.role !== "string"
    ) {
      return false;
    }
    if (!Number.isInteger(row.games) || !Number.isInteger(row.goals)) {
      return false;
    }
  }

  return true;
}

function resolveSafeOutputPath(outputPath) {
  const rootPath = path.resolve(process.cwd());
  const resolvedPath = path.resolve(outputPath);
  const relative = path.relative(rootPath, resolvedPath);

  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Refusing to write outside workspace: ${outputPath}`);
  }
  if (path.extname(resolvedPath).toLowerCase() !== ".js") {
    throw new Error("output path must point to a .js file");
  }

  return resolvedPath;
}

function sanitizeRows(rows) {
  const cleaned = [];
  let dropped = 0;

  for (const row of rows) {
    const player = String(row?.player ?? "").trim();
    const group = String(row?.group ?? "").trim();
    const team = String(row?.team ?? "").trim();
    const role = String(row?.role ?? "").trim();
    const games = Number(row?.games);
    const goals = Number(row?.goals);

    const isValid =
      player.length > 0 &&
      player.length <= 200 &&
      group.length > 0 &&
      group.length <= 120 &&
      team.length > 0 &&
      team.length <= 120 &&
      role.length <= 4 &&
      Number.isInteger(games) &&
      Number.isInteger(goals) &&
      games >= 0 &&
      games <= 200 &&
      goals >= 0 &&
      goals <= 1000;

    if (!isValid) {
      dropped += 1;
      continue;
    }

    cleaned.push({ player, group, team, role, games, goals });
  }

  const validRatio = rows.length > 0 ? cleaned.length / rows.length : 0;
  if (dropped > 0) {
    console.warn(`Dropped invalid rows: ${dropped}/${rows.length}`);
  }
  if (cleaned.length < MIN_VALID_ROWS || validRatio < MIN_VALID_RATIO) {
    throw new Error(
      `Refusing to overwrite output file: valid rows ${cleaned.length}/${rows.length} are below threshold`,
    );
  }

  return cleaned;
}

function parseSeasonYearsFromTitle(value) {
  const match = String(value ?? "").match(/\b(\d{2})\s*\/\s*(\d{2})\b/);
  if (!match) {
    throw new Error(`Cannot parse season years from tournament title: ${value}`);
  }

  return { startYear: 2000 + Number(match[1]), endYear: 2000 + Number(match[2]) };
}

function toIsoDate(rawDate, seasonYears) {
  const text = String(rawDate ?? "");
  const match = text.match(/(\d{2})\.(\d{2})/);
  if (!match) {
    return "";
  }

  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = month >= 7 ? seasonYears.startYear : seasonYears.endYear;

  const mm = String(month).padStart(2, "0");
  const dd = String(day).padStart(2, "0");
  return `${year}-${mm}-${dd}`;
}

function toClockTime(rawDate) {
  const text = String(rawDate ?? "");
  const match = text.match(/(\d{2}:\d{2})$/);
  if (!match) {
    return "";
  }
  return match[1] === "00:00" ? "" : match[1];
}

function toGoals(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

/** Приводит матчи к плоскому виду, понятному странице. */
function normalizeMatchRows(matches) {
  const cleaned = [];

  for (const match of matches) {
    const homeTeam = normalizeTeamName(match?.team1?.name ?? "");
    const awayTeam = normalizeTeamName(match?.team2?.name ?? "");
    const date = String(match?.dateIso ?? "");

    if (!homeTeam || !awayTeam || !date) {
      continue;
    }

    cleaned.push({
      id: Number(match?.id ?? 0),
      homeTeam,
      awayTeam,
      homeGoals: toGoals(match?.team1?.score),
      awayGoals: toGoals(match?.team2?.score),
      date,
      time: String(match?.time ?? ""),
      groupId: Number(match?.groupId ?? 0),
      tournamentId: Number(match?.tournamentId ?? 0),
      group: String(match?.group ?? ""),
      tour: String(match?.tour ?? ""),
      tournament: String(match?.tournament ?? ""),
      status: Number(match?.status ?? 0),
    });
  }

  const uniqueById = new Map();
  cleaned.forEach((row) => {
    if (!uniqueById.has(row.id)) {
      uniqueById.set(row.id, row);
    }
  });

  const deduped = [...uniqueById.values()];
  deduped.sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
  return deduped;
}

async function writeIfChanged(filePath, content) {
  let previous = null;
  try {
    previous = await fs.readFile(filePath, "utf8");
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
  }

  if (previous === content) {
    return false;
  }

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, content, "utf8");
  return true;
}

async function readGeneratedAt(filePath) {
  try {
    const content = await fs.readFile(filePath, "utf8");
    const match = content.match(/"generatedAt":\s*"([^"]+)"/);
    return match ? match[1] : null;
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
    return null;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));

  const tournaments = toArray(
    await invokeFhmPost(`${SOURCE_SITE}/api/filter/tournament`, {
      season: options.seasonId,
    }),
  );

  const teams = [];
  const competitions = [];

  for (const target of TARGET_TOURNAMENT_GROUPS) {
    const tournamentId = Number(target.tournamentId);
    const tournament = tournaments.find((item) => Number(item?.id) === tournamentId);

    if (!tournament) {
      throw new Error(`Tournament ${tournamentId} not found in season ${options.seasonId}`);
    }

    const stages = toArray(
      await invokeFhmPost(`${SOURCE_SITE}/api/filter/stage`, {
        tournament: tournamentId,
      }),
    );

    let stage = stages.find((item) => item?.current === true);
    if (!stage) {
      stage = stages.find((item) => item?.transition !== true);
    }

    if (!stage) {
      throw new Error(`No stage found for tournament ${tournamentId} (${String(tournament?.name ?? "")})`);
    }

    const groups = toArray(
      await invokeFhmPost(`${SOURCE_SITE}/api/filter/group`, {
        stage: Number(stage.id),
      }),
    );

    for (const groupId of target.groupIds) {
      const group = groups.find((item) => Number(item?.id) === Number(groupId));
      if (!group) {
        throw new Error(`Group ${groupId} not found in tournament ${tournamentId} (${String(tournament?.name ?? "")})`);
      }

      const groupTeams = toArray(
        await invokeFhmPost(`${SOURCE_SITE}/api/filter/team`, {
          group: Number(group.id),
        }),
      );

      const competition = {
        tournamentId,
        tournamentName: String(tournament?.name ?? ""),
        stageId: Number(stage.id),
        stageName: String(stage?.name ?? ""),
        groupId: Number(group.id),
        groupName: String(group?.name ?? ""),
        ...parseTournamentTitle(tournament?.name),
        own: false,
        teams: groupTeams.map((team) => ({
          id: Number(team?.id),
          name: normalizeTeamName(team?.shortName || team?.name || ""),
        })),
      };

      if (competition.teams.some((team) => team.id === options.ownTeamId)) {
        competition.own = true;
      }

      competitions.push(competition);

      for (const team of groupTeams) {
        teams.push({
          id: Number(team?.id),
          shortName: team && Object.hasOwn(team, "shortName") ? String(team.shortName ?? "") : "",
          name: team && Object.hasOwn(team, "name") ? String(team.name ?? "") : "",
          groupName: competition.groupName,
          tournament: competition.tournamentName,
        });
      }
    }
  }

  const primaryCompetition = competitions.find((competition) => competition.own);
  if (!primaryCompetition) {
    throw new Error(`Own team ${options.ownTeamId} not found in target groups`);
  }

  const uniqueTeams = [...new Map(teams.map((team) => [team.id, team])).values()];
  const rows = [];
  let roster = [];
  let emptyRosters = 0;

  for (let index = 0; index < uniqueTeams.length; index += 1) {
    const team = uniqueTeams[index];
    const teamId = Number(team.id);
    const teamNameRaw = String(team.shortName || "").trim() === "" ? String(team.name ?? "") : String(team.shortName ?? "");
    const teamName = normalizeTeamName(teamNameRaw);
    const groupName = String(team.groupName ?? "");

    console.log(`[${index + 1}/${uniqueTeams.length}] ${teamName} [${groupName}]`);

    const rosterResponse = await invokeFhmGet(
      `${SOURCE_SITE}/api/team/${teamId}/player?season=${options.seasonId}`,
    );

    const players = Array.isArray(rosterResponse) ? rosterResponse : toArray(rosterResponse?.value);
    if (!players.length) {
      emptyRosters += 1;
      console.warn(`  ! empty roster for team ${teamId} (${teamName})`);
    }

    rows.push(...extractPlayerRows(players, groupName, teamName));

    if (teamId === options.ownTeamId) {
      roster = players
        .map(extractRosterEntry)
        .filter((entry) => entry.player.length > 0)
        .sort((a, b) => a.player.localeCompare(b.player, "ru"));
    }

    if (options.delayMs > 0) {
      await sleep(options.delayMs);
    }
  }

  rows.sort((a, b) => {
    if (b.goals !== a.goals) {
      return b.goals - a.goals;
    }
    if (b.games !== a.games) {
      return b.games - a.games;
    }
    return a.player.localeCompare(b.player, "ru");
  });

  if (!validateRows(rows)) {
    throw new Error("Refusing to overwrite output file: API result is empty or invalid.");
  }

  const sanitizedRows = sanitizeRows(rows);

  if (!roster.length) {
    throw new Error(`Refusing to overwrite output file: roster of team ${options.ownTeamId} is empty.`);
  }

  const allMatchItems = [];

  for (const competition of competitions) {
    const tours = toArray(
      await invokeFhmPost(`${SOURCE_SITE}/api/filter/tour`, {
        season: options.seasonId,
        tournament: competition.tournamentId,
        stage: competition.stageId,
        group: competition.groupId,
      }),
    );

    const seasonYears = parseSeasonYearsFromTitle(competition.tournamentName);

    for (const tour of tours) {
      const response = await invokeFhmPost(`${SOURCE_SITE}/api/game/list`, {
        season: options.seasonId,
        tournament: competition.tournamentId,
        stage: competition.stageId,
        group: competition.groupId,
        tour: Number(tour.id),
      });

      const items = toArray(response?.items).map((item) => ({
        ...item,
        groupId: competition.groupId,
        tournamentId: competition.tournamentId,
        group: String(item?.group ?? competition.groupName),
        tournament: String(item?.tournament ?? competition.tournamentName),
        dateIso: toIsoDate(item?.date, seasonYears),
        time: toClockTime(item?.date),
      }));

      allMatchItems.push(...items);

      if (options.delayMs > 0) {
        await sleep(options.delayMs);
      }
    }
  }

  const normalizedMatchRows = normalizeMatchRows(allMatchItems);

  const playersPath = resolveSafeOutputPath(options.outputJs);
  const matchesPath = resolveSafeOutputPath(options.outputMatchesJs);
  const metaPath = resolveSafeOutputPath(options.outputMetaJs);

  const playersJs = `window.playerGoalsData = ${JSON.stringify(sanitizedRows, null, 2)};`;
  const matchesJs = `window.tournamentMatchesData = ${JSON.stringify(normalizedMatchRows, null, 2)};`;

  const buildMetaJs = (generatedAt) =>
    `window.siteData = ${JSON.stringify(
      {
        generatedAt,
        seasonId: options.seasonId,
        source: {
          label: "Федерация хоккея Москвы",
          site: SOURCE_SITE,
          teamUrl: `${SOURCE_SITE}/team/${options.ownTeamId}?season=${options.seasonId}`,
        },
        ownTeam: {
          id: options.ownTeamId,
          name: normalizeTeamName(
            primaryCompetition.teams.find((team) => team.id === options.ownTeamId)?.name ?? "",
          ),
        },
        season: {
          code: primaryCompetition.code,
          label: primaryCompetition.label,
          yearLabel: primaryCompetition.yearLabel,
          format: primaryCompetition.format,
          stage: primaryCompetition.stageName,
        },
        competitions,
        roster,
      },
      null,
      2,
    )};`;

  const [playersChanged, matchesChanged] = await Promise.all([
    writeIfChanged(playersPath, playersJs),
    writeIfChanged(matchesPath, matchesJs),
  ]);

  const generatedAtMarker = "__GENERATED_AT__";
  const previousGeneratedAt = await readGeneratedAt(metaPath);

  let previousMetaComparable = null;
  try {
    previousMetaComparable = (await fs.readFile(metaPath, "utf8")).replace(
      /"generatedAt":\s*"[^"]*"/,
      `"generatedAt": "${generatedAtMarker}"`,
    );
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
  }

  const nextMetaComparable = buildMetaJs(generatedAtMarker);
  const metaChanged = previousMetaComparable !== nextMetaComparable;

  let generatedAt = previousGeneratedAt;
  if (!generatedAt || playersChanged || matchesChanged || metaChanged) {
    generatedAt = new Date().toISOString();
  }

  const metaChangedWritten = await writeIfChanged(metaPath, buildMetaJs(generatedAt));

  console.log("");
  console.log(`Teams processed: ${uniqueTeams.length} (empty rosters: ${emptyRosters})`);
  console.log(`Player rows: ${sanitizedRows.length}`);
  console.log(`Matches rows: ${normalizedMatchRows.length}`);
  console.log(`Roster rows (own team): ${roster.length}`);
  console.log(`Groups: ${competitions.map((c) => `${c.groupName}/${c.teams.length}`).join(", ")}`);
  console.log(`Data generated at: ${generatedAt}`);
  console.log(
    `Changes: players=${playersChanged ? "yes" : "no"}, matches=${matchesChanged ? "yes" : "no"}, meta=${
      metaChangedWritten ? "yes" : "no"
    }`,
  );
  console.log(`JS:   ${playersPath}`);
  console.log(`JS matches: ${matchesPath}`);
  console.log(`JS meta: ${metaPath}`);
  console.log("");

  for (const row of sanitizedRows.slice(0, 5)) {
    console.log(
      `${row.player} | ${row.group} | ${row.team} | ${row.role || "—"} | games: ${row.games} | goals: ${row.goals}`,
    );
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
