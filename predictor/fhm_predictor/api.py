"""Обёртка над публичным JSON API сайта ФХМ.

Эндпоинты повторяют запросы, которые выполняет сам сайт:

* ``GET  /api/filter/season``          — список сезонов;
* ``POST /api/filter/tournament``      — турниры сезона;
* ``POST /api/filter/stage``           — этапы турнира;
* ``POST /api/filter/group``           — группы этапа;
* ``POST /api/filter/team``            — команды группы;
* ``POST /api/filter/tour``            — туры группы;
* ``POST /api/game/list``              — матчи (с пагинацией limit/offset);
* ``GET  /api/team/{id}/player``       — заявка команды на сезон.

Матчи в ``/api/game/list`` не содержат ID команд — только названия, поэтому
команды сопоставляются по названию внутри группы.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from . import config
from .http import FhmHttp

MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

_DISPLAY_DATE_RE = re.compile(r"(\d{1,2})\s+([а-яё]+)(?:\s+(\d{4}))?", re.IGNORECASE)
_SHORT_DATE_RE = re.compile(r"(\d{2})\.(\d{2})")
_CLOCK_RE = re.compile(r"(\d{2}):(\d{2})")
_AGE_RE = re.compile(r"(20\d{2})\s*г\.?\s*р\.", re.IGNORECASE)
_FORMAT_RE = re.compile(r"формат\s*(\d+)\s*[хx×]\s*(\d+)", re.IGNORECASE)
_SEASON_RE = re.compile(r"(20\d{2})\s*/\s*(20\d{2}|\d{2})")


def as_list(value: Any) -> list[Any]:
    """API иногда возвращает объект вместо списка — приводим к списку."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_age_year(name: str) -> int | None:
    match = _AGE_RE.search(name or "")
    return int(match.group(1)) if match else None


def parse_format(name: str) -> str | None:
    match = _FORMAT_RE.search(name or "")
    return f"{match.group(1)}×{match.group(2)}" if match else None


def parse_season_label(name: str) -> tuple[int, int] | None:
    match = _SEASON_RE.search(name or "")
    if not match:
        return None
    start = int(match.group(1))
    end_text = match.group(2)
    end = int(end_text) if len(end_text) == 4 else 2000 + int(end_text)
    return start, end


def parse_game_datetime(
    display_date: str,
    short_date: str,
    *,
    season_start: int | None = None,
    season_end: int | None = None,
) -> tuple[str, str]:
    """Возвращает (ISO-дата, время ЧЧ:ММ или пустую строку).

    ``displayDate`` обычно выглядит как «31 октября, суббота | 09:45» — без года,
    поэтому год восстанавливается по сезону: июль–декабрь относятся к первому
    году сезона, январь–июнь — ко второму.
    """
    text = (display_date or "").strip().lower()
    match = _DISPLAY_DATE_RE.search(text)
    iso = ""
    if match:
        day = int(match.group(1))
        month = MONTHS.get(match.group(2).replace("ё", "е"))
        year = int(match.group(3)) if match.group(3) else None
        if month and year is None and season_start and season_end:
            year = season_start if month >= 7 else season_end
        if month and year:
            iso = date(year, month, day).isoformat()
    if not iso:
        short = _SHORT_DATE_RE.search(short_date or "")
        year_match = re.search(r"(\d{4})", short_date or "")
        if short and year_match:
            iso = f"{year_match.group(1)}-{short.group(2)}-{short.group(1)}"

    clock = ""
    for source in (display_date or "", short_date or ""):
        found = _CLOCK_RE.search(source)
        if found and (found.group(1), found.group(2)) != ("00", "00"):
            clock = f"{found.group(1)}:{found.group(2)}"
            break
    return iso, clock


