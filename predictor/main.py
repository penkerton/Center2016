"""CLI FHM Hockey Predictor.

Команды:
    python main.py init                       — создать базу и схему
    python main.py collect [--season 5]       — обновить данные ФХМ
    python main.py status                     — состояние базы
    python main.py backtest                   — walk-forward проверка моделей
    python main.py predict --match 22449      — прогноз матча
    python main.py verify --match 22449       — сверка сохранённого прогноза
    python main.py protocols --season 5       — протоколы матчей (события, периоды)
    python main.py export                     — CSV + Excel
    python main.py backup                     — резервная копия базы
    python main.py check                      — проверки качества данных
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime

from fhm_predictor import config, db, repository as repo
from fhm_predictor.backtest import run_backtest, save_model_version
from fhm_predictor.collect import collect
from fhm_predictor.coverage import save_coverage
from fhm_predictor.export import backup_database, export_tables
from fhm_predictor.export_site import export_site
from fhm_predictor.http import FhmHttp
from fhm_predictor.predict import build_prediction, save_prediction, verify_prediction
from fhm_predictor.protocols import collect_protocols
from fhm_predictor.quality import run_checks


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def cmd_init(_args: argparse.Namespace) -> int:
    conn = db.connect()
    db.init_db(conn)
    log(f"База готова: {config.DB_PATH}")
    conn.close()
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    seasons = tuple(args.season) if args.season else config.TARGET_SEASONS
    log(f"Сезоны: {', '.join(str(s) for s in seasons)}")
    stats = collect(
        seasons,
        refresh=args.refresh,
        with_rosters=not args.no_rosters,
        progress=log,
    )
    log(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    conn = db.connect()
    db.init_db(conn)
    result = db.counts(conn)
    last = db.latest_update(conn)
    log(f"База: {config.DB_PATH}")
    log(f"Последнее обновление матчей: {last or 'нет данных'}")
    for table, count in result.items():
        log(f"  {table:28s} {count:6d}")
    conn.close()
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    conn = db.connect()
    report = run_backtest(conn, warmup=args.warmup, retrain_every=args.retrain)
    save_model_version(
        conn,
        model_id=f"ensemble-v1-{datetime.now().strftime('%Y%m%d-%H%M')}",
        params={
            "warmup": args.warmup,
            "retrain_every": args.retrain,
            "ensemble_weights": report["ensemble_weights"],
        },
        metrics={name: values for name, values in report["models"].items()},
        notes="Walk-forward backtest",
    )
    for name, metrics in report["models"].items():
        log(
            f"{name:10s} accuracy={metrics['accuracy']:.3f} "
            f"brier={metrics['brier']:.3f} logloss={metrics['log_loss']:.3f} n={metrics['n']}"
        )
    log(f"Отчёт: {config.PROJECT_DIR / 'reports' / 'backtest.json'}")
    conn.close()
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    conn = db.connect()
    cutoff = datetime.fromisoformat(args.cutoff) if args.cutoff else None
    prediction = build_prediction(conn, args.match, cutoff=cutoff)
    payload = prediction.as_dict()
    log(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.save:
        save_prediction(conn, prediction, immutable=args.immutable)
        log(f"Сохранено: {config.PREDICTIONS_DIR / f'match_{args.match}.json'}")
    conn.close()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    conn = db.connect()
    comparison = verify_prediction(conn, args.match)
    log(json.dumps(comparison, ensure_ascii=False, indent=2))
    conn.close()
    return 0


def cmd_protocols(args: argparse.Namespace) -> int:
    conn = db.connect()
    query = """
        SELECT id, source_url, home_name, away_name, home_goals, away_goals
        FROM matches
        WHERE played = 1 AND source_url IS NOT NULL
    """
    params: list[object] = []
    if args.match:
        placeholders = ",".join("?" for _ in args.match)
        query += f" AND id IN ({placeholders})"
        params.extend(args.match)
    else:
        if args.season:
            query += " AND season_id = ?"
            params.append(args.season)
        if args.tournament:
            query += " AND tournament_id = ?"
            params.append(args.tournament)
    query += " ORDER BY date DESC"
    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)
    rows = conn.execute(query, params).fetchall()
    if not rows:
        log("Нет матчей для разбора протоколов.")
        return 0
    log(f"Протоколов к загрузке: {len(rows)}")
    http = FhmHttp(logger=log)
    matches = [
        (row["id"], row["source_url"], row["home_name"], row["away_name"], row["home_goals"], row["away_goals"])
        for row in rows
    ]
    stats = collect_protocols(conn, http, matches, progress=log)
    log(json.dumps(stats, ensure_ascii=False, indent=2))
    conn.close()
    return 0


def cmd_export(_args: argparse.Namespace) -> int:
    conn = db.connect()
    paths = export_tables(conn)
    for name, path in paths.items():
        log(f"{name:24s} {path}")
    conn.close()
    return 0


def cmd_backup(_args: argparse.Namespace) -> int:
    path = backup_database()
    log(f"Резервная копия: {path}")
    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    conn = db.connect()
    checks = run_checks(conn)
    for check in checks:
        log(f"{check['severity']:8s} {check['kind']:28s} {check['count']:6d}  {check['message']}")
    conn.close()
    return 0


def cmd_report(_args: argparse.Namespace) -> int:
    conn = db.connect()
    coverage = save_coverage(conn)
    log(json.dumps(coverage["totals"], ensure_ascii=False, indent=2))
    for row in coverage["tournaments"]:
        log(f"  {row['season_label']} · {row['name']}: матчей {row['matches']} (сыграно {row['played']})")
    log(f"Отчёты: {config.PROJECT_DIR / 'reports'}")
    conn.close()
    return 0


def cmd_export_site(_args: argparse.Namespace) -> int:
    conn = db.connect()
    path = export_site(conn)
    log(f"Данные для сайта: {path} ({path.stat().st_size / 1024 / 1024:.2f} МБ)")
    conn.close()
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    """Полный ручной цикл: собрать данные, пересчитать модель, выгрузить сайт,
    закоммитить изменения и (по флагу) опубликовать на GitHub."""
    conn = db.connect()
    try:
        if not args.skip_collect:
            log("Шаг 1/4: сбор данных ФХМ")
            collect(config.TARGET_SEASONS, refresh=False, with_rosters=True, progress=log)
        if not args.skip_backtest:
            log("Шаг 2/4: пересчёт backtest")
            report = run_backtest(conn, warmup=args.warmup, retrain_every=args.retrain)
            save_model_version(
                conn,
                model_id=f"ensemble-v1-{datetime.now().strftime('%Y%m%d-%H%M')}",
                params={"warmup": args.warmup, "retrain_every": args.retrain, "source": "publish"},
                metrics=report["models"],
                notes="Ручная публикация",
            )
        log("Шаг 3/4: выгрузка данных для сайта")
        path = export_site(conn)
        log(f"  {path} ({path.stat().st_size / 1024 / 1024:.2f} МБ)")

        repo = config.CENTER_DIR
        if not (repo / ".git").exists():
            log(f"Это не git-репозиторий: {repo}")
            return 1
        log("Шаг 4/4: git")
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
        )
        if not status.stdout.strip():
            log("Изменений нет — коммит и публикация не нужны.")
            return 0
        # Файлы, которые генерирует Node-апдейтер сайта, не публикуем из Python:
        # их обновляет GitHub Actions, иначе rebase конфликтует каждые 3 часа.
        for generated in ("all_2016_matches_season5.js", "all_2016_players_season5.js", "site_data.js"):
            subprocess.run(["git", "checkout", "--", generated], cwd=repo, check=False)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        message = args.message or "data: update FHM Hockey Predictor"
        subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True)
        if args.push:
            log("  git pull --rebase origin main")
            pull = subprocess.run(
                ["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=repo
            )
            if pull.returncode != 0:
                log("  rebase не удался — публикация остановлена, коммит остался локально.")
                return 1
            log("  git push origin main")
            push = subprocess.run(["git", "push", "origin", "main"], cwd=repo)
            if push.returncode != 0:
                log("  push не удался.")
                return 1
            log("Опубликовано. GitHub Actions пересоберёт страницу через 1–2 минуты.")
        else:
            log("Закоммичено локально. Для публикации: git push origin main")
        return 0
    finally:
        conn.close()


def cmd_serve(args: argparse.Namespace) -> int:
    from fhm_predictor.bridge import serve

    serve(port=args.port, open_browser=args.open)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FHM Hockey Predictor")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="создать базу").set_defaults(func=cmd_init)

    collect_parser = sub.add_parser("collect", help="собрать данные ФХМ")
    collect_parser.add_argument("--refresh", action="store_true", help="игнорировать кеш API")
    collect_parser.add_argument("--no-rosters", action="store_true", help="не обновлять заявки игроков")
    collect_parser.add_argument(
        "--season",
        action="append",
        type=int,
        default=None,
        help="сезон (можно несколько раз), по умолчанию все целевые",
    )
    collect_parser.set_defaults(func=cmd_collect)

    sub.add_parser("status", help="состояние базы").set_defaults(func=cmd_status)

    backtest_parser = sub.add_parser("backtest", help="walk-forward проверка")
    backtest_parser.add_argument("--warmup", type=int, default=120)
    backtest_parser.add_argument("--retrain", type=int, default=30)
    backtest_parser.set_defaults(func=cmd_backtest)

    predict_parser = sub.add_parser("predict", help="прогноз матча")
    predict_parser.add_argument("--match", type=int, required=True)
    predict_parser.add_argument("--cutoff", type=str, default=None, help="ISO-время отсечки")
    predict_parser.add_argument("--save", action="store_true", help="сохранить прогноз в файл и БД")
    predict_parser.add_argument("--immutable", action="store_true", help="не перезаписывать существующий файл")
    predict_parser.set_defaults(func=cmd_predict)

    verify_parser = sub.add_parser("verify", help="сверка прогноза с результатом")
    verify_parser.add_argument("--match", type=int, required=True)
    verify_parser.set_defaults(func=cmd_verify)

    protocols_parser = sub.add_parser("protocols", help="разобрать протоколы матчей")
    protocols_parser.add_argument("--season", type=int, default=None)
    protocols_parser.add_argument("--tournament", type=int, default=None)
    protocols_parser.add_argument("--match", type=int, action="append", default=None)
    protocols_parser.add_argument("--limit", type=int, default=None)
    protocols_parser.set_defaults(func=cmd_protocols)

    sub.add_parser("export", help="экспорт CSV/Excel").set_defaults(func=cmd_export)
    sub.add_parser("backup", help="резервная копия").set_defaults(func=cmd_backup)
    sub.add_parser("check", help="качество данных").set_defaults(func=cmd_check)
    sub.add_parser("report", help="отчёт покрытия").set_defaults(func=cmd_report)
    sub.add_parser("export-site", help="выгрузить данные для статической страницы").set_defaults(func=cmd_export_site)

    publish_parser = sub.add_parser("publish", help="обновить данные, модель и опубликовать сайт")
    publish_parser.add_argument("--push", action="store_true", help="выполнить git push origin main")
    publish_parser.add_argument("--skip-collect", action="store_true")
    publish_parser.add_argument("--skip-backtest", action="store_true")
    publish_parser.add_argument("--message", type=str, default=None)
    publish_parser.add_argument("--warmup", type=int, default=120)
    publish_parser.add_argument("--retrain", type=int, default=30)
    publish_parser.set_defaults(func=cmd_publish)

    serve_parser = sub.add_parser("serve", help="локальный сервер страницы прогноза")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--open", action="store_true", help="открыть браузер")
    serve_parser.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
