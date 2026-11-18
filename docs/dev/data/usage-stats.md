# usage: статистика периода и язык распознавания

Добавлено фичей `20261118-story-stats-30d`.

## Колонка `usage.language`

- `VARCHAR(16)`, nullable, миграция `e8b7a6d5c4f3` (down_revision `b1c2d3e4f5a6`).
- Пишется код языка из `TranscriptionResult.language` (ISO 639-1) в трёх местах:
  - Stage-3 update в `TranscriptionOrchestrator` (основной путь);
  - создание child-записи при перераспознавании (`retranscribe_handlers`);
  - benchmark-режим (`handlers`, при `usage_repo.create`).
- Исторические записи остаются NULL — обратного заполнения нет.
- `UsageRepository.create/update` принимают `language`; update меняет только
  при не-None (как `model_size`).

## `UsagePeriodStats` и `get_period_stats(user_id, since)`

Дата-класс: `total_count`, `total_duration_seconds`,
`languages: list[tuple[Optional[str], int]]`.

Один GROUP BY-запрос по `usage` с фильтрами:

- `user_id`;
- `created_at >= since` (скользящее окно, вызов с now(UTC) − 30 суток);
- `parent_usage_id IS NULL` — перераспознавания не считаются новыми
  сообщениями;
- `transcription_length IS NOT NULL` — только завершённые распознавания.

Порядок языков: по убыванию количества, при равенстве — по коду языка
(детерминированно).

## /stats (вывод)

- Блок за 30 дней: сообщения, длительность (`_format_duration`, «1 ч 2 мин
  5 сек»), языки с русскими названиями (`_language_display`; NULL/`unknown`
  → «не определён», неизвестный код → сам код).
- Строка all-time (`count_by_user_id`) и дата регистрации.
- Пустое окно при all-time > 0 → сообщение про пустые 30 дней + all-time.
