import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { renderMarkdown, renderInline, escapeHtml, timecodeToSeconds } from "../scripts/lib/markdown.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const reviewsDir = path.join(root, "reviews");
const reviewDir = path.join(reviewsDir, "22449");

const markdown = fs.readFileSync(path.join(reviewDir, "22449-review.md"), "utf8");
const data = JSON.parse(fs.readFileSync(path.join(reviewDir, "22449-review-data.json"), "utf8"));

test("markdown: заголовки, таблицы, списки и инлайн-разметка", () => {
  const { html, headings } = renderMarkdown(
    [
      "## 1. Тест",
      "",
      "Абзац с **жирным**, *курсивом* и `кодом`.",
      "",
      "| A | B |",
      "|---|---:|",
      "| 1 | 2 |",
      "",
      "- один",
      "- два",
      "",
      "> цитата",
      "",
      "```js",
      "const a = 1;",
      "```",
    ].join("\n"),
  );

  assert.equal(headings.length, 1);
  assert.equal(headings[0].level, 2);
  assert.match(html, /<h2 id="1-test">1\. Тест<\/h2>/);
  assert.match(html, /<strong>жирным<\/strong>/);
  assert.match(html, /<em>курсивом<\/em>/);
  assert.match(html, /<code>кодом<\/code>/);
  assert.match(html, /<table class="md-table">/);
  assert.match(html, /text-align:right/);
  assert.match(html, /<ul class="md-list">/);
  assert.match(html, /<blockquote>/);
  assert.match(html, /<pre><code class="language-js">/);
});

test("markdown: картинки и ссылки не экранируются повторно", () => {
  assert.equal(renderInline("![кадр](evidence/a.jpg)"), '<img class="md-image" src="evidence/a.jpg" alt="кадр" loading="lazy" decoding="async">');
  assert.match(renderInline("[видео](https://vk.com/video-1_2)"), /rel="noopener noreferrer"/);
  assert.equal(escapeHtml('a & b < c "d"'), "a &amp; b &lt; c &quot;d&quot;");
  assert.equal(timecodeToSeconds("21:05"), 1265);
});

test("markdown: HTML из источника экранируется", () => {
  const { html } = renderMarkdown("Текст <script>alert(1)</script> и <b>тег</b>");
  assert.ok(!html.includes("<script>"), "скрипт не должен попадать в HTML");
  assert.match(html, /&lt;script&gt;/);
});

test("разбор 22449: 31 гол, суммы по составам и периодам сходятся", () => {
  assert.equal(data.status, "partial");
  assert.equal(data.events.length, 31);

  const squadSum = { 1: [0, 0], 2: [0, 0] };
  const periodSum = { 1: [0, 0], 2: [0, 0], 3: [0, 0] };
  const teamSum = { "Созвездие": 0, "Центр": 0 };

  for (const event of data.events) {
    const index = event.official_team === "Созвездие" ? 0 : 1;
    squadSum[event.squad][index] += 1;
    periodSum[event.period][index] += 1;
    teamSum[event.official_team] += 1;
    assert.equal(event.type, "goal");
    assert.ok(["S1", "S2"].includes(event.source), `неизвестный источник ${event.source}`);
    assert.ok(event.board_change_s > 0);
  }

  assert.deepEqual(squadSum[1], [7, 9]);
  assert.deepEqual(squadSum[2], [6, 9]);
  assert.deepEqual(periodSum[1], [5, 3]);
  assert.deepEqual(periodSum[2], [2, 7]);
  assert.deepEqual(periodSum[3], [6, 8]);
  assert.equal(teamSum["Созвездие"], 13);
  assert.equal(teamSum["Центр"], 18);

  // сумма по составам равна официальному результату
  assert.equal(squadSum[1][0] + squadSum[2][0], 13);
  assert.equal(squadSum[1][1] + squadSum[2][1], 18);
});

test("разбор 22449: накопительный счёт событий совпадает с протоколом", () => {
  let home = 0;
  let away = 0;
  for (const event of data.events) {
    if (event.official_team === "Созвездие") home += 1;
    else away += 1;
    assert.deepEqual(
      [home, away],
      event.official_cumulative,
      `счёт после ${event.id} не совпал с протоколом`,
    );
  }
  assert.deepEqual([home, away], [13, 18]);
});

