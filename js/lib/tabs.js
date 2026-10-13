/**
 * Доступные вкладки (WAI-ARIA tabs) — один контроллер для турнирной таблицы,
 * матчей и дней рождения вместо трёх копий обработчиков.
 */

export function initTabs(root, { onChange } = {}) {
  if (!root) {
    return null;
  }

  const list = root.querySelector('[role="tablist"]');
  const tabs = list ? Array.from(list.querySelectorAll('[role="tab"]')) : [];
  if (!tabs.length) {
    return null;
  }

  const panelFor = (tab) => {
    const id = tab.getAttribute("aria-controls");
    return id ? document.getElementById(id) : null;
  };

  let activeIndex = Math.max(
    0,
    tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true"),
  );

  function activate(index, { moveFocus = false, silent = false } = {}) {
    const nextTab = tabs[index];
    if (!nextTab) {
      return;
    }

    activeIndex = index;
    tabs.forEach((tab, tabIndex) => {
      const selected = tabIndex === index;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      const panel = panelFor(tab);
      if (panel) {
        panel.hidden = !selected;
      }
    });

    if (moveFocus) {
      nextTab.focus();
    }
    if (!silent && typeof onChange === "function") {
      onChange(index, nextTab);
    }
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(index));
    tab.addEventListener("keydown", (event) => {
      const key = event.key;
      if (!["ArrowLeft", "ArrowRight", "Home", "End", "Enter", " "].includes(key)) {
        return;
      }
      event.preventDefault();

      if (key === "Enter" || key === " ") {
        activate(index);
        return;
      }

      let nextIndex = index;
      if (key === "Home") nextIndex = 0;
      if (key === "End") nextIndex = tabs.length - 1;
      if (key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
      if (key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
      activate(nextIndex, { moveFocus: true });
    });
  });

  activate(activeIndex, { silent: true });

  return {
    activate,
    tabs,
    get activeIndex() {
      return activeIndex;
    },
  };
}
