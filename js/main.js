/**
 * Точка входа приложения.
 *
 * Порядок важен: сначала данные и вся динамическая разметка, затем анимации
 * появления (они навешиваются на уже готовые элементы), затем шапка и таймер.
 */

import { $, onReady } from "./lib/dom.js";
import { readSiteData } from "./lib/data.js";
import { createScheduler } from "./lib/scheduler.js";
import { computeStandings, teamMetrics } from "./lib/standings.js";
import { initTabs } from "./lib/tabs.js";
import { initBirthdays } from "./modules/birthdays.js";
import { initDashboard } from "./modules/dashboard.js";
import { initH2hMatrix } from "./modules/h2h-matrix.js";
import { initHeader } from "./modules/header.js";
import { initMatches } from "./modules/matches.js";
import { initMeta } from "./modules/meta.js";
import { initMotion } from "./modules/motion.js";
import { initStandingsTable } from "./modules/standings-table.js";
import { initStats } from "./modules/stats.js";
import { initTheme } from "./modules/theme.js";

function start() {
  const scheduler = createScheduler();

  try {
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const canHover = window.matchMedia?.("(hover: hover)").matches ?? false;
    const data = readSiteData();
    const rows = data.primary ? computeStandings(data.primary.teams, data.groupMatches) : [];
    const metrics = teamMetrics(rows, data.ownTeamName);

    initTheme();
    initMeta({ meta: data.meta, primary: data.primary, ownTeamName: data.ownTeamName, scheduler });
    initDashboard({ metrics, rows });

    const seasonLabel = data.meta?.season?.label ?? "";
    const matrix = initH2hMatrix({
      rows,
      matches: data.groupMatches,
      caption: ["Матрица очных встреч", data.primary?.groupName, data.meta?.season?.yearLabel]
        .filter(Boolean)
        .join(", "),
    });
    initStandingsTable({
      rows,
      ownTeamName: data.ownTeamName,
      caption: ["Турнирная таблица", data.primary?.groupName, data.meta?.season?.yearLabel, data.primary?.stageName]
        .filter(Boolean)
        .join(", "),
    });
    initMatches({
      ownMatches: data.ownMatches,
      ownTeamName: data.ownTeamName,
      primary: data.primary,
      scheduler,
    });
    initStats({
      players: data.players,
      caption: ["Статистика игроков", data.meta?.season?.yearLabel, seasonLabel].filter(Boolean).join(", "),
    });
    initBirthdays({ roster: data.roster, scheduler });

    initTabs($("#standings"), {
      onChange: (index) => {
        if (index === 1) {
          matrix.render();
        }
      },
    });
    initTabs($("#matches"));
    initTabs($("#birthdays"));

    initMotion({ reduceMotion, canHover });
    initHeader({ scheduler });
    // Отметка для страховки в <head>: страница инициализирована, анимации уместны
    document.documentElement.dataset.appReady = "1";
    scheduler.start();
  } catch (error) {
    // Данные или разметка оказались неожиданными: показываем контент без анимаций
    // (класс has-js скрывает блоки .reveal до появления).
    document.documentElement.classList.remove("has-js");
    console.error("Не удалось инициализировать страницу:", error);
  }
}

onReady(start);