test("разбор 22449: голы игроков сходятся с командными", () => {
  const byTeam = {};
  for (const player of data.players) {
    byTeam[player.team] = (byTeam[player.team] || 0) + player.goals;
    assert.equal(player.goal_ids.length, player.goals, `у ${player.name} не совпало число голов`);
    assert.ok(player.number > 0 && player.name.length > 0);
  }
  assert.equal(byTeam["Созвездие"], 13);
  assert.equal(byTeam["Центр"], 18);
});

test("разбор 22449: в отчёте нет картинок-доказательств", () => {
  // по просьбе владельца картинки убраны: доказательства — только ссылки на эпизоды
  assert.equal((markdown.match(/!\[[^\]]*\]\(/g) ?? []).length, 0, "в отчёте остались картинки");
  assert.equal(fs.existsSync(path.join(reviewDir, "evidence")), false, "папка evidence должна быть удалена");
});
test("разбор 22449: обязательные разделы отчёта на месте", () => {
  for (const heading of [
    "## 1. Как устроен этот матч",
    "## 3. Хронология голов",
    "## 9. Что установлено, а что нет",
    "## 10. Покрытие и источники",
    "## 11. Ограничения",
    "## 12. Рекомендации",
  ]) {
    assert.ok(markdown.includes(heading), `нет раздела «${heading}»`);
  }
  assert.match(markdown, /не установлено/, "отчёт должен явно отмечать неустановленные показатели");
});

test("разбор 22449: время голов привязано к видео, а не к протоколу", () => {
  for (const event of data.events) {
    assert.ok(
      ["broadcast_goal_banner", "board_minus_measured_lag"].includes(event.goal_time_method),
      `неизвестный способ привязки времени у ${event.id}`,
    );
    assert.ok(event.goal_estimate_s > 0, `${event.id}: нет времени гола`);
    assert.ok(
      event.goal_estimate_s < event.board_change_s,
      `${event.id}: гол должен быть раньше смены табло`,
    );
    const lag = event.board_change_s - event.goal_estimate_s;
    assert.ok(lag >= 3 && lag <= 30, `${event.id}: подозрительная задержка табло ${lag} с`);
    if (event.goal_time_method === "broadcast_goal_banner") {
      assert.ok(event.banner_s > 0, `${event.id}: нет времени плашки`);
    } else {
      assert.equal(event.banner_s, null, `${event.id}: плашки быть не должно`);
    }
  }
  const withBanner = data.events.filter((e) => e.goal_time_method === "broadcast_goal_banner");
  assert.equal(withBanner.length, 18, "плашка «ГОЛ!» ставилась на 18 голов «Центра»");
});

test("разбор 22449: буллиты и звенья описаны и согласованы", () => {
  const shots = data.penalty_shots;
  assert.ok(shots, "нет блока про буллиты");
  assert.equal(shots.awarded, 3, "по видео найдено три штрафных броска");
  assert.equal(shots.attempted, 3);
  assert.equal(shots.scored, 0);
  assert.equal(shots.missed, 3);
  assert.equal(shots.protocol_infractions, 0);
  assert.ok(shots.video_checked_windows.length >= 3, "не указаны проверенные окна");
  assert.equal(shots.episodes.length, 3, "нет описания эпизодов");
  for (const ps of shots.episodes) {
    assert.ok(ps.video_url.includes("?t="), `${ps.id}: ссылка без таймкода`);
    assert.ok(ps.video_url.startsWith("https://vkvideo.ru/video-48703984_4562598"), `${ps.id}: чужая ссылка`);
    assert.equal(ps.awarded_to, "Созвездие");
    assert.equal(ps.outcome, "не забит");
    assert.ok(ps.cleared_at_s < ps.attempt_at_s, `${ps.id}: попытка раньше освобождения площадки`);
  }

  assert.equal(data.line_assignments.length, 6, "ожидаются три звена в каждом из двух составов");
  for (const line of data.line_assignments) {
    assert.ok(["red", "yellow", "green"].includes(line.color), `неизвестный цвет ${line.color}`);
    assert.ok([1, 2].includes(line.squad), `неизвестный состав у звена: ${line.squad}`);
    assert.equal(line.players.length, line.names.length, `у звена ${line.squad}/${line.color} не совпало число имён`);
    assert.ok(line.players.length >= 4, `в звене ${line.squad}/${line.color} меньше четырёх игроков`);
    for (const number of line.players) {
      assert.ok(Number.isInteger(number) && number > 0, "некорректный номер игрока звена");
    }
    assert.ok(line.method.length > 10, "не описан способ привязки звена");
  }
  for (const squad of [1, 2]) {
    const colors = data.line_assignments.filter((l) => l.squad === squad).map((l) => l.color).sort();
    assert.deepEqual(colors, ["green", "red", "yellow"], `в составе ${squad} не три звена`);
  }

  const flat = markdown.replace(/\s+/g, " ");
  assert.ok(flat.includes("7.1 Буллиты"), "нет раздела про буллиты");
  assert.match(flat, /красный — 1-е звено/);
  assert.match(flat, /жёлтый — 2-е/);
});