@dataclass
class FhmApi:
    http: FhmHttp

    # -- справочники ----------------------------------------------------

    def seasons(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        return as_list(self.http.get_json("/api/filter/season", refresh=refresh))

    def tournaments(self, season: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return as_list(self.http.post_json("/api/filter/tournament", {"season": season}, refresh=refresh))

    def stages(self, tournament: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return as_list(self.http.post_json("/api/filter/stage", {"tournament": tournament}, refresh=refresh))

    def groups(self, stage: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return as_list(self.http.post_json("/api/filter/group", {"stage": stage}, refresh=refresh))

    def teams(self, group: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        return as_list(self.http.post_json("/api/filter/team", {"group": group}, refresh=refresh))

    def tours(
        self,
        season: int,
        tournament: int,
        stage: int,
        group: int,
        *,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        body = {"season": season, "tournament": tournament, "stage": stage, "group": group}
        return as_list(self.http.post_json("/api/filter/tour", body, refresh=refresh))

    # -- матчи ----------------------------------------------------------

    def game_page(
        self,
        season: int,
        *,
        tournament: int | None = None,
        stage: int | None = None,
        group: int | None = None,
        tour: int | None = None,
        limit: int = 50,
        offset: int = 0,
        refresh: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"season": season, "limit": limit, "offset": offset}
        if tournament is not None:
            body["tournament"] = tournament
        if stage is not None:
            body["stage"] = stage
        if group is not None:
            body["group"] = group
        if tour is not None:
            body["tour"] = tour
        data = self.http.post_json("/api/game/list", body, refresh=refresh)
        return data if isinstance(data, dict) else {"count": len(as_list(data)), "items": as_list(data)}

    def all_games(
        self,
        season: int,
        *,
        tournament: int | None = None,
        stage: int | None = None,
        group: int | None = None,
        page_size: int = config.GAME_PAGE_SIZE,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self.game_page(
                season,
                tournament=tournament,
                stage=stage,
                group=group,
                limit=page_size,
                offset=offset,
                refresh=refresh,
            )
            batch = as_list(page.get("items"))
            total = int(page.get("count") or 0)
            items.extend(batch)
            offset += page_size
            if not batch or offset >= total:
                break
        return items

    def roster(self, team_id: int, season: int, *, refresh: bool = False) -> list[dict[str, Any]]:
        data = self.http.get_json(f"/api/team/{team_id}/player?season={season}", refresh=refresh)
        if isinstance(data, dict) and "value" in data:
            data = data["value"]
        return as_list(data)


@dataclass(frozen=True)
class NormalizedGame:
    id: int
    season: int
    tournament_id: int
    stage_id: int
    group_id: int
    tour_name: str
    tournament_name: str
    group_name: str
    date_iso: str
    time: str
    home_name: str
    away_name: str
    home_goals: int | None
    away_goals: int | None
    status: int
    overtime: bool
    shootout: bool
    technical_defeat: bool
    cancel_status: Any
    is_live: bool
    url: str

    @property
    def played(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None


def normalize_game(
    item: dict[str, Any],
    *,
    season: int,
    tournament_id: int,
    stage_id: int,
    group_id: int,
    season_start: int | None = None,
    season_end: int | None = None,
) -> NormalizedGame | None:
    game_id = item.get("id")
    if game_id is None:
        return None
    team1 = item.get("team1") or {}
    team2 = item.get("team2") or {}
    date_iso, clock = parse_game_datetime(
        str(item.get("displayDate") or ""),
        str(item.get("date") or ""),
        season_start=season_start,
        season_end=season_end,
    )

    def to_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return NormalizedGame(
        id=int(game_id),
        season=season,
        tournament_id=tournament_id,
        stage_id=stage_id,
        group_id=group_id,
        tour_name=str(item.get("tour") or ""),
        tournament_name=str(item.get("tournament") or ""),
        group_name=str(item.get("group") or ""),
        date_iso=date_iso,
        time=clock,
        home_name=str(team1.get("name") or "").strip(),
        away_name=str(team2.get("name") or "").strip(),
        home_goals=to_int(team1.get("score")),
        away_goals=to_int(team2.get("score")),
        status=int(item.get("status") or 0),
        overtime=bool(item.get("overtime")),
        shootout=bool(item.get("shootout")),
        technical_defeat=bool(item.get("technicalDefeat")),
        cancel_status=item.get("cancelStatus"),
        is_live=bool(item.get("isLive")),
        url=f"{config.BASE_URL}{item.get('url') or f'/game/{game_id}'}",
    )


def unique_by(items: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: dict[Any, dict[str, Any]] = {}
    for item in items:
        seen.setdefault(item.get(key), item)
    return list(seen.values())
