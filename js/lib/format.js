/**
 * Форматирование и работа с датами.
 *
 * Весь сайт живёт по московскому времени: даты матчей и дней рождения
 * считаются в Europe/Moscow, независимо от часового пояса посетителя.
 */

export const MSK_TIME_ZONE = "Europe/Moscow";
/** Москва с 2014 года не переходит на летнее время — смещение постоянно. */
export const MSK_OFFSET = "+03:00";

export const numberFmt = new Intl.NumberFormat("ru-RU");
export const decimals2Fmt = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const decimals1Fmt = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const withMoscow = (options) => new Intl.DateTimeFormat("ru-RU", { timeZone: MSK_TIME_ZONE, ...options });

export const fullDateFmt = withMoscow({ day: "2-digit", month: "2-digit", year: "numeric" });
export const dateWeekdayFmt = withMoscow({ weekday: "short", day: "numeric", month: "long" });
export const clockFmt = withMoscow({ hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });

const monthDaysFmt = withMoscow({ day: "numeric", month: "long" });

/** Экранирование текста перед вставкой в HTML. */
export function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
  );
}

export function capitalize(value) {
  const text = String(value ?? "");
  return text ? text.charAt(0).toLocaleUpperCase("ru") + text.slice(1) : text;
}

/** «Группа В» → «группа В»: строчная только первая буква, аббревиатуры не портятся. */
export function lowerFirst(value) {
  const text = String(value ?? "");
  return text ? text.charAt(0).toLocaleLowerCase("ru") + text.slice(1) : text;
}

/** «Буран Москва» → «Буран Москва»; список → «А», «Б» и «В». */
export function quotedList(values) {
  const quoted = (Array.isArray(values) ? values : []).map((value) => `«${value}»`);
  if (quoted.length === 0) return "";
  if (quoted.length === 1) return quoted[0];
  const last = quoted.pop();
  return `${quoted.join(", ")} и ${last}`;
}

/** Русская плюрализация: plural(3, "день", "дня", "дней") → "дня". */
export function plural(count, one, few, many) {
  const n = Math.abs(count) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return many;
  if (n1 > 1 && n1 < 5) return few;
  if (n1 === 1) return one;
  return many;
}

const ORDINALS_FEMININE = [
  "первая", "вторая", "третья", "четвёртая", "пятая", "шестая", "седьмая", "восьмая", "девятая", "десятая",
  "одиннадцатая", "двенадцатая", "тринадцатая", "четырнадцатая", "пятнадцатая", "шестнадцатая", "семнадцатая",
  "восемнадцатая", "девятнадцатая", "двадцатая",
];
const ORDINALS_MASCULINE = [
  "первый", "второй", "третий", "четвёртый", "пятый", "шестой", "седьмой", "восьмой", "девятый", "десятый",
  "одиннадцатый", "двенадцатый", "тринадцатый", "четырнадцатый", "пятнадцатый", "шестнадцатый", "семнадцатый",
  "восемнадцатый", "девятнадцатый", "двадцатый",
];

/** 5 → «пятая» (для слов женского рода: разница, команда). */
export function ordinalFeminine(rank) {
  return ORDINALS_FEMININE[rank - 1] ?? `${rank}-я`;
}

/** 4 → «четвёртый» (для слов мужского рода: показатель). */
export function ordinalMasculine(rank) {
  return ORDINALS_MASCULINE[rank - 1] ?? `${rank}-й`;
}

/** Разбор даты и времени матча как московских: «2026-10-17» + «11:15» → Date. */
export function parseMoscowDateTime(date, time) {
  const isoDate = String(date ?? "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) {
    return null;
  }
  const clock = /^\d{2}:\d{2}$/.test(String(time ?? "")) ? String(time) : "00:00";
  const parsed = new Date(`${isoDate}T${clock}:00${MSK_OFFSET}`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

const MSK_PARTS_FMT = new Intl.DateTimeFormat("en-GB", {
  timeZone: MSK_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** Календарные части момента в московском времени. */
export function moscowParts(date = new Date()) {
  const parts = MSK_PARTS_FMT.formatToParts(date);
  const value = (type) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return {
    year: value("year"),
    month: value("month"),
    day: value("day"),
    hour: value("hour"),
    minute: value("minute"),
  };
}

/** Номер московских суток (целое число дней) — удобно для разницы дат. */
export function moscowDayNumber(date = new Date()) {
  const { year, month, day } = moscowParts(date);
  return dayNumber(year, month, day);
}

export function dayNumber(year, month, day) {
  return Math.round(Date.UTC(year, month - 1, day) / 86400000);
}

/** Разница в календарных днях между двумя моментами по московскому календарю. */
export function daysBetween(from, to) {
  return Math.round(moscowDayNumber(to) - moscowDayNumber(from));
}

/** Разбор «18.10.2016» → { year, month, day } | null. */
export function parseRuDate(value) {
  const match = String(value ?? "").trim().match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (!match) {
    return null;
  }
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return null;
  }
  return { year, month, day };
}

/** «2026-10-17» → «17 октября» (московский календарь). */
export function formatMatchDay(date) {
  const parsed = parseMoscowDateTime(date, "00:00");
  return parsed ? monthDaysFmt.format(parsed) : String(date ?? "");
}

/** Дата и время выгрузки данных в московском времени. */
export function formatGeneratedAt(isoString) {
  const parsed = new Date(String(isoString ?? ""));
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  const { year, month, day } = moscowParts(parsed);
  const time = clockFmt.format(parsed).slice(0, 5);
  return {
    date: `${String(day).padStart(2, "0")}.${String(month).padStart(2, "0")}.${year}`,
    time,
    label: `${String(day).padStart(2, "0")}.${String(month).padStart(2, "0")}.${year}, ${time} МСК`,
  };
}