test("разбор 22449: заявки на игру полные и голы в них укладываются", () => {
  assert.equal(data.lineups.length, 4, "четыре заявки: две команды × два состава");
  const roster = new Map();
  for (const lineup of data.lineups) {
    assert.ok(["Центр", "Созвездие"].includes(lineup.team), `неизвестная команда ${lineup.team}`);
    assert.equal(lineup.goalie.length, 1, `${lineup.team}/${lineup.squad}: вратарь должен быть один`);
    assert.ok(lineup.defenders.length >= 4, "мало защитников");
    assert.ok(lineup.forwards.length >= 7, "мало нападающих");
    assert.match(lineup.source, /match-preview-tab=3/);
    for (const player of [...lineup.goalie, ...lineup.defenders, ...lineup.forwards]) {
      const key = `${lineup.team}|${lineup.squad}|${player.number}`;
      assert.ok(!roster.has(key), `дубль в заявке: ${key}`);
      assert.ok(player.name.length > 3, `пустое имя в заявке: ${key}`);
      roster.set(key, player.name);
    }
  }
  // вратари по составам
  const goalies = data.lineups.map((l) => `${l.team}/${l.squad}:${l.goalie[0].number}`).sort();
  assert.deepEqual(goalies, ["Созвездие/1:1", "Созвездие/2:77", "Центр/1:1", "Центр/2:44"]);

  // каждый гол забит игроком из заявки своего состава
  for (const event of data.events) {
    const key = `${event.official_team}|${event.squad}|${event.official_scorer.number}`;
    assert.ok(roster.has(key), `гол ${event.id}: ${event.official_scorer.name} не в заявке состава ${event.squad}`);
  }
});

test("разбор 22449: голы «Центра» попадают в звенья своего состава (18/18)", () => {
  const lineByPlayer = new Map();
  for (const line of data.line_assignments) {
    for (const number of line.players) {
      lineByPlayer.set(`${line.squad}:${number}`, line.color);
    }
  }
  const byLine = new Map();
  let total = 0;
  for (const event of data.events) {
    if (event.official_team !== "Центр") continue;
    const key = `${event.squad}:${event.official_scorer.number}`;
    const color = lineByPlayer.get(key);
    assert.ok(color, `гол ${event.id}: № ${event.official_scorer.number} не найден в звеньях состава ${event.squad}`);
    byLine.set(`${event.squad}:${color}`, (byLine.get(`${event.squad}:${color}`) ?? 0) + 1);
    total += 1;
  }
  assert.equal(total, 18, "у «Центра» 18 голов");
  // красное звено — самое результативное в обоих составах
  for (const squad of [1, 2]) {
    const red = byLine.get(`${squad}:red`) ?? 0;
    const yellow = byLine.get(`${squad}:yellow`) ?? 0;
    const green = byLine.get(`${squad}:green`) ?? 0;
    assert.equal(red + yellow + green, 9, `состав ${squad}: сумма голов по звеньям`);
    assert.ok(red >= yellow && red >= green, `состав ${squad}: красное звено должно быть результативнее`);
  }
});

test("страницы разбора собраны и соответствуют исходникам", () => {
  execFileSync(process.execPath, [path.join(root, "scripts", "build-reviews.mjs"), "--check"], {
    stdio: "pipe",
  });
  const page = fs.readFileSync(path.join(reviewDir, "index.html"), "utf8");
  assert.match(page, /<meta name="robots" content="noindex, nofollow">/);
  assert.match(page, /reviews\.css/);
  assert.match(page, /13:18/);
  assert.ok(page.includes("Состав 1 <b>7:9</b>"), "нет плашки счёта первого состава");

  const list = fs.readFileSync(path.join(reviewsDir, "index.html"), "utf8");
  assert.match(list, /href="22449\/"/);
  assert.match(list, /Созвездие 2016 — Центр 2016/);
});

