/* FHM Hockey Predictor — интерфейс статической страницы. */
(function () {
  "use strict";

  const M = window.FHMModel;
  const state = {
    tab: "predict",
    tournamentId: null,
    matchId: null,
    excluded: new Set(),
    playerTeamId: null,
    playerId: null,
    compareA: null,
    compareB: null,
    tableTournament: null,
    password: "",
    bridge: null,
    job: null,
    log: "",
  };

  const view = document.getElementById("view");
  const statusEl = document.getElementById("data-status");

  const esc = (value) =>
    String(value == null ? "" : value).replace(/[&<>"']/g, (char) => {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });

  const pct = (value) => `${(value * 100).toFixed(1)}%`;

  function fmtNum(value, digits) {
    return Number(value).toLocaleString("ru-RU", {
      minimumFractionDigits: digits == null ? 0 : digits,
      maximumFractionDigits: digits == null ? 3 : digits,
    });
  }

  function tournamentList() {
    const tids = new Set(M.DATA.upcoming.map((row) => row[3]));
    return Object.entries(M.DATA.tournaments)
      .filter(([id]) => tids.has(Number(id)))
      .map(([id, info]) => ({ id: Number(id), ...info }))
      .sort((a, b) => (b.season || 0) - (a.season || 0) || a.n.localeCompare(b.n, "ru"));
  }

  function tournamentLabel(info) {
    const season = M.DATA.seasons[String(info.season)] || "";
    return `${season} · ${info.n}`;
  }

  function upcomingFor(tournamentId) {
    return M.DATA.upcoming
      .filter((row) => row[3] === tournamentId)
      .sort((a, b) => (a[1] + (a[2] || "")) .localeCompare(b[1] + (b[2] || "")) || a[0] - b[0]);
  }

  function matchLabel(row) {
    const home = M.getTeam(row[5]);
    const away = M.getTeam(row[6]);
    const clock = row[2] ? ` ${row[2]}` : "";
    return `${row[1]}${clock} · ${home.n} — ${away.n}`;
  }

  function teamOptions(selected) {
    return Object.entries(M.DATA.teams)
      .filter(([, team]) => team.g)
      .sort((a, b) => a[1].n.localeCompare(b[1].n, "ru"))
      .map(([id, team]) => `<option value="${id}"${String(selected) === id ? " selected" : ""}>${esc(team.n)}</option>`)
      .join("");
  }

  function initials(name) {
    return name
      .split(" ")
      .slice(0, 2)
      .map((part) => part.charAt(0).toUpperCase())
      .join("");
  }

  function currentPrediction() {
    if (!state.matchId) return null;
    try {
      return M.predictById(state.matchId, state.excluded);
    } catch (error) {
      return { error: error.message };
    }
  }

  // ---------------------------------------------------------------- Прогноз

  function renderPredict() {
    const tours = tournamentList();
    if (!tours.length) {
      view.innerHTML = `<div class="card"><h2>Прогноз</h2><p>Нет предстоящих матчей в загруженных данных.</p></div>`;
      return;
    }
    if (!tours.some((tour) => tour.id === state.tournamentId)) {
      state.tournamentId = tours.find((tour) => tour.id === 51) ? 51 : tours[0].id;
    }
    const matches = upcomingFor(state.tournamentId);
    if (!matches.some((row) => row[0] === state.matchId)) {
      state.matchId = matches.length ? matches[0][0] : null;
    }
    if (!state.matchId) {
      view.innerHTML = `<div class="card"><h2>Прогноз</h2><p>В этом турнире нет будущих матчей.</p></div>`;
      return;
    }
    const tour = tours.find((item) => item.id === state.tournamentId);
    const match = M.getMatch(state.matchId);
    const base = M.predictById(state.matchId, new Set());
    const prediction = state.excluded.size ? M.predictById(state.matchId, state.excluded) : base;
    const winner = prediction.ensemble.indexOf(Math.max(...prediction.ensemble));
    const names = [prediction.home.n, "Ничья", prediction.away.n];
    const delta = state.excluded.size ? (prediction.ensemble[0] - base.ensemble[0]) * 100 : 0;

    const improtential = (teamId) => {
      const team = M.getTeam(teamId);
      return (team.imp || [])
        .slice()
        .sort((a, b) => b[1] * b[2] - a[1] * a[2])
        .slice(0, 10)
        .map((row) => {
          const player = M.getPlayer(row[0]) || { n: `#${row[0]}` };
          const checked = state.excluded.has(row[0]) ? " checked" : "";
          return `<label><input type="checkbox" data-exclude="${row[0]}"${checked}> ${esc(player.n)}</label>`;
        })
        .join("");
    };

    const modelRows = Object.entries(prediction.probabilities)
      .map(([name, probability]) => {
        const label = { elo: "Elo", poisson: "Пуассон", player: "Elo + игроки", logistic: "Логистика" }[name] || name;
        return `<tr><td>${label}</td><td class="num">${pct(probability[0])}</td><td class="num">${pct(probability[1])}</td><td class="num">${pct(probability[2])}</td></tr>`;
      })
      .join("");

    view.innerHTML = `
      <div class="card">
        <h2>Прогноз матча</h2>
        <p class="lead">Выберите турнир и будущую встречу. Расчёт идёт по данным на ${esc(M.DATA.meta.data_as_of || "—")}.</p>
        <div class="grid cols-2">
          <div class="field">
            <label for="tournament">Турнир</label>
            <select id="tournament">
              ${tours.map((item) => `<option value="${item.id}"${item.id === state.tournamentId ? " selected" : ""}>${esc(tournamentLabel(item))}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="match">Матч</label>
            <select id="match">
              ${matches.map((row) => `<option value="${row[0]}"${row[0] === state.matchId ? " selected" : ""}>${esc(matchLabel(row))}</option>`).join("")}
            </select>
          </div>
        </div>
        <button class="btn" id="predict-button">Рассчитать прогноз</button>
      </div>

      <div class="card">
        <h3>${esc(prediction.home.n)} — ${esc(prediction.away.n)}</h3>
        <div class="prob-grid">
          ${[0, 1, 2].map((index) => `
            <div class="prob${winner === index ? " is-winner" : ""}">
              <div class="name">${esc(names[index])}</div>
              <div class="value${index === 1 ? " soft" : ""}">${pct(prediction.ensemble[index])}</div>
            </div>`).join("")}
        </div>
        <p style="margin:16px 0 6px">
          Ожидаемый исход: <b>${esc(names[winner])}</b> ·
          уверенность: <span class="badge ${prediction.confidence === "высокая" ? "good" : prediction.confidence === "средняя" ? "warn" : ""}">${esc(prediction.confidence)}</span>
          · данных: ${fmtNum(prediction.quality.history_matches)} матчей
        </p>
        <p class="meta">Турнир: ${esc(tour.n)} · группа ${esc(M.DATA.groups[String(match[4])] || "—")} · формат ${esc(tour.format || "—")}.
          Дата данных: ${esc(M.DATA.meta.data_as_of || "—")} · модель: ${esc(M.DATA.meta.model_version)} · хеш: <span class="mono">${esc((M.DATA.meta.hash || "").slice(0, 16))}…</span></p>
      </div>

      <div class="card">
        <details${state.excluded.size ? " open" : ""}>
          <summary>Ручная корректировка состава ${state.excluded.size ? `(исключено: ${state.excluded.size})` : ""}</summary>
          <p class="meta">Отметьте игроков, которые точно не играют. Вероятности пересчитаются.</p>
          <div class="grid cols-2">
            <div>
              <h3>${esc(prediction.home.n)}</h3>
              <div class="checkbox-list">${improtential(match[5]) || "<span class='meta'>Нет данных о составе</span>"}</div>
            </div>
            <div>
              <h3>${esc(prediction.away.n)}</h3>
              <div class="checkbox-list">${improtential(match[6]) || "<span class='meta'>Нет данных о составе</span>"}</div>
            </div>
          </div>
          ${state.excluded.size ? `<p class="notice" style="margin-top:14px">Исключение игроков меняет вероятность победы хозяев на <b>${delta >= 0 ? "+" : ""}${delta.toFixed(1)} п.п.</b> (было ${pct(base.ensemble[0])}, стало ${pct(prediction.ensemble[0])}).</p>` : ""}
        </details>
      </div>

      <div class="grid cols-2">
        <div class="card">
          <h3>Сравнение моделей</h3>
          <table>
            <thead><tr><th>Модель</th><th class="num">Хозяева</th><th class="num">Ничья</th><th class="num">Гости</th></tr></thead>
            <tbody>${modelRows}</tbody>
          </table>
          <p class="meta" style="margin-top:10px">Итог: 0,6 × логистика + 0,4 × Пуассон.</p>
        </div>
        <div class="card">
          <h3>Почему такой прогноз</h3>
          <ul class="list">${prediction.reasons.map((reason) => `<li>${esc(reason)}</li>`).join("")}</ul>
        </div>
      </div>

      <div class="card">
        <button class="btn ghost" id="download-prediction">Скачать прогноз JSON</button>
      </div>
    `;

    document.getElementById("tournament").addEventListener("change", (event) => {
      state.tournamentId = Number(event.target.value);
      state.matchId = null;
      state.excluded.clear();
      renderPredict();
    });
    document.getElementById("match").addEventListener("change", (event) => {
      state.matchId = Number(event.target.value);
      state.excluded.clear();
      renderPredict();
    });
    document.getElementById("predict-button").addEventListener("click", () => renderPredict());
    view.querySelectorAll("[data-exclude]").forEach((checkbox) => {
      checkbox.addEventListener("change", (event) => {
        const id = Number(event.target.dataset.exclude);
        if (event.target.checked) state.excluded.add(id);
        else state.excluded.delete(id);
        renderPredict();
      });
    });
    document.getElementById("download-prediction").addEventListener("click", () => {
      const payload = {
        match: { id: match[0], date: match[1], time: match[2], tournament: tour.n, group: M.DATA.groups[String(match[4])] },
        home: prediction.home.n,
        away: prediction.away.n,
        probabilities: {
          home: prediction.ensemble[0],
          draw: prediction.ensemble[1],
          away: prediction.ensemble[2],
        },
        models: prediction.probabilities,
        excluded_players: [...state.excluded],
        data_as_of: M.DATA.meta.data_as_of,
        model: M.DATA.meta.model_version,
        data_hash: M.DATA.meta.hash,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `prediction_${match[0]}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
    });
  }

  // --------------------------------------------------------------- Таблица

  function groupStandings(groupId) {
    const info = M.DATA.group_info[String(groupId)];
    const rows = new Map();
    const ensure = (teamId) => {
      const key = Number(teamId);
      if (!rows.has(key)) {
        const team = M.getTeam(key) || { n: `#${teamId}` };
        rows.set(key, {
          id: key,
          name: team.n,
          played: 0,
          points: 0,
          gf: 0,
          ga: 0,
          expPoints: 0,
          expGD: 0,
          remaining: 0,
        });
      }
      return rows.get(key);
    };
    (info.teams || []).forEach((teamId) => ensure(teamId));

    M.DATA.played.filter((row) => row[7] === Number(groupId)).forEach((row) => {
      const home = ensure(row[2]);
      const away = ensure(row[3]);
      home.played += 1;
      away.played += 1;
      home.gf += row[4];
      home.ga += row[5];
      away.gf += row[5];
      away.ga += row[4];
      if (row[4] > row[5]) home.points += 2;
      else if (row[4] < row[5]) away.points += 2;
      else {
        home.points += 1;
        away.points += 1;
      }
    });

    const matches = M.DATA.upcoming.filter((row) => row[4] === Number(groupId));
    matches.forEach((row) => {
      const prediction = M.predictById(row[0]);
      const [lambdaHome, lambdaAway] = M.expectedGoals(row);
      const home = ensure(row[5]);
      const away = ensure(row[6]);
      home.expPoints += prediction.ensemble[0] * 2 + prediction.ensemble[1];
      away.expPoints += prediction.ensemble[2] * 2 + prediction.ensemble[1];
      home.expGD += lambdaHome - lambdaAway;
      away.expGD -= lambdaHome - lambdaAway;
      home.remaining += 1;
      away.remaining += 1;
    });

    const list = [...rows.values()];
    list.forEach((row) => {
      row.gd = row.gf - row.ga;
      row.projectedPoints = row.points + row.expPoints;
      row.projectedGD = row.gd + row.expGD;
    });
    const current = list.slice().sort((a, b) =>
      b.points - a.points || b.gd - a.gd || b.gf - a.gf || a.name.localeCompare(b.name, "ru")
    );
    current.forEach((row, index) => {
      row.currentRank = index + 1;
    });
    const projected = list.slice().sort((a, b) =>
      b.projectedPoints - a.projectedPoints ||
      b.projectedGD - a.projectedGD ||
      b.points - a.points ||
      a.name.localeCompare(b.name, "ru")
    );
    projected.forEach((row, index) => {
      row.projectedRank = index + 1;
    });
    return { rows: projected, matches };
  }

  function renderTable() {
    const groups = Object.entries(M.DATA.group_info || {});
    if (!groups.length) {
      view.innerHTML = `<div class="card"><h2>Таблица</h2><p>Нет данных по группам 2016 г.р.</p></div>`;
      return;
    }
    const tournamentIds = [...new Set(groups.map(([, info]) => info.t))].sort((a, b) => a - b);
    if (!tournamentIds.includes(state.tableTournament)) state.tableTournament = tournamentIds.includes(51) ? 51 : tournamentIds[0];
    const tournament = M.DATA.tournaments[String(state.tableTournament)] || {};

    const sections = groups
      .filter(([, info]) => info.t === state.tableTournament)
      .sort((a, b) => a[1].n.localeCompare(b[1].n, "ru"))
      .map(([groupId, info]) => {
        const { rows, matches } = groupStandings(groupId);
        const tableRows = rows.map((row) => {
          const delta = row.currentRank - row.projectedRank;
          const deltaText = delta > 0 ? `↑${delta}` : delta < 0 ? `↓${-delta}` : "=";
          const deltaClass = delta > 0 ? "good" : delta < 0 ? "bad" : "";
          return `<tr>
            <td class="num">${row.projectedRank}</td>
            <td><span class="badge ${deltaClass}">${deltaText}</span></td>
            <td>${esc(row.name)}</td>
            <td class="num">${row.played}</td>
            <td class="num">${row.points}</td>
            <td class="num">+${fmtNum(row.expPoints, 1)}</td>
            <td class="num"><b>${fmtNum(row.projectedPoints, 1)}</b></td>
            <td class="num">${fmtNum(row.projectedGD, 0)}</td>
            <td class="num">${row.remaining}</td>
          </tr>`;
        }).join("");

        const matchRows = matches
          .slice()
          .sort((a, b) => (a[1] + (a[2] || "")).localeCompare(b[1] + (b[2] || "")))
          .map((row) => {
            const prediction = M.predictById(row[0]);
            const home = M.getTeam(row[5]);
            const away = M.getTeam(row[6]);
            return `<tr><td>${esc(row[1])}${row[2] ? " " + esc(row[2]) : ""}</td>
              <td>${esc(home.n)} — ${esc(away.n)}</td>
              <td class="num">${pct(prediction.ensemble[0])} / ${pct(prediction.ensemble[1])} / ${pct(prediction.ensemble[2])}</td></tr>`;
          }).join("");

        return `<div class="card">
          <h3>${esc(info.n)} · ${esc(tournament.n)}</h3>
          <p class="meta">Команд: ${rows.length} · сыграно матчей: ${M.DATA.played.filter((row) => row[7] === Number(groupId)).length} · впереди: ${matches.length}</p>
          <div style="overflow:auto"><table>
            <thead><tr><th class="num">Место</th><th>Δ</th><th>Команда</th><th class="num">И</th><th class="num">О</th><th class="num">+О</th><th class="num">Прогноз</th><th class="num">РГ</th><th class="num">Осталось</th></tr></thead>
            <tbody>${tableRows}</tbody>
          </table></div>
          <details style="margin-top:12px"><summary>Предстоящие матчи и вероятности (${matches.length})</summary>
            <div style="max-height:360px; overflow:auto"><table><thead><tr><th>Дата</th><th>Матч</th><th class="num">Хоз / ничья / гости</th></tr></thead><tbody>${matchRows}</tbody></table></div>
          </details>
        </div>`;
      })
      .join("");

    view.innerHTML = `
      <div class="card">
        <h2>Прогноз турнирной таблицы</h2>
        <p class="lead">Текущие очки плюс математическое ожидание очков за все предстоящие матчи группы. Правила: 2 очка за победу, 1 за ничью.</p>
        <div class="field" style="max-width:520px">
          <label for="table-tournament">Турнир</label>
          <select id="table-tournament">
            ${tournamentIds.map((id) => {
              const info = M.DATA.tournaments[String(id)] || {};
              const season = M.DATA.seasons[String(info.season)] || "";
              return `<option value="${id}"${id === state.tableTournament ? " selected" : ""}>${esc(season)} · ${esc(info.n || id)}</option>`;
            }).join("")}
          </select>
        </div>
        <p class="meta">Δ — изменение места относительно текущей таблицы. «+О» — ожидаемые очки за оставшиеся игры, «РГ» — прогнозируемая разница шайб (текущая плюс ожидаемая по λ Пуассона).</p>
      </div>
      ${sections}
      <div class="notice">Прогноз таблицы — математическое ожидание, а не гарантия. Он не учитывает переносы, технические поражения и изменения составов; для отдельного матча используйте раздел «Прогноз».</div>
    `;

    document.getElementById("table-tournament").addEventListener("change", (event) => {
      state.tableTournament = Number(event.target.value);
      renderTable();
    });
  }

  // ----------------------------------------------------------------- Игроки

  function renderPlayers() {
    const teamIds = Object.keys(M.DATA.rosters).sort((a, b) => {
      const left = M.getTeam(a);
      const right = M.getTeam(b);
      return (left ? left.n : a).localeCompare(right ? right.n : b, "ru");
    });
    if (!teamIds.includes(String(state.playerTeamId))) state.playerTeamId = Number(teamIds[0]);
    const roster = M.DATA.rosters[String(state.playerTeamId)] || [];
    if (!roster.some((row) => row[0] === state.playerId)) {
      state.playerId = roster.length ? roster[0][0] : null;
    }
    const team = M.getTeam(state.playerTeamId) || { n: "" };
    const maxGames = Math.max(1, ...roster.map((row) => row[3]));
    const player = state.playerId ? M.getPlayer(state.playerId) : null;
    const history = state.playerId ? M.playerHistory(state.playerId) : [];
    const transitions = [];
    for (let i = 1; i < history.length; i += 1) {
      if (history[i].team_id !== history[i - 1].team_id) {
        transitions.push(`${history[i - 1].season}: ${history[i - 1].team} → ${history[i].season}: ${history[i].team}`);
      }
    }

    view.innerHTML = `
      <div class="card">
        <h2>Игроки</h2>
        <p class="lead">Заявка команды на текущий сезон. «Участие» — доля матчей команды, а не подтверждённый факт выхода на лёд.</p>
        <div class="field">
          <label for="player-team">Команда</label>
          <select id="player-team">${teamOptions(state.playerTeamId)}</select>
        </div>
      </div>

      <div class="card">
        <h3>${esc(team.n)}</h3>
        <div style="overflow:auto">
          <table>
            <thead><tr><th>№</th><th>Игрок</th><th>Роль</th><th>Год</th><th class="num">Игры</th><th class="num">Голы</th><th class="num">Передачи</th><th class="num">Очки</th><th class="num">Участие</th></tr></thead>
            <tbody>
              ${roster.map((row) => {
                const info = M.getPlayer(row[0]) || { n: `#${row[0]}`, b: null, r: "" };
                return `<tr>
                  <td>${row[1] == null ? "" : row[1]}</td>
                  <td><button class="btn ghost" style="padding:4px 8px" data-player="${row[0]}">${esc(info.n)}</button></td>
                  <td>${esc(info.r || row[2] || "")}</td>
                  <td>${info.b || ""}</td>
                  <td class="num">${row[3]}</td>
                  <td class="num">${row[4]}</td>
                  <td class="num">${row[5]}</td>
                  <td class="num">${row[6]}</td>
                  <td class="num">${(Math.min(1, row[3] / maxGames) * 100).toFixed(0)}%</td>
                </tr>`;
              }).join("")}
            </tbody>
          </table>
        </div>
      </div>

      ${player ? `
      <div class="card">
        <h3>${esc(player.n)}</h3>
        <p class="meta">Год рождения: ${player.b || "не указан"} · роль: ${esc(player.r || "—")} · ID ФХМ: ${state.playerId}</p>
        <h3 style="margin-top:16px">История по сезонам</h3>
        ${history.length ? `<table><thead><tr><th>Сезон</th><th>Команда</th><th class="num">Игры</th><th class="num">Голы</th><th class="num">Передачи</th></tr></thead><tbody>
          ${history.map((row) => `<tr><td>${esc(row.season)}</td><td>${esc(row.team)}</td><td class="num">${row.games}</td><td class="num">${row.goals}</td><td class="num">${row.assists}</td></tr>`).join("")}
        </tbody></table>` : `<p class="meta">Истории пока нет.</p>`}
        ${transitions.length ? `<h3 style="margin-top:16px">Смены команды между сезонами</h3><ul class="list">${transitions.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : `<p class="meta" style="margin-top:12px">Смен команды между сезонами не зафиксировано.</p>`}
      </div>` : ""}
    `;

    document.getElementById("player-team").addEventListener("change", (event) => {
      state.playerTeamId = Number(event.target.value);
      state.playerId = null;
      renderPlayers();
    });
    view.querySelectorAll("[data-player]").forEach((button) => {
      button.addEventListener("click", (event) => {
        state.playerId = Number(event.currentTarget.dataset.player);
        renderPlayers();
      });
    });
  }

  // -------------------------------------------------------------- Сравнение

  function renderCompare() {
    const teams = Object.entries(M.DATA.teams).filter(([, team]) => team.g);
    if (!state.compareA) state.compareA = Number(teams[0][0]);
    if (!state.compareB) state.compareB = Number(teams[1] ? teams[1][0] : teams[0][0]);
    const a = M.getTeam(state.compareA);
    const b = M.getTeam(state.compareB);
    const lastA = M.lastMatches(state.compareA, 5);
    const lastB = M.lastMatches(state.compareB, 5);
    const meetings = M.h2h(state.compareA, state.compareB, 10);

    const rows = (rowsList) => rowsList.map((row) => {
      const home = M.getTeam(row[2]);
      const away = M.getTeam(row[3]);
      return `<tr><td>${row[1]}</td><td>${esc(home ? home.n : row[2])} — ${esc(away ? away.n : row[3])}</td><td class="num">${row[4]}:${row[5]}</td></tr>`;
    }).join("");

    const topPlayers = (teamId) => {
      const team = M.getTeam(teamId);
      return (team.imp || [])
        .slice()
        .sort((x, y) => y[1] * y[2] - x[1] * x[2])
        .slice(0, 5)
        .map((row) => {
          const player = M.getPlayer(row[0]) || { n: `#${row[0]}` };
          return `<tr><td>${esc(player.n)}</td><td class="num">${fmtNum(row[2], 2)}</td></tr>`;
        })
        .join("");
    };

    view.innerHTML = `
      <div class="card">
        <h2>Сравнение команд</h2>
        <div class="grid cols-2">
          <div class="field"><label for="cmp-a">Команда 1</label><select id="cmp-a">${teamOptions(state.compareA)}</select></div>
          <div class="field"><label for="cmp-b">Команда 2</label><select id="cmp-b">${teamOptions(state.compareB)}</select></div>
        </div>
      </div>

      <div class="grid cols-2">
        ${[[a, lastA, "cmp-a"], [b, lastB, "cmp-b"]].map(([team, rowsList]) => `
          <div class="card">
            <h3>${esc(team.n)}</h3>
            <p class="meta">Elo: <b>${fmtNum(team.e, 0)}</b> · матчей: ${team.m} · форма: ${fmtNum(team.p, 1)} очка за игру · сила состава: ${fmtNum(team.s, 2)}</p>
            <h3 style="margin-top:14px">Последние матчи</h3>
            ${rowsList.length ? `<table><thead><tr><th>Дата</th><th>Матч</th><th class="num">Счёт</th></tr></thead><tbody>${rows(rowsList)}</tbody></table>` : `<p class="meta">Нет матчей.</p>`}
            <h3 style="margin-top:14px">Сильнейшие игроки</h3>
            ${topPlayers(team === a ? state.compareA : state.compareB) ? `<table><tbody>${topPlayers(team === a ? state.compareA : state.compareB)}</tbody></table>` : `<p class="meta">Нет данных.</p>`}
          </div>`).join("")}
      </div>

      <div class="card">
        <h3>Очные встречи</h3>
        ${meetings.length ? `<table><thead><tr><th>Дата</th><th>Матч</th><th class="num">Счёт</th></tr></thead><tbody>${rows(meetings)}</tbody></table>` : `<p class="meta">Очных матчей в базе нет.</p>`}
      </div>
    `;

    document.getElementById("cmp-a").addEventListener("change", (event) => {
      state.compareA = Number(event.target.value);
      renderCompare();
    });
    document.getElementById("cmp-b").addEventListener("change", (event) => {
      state.compareB = Number(event.target.value);
      renderCompare();
    });
  }

  // ---------------------------------------------------------- Качество модели

  function renderQuality() {
    const quality = M.DATA.quality || {};
    if (!quality.models) {
      view.innerHTML = `<div class="card"><h2>Качество модели</h2><p>Отчёт backtest не выгружен. Запустите <span class="mono">python main.py backtest</span> и <span class="mono">python main.py export-site</span>.</p></div>`;
      return;
    }
    const labels = { elo: "Elo", poisson: "Пуассон", player: "Elo + игроки", logistic: "Логистика", ensemble: "Ансамбль" };
    const modelRows = Object.entries(quality.models).map(([name, m]) => `
      <tr><td>${labels[name] || name}</td><td class="num">${fmtNum(m.accuracy, 3)}</td><td class="num">${fmtNum(m.brier, 3)}</td><td class="num">${fmtNum(m.log_loss, 3)}</td><td class="num">${m.accuracy_ci95 ? `${fmtNum(m.accuracy_ci95[0], 3)}–${fmtNum(m.accuracy_ci95[1], 3)}` : "—"}</td><td class="num">${fmtNum(m.n)}</td></tr>`).join("");
    const calibration = (quality.models.ensemble && quality.models.ensemble.calibration) || [];
    const slices = Object.entries(quality.slices || {})
      .filter(([, value]) => value.ensemble)
      .sort((a, b) => (b[1].ensemble.n || 0) - (a[1].ensemble.n || 0))
      .map(([name, value]) => {
        const e = value.ensemble;
        return `<tr><td>${esc(name)}</td><td class="num">${e.n}</td><td class="num">${fmtNum(e.accuracy, 3)}</td><td class="num">${fmtNum(e.brier, 3)}</td><td class="num">${fmtNum(e.log_loss, 3)}</td></tr>`;
      }).join("");

    view.innerHTML = `
      <div class="card">
        <h2>Качество модели</h2>
        <p class="lead">Walk-forward на ${fmtNum(quality.evaluated)} матчах (${esc(quality.date_from || "")} — ${esc(quality.date_to || "")}). Модели обучались только на прошлом.</p>
        <table>
          <thead><tr><th>Модель</th><th class="num">Accuracy</th><th class="num">Brier</th><th class="num">Log loss</th><th class="num">95% интервал</th><th class="num">Матчей</th></tr></thead>
          <tbody>${modelRows}</tbody>
        </table>
        <p class="meta" style="margin-top:10px">Веса ансамбля: ${Object.entries(quality.ensemble_weights || {}).map(([name, value]) => `${labels[name] || name} ${value}`).join(", ")}.</p>
      </div>

      <div class="grid cols-2">
        <div class="card">
          <h3>Калибровка (победа хозяев)</h3>
          <table><thead><tr><th>Прогноз</th><th class="num">Матчей</th><th class="num">Средний</th><th class="num">Факт</th></tr></thead><tbody>
            ${calibration.map((row) => `<tr><td>${fmtNum(row.from, 2)}–${fmtNum(row.to, 2)}</td><td class="num">${row.n}</td><td class="num">${fmtNum(row.predicted, 3)}</td><td class="num">${fmtNum(row.observed, 3)}</td></tr>`).join("")}
          </tbody></table>
        </div>
        <div class="card">
          <h3>Отложенные 30%</h3>
          <table><thead><tr><th>Модель</th><th class="num">Accuracy</th><th class="num">Brier</th><th class="num">Log loss</th></tr></thead><tbody>
            ${Object.entries((quality.holdout && quality.holdout.models) || {}).map(([name, m]) => `<tr><td>${labels[name] || name}</td><td class="num">${fmtNum(m.accuracy, 3)}</td><td class="num">${fmtNum(m.brier, 3)}</td><td class="num">${fmtNum(m.log_loss, 3)}</td></tr>`).join("")}
          </tbody></table>
          <p class="meta" style="margin-top:10px">Матчей: ${fmtNum((quality.holdout && quality.holdout.n) || 0)}. Веса подбирались на первых 70%.</p>
        </div>
      </div>

      <div class="card">
        <h3>По срезам (ансамбль)</h3>
        <div style="overflow:auto"><table><thead><tr><th>Срез</th><th class="num">Матчей</th><th class="num">Accuracy</th><th class="num">Brier</th><th class="num">Log loss</th></tr></thead><tbody>${slices}</tbody></table></div>
        ${quality.goal_dispersion ? `<p class="meta" style="margin-top:10px">Сверхдисперсия голов: среднее ${fmtNum(quality.goal_dispersion.mean, 2)}, дисперсия ${fmtNum(quality.goal_dispersion.variance, 2)}, отношение ${fmtNum(quality.goal_dispersion.ratio, 2)}. Пуассон — приближение.</p>` : ""}
      </div>

      <div class="notice warn">Метрики получены на исторических матчах 2016–2017 г.р. и не гарантируют такую же точность на будущих встречах. Выборка по отдельным группам небольшая.</div>
    `;
  }

  // ------------------------------------------------------------------ Данные

  function renderData() {
    const meta = M.DATA.meta;
    const coverage = M.DATA.coverage || {};
    const tournaments = coverage.tournaments || [];
    const bridgeOk = Boolean(state.bridge);
    view.innerHTML = `
      <div class="card">
        <h2>Данные</h2>
        <p class="lead">Статическая страница работает на выгруженном снимке базы. Обновление и пересчёт модели требуют локального сервера.</p>
        <div class="grid cols-4">
          <div class="prob"><div class="name">Данные на</div><div class="value" style="font-size:22px">${esc(meta.data_as_of || "—")}</div></div>
          <div class="prob"><div class="name">Матчей</div><div class="value" style="font-size:26px">${fmtNum(meta.counts.matches)}</div></div>
          <div class="prob"><div class="name">Игроков</div><div class="value" style="font-size:26px">${fmtNum(meta.counts.players)}</div></div>
          <div class="prob"><div class="name">Будущих матчей</div><div class="value" style="font-size:26px">${fmtNum(meta.counts.upcoming)}</div></div>
        </div>
        <p class="meta" style="margin-top:12px">Снимок: ${esc(meta.generated_at)} · модель ${esc(meta.model_version)} · хеш <span class="mono">${esc((meta.hash || "").slice(0, 24))}…</span></p>
      </div>

      <div class="card">
        <h3>Покрытие</h3>
        ${tournaments.length ? `<div style="overflow:auto"><table><thead><tr><th>Сезон</th><th>Турнир</th><th class="num">Групп</th><th class="num">Команд</th><th class="num">Матчей</th><th class="num">Сыграно</th></tr></thead><tbody>
          ${tournaments.map((row) => `<tr><td>${esc(row.season_label)}</td><td>${esc(row.name)}</td><td class="num">${row.groups}</td><td class="num">${row.teams}</td><td class="num">${row.matches}</td><td class="num">${row.played}</td></tr>`).join("")}
        </tbody></table></div>` : `<p class="meta">Нет отчёта покрытия.</p>`}
      </div>

      <div class="card">
        <h3>Обновление и публикация</h3>
        <p class="meta">На сайте нет Python, поэтому статистика и модель считаются вручную на локальном компьютере, а затем публикуются. Один шаг — <span class="mono">publish.bat</span>:</p>
        <pre class="log">publish.bat
  → python main.py collect
  → python main.py backtest
  → python main.py export-site
  → git commit + git push</pre>
        <p class="meta">После пуша GitHub Actions пересоберёт Pages, и эта страница получит новый снимок. Пароль веб-кнопок — <b>refresh</b>.</p>
      </div>

      <div class="card">
        <details>
          <summary>Локальные кнопки через bridge.bat (необязательно)</summary>
          <p class="meta">Кнопки запускают Python-сборщик на этом компьютере. Пароль проверяет локальный сервер; на статической странице это только ограничение интерфейса.</p>
          <div class="field" style="max-width:340px">
            <label for="refresh-password">Пароль</label>
            <input type="password" id="refresh-password" placeholder="Введите пароль" value="${esc(state.password)}">
          </div>
          <div style="display:flex; gap:10px; flex-wrap:wrap">
            <button class="btn" id="btn-update"${bridgeOk && state.password === "refresh" ? "" : " disabled"}>Собрать статистику</button>
            <button class="btn ghost" id="btn-backtest"${bridgeOk && state.password === "refresh" ? "" : " disabled"}>Пересчитать модель</button>
          </div>
          <p class="meta" style="margin-top:10px">
            ${bridgeOk ? `Локальный сервер доступен (${esc(state.bridge.host || "127.0.0.1")}).` : "Локальный сервер не запущен: кнопки доступны только при запуске <span class=\"mono\">bridge.bat</span>."}
          </p>
          <pre class="log" id="job-log">${esc(state.log || "Лог появится после запуска задачи.")}</pre>
        </details>
        <p class="meta" style="margin-top:10px">Снимок страницы: ${esc(meta.generated_at)}. Если он старее суток, выполните <span class="mono">publish.bat</span>.</p>
      </div>

      <div class="notice">На GitHub Pages кнопки недоступны: там нет серверной части. Обновление всегда идёт с локального компьютера и публикуется коммитом — это осознанный ручной режим.</div>
    `;

    const passwordInput = document.getElementById("refresh-password");
    passwordInput.addEventListener("input", (event) => {
      state.password = event.target.value;
      const allowed = state.password === "refresh" && Boolean(state.bridge);
      document.getElementById("btn-update").disabled = !allowed;
      document.getElementById("btn-backtest").disabled = !allowed;
    });
    document.getElementById("btn-update").addEventListener("click", () => startJob("update"));
    document.getElementById("btn-backtest").addEventListener("click", () => startJob("backtest"));
  }

  // ------------------------------------------------------- Локальный сервер

  async function checkBridge() {
    try {
      const response = await fetch("api/health", { cache: "no-store" });
      if (!response.ok) return null;
      const data = await response.json();
      state.bridge = data || {};
      return data;
    } catch (error) {
      state.bridge = null;
      return null;
    }
  }

  async function startJob(action) {
    if (state.password !== "refresh") return;
    if (!state.bridge) {
      state.log = "Локальный сервер не запущен. Запустите bridge.bat.";
      renderData();
      return;
    }
    state.log = "Запускаю задачу…";
    renderData();
    try {
      const response = await fetch("api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, password: state.password }),
      });
      if (response.status === 401) {
        state.log = "Неверный пароль.";
        renderData();
        return;
      }
      if (response.status === 409) {
        state.log = "Уже выполняется другая задача. Дождитесь завершения.";
        renderData();
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const job = await response.json();
      state.job = job.id;
      pollJob(job.id);
    } catch (error) {
      state.log = `Не удалось запустить: ${error.message}`;
      renderData();
    }
  }

  async function pollJob(jobId) {
    try {
      const response = await fetch(`api/jobs/${jobId}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const job = await response.json();
      state.log = (job.log || []).join("\n");
      const logEl = document.getElementById("job-log");
      if (logEl) logEl.textContent = state.log;
      if (job.status === "running") {
        setTimeout(() => pollJob(jobId), 1500);
        return;
      }
      if (job.status === "ok") {
        state.log += "\n\nГотово. Перезагружаю данные страницы…";
        const logDone = document.getElementById("job-log");
        if (logDone) logDone.textContent = state.log;
        await reloadData();
        state.log += "\nДанные обновлены.";
      } else {
        state.log += `\n\nОшибка: ${job.error || "неизвестно"}`;
      }
      const finalLog = document.getElementById("job-log");
      if (finalLog) finalLog.textContent = state.log;
    } catch (error) {
      state.log += `\nОшибка опроса: ${error.message}`;
      const logEl = document.getElementById("job-log");
      if (logEl) logEl.textContent = state.log;
    }
  }

  function reloadData() {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `site/data.js?t=${Date.now()}`;
      script.onload = () => {
        M.reload();
        state.excluded.clear();
        resolve();
      };
      script.onerror = () => reject(new Error("не удалось загрузить data.js"));
      document.body.appendChild(script);
    });
  }

  // ---------------------------------------------------------------- Роутинг

  function renderStatus() {
    const meta = M.DATA.meta;
    statusEl.textContent = `Данные на ${meta.data_as_of || "—"} · матчей ${fmtNum(meta.counts.matches)} · игроков ${fmtNum(meta.counts.players)}`;
  }

  function render() {
    renderStatus();
    document.querySelectorAll(".tab").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.tab === state.tab);
    });
    if (state.tab === "predict") renderPredict();
    else if (state.tab === "table") renderTable();
    else if (state.tab === "players") renderPlayers();
    else if (state.tab === "compare") renderCompare();
    else if (state.tab === "quality") renderQuality();
    else renderData();
  }

  const TABS = ["predict", "table", "players", "compare", "quality", "data"];

  document.getElementById("tabs").addEventListener("click", (event) => {
    const button = event.target.closest(".tab");
    if (!button) return;
    state.tab = button.dataset.tab;
    if (history.replaceState) history.replaceState(null, "", `#${state.tab}`);
    render();
  });

  async function init() {
    const hash = (location.hash || "").replace("#", "");
    if (TABS.includes(hash)) state.tab = hash;
    const params = new URLSearchParams(location.search);
    const tournamentParam = Number(params.get("tournament"));
    if (tournamentParam) state.tableTournament = tournamentParam;
    await checkBridge();
    render();
  }

  init();
})();
