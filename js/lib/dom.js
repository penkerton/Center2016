/** Небольшие помощники для работы с DOM. */

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

export function setText(node, value) {
  if (node) {
    node.textContent = String(value ?? "");
  }
}

export function setHidden(node, hidden) {
  if (node) {
    node.hidden = Boolean(hidden);
  }
}

export function toggleClass(node, className, state) {
  if (node) {
    node.classList.toggle(className, Boolean(state));
  }
}

/** Скачивание файла, собранного в браузере (используется для .ics). */
export function downloadFile(name, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/** Вызов после разбора документа: данные подключены как defer-скрипты. */
export function onReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback, { once: true });
  } else {
    callback();
  }
}
