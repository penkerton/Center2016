"""HTTP-клиент ФХМ: троттлинг, повторы, файловый кеш.

Сайт ФХМ отдаёт 429 при частых запросах к ``/api`` и иногда держит соединение.
Клиент держит паузу между запросами (адаптивно увеличивает её после 429),
повторяет неудачные попытки с экспоненциальной задержкой, кеширует ответы на
диск и при сбое сети возвращает устаревший кеш, а не роняет весь сбор.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import requests

from . import config

Logger = Callable[[str], None]


class FhmHttpError(RuntimeError):
    """Ошибка запроса к ФХМ после исчерпания повторов."""


@dataclass
class HttpStats:
    requests: int = 0
    cache_hits: int = 0
    stale_hits: int = 0
    retries: int = 0
    throttles: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "cache_hits": self.cache_hits,
            "stale_hits": self.stale_hits,
            "retries": self.retries,
            "throttles": self.throttles,
            "errors": list(self.errors),
        }


class FhmHttp:
    """Клиент с кешем и адаптивным ограничением частоты."""

    def __init__(
        self,
        *,
        base_url: str = config.BASE_URL,
        cache_dir: Path = config.CACHE_DIR,
        min_interval: float = config.API_MIN_INTERVAL_SECONDS,
        timeout: tuple[float, float] = (10.0, 35.0),
        logger: Logger | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.base_interval = min_interval
        self.min_interval = min_interval
        self.timeout = timeout
        self.logger = logger or (lambda message: None)
        self.stats = HttpStats()
        self._last_request_at = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
            }
        )
        (self.cache_dir / "api").mkdir(parents=True, exist_ok=True)

    # -- кеш ------------------------------------------------------------

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / "api" / f"{key}.json.gz"

    def _read_cache(self, key: str, ttl: float) -> tuple[Any | None, bool]:
        """Возвращает (данные, устарел_ли)."""
        path = self._cache_path(key)
        if not path.exists():
            return None, False
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError, KeyError):
            return None, False
        age = time.time() - float(payload.get("saved_at") or path.stat().st_mtime)
        stale = ttl >= 0 and age > ttl
        self.stats.cache_hits += 1
        return payload.get("data"), stale

    def _write_cache(self, key: str, data: Any) -> None:
        path = self._cache_path(key)
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump({"saved_at": time.time(), "data": data}, fh, ensure_ascii=False)
        tmp.replace(path)

    # -- сеть -----------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_at = time.time()

    def _on_throttled(self) -> None:
        self.stats.throttles += 1
        self.min_interval = min(12.0, self.min_interval * 1.5)
        self.logger(f"  429: пауза увеличена до {self.min_interval:.1f} c")

    def _on_success(self) -> None:
        if self.min_interval > self.base_interval:
            self.min_interval = max(self.base_interval, self.min_interval * 0.9)

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(config.MAX_RETRIES):
            self._throttle()
            started = time.time()
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                last_error = exc
                self.stats.errors.append(f"{method} {url}: {exc}")
                self.logger(f"  сеть: {type(exc).__name__} ({attempt + 1}/{config.MAX_RETRIES})")
                self._backoff(attempt)
                continue

            elapsed = time.time() - started
            if response.status_code == 200:
                self.stats.requests += 1
                self._on_success()
                if elapsed > 5:
                    self.logger(f"  медленный ответ {elapsed:.1f} c: {url}")
                return response
            if response.status_code == 429:
                self.stats.retries += 1
                self._on_throttled()
                retry_after = response.headers.get("Retry-After") or ""
                delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 0.0
                self._backoff(attempt, minimum=max(delay, 4.0))
                last_error = FhmHttpError("HTTP 429")
                continue
            if response.status_code >= 500:
                self.stats.retries += 1
                self.logger(f"  HTTP {response.status_code} ({attempt + 1}/{config.MAX_RETRIES})")
                self._backoff(attempt)
                last_error = FhmHttpError(f"HTTP {response.status_code}")
                continue
            raise FhmHttpError(f"HTTP {response.status_code} для {url}")

        raise FhmHttpError(f"Не удалось выполнить {method} {url}: {last_error}")

    @staticmethod
    def _backoff(attempt: int, minimum: float = 0.0) -> None:
        delay = max(minimum, 2.0 * (2**attempt))
        time.sleep(min(delay, 60.0))

    def _with_cache(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None,
        ttl: float,
        refresh: bool,
        html: bool = False,
    ) -> Any:
        if html:
            key = self._cache_key(f"GET {path}")
            directory = self.cache_dir / "html"
            directory.mkdir(parents=True, exist_ok=True)
            path_on_disk = directory / f"{key}.html.gz"
        else:
            key = self._cache_key(
                f"{method} {path} {json.dumps(body, sort_keys=True, ensure_ascii=False) if body else ''}"
            )
            path_on_disk = self._cache_path(key)

        if not refresh and path_on_disk.exists():
            if html:
                age = time.time() - path_on_disk.stat().st_mtime
                if ttl < 0 or age <= ttl:
                    self.stats.cache_hits += 1
                    with gzip.open(path_on_disk, "rt", encoding="utf-8") as fh:
                        return fh.read()
            else:
                data, stale = self._read_cache(key, ttl)
                if data is not None and not stale:
                    return data

        try:
            url = f"{self.base_url}{path}"
            if method == "POST":
                response = self._request(
                    "POST",
                    url,
                    json=body or {},
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
            else:
                response = self._request("GET", url)
            if html:
                response.encoding = response.encoding or "utf-8"
                text = response.text
                tmp = path_on_disk.with_suffix(".tmp")
                with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                    fh.write(text)
                tmp.replace(path_on_disk)
                return text
            data = response.json()
            self._write_cache(key, data)
            return data
        except Exception as exc:  # noqa: BLE001
            # Аварийный режим: отдаём устаревший кеш, если он есть.
            if html and path_on_disk.exists():
                self.stats.stale_hits += 1
                self.logger(f"  использую устаревший кеш: {path}")
                with gzip.open(path_on_disk, "rt", encoding="utf-8") as fh:
                    return fh.read()
            if not html and path_on_disk.exists():
                data, _ = self._read_cache(key, ttl=-1)
                if data is not None:
                    self.stats.stale_hits += 1
                    self.logger(f"  использую устаревший кеш: {path}")
                    return data
            raise exc

    # -- публичные методы ----------------------------------------------

    def post_json(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        ttl: float = config.API_CACHE_TTL_SECONDS,
        refresh: bool = False,
    ) -> Any:
        return self._with_cache("POST", path, body=body or {}, ttl=ttl, refresh=refresh)

    def get_json(
        self,
        path: str,
        *,
        ttl: float = config.API_CACHE_TTL_SECONDS,
        refresh: bool = False,
    ) -> Any:
        return self._with_cache("GET", path, body=None, ttl=ttl, refresh=refresh)

    def get_html(
        self,
        url: str,
        *,
        ttl: float = config.HTML_CACHE_TTL_SECONDS,
        refresh: bool = False,
    ) -> str:
        path = url[len(self.base_url) :] if url.startswith(self.base_url) else url
        return self._with_cache("GET", path, body=None, ttl=ttl, refresh=refresh, html=True)
