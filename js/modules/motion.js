/** Появление блоков, счётчики и блик под курсором. */

import { $$ } from "../lib/dom.js";

const REVEAL_OPTIONS = { threshold: 0.12, rootMargin: "0px 0px -60px 0px" };

function createCounter(element, reduceMotion) {
  const target = Number(element.dataset.count);
  if (!Number.isFinite(target)) {
    return null;
  }

  const format = Number(element.dataset.decimals || 0)
    ? new Intl.NumberFormat("ru-RU", {
        minimumFractionDigits: Number(element.dataset.decimals),
        maximumFractionDigits: Number(element.dataset.decimals),
      })
    : new Intl.NumberFormat("ru-RU");

  if (reduceMotion) {
    element.textContent = format.format(target);
    return null;
  }

  const duration = 1100;
  const start = performance.now();
  const frame = (now) => {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = format.format(target * eased);
    if (progress < 1) {
      requestAnimationFrame(frame);
    }
  };
  return () => requestAnimationFrame(frame);
}

function initReveal(reduceMotion) {
  const items = $$(".reveal");

  if (reduceMotion || !("IntersectionObserver" in window)) {
    items.forEach((item) => {
      item.classList.add("is-visible");
      $$("[data-count]", item).forEach((counter) => createCounter(counter, true));
    });
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      $$("[data-count]", entry.target).forEach((counter) => {
        const start = createCounter(counter, false);
        start?.();
      });
      observer.unobserve(entry.target);
    });
  }, REVEAL_OPTIONS);

  items.forEach((item) => observer.observe(item));
}

/**
 * Блик под курсором: положение пересчитывается только при входе на новую
 * карточку и после прокрутки/изменения размера, а не на каждое движение мыши.
 */
function initSpotlight() {
  let activeCard = null;
  let activeRect = null;
  let rectStale = true;

  const markStale = () => {
    rectStale = true;
  };
  window.addEventListener("scroll", markStale, { passive: true });
  window.addEventListener("resize", markStale);

  document.addEventListener(
    "pointermove",
    (event) => {
      const target = event.target;
      const card = target instanceof Element ? target.closest(".spotlight") : null;

      if (!card) {
        activeCard = null;
        return;
      }
      if (card !== activeCard || rectStale) {
        activeCard = card;
        activeRect = card.getBoundingClientRect();
        rectStale = false;
      }
      if (!activeRect) {
        return;
      }

      card.style.setProperty("--mx", `${event.clientX - activeRect.left}px`);
      card.style.setProperty("--my", `${event.clientY - activeRect.top}px`);
    },
    { passive: true },
  );
}

export function initMotion({ reduceMotion, canHover }) {
  initReveal(reduceMotion);
  if (!reduceMotion && canHover) {
    initSpotlight();
  }
}
