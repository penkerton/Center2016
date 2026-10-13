/**
 * Статистика игроков турниров: фильтры по группе/команде, поиск, сортировка
 * по любой колонке и постраничный вывод.
 */

import { $, $$ } from "../lib/dom.js";
import { decimals2Fmt, escapeHtml, numberFmt } from "../lib/format.js";
import { roleLabel } from "../lib/data.js";

const EMPTY_ROW = (columns) =>
  `<tr class="empty-row"><td colspan="${columns}">По выбранным фильтрам игроков не найдено. Попробуйте изменить запрос.</td></tr>`;

function fillFilterOptions(selectElement, values) {
  [...values]
    .sort((left, right) => String(left).localeCompare(String(right), "ru", { sensitivity: "base", numeric: true }))
    .forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      selectElement.append(option);
    });
}

function highlightName(name, query) {
  const text = String(name);
  if (!query) {
    return escapeHtml(text);
  }
  const index = text.toLocaleLowerCase("ru").indexOf(query);
  if (index === -1) {
    return escapeHtml(text);
  }
  return `${escapeHtml(text.slice(0, index))}<mark>${escapeHtml(text.slice(index, index + query.length))}</mark>${escapeHtml(
    text.slice(index + query.length),
  )}`;
}

function roleCellHtml(role) {
  const label = roleLabel(role);
  if (!label) {
    return "—";
  }
  return `<abbr title="${escapeHtml(label.full)}">${escapeHtml(label.short)}</abbr>`;
}

