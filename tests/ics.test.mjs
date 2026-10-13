import test from "node:test";
import assert from "node:assert/strict";

import { buildIcs, escapeIcsText, foldIcsLine } from "../js/lib/ics.js";

const encoder = new TextEncoder();

const match = {
  id: 22293,
  date: "2026-10-17",
  time: "11:15",
  datetime: new Date("2026-10-17T08:15:00.000Z"),
  home: "Вымпел",
  away: "Центр",
  group: "Группа В",
  tournament: "2016 г.р. 26/27 (формат 4х4)",
  tour: "5 тур",
};

test("время матча записывается в UTC, а не как плавающее локальное", () => {
  const ics = buildIcs(match, { now: new Date("2026-10-13T00:00:00.000Z") });
  assert.match(ics, /DTSTART:20261017T081500Z/);
  assert.match(ics, /DTEND:20261017T094500Z/);
  assert.match(ics, /UID:centr2016-22293@centr-hockey/);
  assert.ok(ics.endsWith("\r\n"));
});

test("строки .ics складываются по 75 октетов с продолжением через пробел", () => {
  const long = `SUMMARY:${"я".repeat(80)}`;
  const folded = foldIcsLine(long).split("\r\n");
  assert.ok(folded.length > 1);
  for (const line of folded) {
    assert.ok(encoder.encode(line).length <= 75, `строка длиннее 75 октетов: ${line.length}`);
  }
  assert.ok(folded[1].startsWith(" "));
});

test("служебные символы экранируются", () => {
  assert.equal(escapeIcsText("a,b;c\\d"), "a\\,b\\;c\\\\d");
  assert.equal(escapeIcsText("строка\nвторая"), "строка\\nвторая");
});

test("описание содержит турнир, группу и тур", () => {
  // длинные строки сложены по 75 октетов — перед проверкой разворачиваем их
  const unfolded = buildIcs(match).replace(/\r\n[ \t]/g, "");
  assert.match(unfolded, /DESCRIPTION:2016 г\.р\. 26\/27 \(формат 4х4\)\\, Группа В\\, 5 тур/);
});

test("без корректной даты сборка падает, а не отдаёт битый файл", () => {
  assert.throws(() => buildIcs({ home: "А", away: "Б" }));
});
