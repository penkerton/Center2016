/**
 * Матчи: карточка ближайшего матча с обратным отсчётом, списки предстоящих и
 * прошедших игр, добавление в календарь (.ics).
 *
 * Сыгранные матчи показывают счёт отдельным контролом, а не цифрами в строке
 * с названиями команд.
 */

import { $, downloadFile } from "../lib/dom.js";
import { dateWeekdayFmt, daysBetween, escapeHtml, moscowDayNumber, plural } from "../lib/format.js";
import { buildIcs } from "../lib/ics.js";

const CALENDAR_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M8 3v4M16 3v4M3 10h18" /></svg>`;

function dayState(match, now) {
  const days = daysBetween(now, match.datetime);
  if (days === 0) {
    return { state: "today", text: "сегодня" };
  }
  if (days > 0) {
    return { state: "future", text: `через ${days} ${plural(days, "день", "дня", "дней")}` };
  }
  const past = Math.abs(days);
  return { state: "past", text: `${past} ${plural(past, "день", "дня", "дней")} назад` };
}

function whenLabel(match) {
  const date = dateWeekdayFmt.format(match.datetime);
  return match.hasTime ? `${date}, ${match.time}` : `${date}, время уточняется`;
}

function matchHtml(match, { ownTeamName, primary, now, isNext }) {
  const venue = match.home === ownTeamName ? "home" : "away";
  const played = match.hasScore;
  const state = played ? { state: "past", text: "" } : dayState(match, now);
  const chip = played
    ? `<span class="countdown-chip past score">счёт ${match.homeGoals}:${match.awayGoals}</span>`
    : `<span class="countdown-chip ${state.state === "future" ? "" : state.state}">${escapeHtml(state.text)}</span>`;

  const calendarButton =
    !played && match.hasTime
      ? `<button class="btn-mini" type="button" data-ics>В календарь</button>`
      : "";

  const metaParts = [match.group || primary?.groupName, match.tournament].filter(Boolean);

  return `<li class="match ${venue === "home" ? "is-home" : "is-away"}${isNext ? " is-next" : ""}${
    played || state.state === "past" ? " is-past" : ""
  }" data-state="${played ? "past" : state.state}" data-venue="${venue}" title="${escapeHtml(metaParts.join(" · "))}">
              <div class="match-top">
                <span class="badge${venue === "home" ? " accent" : ""}">${venue === "home" ? "дома" : "в гостях"}</span>
                <span class="when">${CALENDAR_ICON}${escapeHtml(whenLabel(match))}</span>
                ${isNext ? '<span class="badge accent">следующий</span>' : ""}
              </div>
              <div class="match-teams">
                <span>${escapeHtml(match.home)}</span>
                <span class="vs">vs</span>
                <span>${escapeHtml(match.away)}</span>
              </div>
              <div class="match-foot">
                ${chip}
                <span class="spacer"></span>
                ${calendarButton}
              </div>
            </li>`;
}

