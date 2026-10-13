/** Обзор сезона: плитки показателей и график очков — всё считается из данных. */

import { $ } from "../lib/dom.js";
import {
  capitalize,
  decimals1Fmt,
  escapeHtml,
  ordinalFeminine,
  ordinalMasculine,
  plural,
  quotedList,
} from "../lib/format.js";

function tileHtml({ variant = "", label, valueHtml, note }) {
  return `<article class="tile${variant ? ` ${variant}` : ""} spotlight">
              <p class="tile-label">${escapeHtml(label)}</p>
              <p class="tile-value">${valueHtml}</p>
              <p class="tile-note">${escapeHtml(note)}</p>
            </article>`;
}

function buildTiles(metrics) {
  const {
    place,
    total,
    games,
    wins,
    draws,
    losses,
    goalsFor,
    goalsAgainst,
    diff,
    points,
    pointsPerGame,
    diffRank,
    ppgRank,
    tiedTeams,
  } = metrics;

  const pointsNote = [`${points} ${plural(points, "очко", "очка", "очков")}`];
  if (tiedTeams.length) {
    pointsNote.push(`столько же, сколько у ${quotedList(tiedTeams)}`);
  }

  const gamesNote = [`${wins} ${plural(wins, "победа", "победы", "побед")}`];
  if (draws > 0) {
    gamesNote.push(`${draws} ${plural(draws, "ничья", "ничьи", "ничьих")}`);
  }
  gamesNote.push(`${losses} ${plural(losses, "поражение", "поражения", "поражений")}`);

  const perGame = (value) => decimals1Fmt.format(games > 0 ? value / games : 0);
  const sign = diff > 0 ? "+" : "";
  const diffAbs = Math.abs(diff);

  return [
    tileHtml({
      variant: "accent",
      label: "Место",
      valueHtml: `${place}<span class="tile-total"> / ${total}</span>`,
      note: pointsNote.join(", "),
    }),
    tileHtml({
      label: "Игры",
      valueHtml: `<span data-count="${games}">${games}</span>`,
      note: gamesNote.join(", "),
    }),
    tileHtml({
      variant: "good",
      label: "Заброшено",
      valueHtml: `<span data-count="${goalsFor}">${goalsFor}</span>`,
      note: `${perGame(goalsFor)} шайбы за матч в среднем`,
    }),
    tileHtml({
      label: "Пропущено",
      valueHtml: `<span data-count="${goalsAgainst}">${goalsAgainst}</span>`,
      note: `${perGame(goalsAgainst)} шайбы за матч в среднем`,
    }),
    tileHtml({
      variant: "good",
      label: "Разница шайб",
      valueHtml: `${sign}<span data-count="${diffAbs}">${diffAbs}</span>`,
      note: `${capitalize(ordinalFeminine(diffRank))} разница в турнире`,
    }),
    tileHtml({
      variant: "warn",
      label: "Очков за игру",
      valueHtml: `<span data-count="${pointsPerGame.toFixed(2)}" data-decimals="2">${decimals1Fmt.format(
        pointsPerGame,
      )}</span>`,
      note: `${capitalize(ordinalMasculine(ppgRank))} показатель в таблице`,
    }),
  ];
}

function renderChart(container, rows) {
  if (!container) {
    return;
  }

  const ranked = [...rows].sort(
    (a, b) => b.points - a.points || b.diff - a.diff || a.name.localeCompare(b.name, "ru"),
  );
  const max = Math.max(1, ...ranked.map((row) => row.points));

  container.innerHTML = ranked
    .map((row, index) => {
      const step = index * 50;
      return `<div class="chart-row" style="--delay: ${step}ms">
                  <span class="track">
                    <span class="fill" style="--w: ${(row.points / max) * 100}%; --delay: ${step}ms"></span>
                    <span class="label">${escapeHtml(row.name)}</span>
                    <span class="value">${row.points}</span>
                  </span>
                </div>`;
    })
    .join("");
}

export function initDashboard({ metrics, rows }) {
  const tilesContainer = $("#stat-tiles");
  const chartContainer = $("#chart-rows");

  if (tilesContainer) {
    tilesContainer.innerHTML = metrics ? buildTiles(metrics).join("") : "";
  }
  renderChart(chartContainer, rows);
}
