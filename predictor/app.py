"""FHM Hockey Predictor — локальный русскоязычный интерфейс (Streamlit).

Запуск:  streamlit run app.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from fhm_predictor import config, db
from fhm_predictor.backtest import run_backtest
from fhm_predictor.engine import PlayerStrength
from fhm_predictor.export import backup_database, export_tables
from fhm_predictor.predict import Prediction, build_prediction, save_prediction
from fhm_predictor.projections import projected_groups
from fhm_predictor.quality import run_checks
from fhm_predictor import repository as repo

st.set_page_config(page_title="FHM Hockey Predictor", page_icon="🏒", layout="wide")

OUTCOME_TEXT = ("победа хозяев", "ничья", "победа гостей")


@st.cache_resource
def get_connection():
    conn = db.connect()
    db.init_db(conn)
    return conn


conn = get_connection()


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def team_name(team_id: int) -> str:
    row = conn.execute("SELECT name FROM teams WHERE id = ?", (team_id,)).fetchone()
    return row["name"] if row else f"#{team_id}"


def match_label(row) -> str:
    score = ""
    if row["home_goals"] is not None and row["away_goals"] is not None:
        score = f"  {row['home_goals']}:{row['away_goals']}"
    clock = f" {row['time']}" if row["time"] else ""
    return f"{row['date']}{clock} · {row['home_name']} — {row['away_name']}{score}"


def render_probabilities(prediction: Prediction) -> None:
    home, draw, away = prediction.ensemble
    columns = st.columns(3)
    for column, label, value in zip(columns, (prediction.home_name, "Ничья", prediction.away_name), (home, draw, away)):
        with column:
            st.metric(label, fmt_pct(value))
    winner_index = max(range(3), key=lambda index: prediction.ensemble[index])
    winner = (prediction.home_name, "ничья", prediction.away_name)[winner_index]
    st.markdown(
        f"**Ожидаемый исход:** {winner} · **Уверенность:** {prediction.confidence} · "
        f"**Учтено матчей:** {prediction.data_quality['history_matches']}"
    )
    st.caption(
        f"Отсечка данных: {prediction.cutoff} · версия модели: ensemble-v1 · "
        f"хеш признаков: `{prediction.features_hash[:16]}…`"
    )


def render_model_table(prediction: Prediction) -> None:
    rows = []
    for name, probabilities in prediction.probabilities.items():
        rows.append(
            {
                "Модель": {
                    "elo": "Elo",
                    "poisson": "Пуассон",
                    "player": "Elo + игроки",
                    "logistic": "Логистическая регрессия",
                    "ensemble": "Ансамбль",
                }[name],
                "Хозяева": fmt_pct(probabilities[0]),
                "Ничья": fmt_pct(probabilities[1]),
                "Гости": fmt_pct(probabilities[2]),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_reasons(prediction: Prediction) -> None:
    for reason in prediction.reasons:
        st.markdown(f"- {reason}")


def section_prediction() -> None:
    st.header("Прогноз матча")
    with st.expander("Как пользоваться", expanded=False):
        st.markdown(
            "1. Выберите турнир — для текущего сезона это "
            "«2026/2027 · 2016 г.р. 26/27 (формат 4х4)».\n"
            "2. Выберите матч: по умолчанию показаны ближайшие будущие игры.\n"
            "3. Нажмите **«Рассчитать прогноз»**.\n"
            "4. Чтобы учесть отсутствие игрока, раскройте «Ручная корректировка состава» "
            "и отметьте его — прогноз пересчитается."
        )

    tournaments = repo.tournaments(conn)
    if not tournaments:
        st.warning("База пуста. Откройте вкладку «Данные» и обновите статистику.")
        return

    tournament_options = {f"{row['season_label']} · {row['name']}": row["id"] for row in tournaments}
    default_key = next((key for key in tournament_options if "4х4" in key and "2016" in key), list(tournament_options)[0])
    selected_tournament = tournament_options[st.selectbox("Турнир", list(tournament_options), index=list(tournament_options).index(default_key))]

    mode = st.radio("Список матчей", ["Предстоящие", "Все"], horizontal=True)
    base_query = """
        SELECT m.*, tr.name AS tournament_name, tr.age_year, tr.format, g.name AS group_name
        FROM matches m
        JOIN tournaments tr ON tr.id = m.tournament_id
        JOIN tournament_groups g ON g.id = m.group_id
        WHERE m.tournament_id = ?
    """
    if mode == "Предстоящие":
        matches = conn.execute(
            base_query + " AND m.played = 0 AND m.date >= date('now') ORDER BY m.date, m.time, m.id",
            (selected_tournament,),
        ).fetchall()
        if not matches:
            st.info("Предстоящих матчей в этом турнире нет — показаны все матчи.")
            mode = "Все"
    if mode == "Все":
        matches = conn.execute(
            base_query + " ORDER BY m.date DESC, m.time DESC, m.id DESC",
            (selected_tournament,),
        ).fetchall()
    if not matches:
        st.info("В этом турнире пока нет матчей.")
        return

    labels = [match_label(row) for row in matches]
    default_match = next((index for index, row in enumerate(matches) if row["id"] == config.CONTROL_MATCH_ID), 0)
    chosen = st.selectbox("Матч", labels, index=default_match)
    match = matches[labels.index(chosen)]

    st.caption(
        f"{match['tournament_name'] or ''} · группа {match['group_name'] or '—'} · {match['format'] or ''} · "
        f"{match['age_year'] or ''} г.р."
    )

    excluded: set[int] = set()
    if match["played"]:
        st.info("Матч уже сыгран: прогноз строится по данным до его начала, результат показан только для сверки.")

    with st.expander("Ручная корректировка состава (режим B)"):
        seasons = repo.seasons(conn)
        season_ids = [row["id"] for row in seasons]
        target_season = match["season_id"]
        roster_season = target_season if target_season in season_ids else (season_ids[-1] if season_ids else None)
        if roster_season:
            options: dict[str, int] = {}
            for team_id, name in ((match["home_team_id"], match["home_name"]), (match["away_team_id"], match["away_name"])):
                for row in repo.roster(conn, team_id, roster_season):
                    options[f"{name}: {row['full_name']} ({row['goals']} г.)"] = row["id"]
            selected_players = st.multiselect(
                "Кого исключить из состава (травма, отъезд, неизвестное участие)",
                options=list(options),
            )
            excluded = {options[label] for label in selected_players}

    button = st.button("Рассчитать прогноз", type="primary")

    cache_key = (match["id"], tuple(sorted(excluded)))
    if button or cache_key in st.session_state.get("predictions", {}):
        store = st.session_state.setdefault("predictions", {})
        if button or cache_key not in store:
            with st.spinner("Считаю рейтинги и вероятности…"):
                try:
                    store[cache_key] = build_prediction(conn, match["id"], excluded_players=excluded or None)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Не удалось рассчитать прогноз: {exc}")
                    return
        prediction = store[cache_key]
        base_key = (match["id"], ())
        if excluded and base_key not in store:
            with st.spinner("Считаю базовый прогноз для сравнения…"):
                try:
                    store[base_key] = build_prediction(conn, match["id"])
                except Exception:  # noqa: BLE001 - сравнение необязательно
                    pass
        render_probabilities(prediction)
        st.subheader("Сравнение моделей")
        render_model_table(prediction)
        st.subheader("Почему такой прогноз")
        render_reasons(prediction)

        if excluded:
            base = store.get(base_key)
            if base:
                delta_home = (prediction.ensemble[0] - base.ensemble[0]) * 100
                st.info(
                    f"Исключение выбранных игроков меняет вероятность победы хозяев на "
                    f"{delta_home:+.1f} п.п. (было {fmt_pct(base.ensemble[0])}, стало {fmt_pct(prediction.ensemble[0])})."
                )

        if match["played"]:
            actual = "победа хозяев" if match["home_goals"] > match["away_goals"] else (
                "ничья" if match["home_goals"] == match["away_goals"] else "победа гостей"
            )
            predicted = max(range(3), key=lambda index: prediction.ensemble[index])
            st.success(
                f"Фактический счёт {match['home_goals']}:{match['away_goals']} — {actual}. "
                f"Прогноз: {OUTCOME_TEXT[predicted]}. {'Совпало' if OUTCOME_TEXT[predicted] == actual else 'Не совпало'}."
            )
            if st.button("Сохранить прогноз в неизменяемый файл"):
                try:
                    save_prediction(conn, prediction, immutable=True)
                    st.success(f"Сохранено: {config.PREDICTIONS_DIR / ('match_' + str(match['id']) + '.json')}")
                except FileExistsError as exc:
                    st.warning(str(exc))


@st.cache_data(ttl=300, show_spinner=False)
def _projected_tables() -> list[dict]:
    connection = db.connect()
    db.init_db(connection)
    try:
        return [group.as_dict() for group in projected_groups(connection)]
    finally:
        connection.close()


def section_table() -> None:
    st.header("Прогноз турнирной таблицы")
    st.caption(
        "Текущие очки плюс ожидаемые очки за все предстоящие матчи группы. "
        "Правила: 2 очка за победу, 1 за ничью."
    )
    groups = _projected_tables()
    if not groups:
        st.info("Нет предстоящих матчей 2016 г.р. для расчёта.")
        return
    labels = sorted({f"{group['season']} · {group['tournament']}" for group in groups})
    selected = st.selectbox("Турнир", labels)
    for group in groups:
        if f"{group['season']} · {group['tournament']}" != selected:
            continue
        st.subheader(group["group"])
        rows = []
        for team in group["teams"]:
            delta = team["current_rank"] - team["projected_rank"]
            rows.append(
                {
                    "Место": team["projected_rank"],
                    "Δ": f"↑{delta}" if delta > 0 else (f"↓{-delta}" if delta < 0 else "="),
                    "Команда": team["name"],
                    "И": team["played"],
                    "О": team["points"],
                    "+О": round(team["expected_points"], 1),
                    "Прогноз": round(team["projected_points"], 1),
                    "РГ": round(team["projected_goal_diff"], 0),
                    "Осталось": team["remaining"],
                }
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(
            f"Предстоящих матчей в группе: {group['matches']}. "
            "Прогноз — математическое ожидание, а не гарантия."
        )


def section_players() -> None:
    st.header("Игроки")
    seasons = repo.seasons(conn)
    season_labels = {f"{row['label']}": row["id"] for row in seasons}
    season_label = st.selectbox("Сезон", list(season_labels))
    season_id = season_labels[season_label]
    teams = repo.team_rows(conn, season_id)
    if not teams:
        st.info("Нет команд за выбранный сезон.")
        return
    team_labels = {row["name"]: row["id"] for row in teams}
    team_label = st.selectbox("Команда", list(team_labels))
    team_id = team_labels[team_label]

    roster = repo.roster(conn, team_id, season_id)
    if not roster:
        st.info("Заявка не найдена.")
        return
    max_games = max((row["games"] for row in roster), default=1) or 1
    frame = pd.DataFrame(
        [
            {
                "Игрок": row["full_name"],
                "№": row["number"],
                "Роль": row["role"],
                "Год рождения": row["birth_date"],
                "Игры": row["games"],
                "Голы": row["goals"],
                "Передачи": row["assists"],
                "Очки": row["points"],
                "Штраф": row["penalties"],
                "Участие": round(min(1.0, row["games"] / max_games), 2),
                "ID ФХМ": row["id"],
            }
            for row in roster
        ]
    )
    st.dataframe(frame, hide_index=True, width="stretch")
    st.caption(
        "«Участие» — доля сыгранных матчей команды; это приближение вероятности "
        "участия, а не официальное подтверждение."
    )

    player_labels = {f"{row['full_name']} (ID {row['id']})": row["id"] for row in roster}
    chosen = st.selectbox("Карточка игрока", list(player_labels))
    player_id = player_labels[chosen]
    player = repo.player_row(conn, player_id)
    if player:
        st.subheader(player["full_name"])
        st.caption(f"Дата рождения: {player['birth_date'] or 'не указана'} · роль: {player['role'] or '—'} · карточка: {player['url']}")
    history = repo.player_history(conn, player_id)
    if history:
        st.markdown("**История выступлений по сезонам**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Сезон": row["season_label"],
                        "Команда": row["team_name"],
                        "Игры": row["games"],
                        "Голы": row["goals"],
                        "Передачи": row["assists"],
                    }
                    for row in history
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        transitions = []
        ordered = sorted(history, key=lambda row: row["season_id"])
        for previous, current in zip(ordered, ordered[1:]):
            if previous["team_name"] != current["team_name"]:
                transitions.append(
                    f"{previous['season_label']}: {previous['team_name']} → {current['season_label']}: {current['team_name']}"
                )
        if transitions:
            st.markdown("**Подтверждённые переходы (по смене команды между сезонами)**")
            for transition in transitions:
                st.markdown(f"- {transition}")
        else:
            st.caption("Смены команды между сезонами не зафиксировано.")


def section_comparison() -> None:
    st.header("Сравнение команд")
    teams = repo.team_rows(conn, 5) or repo.teams(conn)
    if len(teams) < 2:
        st.info("Недостаточно команд в базе.")
        return
    labels = {row["name"]: row["id"] for row in teams}
    names = list(labels)
    col1, col2 = st.columns(2)
    with col1:
        first = st.selectbox("Команда 1", names, index=0)
    with col2:
        second = st.selectbox("Команда 2", names, index=1 if len(names) > 1 else 0)
    if first == second:
        st.warning("Выберите две разные команды.")
        return

    elo = repo.elo_snapshot(conn)
    for name in (first, second):
        team_id = labels[name]
        info = elo.get(team_id, {"elo": 1500.0, "games": 0})
        st.metric(name, f"Elo {info['elo']:.0f}", f"{info['games']} матчей")

    player_strength = PlayerStrength()
    player_strength.build(conn)
    latest_season = max((row["id"] for row in repo.seasons(conn)), default=5)

    st.markdown("**Сила состава по прошлым сезонам**")
    col1, col2 = st.columns(2)
    for column, name in ((col1, first), (col2, second)):
        with column:
            strength = player_strength.team_strength(labels[name], latest_season)
            st.metric(f"{name}: условная сила", f"{strength:.2f}" if strength is not None else "нет данных")
            players = sorted(
                player_strength.lineup(labels[name], latest_season),
                key=lambda player: (player.participation * player.impact),
                reverse=True,
            )[:5]
            if players:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Игрок": player.name,
                                "Игры": player.games,
                                "Голы": player.goals,
                                "Вклад": round(player.impact, 2),
                            }
                            for player in players
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )

    st.markdown("**Последние матчи**")
    col1, col2 = st.columns(2)
    for column, name in ((col1, first), (col2, second)):
        with column:
            st.markdown(f"*{name}*")
            rows = repo.team_matches(conn, labels[name], limit=5)
            if rows:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Дата": row["date"],
                                "Матч": f"{row['home_name']} — {row['away_name']}",
                                "Счёт": f"{row['home_goals']}:{row['away_goals']}",
                            }
                            for row in rows
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.caption("Нет матчей.")

    st.markdown("**Очные встречи**")
    meetings = repo.h2h(conn, labels[first], labels[second], limit=10)
    if meetings:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Дата": row["date"],
                        "Турнир": row["tournament_id"],
                        "Матч": f"{row['home_name']} — {row['away_name']}",
                        "Счёт": f"{row['home_goals']}:{row['away_goals']}",
                    }
                    for row in meetings
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("Очных матчей в базе нет.")


def section_quality() -> None:
    st.header("Качество модели")
    path = config.PROJECT_DIR / "reports" / "backtest.json"
    if not path.exists():
        st.info("Backtest ещё не рассчитан. Запустите `python main.py backtest`.")
        return
    report = json.loads(path.read_text(encoding="utf-8"))
    st.caption(
        f"Оценено матчей: {report['evaluated']} из {report['matches_total']} "
        f"({report['date_from']} — {report['date_to']}), разогрев: {report['warmup']}."
    )
    labels = {
        "elo": "Elo",
        "poisson": "Пуассон",
        "player": "Elo + игроки",
        "logistic": "Логистическая регрессия",
        "ensemble": "Ансамбль",
    }
    rows = []
    for name, metrics in report["models"].items():
        rows.append(
            {
                "Модель": labels.get(name, name),
                "Точность": metrics["accuracy"],
                "Brier": metrics["brier"],
                "Log loss": metrics["log_loss"],
                "95% интервал точности": f"{metrics['accuracy_ci95'][0]:.3f}–{metrics['accuracy_ci95'][1]:.3f}",
                "Матчей": metrics["n"],
            }
        )
    frame = pd.DataFrame(rows).sort_values("Log loss")
    st.dataframe(frame, hide_index=True, width="stretch")

    best = frame.iloc[0]["Модель"]
    st.caption(f"Лучшая по log loss: {best}. Меньше — лучше; случайный прогноз даёт ≈1.1.")

    st.markdown("**Калибровка (победа хозяев)**")
    model_key = st.selectbox("Модель", list(report["models"]), format_func=lambda key: labels.get(key, key))
    calibration = report["models"][model_key]["calibration"]
    if calibration:
        st.dataframe(pd.DataFrame(calibration), hide_index=True, width="stretch")
        chart = pd.DataFrame(calibration).set_index("predicted")["observed"]
        st.line_chart(chart)

    if report.get("slices"):
        st.markdown("**Точность по срезам**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Срез": name,
                        "Матчей": values["ensemble"]["n"],
                        "Точность (ансамбль)": values["ensemble"]["accuracy"],
                        "Brier": values["ensemble"]["brier"],
                    }
                    for name, values in sorted(report["slices"].items())
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    st.warning(
        "Метрики получены на матчах 2016–2017 г.р. и не гарантируют такую же точность на будущих встречах. "
        "Выборка небольшая, интервалы широкие."
    )


def section_data() -> None:
    st.header("Управление данными")
    info = conn.execute("SELECT MAX(fetched_at) AS value FROM matches").fetchone()["value"]
    counts = db.counts(conn)
    col1, col2, col3 = st.columns(3)
    col1.metric("Матчей", counts.get("matches", 0))
    col2.metric("Игроков", counts.get("players", 0))
    col3.metric("Последнее обновление", (info or "—")[:16])

    st.markdown("**Действия**")
    password = st.text_input(
        "Пароль для сбора статистики и пересчёта модели",
        type="password",
        help="Пароль: refresh",
    )
    allowed = password == "refresh"
    if not allowed:
        st.caption("Кнопки обновления заблокированы. Введите пароль refresh.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Обновить статистику ФХМ", disabled=not allowed):
            with st.spinner("Скачиваю новые матчи и заявки…"):
                result = subprocess.run(
                    [sys.executable, "main.py", "collect"],
                    cwd=str(config.PROJECT_DIR),
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
            if result.returncode == 0:
                st.success("Обновление завершено.")
            else:
                st.error("Обновление завершилось ошибкой.")
            st.code((result.stdout or "")[-3000:] + "\n" + (result.stderr or "")[-2000:])
        if st.button("Пересчитать backtest", disabled=not allowed):
            with st.spinner("Иду по хронологии матчей…"):
                try:
                    report = run_backtest(conn)
                    st.success(
                        f"Готово: оценено {report['evaluated']} матчей, "
                        f"точность ансамбля {report['models']['ensemble']['accuracy']:.3f}."
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Ошибка: {exc}")
    with col2:
        if st.button("Проверить качество данных"):
            checks = run_checks(conn)
            st.dataframe(pd.DataFrame(checks), hide_index=True, width="stretch")
        if st.button("Экспортировать базу (CSV + Excel)"):
            paths = export_tables(conn)
            st.success(f"Готово: {len(paths)} файлов в {config.EXPORT_DIR}")
            st.dataframe(pd.DataFrame([{"Файл": str(path)} for path in paths.values()]), hide_index=True)
        if st.button("Создать резервную копию"):
            destination = backup_database()
            st.success(f"Копия: {destination}")

    st.markdown("**Последние запуски сбора**")
    runs = repo.collection_runs(conn, limit=8)
    if runs:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": row["id"],
                        "Начало": row["started_at"],
                        "Завершение": row["finished_at"],
                        "Статус": row["status"],
                        "Ошибка": (row["error"] or "")[:120],
                    }
                    for row in runs
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    issues = repo.quality_issues(conn, limit=30)
    if issues:
        st.markdown("**Последние замечания**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Тип": row["kind"], "Важность": row["severity"], "Объект": row["entity"], "Сообщение": row["message"][:160]}
                    for row in issues
                ]
            ),
            hide_index=True,
            width="stretch",
        )


def main() -> None:
    st.title("FHM Hockey Predictor")
    st.caption("Прогноз матчей команд ФХМ 2016–2017 г.р. по официальным данным fhmoscow.com")

    with st.sidebar:
        st.header("Навигация")
        page = st.radio("Раздел", ["Прогноз", "Таблица", "Игроки", "Сравнение команд", "Качество модели", "Данные"])
        st.divider()
        last = conn.execute("SELECT MAX(fetched_at) AS value FROM matches").fetchone()["value"]
        st.caption(f"Данные: {(last or 'нет')[:16]}")
        st.caption("Модель: ensemble-v1")
        st.caption(f"База: {config.DB_PATH.name}")

    if page == "Прогноз":
        section_prediction()
    elif page == "Таблица":
        section_table()
    elif page == "Игроки":
        section_players()
    elif page == "Сравнение команд":
        section_comparison()
    elif page == "Качество модели":
        section_quality()
    else:
        section_data()


if __name__ == "__main__":
    main()
