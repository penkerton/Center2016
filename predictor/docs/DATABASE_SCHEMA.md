# Схема базы данных

SQLite, файл `data/fhm.db`. Схема создаётся `db.init_db()`, версия хранится в
`schema_meta.schema_version` (сейчас `1`). Включены внешние ключи и WAL.

## Справочники

### seasons
`id` (PK, ID ФХМ), `label` («2026/2027»), `start_year`, `end_year`,
`is_current`.

### tournaments
`id` (PK), `season_id` → seasons, `name`, `age_year` (2016/2017), `format`
(«4×4»/«5×5»), `play_off`, `transition`, `is_current`.

### stages
`id` (PK), `tournament_id` → tournaments, `name`, `is_current`,
`is_transition`.

### tournament_groups
`id` (PK), `stage_id` → stages, `tournament_id` → tournaments, `name`
(«Группа А», «Группа В», …).

### teams
`id` (PK, ID ФХМ), `name`, `short_name`, `age_year`, `club` (название без года).

### team_seasons
`team_id`, `season_id`, `tournament_id`, `group_id` — в каких группах команда
играла в сезоне. PK — все четыре поля.

## Матчи

### matches
`id` (PK, ID ФХМ), `season_id`, `tournament_id`, `stage_id`, `group_id`,
`tour_name`, `date` (ISO), `time`, `home_team_id`, `away_team_id`,
`home_name`, `away_name`, `home_goals`, `away_goals`, `status`, `overtime`,
`shootout`, `technical_defeat`, `cancel_status`, `played`,
`source_url` (страница матча), `fetched_at`, `updated_at`.

Индексы: дата, домашняя/гостевая команда, сезон, группа.

### match_periods
`match_id`, `period`, `home_goals`, `away_goals`. Заполняется из HTML-протокола.

### match_events
`id`, `match_id`, `period`, `minute`, `team_id`, `player_id`, `event_type`
(`goal`/`penalty`), `detail`, `score_home`, `score_away`, `source`.
Уникальность: `(match_id, period, minute, player_id, event_type)`.

## Игроки

### players
`id` (PK, ID из `/player/{id}`), `full_name`, `birth_date`, `role`
(В/З/Н), `url`, `first_seen`, `last_seen`.

### team_rosters
`team_id`, `season_id`, `player_id`, `number`, `role`, `source`, `fetched_at`.
PK — `(team_id, season_id, player_id)`.

### player_season_stats
`player_id`, `team_id`, `season_id`, `tournament_id`, `games`, `goals`,
`assists`, `points`, `penalties`, `missed`, `time_seconds`, `source`,
`fetched_at`.

Важно: это сезонные агрегаты из заявки, а не суммы по протоколам.

### player_team_history
`player_id`, `team_id`, `season_id`, `first_match_date`, `last_match_date`,
`games`, `goals`, `assists`, `source`. Строится из `player_season_stats`
функцией `rebuild_player_history()`. Даты первого/последнего матча пока пустые:
построчных составов нет.

### player_match_statistics
`player_id`, `match_id`, `team_id`, `goals`, `assists`, `participated`,
`source`. Заполняется из протоколов; `participated = NULL`, потому что факт
участия в матче официально не подтверждён (известны только авторы голов).

## Рейтинги и прогнозы

### team_ratings_history
`team_id`, `as_of`, `elo`, `matches`, `attack`, `defense`. Зарезервирована для
снимков рейтингов; текущая версия пересчитывает Elo на лету.

### player_ratings_history
`player_id`, `as_of`, `rating`, `games`, `goals`, `assists`.

### predictions
`id`, `match_id`, `model_version`, `model_kind`, `created_at`, `cutoff`,
`prob_home`, `prob_draw`, `prob_away`, `features_json`, `features_hash`,
`actual_home`, `actual_away`, `actual_outcome`, `correct`.

### model_versions
`id` (строка вида `ensemble-v1-20261101-0107`), `created_at`, `kind`,
`params_json`, `metrics_json`, `is_active`, `notes`.

### model_training_runs
`id`, `started_at`, `finished_at`, `status`, `model_version`, `params_json`,
`metrics_json`, `error`.

## Журналы

### collection_runs
`id`, `started_at`, `finished_at`, `status` (`running`/`ok`/`failed`),
`params_json`, `stats_json`, `error`.

### data_quality_issues
`id`, `run_id`, `kind`, `severity`, `entity`, `message`, `created_at`.

## Примеры запросов

Последние матчи команды:

```sql
SELECT date, home_name, away_name, home_goals, away_goals
FROM matches
WHERE (home_team_id = :team OR away_team_id = :team) AND played = 1
ORDER BY date DESC LIMIT 10;
```

Игроки команды с агрегатами:

```sql
SELECT p.full_name, r.number, s.games, s.goals, s.assists
FROM team_rosters r
JOIN players p ON p.id = r.player_id
LEFT JOIN player_season_stats s
       ON s.player_id = r.player_id AND s.team_id = r.team_id AND s.season_id = r.season_id
WHERE r.team_id = :team AND r.season_id = :season
ORDER BY s.goals DESC;
```

История игрока:

```sql
SELECT se.label, t.name, th.games, th.goals, th.assists
FROM player_team_history th
JOIN seasons se ON se.id = th.season_id
JOIN teams t ON t.id = th.team_id
WHERE th.player_id = :player
ORDER BY th.season_id;
```

## Происхождение данных

- `matches.source_url` — страница матча на ФХМ.
- `team_rosters.source`, `player_season_stats.source` — URL заявки.
- `match_events.source` — URL протокола.
- `fetched_at` — время загрузки.
- `collection_runs` — параметры и статистика каждого запуска.

## Ограничения схемы

- Нет таблицы клубов: клуб хранится строкой в `teams.club`.
- Нет `goalkeeper_statistics`: официальных сейвов и бросков сайт не отдаёт.
- `team_ratings_history` и `player_ratings_history` заполняются снимком на дату
  последнего матча при каждом `backtest` (262 команды и 3 299 игроков на
  2026-11-01). История снимков по датам пока не ведётся — только последний.