test("все таймкоды в отчёте — ссылки на эпизод с ?t=", () => {
  const links = [...markdown.matchAll(/\]\((https:\/\/vkvideo\.ru\/video-[^)\s]*\?t=[^)\s]+)\)/g)].map((m) => m[1]);
  assert.ok(links.length >= 40, `слишком мало ссылок на эпизоды: ${links.length}`);
  for (const url of links) {
    assert.match(
      url,
      /^https:\/\/vkvideo\.ru\/video-48703984_4562598(31|32)\?t=(\d+h)?(\d+m)?\d+s$/,
      `некорректная ссылка на эпизод: ${url}`,
    );
  }
  // хронология голов: каждая строка таблицы содержит две ссылки (гол и табло)
  const goalRows = markdown.split("\n").filter((line) => /^\| \d+ \| [123] \| \[/.test(line));
  assert.equal(goalRows.length, 31, "в таблицах хронологии должно быть 31 строка");
  for (const row of goalRows) {
    assert.equal((row.match(/vkvideo\.ru/g) ?? []).length, 2, `в строке нет двух ссылок: ${row}`);
  }
});

test("оглавление не дублирует номера разделов", () => {
  const page = fs.readFileSync(path.join(reviewDir, "index.html"), "utf8");
  const block = /<nav class="toc"[\s\S]*?<\/nav>/.exec(page);
  assert.ok(block, "нет оглавления");
  const items = [...block[0].matchAll(/<li><a href="#([^"]+)">([^<]+)<\/a><\/li>/g)];
  assert.ok(items.length >= 5, "в оглавлении мало пунктов");
  // список без собственной нумерации: ни <ol>, ни нумерации в разметке
  assert.ok(!/<ol[\s>]/.test(block[0]), "оглавление не должно быть нумерованным списком");
  assert.match(block[0], /<ul class="toc__list">/);
  for (const [, , text] of items) {
    // номер берётся из текста заголовка и не дублируется («1. 1. …»)
    assert.match(text, /^\d+(\.\d+)*\.?\s/, `пункт без номера из текста: ${text}`);
    assert.ok(!/^\d+\.\s+\d+\.\s/.test(text), `двойная нумерация: ${text}`);
  }
});

// --- разбор 22440 ---------------------------------------------------------

const review2Dir = path.join(reviewsDir, "22440");
const markdown2 = fs.readFileSync(path.join(review2Dir, "22440-review.md"), "utf8");
const data2 = JSON.parse(fs.readFileSync(path.join(review2Dir, "22440-review-data.json"), "utf8"));

test("разбор 22440: 33 гола, суммы по составам и периодам сходятся", () => {
  assert.equal(data2.status, "partial");
  assert.equal(data2.events.length, 33);

  const squadSum = { 1: [0, 0], 2: [0, 0] };
  const periodSum = { 1: [0, 0], 2: [0, 0], 3: [0, 0] };
  const teamSum = { "Центр": 0, "Марьино": 0 };

  for (const event of data2.events) {
    assert.equal(event.type, "goal");
    const index = event.official_team === "Центр" ? 0 : 1;
    squadSum[event.squad][index] += 1;
    periodSum[event.period][index] += 1;
    teamSum[event.official_team] += 1;
    assert.ok(["S1", "S2"].includes(event.source));
  }

  assert.deepEqual(squadSum[1], [10, 4]);
  assert.deepEqual(squadSum[2], [15, 4]);
  assert.deepEqual(periodSum[1], [8, 2]);
  assert.deepEqual(periodSum[2], [8, 4]);
  assert.deepEqual(periodSum[3], [9, 2]);
  assert.equal(teamSum["Центр"], 25);
  assert.equal(teamSum["Марьино"], 8);
  assert.equal(squadSum[1][0] + squadSum[2][0], 25);
  assert.equal(squadSum[1][1] + squadSum[2][1], 8);
});

