"""Локальный сервер для статической страницы прогноза.

Отдаёт `predictor/index.html` и API для запуска сбора данных и пересчёта
модели. Пароль проверяется здесь, а не только в браузере.

Запуск: python main.py serve  (или bridge.bat)
"""

from __future__ import annotations

import hmac
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import config

# Консоль Windows может быть в cp1252 — принудительно UTF-8, иначе print падает.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

HOST = "127.0.0.1"
PORT = 8765
PASSWORD = os.environ.get("FHM_REFRESH_PASSWORD", "refresh")
PROJECT_DIR = config.PROJECT_DIR
SITE_ROOT = PROJECT_DIR  # index.html лежит в predictor/
MAX_LOG_LINES = 800

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
RUNNING: str | None = None


def _run_step(command: list[str], job: dict[str, Any]) -> int:
    job["log"].append("$ " + " ".join(command))
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        job["log"].append(line.rstrip())
    return process.wait()


def _run_job(job_id: str, action: str) -> None:
    global RUNNING
    job = JOBS[job_id]
    job["status"] = "running"
    job["started"] = time.time()
    try:
        if action == "update":
            steps = [
                [sys.executable, "main.py", "collect"],
                [sys.executable, "main.py", "export-site"],
            ]
        elif action == "backtest":
            steps = [
                [sys.executable, "main.py", "backtest"],
                [sys.executable, "main.py", "export-site"],
            ]
        else:
            raise ValueError(f"Неизвестное действие: {action}")

        for command in steps:
            code = _run_step(command, job)
            if code != 0:
                raise RuntimeError(f"Команда завершилась с кодом {code}: {' '.join(command)}")
        job["status"] = "ok"
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(exc)
        job["log"].append(f"Ошибка: {exc}")
    finally:
        job["finished"] = time.time()
        with JOBS_LOCK:
            RUNNING = None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(SITE_ROOT), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Не засоряем консоль каждым запросом статики.
        if self.path.startswith("/api/"):
            super().log_message(format, *args)

    def _json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 65536:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            return {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/health"):
            self._json(
                {
                    "ok": True,
                    "host": f"{HOST}:{PORT}",
                    "version": "1",
                    "password_required": True,
                }
            )
            return
        if self.path.startswith("/api/jobs/"):
            job_id = self.path.rsplit("/", 1)[-1].split("?")[0]
            job = JOBS.get(job_id)
            if job is None:
                self._json({"error": "job not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(
                {
                    "id": job_id,
                    "action": job["action"],
                    "status": job["status"],
                    "log": list(job["log"]),
                    "error": job.get("error"),
                }
            )
            return
        if self.path.split("?")[0] in ("/api/jobs", "/api/jobs/"):
            self._json({"jobs": [{"id": key, "action": value["action"], "status": value["status"]} for key, value in JOBS.items()]})
            return
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        global RUNNING
        if self.path.rstrip("/") != "/api/jobs":
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        body = self._read_body()
        password = str(body.get("password") or "")
        if not hmac.compare_digest(password, PASSWORD):
            self._json({"error": "invalid password"}, HTTPStatus.UNAUTHORIZED)
            return
        action = str(body.get("action") or "")
        if action not in ("update", "backtest"):
            self._json({"error": "unknown action"}, HTTPStatus.BAD_REQUEST)
            return
        with JOBS_LOCK:
            if RUNNING is not None:
                self._json({"error": "job already running", "id": RUNNING}, HTTPStatus.CONFLICT)
                return
            job_id = uuid.uuid4().hex[:12]
            JOBS[job_id] = {
                "id": job_id,
                "action": action,
                "status": "queued",
                "log": deque(maxlen=MAX_LOG_LINES),
                "error": None,
            }
            RUNNING = job_id
        thread = threading.Thread(target=_run_job, args=(job_id, action), daemon=True)
        thread.start()
        self._json({"id": job_id, "status": "queued"}, HTTPStatus.ACCEPTED)


def serve(host: str = HOST, port: int = PORT, open_browser: bool = False) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"FHM Hockey Predictor: {url}")
    print(f"Пароль для обновления: {'задан через FHM_REFRESH_PASSWORD' if os.environ.get('FHM_REFRESH_PASSWORD') else 'refresh'}")
    print("Остановка: Ctrl+C")
    if open_browser:
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        server.server_close()
