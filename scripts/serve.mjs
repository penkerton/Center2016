#!/usr/bin/env node

/**
 * Мини-сервер для локального просмотра сайта.
 *
 * Нужен потому, что страница использует ES-модули: по file:// браузер их
 * не загрузит. Деплой на GitHub Pages работает с обычным HTTP.
 *
 * Запуск: npm start  →  http://127.0.0.1:4173/
 */

import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const port = Number(process.env.PORT || 4173);

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
};

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost");
  const relative = decodeURIComponent(url.pathname).replace(/^\/+/, "") || "index.html";
  const filePath = path.resolve(root, relative);

  if (!filePath.startsWith(root)) {
    response.writeHead(403, { "Content-Type": "text/plain; charset=utf-8" }).end("Forbidden");
    return;
  }

  // Как на GitHub Pages: каталог отдаётся своим index.html.
  const target = await resolveIndex(filePath);

  try {
    const data = await fs.readFile(target);
    response.writeHead(200, {
      "Content-Type": CONTENT_TYPES[path.extname(target).toLowerCase()] ?? "application/octet-stream",
      "Cache-Control": "no-cache",
    });
    response.end(data);
  } catch {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" }).end("Not found");
  }
});

/** Если путь — каталог (в том числе без завершающего слэша), добавляем index.html. */
async function resolveIndex(filePath) {
  try {
    const stat = await fs.stat(filePath);
    if (stat.isDirectory()) {
      return path.join(filePath, "index.html");
    }
    return filePath;
  } catch {
    return filePath;
  }
}

server.listen(port, "127.0.0.1", () => {
  console.log(`Сайт доступен: http://127.0.0.1:${port}/`);
});
