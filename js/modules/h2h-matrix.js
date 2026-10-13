/**
 * Матрица очных встреч. Таблица строится лениво — при первом открытии вкладки,
 * чтобы не создавать 14×14 ячеек при загрузке страницы.
 */

import { $ } from "../lib/dom.js";
import { escapeHtml } from "../lib/format.js";
import { buildH2hLookup, h2hResult } from "../lib/h2h.js";

const STATE_MARK = { win: "В", loss: "П", draw: "Н" };

export function initH2hMatrix({ rows, matches, caption = "" }) {
  const root = $("#h2h-matrix-root");
  if (!root) {
    return { render: () => {} };
  }

  let rendered = false;

  function render() {
    if (rendered) {
      return;
    }

    const teams = rows.map((row) => row.name);
    if (!teams.length) {
      root.innerHTML = "";
      return;
    }

    const lookup = buildH2hLookup(matches, teams);

    const head = teams
      .map((team) => `<th scope="col" class="col-team"><span class="h2h-col-label">${escapeHtml(team)}</span></th>`)
      .join("");

    const body = teams
      .map((rowTeam) => {
        const cells = teams
          .map((colTeam) => {
            const result = h2hResult(lookup, rowTeam, colTeam);

            if (result.kind === "self") {
              return `<td><span class="cell self" aria-label="${escapeHtml(rowTeam)}: та же команда"></span></td>`;
            }
            if (result.kind === "empty") {
              return `<td><span class="cell empty" aria-label="${escapeHtml(rowTeam)} против ${escapeHtml(
                colTeam,
              )}: матч не сыгран"></span></td>`;
            }

            const mark = STATE_MARK[result.state] ?? "";
            return `<td><span class="cell ${result.state}" title="${escapeHtml(rowTeam)} — ${escapeHtml(
              colTeam,
            )}: ${result.score}" aria-label="${escapeHtml(rowTeam)} против ${escapeHtml(colTeam)}: счёт ${
              result.score
            }, ${mark}">${result.score}</span></td>`;
          })
          .join("");

        return `<tr><th scope="row">${escapeHtml(rowTeam)}</th>${cells}</tr>`;
      })
      .join("");

    root.innerHTML = `<table class="h2h-matrix" aria-describedby="h2h-matrix-description">
              <caption class="visually-hidden">${escapeHtml(caption)}</caption>
              <thead>
                <tr>
                  <th class="corner" scope="col">Команда</th>
                  ${head}
                </tr>
              </thead>
              <tbody>
                ${body}
              </tbody>
            </table>`;

    rendered = true;
  }

  return { render, isRendered: () => rendered };
}