test("разбор 22440: накопительный счёт событий совпадает с протоколом", () => {
  let home = 0;
  let away = 0;
  for (const event of data2.events) {
    if (event.official_team === "Центр") home += 1;
    else away += 1;
    assert.deepEqual([home, away], event.official_cumulative, `счёт после ${event.id} не совпал`);
  }
  assert.deepEqual([home, away], [25, 8]);
});

test("разбор 22440: голы игроков сходятся с командными", () => {
  const byTeam = {};
  for (const player of data2.players) {
    byTeam[player.team] = (byTeam[player.team] || 0) + player.goals;
    assert.equal(player.goal_ids.length, player.goals, `у ${player.name} не совпало число голов`);
    assert.ok(player.number > 0 && player.name.length > 0);
  }
  assert.equal(byTeam["Центр"], 25);
  assert.equal(byTeam["Марьино"], 8);
});

test("разбор 22440: время голов привязано к видео, два гола без времени отмечены", () => {
  let withoutTime = 0;
  for (const event of data2.events) {
    if (event.goal_estimate_s === null) {
      withoutTime += 1;
      assert.equal(event.goal_time_method, "not_established");
      assert.equal(event.video_url, null);
      continue;
    }
    assert.ok(["broadcast_goal_banner", "board_minus_measured_lag"].includes(event.goal_time_method));
    assert.match(event.video_url, /\?t=(\d+h)?(\d+m)?\d+s$/);
    assert.ok(event.goal_estimate_s < event.board_change_s, `${event.id}: гол позже смены табло`);
    const lag = event.board_change_s - event.goal_estimate_s;
    assert.ok(lag >= 3 && lag <= 30, `${event.id}: подозрительная задержка ${lag} с`);
    if (event.goal_time_method === "broadcast_goal_banner") assert.ok(event.banner_s > 0);
  }
  assert.equal(withoutTime, 2, "у Состава 2 два гола прошли до включения табло");
});

test("разбор 22440: заявки на игру полные, голы в них укладываются", () => {
  assert.equal(data2.lineups.length, 4);
  const roster = new Map();
  for (const lineup of data2.lineups) {
    assert.ok(["Центр", "Марьино"].includes(lineup.team));
    assert.equal(lineup.goalie.length, 1, `${lineup.team}/${lineup.squad}: вратарь должен быть один`);
    assert.ok(lineup.defenders.length >= 4);
    assert.ok(lineup.forwards.length >= 7);
    assert.match(lineup.source, /match-preview-tab=3/);
    for (const player of [...lineup.goalie, ...lineup.defenders, ...lineup.forwards]) {
      const key = `${lineup.team}|${lineup.squad}|${player.number}`;
      assert.ok(!roster.has(key), `дубль в заявке: ${key}`);
      roster.set(key, player.name);
    }
  }
  for (const event of data2.events) {
    const key = `${event.official_team}|${event.squad}|${event.official_scorer.number}`;
    assert.ok(roster.has(key), `гол ${event.id}: ${event.official_scorer.name} не в заявке состава ${event.squad}`);
  }
});

