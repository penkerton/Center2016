/**
 * Дни рождения: список строится из состава команды, выгруженного с ФХМ
 * (поле dateOfBirth), и пересчитывается по московскому календарю.
 */

import { $, setText } from "../lib/dom.js";
import { dayNumber, escapeHtml, moscowDayNumber, moscowParts, plural } from "../lib/format.js";

function buildEntry(entry, todayNumber, currentYear) {
  const thisYearNumber = dayNumber(currentYear, entry.birth.month, entry.birth.day);
  const upcoming = todayNumber <= thisYearNumber;
  const nextNumber = upcoming ? thisYearNumber : dayNumber(currentYear + 1, entry.birth.month, entry.birth.day);

  return {
    ...entry,
    upcoming,
    daysUntil: nextNumber - todayNumber,
    daysAgo: todayNumber - thisYearNumber,
    age: currentYear - entry.birth.year,
  };
}

function itemHtml(entry) {
  const days = Math.abs(entry.daysUntil);
  let label;
  let stateClass = "";

  if (entry.upcoming && days === 0) {
    label = "сегодня!";
    stateClass = "today";
  } else if (entry.upcoming) {
    label = `через ${days} ${plural(days, "день", "дня", "дней")}`;
    stateClass = days <= 7 ? "soon" : "";
  } else {
    label = `${entry.daysAgo} ${plural(entry.daysAgo, "день", "дня", "дней")} назад`;
  }

  const classes = ["bday-item", entry.upcoming ? "upcoming" : "past", stateClass].filter(Boolean).join(" ");

  return `<li class="${classes}">
              <span class="who">
                <strong>${escapeHtml(entry.player)}</strong>
                <small>${entry.upcoming ? "исполнится" : "исполнилось"} ${entry.age} ${plural(
                  entry.age,
                  "год",
                  "года",
                  "лет",
                )}</small>
              </span>
              <span class="when">
                <span>${escapeHtml(entry.birthdayRaw)}</span>
                <span class="in">${escapeHtml(label)}</span>
              </span>
            </li>`;
}

export function initBirthdays({ roster, scheduler }) {
  const upcomingList = $("#bday-upcoming");
  const pastList = $("#bday-past");
  const upcomingCount = $("#bday-upcoming-count");
  const pastCount = $("#bday-past-count");

  if (!upcomingList || !pastList) {
    return null;
  }

  const entries = roster.filter((entry) => entry.birth);
  if (!entries.length) {
    upcomingList.innerHTML = '<li class="bday-item"><span class="who"><strong>Данные о днях рождения недоступны</strong></span></li>';
    pastList.innerHTML = "";
    setText(upcomingCount, "0");
    setText(pastCount, "0");
    return null;
  }

  let lastDayNumber = null;

  function render(now) {
    const todayNumber = moscowDayNumber(now);
    const { year: currentYear } = moscowParts(now);
    const birthdays = entries.map((entry) => buildEntry(entry, todayNumber, currentYear));

    const upcomingEntries = birthdays.filter((entry) => entry.upcoming).sort((a, b) => a.daysUntil - b.daysUntil);
    const pastEntries = birthdays.filter((entry) => !entry.upcoming).sort((a, b) => a.daysAgo - b.daysAgo);

    upcomingList.innerHTML =
      upcomingEntries.map(itemHtml).join("") ||
      '<li class="bday-item"><span class="who"><strong>В ближайшее время дней рождения нет</strong></span></li>';
    pastList.innerHTML =
      pastEntries.map(itemHtml).join("") ||
      '<li class="bday-item"><span class="who"><strong>Прошедших дней рождения пока нет</strong></span></li>';

    setText(upcomingCount, upcomingEntries.length);
    setText(pastCount, pastEntries.length);
    lastDayNumber = todayNumber;
  }

  render(new Date());

  scheduler.onMinute((now) => {
    if (moscowDayNumber(now) !== lastDayNumber) {
      render(now);
    }
  });

  return { render };
}
