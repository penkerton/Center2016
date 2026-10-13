/**
 * Турнирная таблица: считается из матчей, поэтому не может разойтись
 * с матрицей очных встреч — оба блока используют одни и те же данные.
 *
 * Регламент турниров 2016 г.р.: победа — 2 очка, ничья — 1, поражение — 0.
 */

export const POINTS_WIN = 2;
export const POINTS_DRAW = 1;

/**
 * @param {Array<{id:number,name:string}>} teams состав группы (может быть пустым)
 * @param {Array<{home:string,away:string,homeGoals:number|null,awayGoals:number|null,hasScore:boolean}>} matches матчи группы
 */
export function computeStandings(teams, matches) {
  const rows = new Map();
  const known = new Set();

  const ensure = (name) => {
    const key = String(name ?? "").trim();
    if (!key) {
      return null;
    }
    if (!rows.has(key)) {
      rows.set(key, {
        name: key,
        games: 0,
        wins: 0,
        draws: 0,
        losses: 0,
        goalsFor: 0,
        goalsAgainst: 0,
        diff: 0,
        points: 0,
        inRoster: known.has(key),
      });
    }
    return rows.get(key);
  };

  for (const team of Array.isArray(teams) ? teams : []) {
    const name = String(team?.name ?? "").trim();
    if (!name) {
      continue;
    }
    known.add(name);
    ensure(name);
  }

  for (const match of Array.isArray(matches) ? matches : []) {
    if (!match?.hasScore) {
      continue;
    }
    const home = ensure(match.home);
    const away = ensure(match.away);
    if (!home || !away) {
      continue;
    }

    home.games += 1;
    away.games += 1;
    home.goalsFor += match.homeGoals;
    home.goalsAgainst += match.awayGoals;
    away.goalsFor += match.awayGoals;
    away.goalsAgainst += match.homeGoals;

    if (match.homeGoals > match.awayGoals) {
      home.wins += 1;
      away.losses += 1;
      home.points += POINTS_WIN;
    } else if (match.homeGoals < match.awayGoals) {
      away.wins += 1;
      home.losses += 1;
      away.points += POINTS_WIN;
    } else {
      home.draws += 1;
      away.draws += 1;
      home.points += POINTS_DRAW;
      away.points += POINTS_DRAW;
    }
  }

  const list = [...rows.values()].map((row) => ({ ...row, diff: row.goalsFor - row.goalsAgainst }));
  list.forEach((row) => {
    row.pointsPerGame = row.games > 0 ? row.points / row.games : 0;
  });

  return sortStandings(list);
}

/** Официальный порядок: очки → разница шайб → заброшенные → имя. */
export function sortStandings(rows) {
  return [...rows].sort(
    (a, b) =>
      b.points - a.points || b.diff - a.diff || b.goalsFor - a.goalsFor || a.name.localeCompare(b.name, "ru"),
  );
}

/** Место команды в произвольной сортировке (1-based). */
function rankOf(rows, ownName, compare) {
  const sorted = [...rows].sort(compare);
  const index = sorted.findIndex((row) => row.name === ownName);
  return index === -1 ? 0 : index + 1;
}

/**
 * Показатели команды для блока «Обзор сезона».
 * Ранги считаются по тем же данным, что и таблица.
 */
export function teamMetrics(rows, ownName) {
  const sorted = sortStandings(rows);
  const own = sorted.find((row) => row.name === ownName);
  if (!own) {
    return null;
  }

  const tied = sorted.filter((row) => row.name !== own.name && row.points === own.points);

  return {
    ...own,
    place: sorted.indexOf(own) + 1,
    total: sorted.length,
    diffRank: rankOf(sorted, ownName, (a, b) => b.diff - a.diff || a.name.localeCompare(b.name, "ru")),
    ppgRank: rankOf(
      sorted,
      ownName,
      (a, b) => b.pointsPerGame - a.pointsPerGame || b.points - a.points || a.name.localeCompare(b.name, "ru"),
    ),
    tiedTeams: tied.map((row) => row.name),
  };
}
