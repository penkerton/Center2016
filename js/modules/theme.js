/** Переключение клубной светлой и тёмной темы. */

import { $$ } from "../lib/dom.js";

/** Ключ должен совпадать с inline-скриптом в <head> (тема до первой отрисовки). */
const THEME_KEY = "centr2016:theme";
const DEFAULT_THEME = "club-light";
const THEMES = {
  "club-light": { label: "Клубная светлая", color: "#f6f4f5" },
  "club-dark": { label: "Клубная тёмная", color: "#0a0a0c" },
};

export function initTheme() {
  const html = document.documentElement;
  const buttons = $$(".theme-picker .swatch");
  const themeColor = document.querySelector('meta[name="theme-color"]');

  function applyTheme(theme, persist) {
    const next = Object.hasOwn(THEMES, theme) ? theme : DEFAULT_THEME;
    html.dataset.theme = next;

    buttons.forEach((button) => {
      const isActive = button.dataset.themeValue === next;
      button.setAttribute("aria-pressed", String(isActive));
      button.tabIndex = isActive ? 0 : -1;
    });

    themeColor?.setAttribute("content", THEMES[next].color);

    if (persist) {
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch (error) {
        /* приватный режим — выбор просто не запоминается */
      }
    }
  }

  buttons.forEach((button, index) => {
    button.addEventListener("click", () => applyTheme(button.dataset.themeValue, true));
    button.addEventListener("keydown", (event) => {
      let step = 0;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") step = 1;
      if (event.key === "ArrowLeft" || event.key === "ArrowUp") step = -1;
      if (!step) return;
      event.preventDefault();
      const target = buttons[(index + step + buttons.length) % buttons.length];
      target.focus();
      applyTheme(target.dataset.themeValue, true);
    });
  });

  applyTheme(html.dataset.theme || DEFAULT_THEME, false);
}