export function initStats({ players, caption = "" }) {
  const table = $("#goals-table");
  const tableBody = $("#goals-table-body");
  const groupFilter = $("#group-filter");
  const teamFilter = $("#team-filter");
  const playerSearch = $("#player-search");
  const pageSizeSelect = $("#page-size");
  const prevPageButton = $("#stats-prev-page");
  const nextPageButton = $("#stats-next-page");
  const pagesContainer = $("#stats-pages");
  const statsStatus = $("#stats-status");

  if (!table || !tableBody) {
    return null;
  }

  const headCells = $$("thead th", table);
  const columnCount = headCells.length;
  const captionNode = $("caption", table);
  if (captionNode && caption) {
    captionNode.textContent = caption;
  }

  if (!players.length) {
    tableBody.innerHTML = `<tr class="empty-row"><td colspan="${columnCount}">Не удалось загрузить данные статистики игроков.</td></tr>`;
    if (statsStatus) {
      statsStatus.textContent = "Данные недоступны";
    }
    return null;
  }

  const rankedPlayers = [...players]
    .sort((a, b) => b.goals - a.goals || b.games - a.games || a.player.localeCompare(b.player, "ru"))
    .map((item, index) => ({
      ...item,
      position: index + 1,
      ppg: item.games > 0 ? item.goals / item.games : 0,
    }));

  let currentPage = 1;
  let pageSize = Number(pageSizeSelect?.value || 15);
  let sort = { key: "goals", direction: -1 };
  let searchTimer = 0;

  function filteredPlayers() {
    const group = groupFilter?.value || "all";
    const team = teamFilter?.value || "all";
    const query = (playerSearch?.value || "").trim().toLocaleLowerCase("ru");

    const filtered = rankedPlayers
      .filter((item) => (group === "all" ? true : item.group === group))
      .filter((item) => (team === "all" ? true : item.team === team))
      .filter((item) => (query ? item.player.toLocaleLowerCase("ru").includes(query) : true));

    const direction = sort.direction;
    return filtered.sort((a, b) => {
      if (sort.key === "player" || sort.key === "group" || sort.key === "team" || sort.key === "role") {
        const left = sort.key === "role" ? roleLabel(a.role)?.full ?? "" : String(a[sort.key]);
        const right = sort.key === "role" ? roleLabel(b.role)?.full ?? "" : String(b[sort.key]);
        return left.localeCompare(right, "ru") * direction;
      }
      return ((a[sort.key] || 0) - (b[sort.key] || 0)) * direction;
    });
  }

  function renderPageButtons(totalPages) {
    if (!pagesContainer) {
      return;
    }
    const windowSize = 5;
    let start = Math.max(1, currentPage - Math.floor(windowSize / 2));
    const end = Math.min(totalPages, start + windowSize - 1);
    start = Math.max(1, end - windowSize + 1);

    const buttons = [];
    for (let page = start; page <= end; page += 1) {
      buttons.push(
        `<button type="button" data-page="${page}"${page === currentPage ? ' aria-current="page"' : ""}>${page}</button>`,
      );
    }
    pagesContainer.innerHTML = buttons.join("");
  }

  function updateSortAria() {
    headCells.forEach((cell) => {
      if (cell.dataset.key === sort.key) {
        cell.setAttribute("aria-sort", sort.direction === 1 ? "ascending" : "descending");
      } else {
        cell.removeAttribute("aria-sort");
      }
    });
  }

  function render() {
    const query = (playerSearch?.value || "").trim().toLocaleLowerCase("ru");
    const filtered = filteredPlayers();
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    currentPage = Math.min(currentPage, totalPages);

    if (!filtered.length) {
      tableBody.innerHTML = EMPTY_ROW(columnCount);
      if (statsStatus) statsStatus.textContent = "Найдено: 0";
      if (prevPageButton) prevPageButton.disabled = true;
      if (nextPageButton) nextPageButton.disabled = true;
      if (pagesContainer) pagesContainer.innerHTML = "";
      return;
    }

    const startIndex = (currentPage - 1) * pageSize;
    const pageItems = filtered.slice(startIndex, startIndex + pageSize);

    tableBody.innerHTML = pageItems
      .map((item) => {
        const role = roleLabel(item.role);
        return `<tr>
                <td class="num cell-place" data-label="Место"><span class="rank">${item.position}</span></td>
                <td class="cell-player" data-label="Игрок">
                  <span class="player-name">${highlightName(item.player, query)}</span>
                  <span class="player-sub"><span class="player-team">${escapeHtml(item.team)}</span>${
                    role ? `<span class="player-role">${escapeHtml(role.short)}</span>` : ""
                  }</span>
                </td>
                <td class="cell-role" data-label="Амплуа">${roleCellHtml(item.role)}</td>
                <td class="cell-group" data-label="Группа">${escapeHtml(item.group)}</td>
                <td class="cell-team" data-label="Команда">${escapeHtml(item.team)}</td>
                <td class="num cell-games" data-label="Игры">${numberFmt.format(item.games)}</td>
                <td class="num cell-goals" data-label="Голы">${numberFmt.format(item.goals)}<span class="ppg-inline"> / ${decimals2Fmt.format(
                  item.ppg,
                )}</span></td>
                <td class="num cell-ppg" data-label="PPG">${decimals2Fmt.format(item.ppg)}</td>
              </tr>`;
      })
      .join("");

    table.classList.add("as-cards");

    const from = startIndex + 1;
    const to = Math.min(startIndex + pageSize, filtered.length);
    if (statsStatus) {
      statsStatus.textContent = `Показано ${from}–${to} из ${filtered.length} · страница ${currentPage} из ${totalPages}`;
    }
    if (prevPageButton) prevPageButton.disabled = currentPage <= 1;
    if (nextPageButton) nextPageButton.disabled = currentPage >= totalPages;
    renderPageButtons(totalPages);
  }

  const resetPaginationAndRender = () => {
    currentPage = 1;
    render();
  };

  if (groupFilter && teamFilter) {
    fillFilterOptions(groupFilter, new Set(rankedPlayers.map((item) => item.group).filter(Boolean)));
    fillFilterOptions(teamFilter, new Set(rankedPlayers.map((item) => item.team).filter(Boolean)));

    groupFilter.addEventListener("change", resetPaginationAndRender);
    teamFilter.addEventListener("change", resetPaginationAndRender);
  }

  pageSizeSelect?.addEventListener("change", () => {
    pageSize = Number(pageSizeSelect.value) || 15;
    resetPaginationAndRender();
  });

  playerSearch?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(resetPaginationAndRender, 180);
  });

  prevPageButton?.addEventListener("click", () => {
    if (currentPage > 1) {
      currentPage -= 1;
      render();
    }
  });

  nextPageButton?.addEventListener("click", () => {
    const totalPages = Math.max(1, Math.ceil(filteredPlayers().length / pageSize));
    if (currentPage < totalPages) {
      currentPage += 1;
      render();
    }
  });

  pagesContainer?.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("button[data-page]") : null;
    if (!button) {
      return;
    }
    currentPage = Number(button.dataset.page);
    render();
  });

  $("#stats-reset")?.addEventListener("click", () => {
    if (groupFilter) groupFilter.value = "all";
    if (teamFilter) teamFilter.value = "all";
    if (playerSearch) playerSearch.value = "";
    sort = { key: "position", direction: 1 };
    updateSortAria();
    resetPaginationAndRender();
  });

  headCells.forEach((th) => {
    const key = th.dataset.key;
    if (!key) {
      return;
    }
    th.tabIndex = 0;

    const applySort = () => {
      sort =
        sort.key === key
          ? { key, direction: sort.direction * -1 }
          : { key, direction: th.dataset.sort === "text" ? 1 : -1 };
      updateSortAria();
      resetPaginationAndRender();
    };

    th.addEventListener("click", applySort);
    th.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        applySort();
      }
    });
  });

  updateSortAria();
  render();

  return { render };
}
