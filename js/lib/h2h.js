/** Матрица очных встреч: чистые функции без обращения к DOM. */

/**
 * @param {Array} matches матчи группы (уже отсортированы по дате)
 * @param {Array<string>} teamNames команды, которые попадут в матрицу
 */
export function buildH2hLookup(matches, teamNames) {
  const known = new Set(teamNames);
  const lookup = new Map();

  for (const match of Array.isArray(matches) ? matches : []) {
    if (!match?.hasScore) {
      continue;
    }
    const home = String(match.home ?? "");
    const away = String(match.away ?? "");
    if (!known.has(home) || !known.has(away)) {
      continue;
    }
    const key = `${home}::${away}`;
    if (lookup.has(key)) {
      continue;
    }
    lookup.set(key, {
      home,
      away,
      homeGoals: match.homeGoals,
      awayGoals: match.awayGoals,
      date: String(match.date ?? ""),
    });
  }

  return lookup;
}

/**
 * Результат встречи «строка против столбца» с точки зрения строки.
 * @returns {{kind:"self"}|{kind:"empty"}|{kind:"played",state:"win"|"loss"|"draw",score:string,goalsFor:number,goalsAgainst:number}}
 */
export function h2hResult(lookup, rowTeam, colTeam) {
  if (rowTeam === colTeam) {
    return { kind: "self" };
  }

  const direct = lookup.get(`${rowTeam}::${colTeam}`);
  const reverse = lookup.get(`${colTeam}::${rowTeam}`);
  if (!direct && !reverse) {
    return { kind: "empty" };
  }

  const goalsFor = direct ? direct.homeGoals : reverse.awayGoals;
  const goalsAgainst = direct ? direct.awayGoals : reverse.homeGoals;
  const state = goalsFor > goalsAgainst ? "win" : goalsFor < goalsAgainst ? "loss" : "draw";

  return {
    kind: "played",
    state,
    goalsFor,
    goalsAgainst,
    score: `${goalsFor}:${goalsAgainst}`,
  };
}
