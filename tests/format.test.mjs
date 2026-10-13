import test from "node:test";
import assert from "node:assert/strict";

import {
  daysBetween,
  escapeHtml,
  formatGeneratedAt,
  moscowDayNumber,
  ordinalFeminine,
  ordinalMasculine,
  parseMoscowDateTime,
  parseRuDate,
  plural,
  quotedList,
} from "../js/lib/format.js";

test("plural выбирает форму по правилам русского языка", () => {
  assert.equal(plural(1, "день", "дня", "дней"), "день");
  assert.equal(plural(3, "день", "дня", "дней"), "дня");
  assert.equal(plural(5, "день", "дня", "дней"), "дней");
  assert.equal(plural(11, "день", "дня", "дней"), "дней");
  assert.equal(plural(21, "день", "дня", "дней"), "день");
  assert.equal(plural(0, "очко", "очка", "очков"), "очков");
});

test("порядковые числительные", () => {
  assert.equal(ordinalFeminine(1), "первая");
  assert.equal(ordinalFeminine(5), "пятая");
  assert.equal(ordinalMasculine(4), "четвёртый");
  assert.equal(ordinalFeminine(25), "25-я");
});

test("список имён в кавычках", () => {
  assert.equal(quotedList(["Буран Москва"]), "«Буран Москва»");
  assert.equal(quotedList(["А", "Б"]), "«А» и «Б»");
  assert.equal(quotedList(["А", "Б", "В"]), "«А», «Б» и «В»");
  assert.equal(quotedList([]), "");
});

test("время матча трактуется как московское", () => {
  const date = parseMoscowDateTime("2026-10-17", "11:15");
  assert.equal(date.toISOString(), "2026-10-17T08:15:00.000Z");
  assert.equal(parseMoscowDateTime("2026-10-17", "").toISOString(), "2026-10-16T21:00:00.000Z");
  assert.equal(parseMoscowDateTime("мусор", "11:15"), null);
});

test("московский календарь не зависит от пояса посетителя", () => {
  // 2026-10-13T22:30Z — в Москве уже 14 октября
  const lateEvening = new Date("2026-10-13T22:30:00.000Z");
  const noon = new Date("2026-10-13T09:00:00.000Z");
  assert.equal(daysBetween(noon, lateEvening), 1);
  assert.equal(moscowDayNumber(lateEvening) - moscowDayNumber(noon), 1);
});

test("дата выгрузки переводится в московское время", () => {
  const formatted = formatGeneratedAt("2026-10-13T15:35:32.219Z");
  assert.equal(formatted.date, "13.10.2026");
  assert.equal(formatted.time, "18:35");
  assert.equal(formatted.label, "13.10.2026, 18:35 МСК");
  assert.equal(formatGeneratedAt("не дата"), null);
});

test("разбор даты рождения в формате ФХМ", () => {
  assert.deepEqual(parseRuDate("18.10.2016"), { year: 2016, month: 10, day: 18 });
  assert.equal(parseRuDate("2016-10-18"), null);
  assert.equal(parseRuDate(""), null);
});

test("экранирование HTML", () => {
  assert.equal(escapeHtml('<b>"x" & \'y\'</b>'), "&lt;b&gt;&quot;x&quot; &amp; &#39;y&#39;&lt;/b&gt;");
});
