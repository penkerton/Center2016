#!/usr/bin/env node
/**
 * Сборка страниц разборов матчей.
 *
 * Источник правды — Markdown и JSON в каталогах `reviews/<slug>/`:
 *   <slug>/<slug>-review.md        полный текст разбора
 *   <slug>/<slug>-review-data.json машинная разметка и метаданные
 *   <slug>/evidence/*.jpg          кадры-доказательства (по желанию)
 *
 * Скрипт рендерит `reviews/<slug>/index.html` и общий список `reviews/index.html`.
 * GitHub Pages отдаёт репозиторий как статику, поэтому сгенерированные файлы
 * коммитятся вместе с источниками.
 *
 * Использование:
 *   node scripts/build-reviews.mjs           # перезаписать страницы
 *   node scripts/build-reviews.mjs --check   # только проверить актуальность
 */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { escapeHtml, renderMarkdown } from "./lib/markdown.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REVIEWS_DIR = path.join(ROOT, "reviews");
const CHECK_ONLY = process.argv.includes("--check");

function fmtDate(iso) {
  const months = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
  ];
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) return iso || "";
  return `${Number(m[3])} ${months[Number(m[2]) - 1]} ${m[1]}`;
}

function statusLabel(status) {
  if (status === "complete") return "полный разбор";
  if (status === "partial") return "частичный разбор";
  return "разбор";
}

async function readJson(file) {
  return JSON.parse(await fs.readFile(file, "utf8"));
}

async function collect() {
  const entries = await fs.readdir(REVIEWS_DIR, { withFileTypes: true });
  const dirs = entries.filter((e) => e.isDirectory()).map((e) => e.name).sort();
  const reviews = [];

  for (const dir of dirs) {
    const abs = path.join(REVIEWS_DIR, dir);
    const files = await fs.readdir(abs);
    const mdFile = files.find((f) => f.endsWith("-review.md"));
    if (!mdFile) continue;
    const dataFile = files.find((f) => f.endsWith("-review-data.json"));
    const markdown = await fs.readFile(path.join(abs, mdFile), "utf8");
    const data = dataFile ? await readJson(path.join(abs, dataFile)) : {};
    const match = data.match || {};
    reviews.push({
      slug: dir,
      dir: abs,
      mdFile,
      dataFile,
      markdown,
      data,
      match,
      review: data.review || { status: data.status, version: data.review_version },
      title: match.home && match.away ? `${match.home} — ${match.away}` : mdFile.replace(/-review\.md$/, ""),
      date: match.date || "",
    });
  }

  reviews.sort((a, b) => (b.date || "").localeCompare(a.date || "") || a.slug.localeCompare(b.slug));
  return reviews;
}

function shell({ title, description, bodyClass, content, headerExtra = "", footerExtra = "" }) {
  return `<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>${escapeHtml(title)}</title>
<meta name="description" content="${escapeHtml(description)}">
<link rel="stylesheet" href="REVIEWS_CSS_PATH">
</head>
<body class="${bodyClass}">
${content}
${footerExtra}
</body>
</html>
`;
}

const REVIEW_CSS_DEPTH = { list: "reviews.css", detail: "../reviews.css" };

function reviewCard(review) {
  const m = review.match;
  const squads = Array.isArray(review.data.squads) ? review.data.squads : [];
  const squadLine = squads
    .map((s) => `${escapeHtml(s.name || "")} ${escapeHtml(s.score || "")}`.trim())
    .filter(Boolean)
    .join(" · ");
  return `<a class="card" href="${encodeURI(review.slug)}/">
  <span class="card__status">${escapeHtml(statusLabel(review.review.status))}</span>
  <span class="card__teams">${escapeHtml(review.title)}</span>
  <span class="card__score">${escapeHtml(m.score || "")}</span>
  <span class="card__meta">${escapeHtml(fmtDate(review.date))}${m.tournament ? ` · ${escapeHtml(m.tournament)}` : ""}${m.group ? ` · ${escapeHtml(m.group)}` : ""}</span>
  ${squadLine ? `<span class="card__squads">${squadLine}</span>` : ""}
</a>`;
}

function toc(headings) {
  const items = headings.filter((h) => h.level === 2);
  if (items.length < 2) return "";
  // Заголовки в отчёте уже нумерованы («1.», «5.1»), поэтому список без своей
  // нумерации: иначе получается «1. 1. Как устроен этот матч».
  return `<nav class="toc" aria-label="Содержание">
  <p class="toc__title">Содержание</p>
  <ul class="toc__list">${items.map((h) => `<li><a href="#${h.id}">${escapeHtml(h.text)}</a></li>`).join("")}</ul>
</nav>`;
}

