/**
 * Один интервал на всё приложение.
 *
 * Раньше часы, обратный отсчёт и подписи обновления работали тремя
 * независимыми setInterval. Теперь тикает один таймер: задачи «раз в секунду»
 * и «раз в минуту». В скрытой вкладке таймер останавливается.
 */

export function createScheduler({ tickMs = 1000 } = {}) {
  const secondTasks = new Set();
  const minuteTasks = new Set();
  let timer = 0;
  let lastMinute = -1;

  function runTasks(tasks, now) {
    for (const task of [...tasks]) {
      try {
        task(now);
      } catch (error) {
        console.error(error);
      }
    }
  }

  function tick() {
    const now = new Date();
    runTasks(secondTasks, now);
    const minute = Math.floor(now.getTime() / 60000);
    if (minute !== lastMinute) {
      lastMinute = minute;
      runTasks(minuteTasks, now);
    }
  }

  function start() {
    if (timer) {
      return;
    }
    tick();
    timer = window.setInterval(tick, tickMs);
  }

  function stop() {
    if (timer) {
      window.clearInterval(timer);
      timer = 0;
    }
  }

  function isRunning() {
    return Boolean(timer);
  }

  const onSecond = (task) => {
    secondTasks.add(task);
    return () => secondTasks.delete(task);
  };

  const onMinute = (task) => {
    minuteTasks.add(task);
    return () => minuteTasks.delete(task);
  };

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stop();
    } else {
      start();
    }
  });

  return { onSecond, onMinute, start, stop, isRunning, refresh: tick };
}
