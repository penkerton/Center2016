/** Турнирная таблица: строки строятся из расчёта по матчам, сортировка — по шапке. */

import { $, $$ } from "../lib/dom.js";
import { escapeHtml, numberFmt } from "../lib/format.js";

/** Порядок колонок совпадает с <thead> в разметке. */
const COLUMN_KEYS = ["place", "team", "games", "wins", "draws", "losses", "goalsFor", "goalsAgainst", "diff", "points"];

export function initStandingsTable({ rows, ownTeamName, caption = "" }) {
  const table = $("#standings-table");
  if (!table) {
    return null;
  }

  const captionNode = $("caption", table);
  if (captionNode && caption) {
    captionNode.textContent = caption;
  }

  const tbody = $("tbody", table);
  const headCells = $$("thead th", table);
  const labels = headCells.map((th) => th.textContent.trim());
  const places = new Map(rows.map((row, index) => [row.name, index + 1]));

  let sort = { key: "", direction: 1 };

  const placeOf = (row) => places.get(row.name) ?? 0;

  function visibleRows() {
    if (!sort.key) {
      return rows;
    }
    const direction = sort.direction;
    return [...rows].sort((a, b) => {
      if (sort.key === "team") return a.name.localeCompare(b.name, "ru") * direction;
      if (sort.key === "place") return (placeOf(a) - placeOf(b)) * direction;
      return (Number(a[sort.key] ?? 0) - Number(b[sort.key] ?? 0)) * direction;
    });
  }

  function rowHtml(row) {
    const place = placeOf(row);
    const medal = place <= 3 ? ` medal-${place}` : "";
    const own = row.name === ownTeamName;
    const values = [row.games, row.wins, row.draws, row.losses, row.goalsFor, row.goalsAgainst, row.diff, row.points];

    return `<tr>
              <td class="num cell-place" data-label="${escapeHtml(labels[0])}"><span class="rank${medal}">${place}</span></td>
              <td class="cell-team" data-label="${escapeHtml(labels[1])}">${escapeHtml(row.name)}${
                own ? ' <span class="badge accent">мы</span>' : ""
              }</td>
              ${values
                .map(
                  (value, index) =>
                    `<td class="num" data-label="${escapeHtml(labels[index + 2] ?? "")}">${numberFmt.format(value)}</td>`,
                )
                .join("")}
            </tr>`;
  }

  function render() {
    tbody.innerHTML = visibleRows().map(rowHtml).join("");
  }

  headCells.forEach((th, index) => {
    if (!th.dataset.sort) {
      return;
    }
    th.tabIndex = 0;

    const applySort = () => {
      const key = COLUMN_KEYS[index];
      sort =
        sort.key === key
          ? { key, direction: sort.direction * -1 }
          : { key, direction: th.dataset.sort === "text" ? 1 : -1 };

      headCells.forEach((cell, cellIndex) => {
        if (cellIndex === index) {
          cell.setAttribute("aria-sort", sort.direction === 1 ? "ascending" : "descending");
        } else {
          cell.removeAttribute("aria-sort");
        }
      });

      render();
    };

    th.addEventListener("click", applySort);
    th.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        applySort();
      }
    });
  });

  render();

  return { render };
}