function reviewPage(review) {
  const m = review.match;
  const rendered = renderMarkdown(review.markdown);
  // Заголовок H1 уже выведен в шапке страницы — убираем дубль.
  const html = rendered.html.replace(/^\s*<h1[^>]*>[\s\S]*?<\/h1>\s*/, "");
  const headings = rendered.headings;
  const squads = Array.isArray(review.data.squads) ? review.data.squads : [];
  const chips = [
    fmtDate(review.date),
    m.time,
    m.tournament,
    m.group,
    m.format ? `формат ${m.format}` : "",
    statusLabel(review.review.status),
    review.review.version ? `версия ${review.review.version}` : "",
  ].filter(Boolean);

  const squadChips = squads
    .map((s) => `<span class="chip chip--squad">${escapeHtml(s.name || "")} <b>${escapeHtml(s.score || "")}</b></span>`)
    .join("");

  const official = m.official_url
    ? `<a class="topbar__link" href="${m.official_url}" rel="noopener noreferrer">Протокол на fhmoscow.com</a>`
    : "";

  const content = `<header class="topbar">
  <div class="brand">
    <a class="brand__back" href="../">← все разборы</a>
    <h1>${escapeHtml(review.title)}</h1>
    <p class="brand__score">${escapeHtml(m.score || "")}${m.venue ? ` · ${escapeHtml(m.venue)}` : ""}</p>
  </div>
  <div class="topbar__side">
    ${official}
    <span class="chip">${escapeHtml(review.review.status === "complete" ? "полный разбор" : statusLabel(review.review.status))}</span>
  </div>
</header>

<div class="chips">
  ${chips.map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join("")}
  ${squadChips}
</div>

<main class="layout">
  ${toc(headings)}
  <article class="article">
${html}
  </article>
</main>

<footer class="footer">
  <span>Разбор матча №${escapeHtml(String(m.id || review.slug))} · ${escapeHtml(fmtDate(review.date))}</span>
  <span>Видео: трансляции ФХМ · данные: fhmoscow.com</span>
  <span>Страница не связана ссылками с основным сайтом</span>
</footer>`;

  return shell({
    title: `${review.title} — разбор матча`,
    description: `Видеоразбор матча ${review.title}: ${m.score || ""}`,
    bodyClass: "page page--review",
    content,
  }).replace("REVIEWS_CSS_PATH", REVIEW_CSS_DEPTH.detail);
}

function listPage(reviews) {
  const cards = reviews.map(reviewCard).join("\n");
  const content = `<header class="topbar">
  <div class="brand">
    <h1>Разборы матчей</h1>
    <p>Видеоанализ игр команды «Центр» 2016 г.р.: голы, смены, звенья, вратари и дисциплина.</p>
  </div>
  <div class="topbar__side">
    <span class="chip">${reviews.length} ${reviews.length === 1 ? "разбор" : "разбора"}</span>
  </div>
</header>

<main class="layout layout--list">
  <section class="cards">
${cards || '<p class="empty">Пока нет опубликованных разборов.</p>'}
  </section>
</main>

<footer class="footer">
  <span>Данные: fhmoscow.com · видео: трансляции ФХМ</span>
  <span>Страница не связана ссылками с основным сайтом</span>
</footer>`;

  return shell({
    title: "Разборы матчей — «Центр» 2016",
    description: "Видеоразборы матчей команды «Центр» 2016 г.р.",
    bodyClass: "page page--list",
    content,
  }).replace("REVIEWS_CSS_PATH", REVIEW_CSS_DEPTH.list);
}

async function writeIfChanged(file, content) {
  let current = null;
  try {
    current = await fs.readFile(file, "utf8");
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  if (current === content) return false;
  if (CHECK_ONLY) {
    throw new Error(`устаревший файл: ${path.relative(ROOT, file)} (запустите node scripts/build-reviews.mjs)`);
  }
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, content, "utf8");
  return true;
}

async function main() {
  const reviews = await collect();
  let written = 0;
  for (const review of reviews) {
    const changed = await writeIfChanged(path.join(review.dir, "index.html"), reviewPage(review));
    if (changed) written += 1;
    console.log(`reviews/${review.slug}/index.html ${changed ? "обновлён" : "без изменений"}`);
  }
  const listChanged = await writeIfChanged(path.join(REVIEWS_DIR, "index.html"), listPage(reviews));
  if (listChanged) written += 1;
  console.log(`reviews/index.html ${listChanged ? "обновлён" : "без изменений"}`);
  console.log(CHECK_ONLY ? "проверка пройдена" : `готово, файлов обновлено: ${written}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