export function initMatches({ ownMatches, ownTeamName, primary, scheduler }) {
  const upcomingList = $('[data-match-list="upcoming"]');
  const pastList = $('[data-match-list="past"]');
  const upcomingEmpty = $('[data-empty="upcoming"]');
  const pastEmpty = $('[data-empty="past"]');
  const heroTeams = $(".next-match .teams");
  const heroMeta = $(".next-match .meta");
  const countdown = $("#countdown");

  const unplayed = ownMatches.filter((match) => !match.hasScore);
  const nextMatch = unplayed[0] ?? null;
  let listSignature = "";
  let countdownCache = "";

  const todayNumber = () => moscowDayNumber(new Date());
  const isUpcoming = (match) => moscowDayNumber(match.datetime) >= todayNumber();

  const upcoming = () => unplayed.filter(isUpcoming);
  const past = () =>
    ownMatches
      .filter((match) => match.hasScore || !isUpcoming(match))
      .sort((a, b) => b.datetime - a.datetime);

  function renderList(list, matches, now) {
    if (!list) {
      return;
    }
    list.innerHTML = matches
      .map((match) => matchHtml(match, { ownTeamName, primary, now, isNext: match === nextMatch }))
      .join("");
    Array.from(list.children).forEach((element, index) => {
      const match = matches[index];
      if (match) {
        element.dataset.matchId = String(match.id);
      }
    });
  }

  function renderLists(now, force = false) {
    const upcomingMatches = upcoming();
    const pastMatches = past();
    const signature = [
      upcomingMatches.length,
      pastMatches.length,
      ...upcomingMatches.map((match) => dayState(match, now).state),
    ].join("|");
    if (!force && signature === listSignature) {
      return;
    }
    listSignature = signature;

    renderList(upcomingList, upcomingMatches, now);
    renderList(pastList, pastMatches, now);
    if (upcomingEmpty) upcomingEmpty.hidden = upcomingMatches.length > 0;
    if (pastEmpty) pastEmpty.hidden = pastMatches.length > 0;
  }

  const countdownFields = {
    days: $('[data-cd="days"]'),
    hours: $('[data-cd="hours"]'),
    minutes: $('[data-cd="minutes"]'),
    seconds: $('[data-cd="seconds"]'),
  };

  /* Подписи в отсчёте согласуются с числом: «3 дня», «16 часов», «1 минута». */
  const countdownLabels = {
    days: $('[data-cd-label="days"]'),
    hours: $('[data-cd-label="hours"]'),
    minutes: $('[data-cd-label="minutes"]'),
    seconds: $('[data-cd-label="seconds"]'),
  };
  const countdownPlurals = {
    days: (value) => plural(value, "день", "дня", "дней"),
    hours: (value) => plural(value, "час", "часа", "часов"),
    minutes: (value) => plural(value, "минута", "минуты", "минут"),
    seconds: (value) => plural(value, "секунда", "секунды", "секунд"),
  };

  function heroMetaText(match, expired) {
    const venue = match.home === ownTeamName ? "home" : "away";
    const parts = [
      whenLabel(match),
      match.group || primary?.groupName,
      match.tournament,
      venue === "home" ? "дома" : "в гостях",
      expired ? "матч идёт или завершён" : "",
    ].filter(Boolean);
    return parts.join(" · ");
  }

  function renderHero(now) {
    if (!heroTeams || !heroMeta) {
      return;
    }

    if (!nextMatch) {
      heroTeams.innerHTML = "<span>Расписание уточняется</span>";
      heroMeta.textContent = "Данные о матчах появятся после публикации календаря";
      if (countdown) {
        countdown.hidden = true;
      }
      return;
    }

    heroTeams.innerHTML = `<span>${escapeHtml(nextMatch.home)}</span><span class="vs">vs</span><span>${escapeHtml(
      nextMatch.away,
    )}</span>`;

    const expired = nextMatch.hasTime && nextMatch.datetime - now <= 0;
    heroMeta.textContent = heroMetaText(nextMatch, expired);
    if (countdown) {
      countdown.hidden = !nextMatch.hasTime;
    }
  }

  function renderCountdown(now) {
    if (!countdown || !nextMatch || !nextMatch.hasTime || countdown.hidden) {
      return;
    }

    const diff = nextMatch.datetime - now;
    const totalSeconds = Math.max(0, Math.floor(diff / 1000));
    const parts = {
      days: Math.floor(totalSeconds / 86400),
      hours: Math.floor((totalSeconds % 86400) / 3600),
      minutes: Math.floor((totalSeconds % 3600) / 60),
      seconds: totalSeconds % 60,
    };
    const pad = (value) => String(value).padStart(2, "0");
    const display = {
      days: String(parts.days),
      hours: pad(parts.hours),
      minutes: pad(parts.minutes),
      seconds: pad(parts.seconds),
    };

    const signature = Object.values(display).join(":");
    if (signature === countdownCache) {
      return;
    }
    countdownCache = signature;

    Object.entries(display).forEach(([key, value]) => {
      const field = countdownFields[key];
      if (field) {
        field.textContent = value;
      }
      const label = countdownLabels[key];
      if (label) {
        label.textContent = countdownPlurals[key](parts[key]);
      }
    });
  }

  function initialiseCalendarButtons(list) {
    list?.addEventListener("click", (event) => {
      const button = event.target instanceof Element ? event.target.closest("[data-ics]") : null;
      if (!button) {
        return;
      }
      const element = button.closest("li.match");
      const match = ownMatches.find((item) => String(item.id) === element?.dataset.matchId);
      if (!match) {
        return;
      }

      downloadFile(
        `centr-2016-${match.date}.ics`,
        buildIcs(match, { uidDomain: "centr-hockey" }),
        "text/calendar;charset=utf-8",
      );

      button.textContent = "Файл готов";
      window.setTimeout(() => {
        button.textContent = "В календарь";
      }, 2000);
    });
  }

  renderHero(new Date());
  renderLists(new Date(), true);
  renderCountdown(new Date());
  initialiseCalendarButtons(upcomingList);

  scheduler.onSecond((now) => renderCountdown(now));
  scheduler.onMinute((now) => {
    renderLists(now);
    renderHero(now);
    renderCountdown(now);
  });

  return { nextMatch };
}