test("разбор 22440: в обзоре нет картинок, время только в мм:сс", () => {
  assert.equal((markdown2.match(/!\[[^\]]*\]\(/g) ?? []).length, 0, "в обзор нельзя вставлять картинки");
  assert.ok(!/evidence\//.test(markdown2), "ссылок на папку кадров в тексте быть не должно");
  // координаты на записи — только мм:сс / ч:мм:сс, не число секунд
  const secondTimes = [...markdown2.matchAll(/\[(\d+) с\]\(/g)];
  assert.equal(secondTimes.length, 0, `время в секундах вместо мм:сс: ${secondTimes.map((m) => m[0]).join(", ")}`);
  const goalRows = markdown2.split("\n").filter((line) => /^\| \d+ \| [123] \|/.test(line));
  assert.equal(goalRows.length, 33, "в таблицах хронологии должно быть 33 строки");
  for (const row of goalRows) {
    if (row.includes("не установлено")) continue;
    const times = [...row.matchAll(/\[(\d+:\d{2}(?::\d{2})?)\]/g)].map((m) => m[1]);
    assert.equal(times.length, 2, `в строке нет двух времён: ${row}`);
  }
});

test("разбор 22440: статус частичный, ограничения описаны явно", () => {
  for (const heading of [
    "## 1. Как устроен этот матч",
    "## 3. Хронология голов",
    "## 9. Что установлено, а что нет",
    "## 10. Покрытие и источники",
    "## 11. Ограничения",
    "## 12. Рекомендации",
  ]) {
    assert.ok(markdown2.includes(heading), `нет раздела «${heading}»`);
  }
  assert.match(markdown2, /не установлено/);
  assert.ok(data2.limitations.length >= 5, "мало ограничений");
  assert.match(markdown2, /порядок авторов внутри периода/i);
});

test("разбор 22440: структура 2.1/2.3/7 по правилам навыка", () => {
  // 2.1 — без столбца «Длительность» (длительность живёт в разделе 10)
  const s21 = markdown2.slice(markdown2.indexOf("### 2.1"), markdown2.indexOf("### 2.2"));
  assert.ok(!/\|\s*Длительность\s*\|/.test(s21), "в 2.1 не должно быть столбца «Длительность»");
  // 2.3 — в ФХМ 4×4 раздела нет вовсе
  assert.ok(!markdown2.includes("### 2.3"), "раздел 2.3 в 4×4 не включается");
  assert.ok(!/\|\s*Игрок\s*\|\s*Голы\s*\|/.test(markdown2), "персональной сводки голов в 4×4 быть не должно");
  assert.match(markdown2, /Голевые передачи в турнире ФХМ не ведутся/);
  // 7 — нарушения только по видео, протокол их не ведёт
  const s7 = markdown2.slice(markdown2.indexOf("## 7."), markdown2.indexOf("## 8."));
  assert.match(s7, /только по видео/);
  assert.match(s7, /штрафным броском/);
  assert.ok(!/нет ни одного нарушения/.test(s7), "нельзя опираться на пустой фильтр протокола");
  assert.match(s7, /не установлен/);
});

test("разбор 22440: звенья «Центра» — шесть групп, все полевые, голы сходятся", () => {
  const lines = data2.line_assignments;
  assert.equal(lines.length, 6, "ожидаются три звена в каждом из двух составов");

  for (const line of lines) {
    assert.equal(line.team, "Центр");
    assert.ok(["red", "yellow", "green"].includes(line.color), `неизвестный цвет ${line.color}`);
    assert.ok([1, 2].includes(line.squad));
    assert.equal(line.players.length, line.names.length);
    assert.ok(line.players.length >= 4, `в звене ${line.squad}/${line.color} меньше четырёх игроков`);
    assert.match(line.source, /со слов пользователя/);
    assert.ok(line.method.length > 20, "не описан способ привязки звена");
    assert.ok(Number.isInteger(line.goals) && line.goals >= 0);
  }

  for (const squad of [1, 2]) {
    const ofSquad = lines.filter((l) => l.squad === squad);
    assert.deepEqual(ofSquad.map((l) => l.color).sort(), ["green", "red", "yellow"]);
    const numbers = ofSquad.flatMap((l) => l.players);
    assert.equal(numbers.length, 13, `состав ${squad}: в звеньях должно быть 13 полевых`);
    assert.equal(new Set(numbers).size, 13, `состав ${squad}: игрок попал в два звена`);
    const lineup = data2.lineups.find((l) => l.team === "Центр" && l.squad === squad);
    const roster = new Set([...lineup.defenders, ...lineup.forwards].map((p) => p.number));
    for (const n of numbers) assert.ok(roster.has(n), `состав ${squad}: № ${n} нет в заявке`);
    const lineGoals = ofSquad.reduce((sum, l) => sum + l.goals, 0);
    const squadGoals = data2.squads.find((s) => s.id === squad).score_for;
    assert.equal(lineGoals, squadGoals, `состав ${squad}: голы звеньев не равны голам состава`);
  }
});

test("страница разбора 22440 собрана и есть в списке", () => {
  const page = fs.readFileSync(path.join(review2Dir, "index.html"), "utf8");
  assert.match(page, /<meta name="robots" content="noindex, nofollow">/);
  assert.match(page, /reviews\.css/);
  assert.match(page, /25:8/);
  assert.ok(page.includes("Состав 1 <b>10:4</b>"));
  const list = fs.readFileSync(path.join(reviewsDir, "index.html"), "utf8");
  assert.match(list, /href="22440\/"/);
  assert.match(list, /Центр 2016 — Марьино 2016/);
});
