"""Разбор HTML-протокола матча с сайта ФХМ.

Страница матча отдаётся сервером целиком: счёт, счёт по периодам, события
(голы с авторами) и тренерский штаб. Построчные составы подгружаются отдельным
JS-модулем и в HTML отсутствуют — это ограничение зафиксировано в документации.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from lxml import html as lxml_html

from . import config, db
from .http import FhmHttp

_PLAYER_HREF_RE = re.compile(r"/player/(\d+)")
_SCORE_RE = re.compile(r"(\d+)\s*:\s*(\d+)")
_PERIOD_RE = re.compile(r"(\d+)\s*период", re.IGNORECASE)
_MINUTE_RE = re.compile(r"(\d{1,3}):(\d{2})")


@dataclass
class ParsedEvent:
    period: int
    minute: str
    team_name: str
    player_id: int | None
    player_name: str
    event_type: str
    score_home: int | None
    score_away: int | None


@dataclass
class ParsedGame:
    match_id: int
    title: str
    tournament: str
    date_iso: str
    time: str
    place: str
    home_name: str
    away_name: str
    home_goals: int | None
    away_goals: int | None
    periods: list[tuple[int, int | None, int | None]] = field(default_factory=list)
    events: list[ParsedEvent] = field(default_factory=list)
    staff: list[dict[str, str]] = field(default_factory=list)

    @property
    def goals_by_player(self) -> dict[int, int]:
        result: dict[int, int] = {}
        for event in self.events:
            if event.event_type == "goal" and event.player_id:
                result[event.player_id] = result.get(event.player_id, 0) + 1
        return result


def _text(node) -> str:
    return " ".join(node.text_content().split()) if node is not None else ""


def _to_int(value: str) -> int | None:
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


def parse_game_page(html_text: str, *, match_id: int, url: str = "") -> ParsedGame:
    doc = lxml_html.fromstring(html_text)
    title = doc.findtext(".//title") or ""

    teams = [_text(node) for node in doc.xpath("//div[contains(@class,'match-scores')]//a[contains(@class,'name')]")]
    if len(teams) < 2:
        teams = [_text(node) for node in doc.xpath("//div[contains(@class,'scores')]//a[contains(@class,'name')]")]
    home_name = teams[0] if teams else ""
    away_name = teams[1] if len(teams) > 1 else ""

    scores = [_text(node) for node in doc.xpath("//div[contains(@class,'scores-table')]//p[contains(@class,'h2')]")]
    home_goals = _to_int(scores[0]) if len(scores) > 0 else None
    away_goals = _to_int(scores[1]) if len(scores) > 1 else None

    periods: list[tuple[int, int | None, int | None]] = []
    for item in doc.xpath("//ul[contains(@class,'period')]/li"):
        label = item.get("aria-label") or ""
        number = _PERIOD_RE.search(label)
        match = _SCORE_RE.search(_text(item))
        if number and match:
            periods.append((int(number.group(1)), int(match.group(1)), int(match.group(2))))
        elif _text(item):
            match = _SCORE_RE.search(_text(item))
            if match:
                periods.append((len(periods) + 1, int(match.group(1)), int(match.group(2))))

    date_iso = ""
    time_text = ""
    time_node = doc.xpath("//p[contains(@class,'match-date')]//time")
    if time_node:
        datetime_attr = time_node[0].get("datetime") or ""
        if datetime_attr:
            date_iso, _, time_text = datetime_attr.partition("T")
            time_text = time_text[:5]
        else:
            raw = _text(time_node[0])
            date_match = re.search(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", raw.lower())
            if date_match:
                date_iso = raw
            clock = re.search(r"(\d{2}:\d{2})", raw)
            time_text = clock.group(1) if clock else ""

    place = _text(doc.xpath("//p[contains(@class,'match-place')]")[0]) if doc.xpath("//p[contains(@class,'match-place')]") else ""
    tournament = _text(doc.xpath("//h1")[0]) if doc.xpath("//h1") else ""

    events: list[ParsedEvent] = []
    for section in doc.xpath("//section[contains(@class,'events__period')]"):
        period_label = _text(section.xpath(".//h3[contains(@class,'events__period-title')]")[0]) if section.xpath(
            ".//h3[contains(@class,'events__period-title')]"
        ) else ""
        period_match = _PERIOD_RE.search(period_label)
        period = int(period_match.group(1)) if period_match else 0
        for row in section.xpath(".//div[contains(@class,'events__row')]"):
            minute = _text(row.xpath("./div[contains(@class,'timestamp')]")[0]) if row.xpath(
                "./div[contains(@class,'timestamp')]"
            ) else ""
            team = _text(row.xpath(".//div[contains(@class,'events__team')]")[0]) if row.xpath(
                ".//div[contains(@class,'events__team')]"
            ) else ""
            label = _text(row.xpath(".//span[contains(@class,'events__goal-label')]")[0]) if row.xpath(
                ".//span[contains(@class,'events__goal-label')]"
            ) else ""
            player_link = row.xpath(".//a[contains(@href,'/player/')]")
            player_id = None
            player_name = ""
            if player_link:
                href = player_link[0].get("href") or ""
                found = _PLAYER_HREF_RE.search(href)
                player_id = int(found.group(1)) if found else None
                player_name = _text(player_link[0])
            score_node = row.xpath(".//div[contains(@class,'events__count')]")
            score_home = score_away = None
            if score_node:
                aria = score_node[0].get("aria-label") or ""
                score_match = _SCORE_RE.search(aria)
                if score_match:
                    score_home, score_away = int(score_match.group(1)), int(score_match.group(2))
            event_type = "goal" if "гол" in label.lower() else ("penalty" if label else "other")
            events.append(
                ParsedEvent(
                    period=period,
                    minute=minute,
                    team_name=team,
                    player_id=player_id,
                    player_name=player_name,
                    event_type=event_type,
                    score_home=score_home,
                    score_away=score_away,
                )
            )

    staff: list[dict[str, str]] = []
    for card in doc.xpath("//li[contains(@class,'roster-card--staff')]"):
        name = _text(card.xpath(".//a[contains(@class,'roster-profile')]")[0]) if card.xpath(
            ".//a[contains(@class,'roster-profile')]"
        ) else ""
        role = _text(card.xpath(".//span[contains(@class,'game-lineup-staff__role')]")[0]) if card.xpath(
            ".//span[contains(@class,'game-lineup-staff__role')]"
        ) else ""
        if name:
            staff.append({"name": name, "role": role})

    return ParsedGame(
        match_id=match_id,
        title=title,
        tournament=tournament,
        date_iso=date_iso,
        time=time_text,
        place=place,
        home_name=home_name,
        away_name=away_name,
        home_goals=home_goals,
        away_goals=away_goals,
        periods=periods,
        events=events,
        staff=staff,
    )


def collect_protocols(
    conn,
    http: FhmHttp,
    matches: list[tuple[int, str, str, str, int | None, int | None]],
    *,
    progress=lambda message: None,
) -> dict[str, int]:
    """Скачивает и разбирает протоколы.

    ``matches`` — список (match_id, url, home_name, away_name, home_goals, away_goals).
    """
    stats = {"fetched": 0, "parsed": 0, "score_mismatch": 0, "errors": 0, "events": 0}
    for match_id, url, home_name, away_name, home_goals, away_goals in matches:
        try:
            html_text = http.get_html(url)
        except Exception as exc:  # noqa: BLE001
            stats["errors"] += 1
            db.add_issue(
                conn,
                run_id=None,
                kind="protocol_fetch_error",
                severity="error",
                entity=str(match_id),
                message=f"{url}: {exc}",
            )
            conn.commit()
            continue
        stats["fetched"] += 1
        try:
            parsed = parse_game_page(html_text, match_id=match_id, url=url)
        except Exception as exc:  # noqa: BLE001
            stats["errors"] += 1
            db.add_issue(
                conn,
                run_id=None,
                kind="protocol_parse_error",
                severity="error",
                entity=str(match_id),
                message=str(exc),
            )
            conn.commit()
            continue
        stats["parsed"] += 1

        if (
            home_goals is not None
            and away_goals is not None
            and parsed.home_goals is not None
            and parsed.away_goals is not None
            and (home_goals, away_goals) != (parsed.home_goals, parsed.away_goals)
        ):
            stats["score_mismatch"] += 1
            db.add_issue(
                conn,
                run_id=None,
                kind="score_mismatch",
                severity="warning",
                entity=str(match_id),
                message=(
                    f"API {home_goals}:{away_goals} не совпадает с протоколом "
                    f"{parsed.home_goals}:{parsed.away_goals}"
                ),
            )

        team_ids = {home_name: None, away_name: None}
        row = conn.execute("SELECT home_team_id, away_team_id FROM matches WHERE id = ?", (match_id,)).fetchone()
        if row:
            team_ids[home_name] = row["home_team_id"]
            team_ids[away_name] = row["away_team_id"]

        period_rows = [
            {
                "match_id": match_id,
                "period": period,
                "home_goals": home,
                "away_goals": away,
            }
            for period, home, away in parsed.periods
        ]
        if period_rows:
            db.upsert(conn, "match_periods", period_rows, ["match_id", "period"])

        event_rows = []
        for event in parsed.events:
            event_rows.append(
                {
                    "match_id": match_id,
                    "period": event.period,
                    "minute": event.minute,
                    "team_id": team_ids.get(event.team_name),
                    "player_id": event.player_id,
                    "event_type": event.event_type,
                    "detail": event.player_name,
                    "score_home": event.score_home,
                    "score_away": event.score_away,
                    "source": url,
                }
            )
        if event_rows:
            # UNIQUE(match_id, period, minute, player_id, event_type) отсекает дубли.
            db.upsert(
                conn,
                "match_events",
                event_rows,
                ["match_id", "period", "minute", "player_id", "event_type"],
            )
            stats["events"] += len(event_rows)

        for player_id, goals in parsed.goals_by_player.items():
            team_id = None
            for event in parsed.events:
                if event.player_id == player_id and event.team_name in team_ids:
                    team_id = team_ids[event.team_name]
                    break
            if team_id is None:
                continue
            conn.execute(
                """
                INSERT INTO player_match_statistics(player_id, match_id, team_id, goals, assists, participated, source)
                VALUES(?, ?, ?, ?, 0, NULL, ?)
                ON CONFLICT(player_id, match_id) DO UPDATE SET goals = excluded.goals
                """,
                (player_id, match_id, team_id, goals, url),
            )
        conn.commit()
        progress(f"  протокол {match_id}: {parsed.home_name} {parsed.home_goals}:{parsed.away_goals} {parsed.away_name}")
    return stats
