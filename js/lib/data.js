/**
 * Единственное место, где читаются данные, выгруженные скриптом ФХМ:
 * window.siteData, window.playerGoalsData, window.tournamentMatchesData.
 *
 * Нормализация имён команд выполняется на стороне выгрузки (update_fhm_2016_stats.mjs),
 * поэтому страница работает с уже готовыми значениями.
 */

import { parseMoscowDateTime, parseRuDate } from "./format.js";

export const ROLE_LABELS = {
  В: { short: "Вр", full: "Вратарь" },
  З: { short: "Защ", full: "Защитник" },
  Н: { short: "Нап", full: "Нападающий" },
};

export function roleLabel(role) {
  return ROLE_LABELS[String(role ?? "").trim()] ?? null;
}

function normalizePlayer(item) {
  const player = String(item?.player ?? "").trim();
  const team = String(item?.team ?? "").trim();
  if (!player || !team) {
    return null;
  }
  return {
    player,
    group: String(item?.group ?? "").trim(),
    team,
    role: String(item?.role ?? "").trim(),
    games: Number.isFinite(Number(item?.games)) ? Number(item.games) : 0,
    goals: Number.isFinite(Number(item?.goals)) ? Number(item.goals) : 0,
  };
}

function normalizeMatch(item) {
  const home = String(item?.homeTeam ?? "").trim();
  const away = String(item?.awayTeam ?? "").trim();
  const date = String(item?.date ?? "").trim();
  const datetime = parseMoscowDateTime(date, item?.time);
  if (!home || !away || !datetime) {
    return null;
  }

  const homeGoals = item?.homeGoals === null || item?.homeGoals === undefined ? null : Number(item.homeGoals);
  const awayGoals = item?.awayGoals === null || item?.awayGoals === undefined ? null : Number(item.awayGoals);
  const hasScore = Number.isFinite(homeGoals) && Number.isFinite(awayGoals);

  return {
    id: Number(item?.id ?? 0),
    home,
    away,
    homeGoals: hasScore ? homeGoals : null,
    awayGoals: hasScore ? awayGoals : null,
    hasScore,
    date,
    time: String(item?.time ?? ""),
    hasTime: /^\d{2}:\d{2}$/.test(String(item?.time ?? "")),
    datetime,
    groupId: Number(item?.groupId ?? 0),
    tournamentId: Number(item?.tournamentId ?? 0),
    group: String(item?.group ?? ""),
    tour: String(item?.tour ?? ""),
    tournament: String(item?.tournament ?? ""),
  };
}

function normalizeRosterEntry(item) {
  const player = String(item?.player ?? "").trim();
  if (!player) {
    return null;
  }
  const number = Number(item?.number);
  return {
    player,
    role: String(item?.role ?? "").trim(),
    number: Number.isInteger(number) ? number : null,
    birth: parseRuDate(item?.dateOfBirth),
    birthdayRaw: String(item?.dateOfBirth ?? "").trim(),
  };
}

/**
 * Собирает модель страницы из выгруженных файлов.
 * Отсутствующие данные не ломают инициализацию — модули показывают пустые состояния.
 */
export function readSiteData() {
  const meta = window.siteData && typeof window.siteData === "object" ? window.siteData : null;
  const competitions = Array.isArray(meta?.competitions) ? meta.competitions : [];
  const primary = competitions.find((competition) => competition?.own) ?? competitions[0] ?? null;
  const ownTeamName = String(meta?.ownTeam?.name ?? "").trim();

  const players = (Array.isArray(window.playerGoalsData) ? window.playerGoalsData : [])
    .map(normalizePlayer)
    .filter(Boolean);
  const matches = (Array.isArray(window.tournamentMatchesData) ? window.tournamentMatchesData : [])
    .map(normalizeMatch)
    .filter(Boolean)
    .sort((a, b) => a.datetime - b.datetime);
  const roster = (Array.isArray(meta?.roster) ? meta.roster : []).map(normalizeRosterEntry).filter(Boolean);

  const ownMatches = ownTeamName ? matches.filter((match) => match.home === ownTeamName || match.away === ownTeamName) : [];
  const groupMatches = primary ? matches.filter((match) => match.groupId === Number(primary.groupId)) : [];

  return {
    meta,
    primary,
    ownTeamName,
    competitions,
    players,
    matches,
    ownMatches,
    groupMatches,
    roster,
    ready: Boolean(meta && ownTeamName && players.length),
  };
}
