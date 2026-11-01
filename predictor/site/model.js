/* FHM Hockey Predictor — клиентские модели.
 *
 * Повторяет Python-расчёт (engine.py/features.py/models.py) на данных,
 * выгруженных export_site.py. Все коэффициенты приходят из data.js.
 */
(function (global) {
  "use strict";

  let DATA = global.PREDICTOR_DATA;
  if (!DATA) {
    throw new Error("data.js не загружен: window.PREDICTOR_DATA отсутствует");
  }

  let P = DATA.params;
  let MODEL = DATA.model;

  function refresh() {
    DATA = global.PREDICTOR_DATA;
    P = DATA.params;
    MODEL = DATA.model;
  }
  const FACT = [1];
  for (let i = 1; i <= 16; i += 1) FACT[i] = FACT[i - 1] * i;

  function softmax(values) {
    const max = Math.max(...values);
    const exp = values.map((value) => Math.exp(value - max));
    const total = exp.reduce((sum, value) => sum + value, 0) || 1;
    return exp.map((value) => value / total);
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function dayDiff(from, to) {
    const a = Date.parse(`${from}T00:00:00Z`);
    const b = Date.parse(`${to}T00:00:00Z`);
    if (Number.isNaN(a) || Number.isNaN(b)) return 0;
    return Math.round((b - a) / 86400000);
  }

  function getTeam(teamId) {
    return DATA.teams[String(teamId)];
  }

  function getPlayer(playerId) {
    return DATA.players[String(playerId)];
  }

  function getMatch(matchId) {
    return DATA.upcoming.find((row) => row[0] === Number(matchId)) || null;
  }

  function tournamentOf(matchRow) {
    return DATA.tournaments[String(matchRow[3])] || {};
  }

  function groupName(matchRow) {
    return DATA.groups[String(matchRow[4])] || "";
  }

  function restDays(team, matchDate) {
    if (!team || !team.ld) return 30;
    return clamp(dayDiff(team.ld, matchDate), 0, 60);
  }

  function teamStrength(team, excluded) {
    if (!team) return DATA.meta.league_strength;
    if (!excluded || excluded.size === 0) return team.s;
    const impacts = (team.imp || []).filter((row) => !excluded.has(row[0]));
    if (!impacts.length) return DATA.meta.league_strength;
    impacts.sort((a, b) => b[1] * b[2] - a[1] * a[2]);
    const top = impacts.slice(0, 8);
    const weight = top.reduce((sum, row) => sum + Math.max(0.1, row[1]), 0) || 1;
    return top.reduce((sum, row) => sum + Math.max(0.1, row[1]) * row[2], 0) / weight;
  }

  function eloProbs(diff, drawRate) {
    const raw = 1 / (1 + Math.pow(10, -diff / 400));
    const closeness = Math.max(0, 1 - 2 * Math.abs(raw - 0.5));
    const draw = clamp(drawRate * closeness, 0, 0.35);
    return [raw * (1 - draw), draw, (1 - raw) * (1 - draw)];
  }

  function poissonProbs(lambdaHome, lambdaAway) {
    const home = [];
    const away = [];
    let sumHome = 0;
    let sumAway = 0;
    const maxGoals = 15;
    for (let k = 0; k <= maxGoals; k += 1) {
      home[k] = (Math.exp(-lambdaHome) * Math.pow(lambdaHome, k)) / FACT[k];
      away[k] = (Math.exp(-lambdaAway) * Math.pow(lambdaAway, k)) / FACT[k];
      sumHome += home[k];
      sumAway += away[k];
    }
    let pHome = 0;
    let pDraw = 0;
    let pAway = 0;
    for (let i = 0; i <= maxGoals; i += 1) {
      for (let j = 0; j <= maxGoals; j += 1) {
        const probability = (home[i] / sumHome) * (away[j] / sumAway);
        if (i > j) pHome += probability;
        else if (i === j) pDraw += probability;
        else pAway += probability;
      }
    }
    const total = pHome + pDraw + pAway;
    return [pHome / total, pDraw / total, pAway / total];
  }

  function logisticProbs(features) {
    const values = MODEL.features.map((name) => features[name] || 0);
    const z = [0, 0, 0];
    for (let i = 0; i < values.length; i += 1) {
      const x = (values[i] - MODEL.mean[i]) / MODEL.scale[i];
      for (let c = 0; c < z.length; c += 1) {
        z[c] += x * MODEL.weights[i][c];
      }
    }
    const out = softmax(z.map((value, c) => value + MODEL.bias[c]));
    const result = [0, 0, 0];
    MODEL.classes.forEach((cls, index) => {
      result[cls] = out[index];
    });
    const total = result.reduce((sum, value) => sum + value, 0) || 1;
    return result.map((value) => value / total);
  }

  function computeFeatures(matchRow, excluded) {
    const home = getTeam(matchRow[5]);
    const away = getTeam(matchRow[6]);
    const tournament = tournamentOf(matchRow);
    const group = groupName(matchRow).toLowerCase();
    const format = (tournament.format || "").toLowerCase();
    const lambdaHome = poissonLambdas(matchRow)[0];
    const lambdaAway = poissonLambdas(matchRow)[1];
    return {
      elo_diff: (home.e - away.e) / 100,
      elo_home: (home.e - P.elo.start) / 100,
      elo_away: (away.e - P.elo.start) / 100,
      form_ppg_diff: home.p - away.p,
      form_gf_diff: home.gf - away.gf,
      form_ga_diff: home.ga - away.ga,
      rest_diff: restDays(home, matchRow[1]) - restDays(away, matchRow[1]),
      experience_diff: Math.log1p(home.m) - Math.log1p(away.m),
      poisson_log_ratio: Math.log(lambdaHome / lambdaAway),
      player_diff: teamStrength(home, excluded) - teamStrength(away, excluded),
      is_4x4: format.includes("4") ? 1 : 0,
      is_5x5: format.includes("5") ? 1 : 0,
      is_2016: tournament.age === 2016 ? 1 : 0,
      is_group_a: group.endsWith("а") ? 1 : 0,
      is_group_b: group.endsWith("б") ? 1 : 0,
      is_group_v: group.endsWith("в") ? 1 : 0,
    };
  }

  function poissonLambdas(matchRow) {
    const attack = P.poisson.attack;
    const defense = P.poisson.defense;
    const homeId = String(matchRow[5]);
    const awayId = String(matchRow[6]);
    const lambdaHome =
      P.poisson.avg *
      (attack[homeId] || 1) *
      (defense[awayId] || 1) *
      P.poisson.home_factor;
    const lambdaAway = P.poisson.avg * (attack[awayId] || 1) * (defense[homeId] || 1);
    return [Math.max(0.2, lambdaHome), Math.max(0.2, lambdaAway)];
  }

  function blend(models) {
    const weights = P.ensemble;
    const total = Object.values(weights).reduce((sum, value) => sum + value, 0) || 1;
    const result = [0, 0, 0];
    Object.keys(weights).forEach((name) => {
      const probability = models[name];
      if (!probability) return;
      for (let i = 0; i < 3; i += 1) result[i] += (weights[name] * probability[i]) / total;
    });
    const sum = result.reduce((acc, value) => acc + value, 0) || 1;
    return result.map((value) => value / sum);
  }

  function reasons(matchRow, features, probabilities, excluded) {
    const home = getTeam(matchRow[5]);
    const away = getTeam(matchRow[6]);
    const tournament = tournamentOf(matchRow);
    const list = [];
    const diff = home.e - away.e;
    if (Math.abs(diff) < 25) {
      list.push(`Рейтинги команд практически равны (${home.e.toFixed(0)} против ${away.e.toFixed(0)}).`);
    } else {
      list.push(
        `По рейтингу Elo сильнее ${diff > 0 ? home.n : away.n}: ${home.e.toFixed(0)} против ` +
          `${away.e.toFixed(0)} (разница ${Math.abs(diff).toFixed(0)}).`
      );
    }
    const [lambdaHome, lambdaAway] = poissonLambdas(matchRow);
    list.push(
      `Ожидаемая результативность: ${lambdaHome.toFixed(1)} шайбы у хозяев и ${lambdaAway.toFixed(1)} у гостей.`
    );
    list.push(
      `Форма последних матчей: ${home.p.toFixed(1)} очка за игру у ${home.n}, ` +
        `${away.p.toFixed(1)} у ${away.n}.`
    );
    const strengthHome = teamStrength(home, excluded);
    const strengthAway = teamStrength(away, excluded);
    if (Math.abs(strengthHome - strengthAway) > 0.02) {
      list.push(
        `Оценка состава по прошлым сезонам выше у ${strengthHome > strengthAway ? home.n : away.n} ` +
          `(${strengthHome.toFixed(2)} против ${strengthAway.toFixed(2)} условных шайб на игрока).`
      );
    }
    if (tournament.format) list.push(`Формат встречи: ${tournament.format}.`);
    return list;
  }

  function predictMatch(matchRow, excluded) {
    const excludedSet = excluded instanceof Set ? excluded : new Set(excluded || []);
    const home = getTeam(matchRow[5]);
    const away = getTeam(matchRow[6]);
    const features = computeFeatures(matchRow, excludedSet);
    const [lambdaHome, lambdaAway] = poissonLambdas(matchRow);

    const elo = eloProbs(home.e - away.e + P.elo.home_advantage, DATA.meta.draw_rate);
    const poisson = poissonProbs(lambdaHome, lambdaAway);
    const bonus = clamp(
      P.player_scale * (teamStrength(home, excludedSet) - teamStrength(away, excludedSet)),
      -P.player_clip,
      P.player_clip
    );
    const player = eloProbs(home.e - away.e + P.elo.home_advantage + bonus, DATA.meta.draw_rate);
    const logistic = logisticProbs(features);
    const models = { elo, poisson, player, logistic };
    const ensemble = blend(models);

    return {
      match: matchRow,
      home,
      away,
      features,
      probabilities: models,
      ensemble,
      reasons: reasons(matchRow, features, ensemble, excludedSet),
      quality: {
        history_matches: DATA.meta.counts.played,
        home_games: home.m,
        away_games: away.m,
        roster_stat_rows: (DATA.rosters[String(matchRow[5])] || []).length,
      },
      confidence:
        Math.min(home.m, away.m) >= 10 ? "высокая" : Math.min(home.m, away.m) >= 5 ? "средняя" : "низкая",
    };
  }

  function expectedGoals(matchRow) {
    return poissonLambdas(matchRow);
  }

  function predictById(matchId, excluded) {
    const row = getMatch(matchId);
    if (!row) throw new Error(`Матч ${matchId} не найден в расписании`);
    return predictMatch(row, excluded);
  }

  function lastMatches(teamId, limit) {
    const id = Number(teamId);
    return DATA.played
      .filter((row) => row[2] === id || row[3] === id)
      .sort((a, b) => (a[1] < b[1] ? 1 : a[1] > b[1] ? -1 : 0))
      .slice(0, limit || 5);
  }

  function h2h(teamA, teamB, limit) {
    const a = Number(teamA);
    const b = Number(teamB);
    return DATA.played
      .filter(
        (row) => (row[2] === a && row[3] === b) || (row[2] === b && row[3] === a)
      )
      .sort((x, y) => (x[1] < y[1] ? 1 : x[1] > y[1] ? -1 : 0))
      .slice(0, limit || 10);
  }

  function playerHistory(playerId) {
    const player = getPlayer(playerId);
    if (!player) return [];
    return (player.h || [])
      .slice()
      .sort((a, b) => a[0] - b[0])
      .map((row) => ({
        season_id: row[0],
        season: DATA.seasons[String(row[0])] || row[0],
        team_id: row[1],
        team: (getTeam(row[1]) || {}).n || `#${row[1]}`,
        games: row[2],
        goals: row[3],
        assists: row[4],
      }));
  }

  global.FHMModel = {
    DATA,
    predictById,
    predictMatch,
    expectedGoals,
    lastMatches,
    h2h,
    playerHistory,
    teamStrength,
    reload: refresh,
    getTeam,
    getPlayer,
    getMatch,
  };
})(window);
