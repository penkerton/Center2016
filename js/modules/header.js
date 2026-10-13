/** Шапка: прогресс прокрутки, состояние, мобильное меню, часы МСК, активный раздел. */

import { $, $$ } from "../lib/dom.js";
import { clockFmt } from "../lib/format.js";

export function initHeader({ scheduler }) {
  const html = document.documentElement;
  const progressBar = $("#scroll-progress-bar");
  const header = $(".site-header");
  const toTop = $("#to-top");
  const nativeScrollTimeline = Boolean(window.CSS && CSS.supports && CSS.supports("animation-timeline: scroll()"));
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let scrollScheduled = false;

  function onScroll() {
    const scrollTop = window.scrollY || html.scrollTop;
    const max = html.scrollHeight - html.clientHeight;

    if (!nativeScrollTimeline && progressBar) {
      progressBar.style.setProperty("--p", max > 0 ? String(Math.min(scrollTop / max, 1)) : "0");
    }
    header?.classList.toggle("is-scrolled", scrollTop > 12);
    toTop?.classList.toggle("is-visible", scrollTop > 600);
    scrollScheduled = false;
  }

  window.addEventListener(
    "scroll",
    () => {
      if (!scrollScheduled) {
        scrollScheduled = true;
        requestAnimationFrame(onScroll);
      }
    },
    { passive: true },
  );
  onScroll();

  const scrollToTop = () => window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
  toTop?.addEventListener("click", scrollToTop);
  $$("a[href='#top']").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      scrollToTop();
    });
  });

  const navToggle = $("#nav-toggle");
  const nav = $("#primary-nav");

  function closeNav() {
    document.body.classList.remove("nav-open");
    navToggle?.setAttribute("aria-expanded", "false");
  }

  navToggle?.addEventListener("click", () => {
    const open = document.body.classList.toggle("nav-open");
    navToggle.setAttribute("aria-expanded", String(open));
  });

  nav?.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("a")) {
      closeNav();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeNav();
    }
  });

  const clock = $("#live-clock");
  if (clock) {
    scheduler.onSecond(() => {
      clock.textContent = `${clockFmt.format(new Date())} МСК`;
    });
  }

  const navLinks = $$("#primary-nav a");
  const navSections = navLinks.map((link) => $(link.getAttribute("href"))).filter(Boolean);

  if ("IntersectionObserver" in window && navSections.length) {
    const navObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          navLinks.forEach((link) => {
            link.classList.toggle("is-active", link.getAttribute("href") === `#${entry.target.id}`);
          });
        });
      },
      { rootMargin: "-45% 0px -50% 0px" },
    );
    navSections.forEach((section) => navObserver.observe(section));
  }
}
