/**
 * Подписи и ссылки, которые зависят от данных: дата выгрузки, время следующего
 * обновления, тексты героя и ссылки на карточку команды.
 */

import { $, $$, setText } from "../lib/dom.js";
import { escapeHtml, formatGeneratedAt, lowerFirst, moscowParts } from "../lib/format.js";

/** GitHub Actions обновляет данные каждые 3 часа (см. .github/workflows/update-data.yml). */
const UPDATE_SLOT_HOURS = [0, 3, 6, 9, 12, 15, 18, 21];

export function nextUpdateLabel(now = new Date()) {
  const { hour, minute } = moscowParts(now);
  const currentMinutes = hour * 60 + minute;
  const nextSlot = UPDATE_SLOT_HOURS.find((slot) => slot * 60 > currentMinutes);
  const hourValue = nextSlot === undefined ? UPDATE_SLOT_HOURS[0] : nextSlot;
  return `${String(hourValue).padStart(2, "0")}:00 МСК`;
}

function renderHeroTexts({ meta, primary }) {
  const season = meta?.season ?? {};
  const groupName = String(primary?.groupName ?? "").trim();

  const eyebrow = $("#hero-eyebrow");
  if (eyebrow && season.label) {
    setText(eyebrow, `ФХМ · Сезон ${season.label}`);
  }

  const lead = $("#hero-lead");
  const parts = [];
  if (season.yearLabel) parts.push(`Турнир ${season.yearLabel}`);
  if (season.format) parts.push(`формат ${season.format}`);
  if (groupName) parts.push(lowerFirst(groupName));

  if (lead && parts.length >= 2) {
    const stage = lowerFirst(season.stage);
    const tail = [stage, season.code ? `сезона ${season.code}` : ""].filter(Boolean).join(" ");
    setText(
      lead,
      `Команда из Москвы, выступающая в системе Федерации хоккея Москвы. ${parts.join(", ")}${
        tail ? ` — ${tail}` : ""
      }.`,
    );
  }

  const chips = $("#hero-chips");
  if (chips) {
    const values = ["Москва", season.yearLabel, season.format ? `Формат ${season.format}` : "", groupName].filter(Boolean);
    chips.innerHTML = values
      .map((value, index) => `<span class="badge${index === 0 ? " accent" : ""}">${escapeHtml(value)}</span>`)
      .join("");
  }
}

/** Подпись под заголовком «Обзор сезона»: команда, турнир, формат, группа и дата данных. */
function renderDashboardNote({ meta, primary, ownTeamName }) {
  const note = $("#dashboard-note");
  if (!note || !ownTeamName) {
    return;
  }

  const season = meta?.season ?? {};
  const parts = [];
  if (season.yearLabel) parts.push(`турнире ${season.yearLabel}`);
  if (season.format) parts.push(`формат ${season.format}`);
  if (primary?.groupName) parts.push(lowerFirst(primary.groupName));

  note.innerHTML = `Показатели «${escapeHtml(ownTeamName)}»${parts.length ? ` в ${parts.join(", ")}` : ""}. Данные обновлены <span class="data-snapshot-date">—</span>.`;
}

export function initMeta({ meta, primary, ownTeamName, scheduler }) {
  const generated = formatGeneratedAt(meta?.generatedAt);

  if (meta) {
    renderHeroTexts({ meta, primary });
    renderDashboardNote({ meta, primary, ownTeamName });
  }

  const applySnapshot = () => {
    $$(".data-snapshot-date").forEach((node) => {
      node.textContent = generated ? generated.date : "—";
    });
  };
  applySnapshot();

  const applyNextUpdate = (now) => {
    const node = $("#next-update-time");
    if (node) {
      node.textContent = nextUpdateLabel(now);
    }
  };
  applyNextUpdate(new Date());
  scheduler.onMinute((now) => applyNextUpdate(now));

  const teamUrl = String(meta?.source?.teamUrl ?? "");
  if (teamUrl) {
    $$("[data-team-link]").forEach((link) => {
      link.href = teamUrl;
    });
  }

  const sourceLabel = $("#source-label");
  if (sourceLabel && meta?.source?.label) {
    setText(sourceLabel, meta.source.label);
  }

  return { snapshotLabel: generated?.label ?? "" };
}
