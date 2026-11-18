# План: 20261118-story-stats-30d

Ветка: `kanon/20261118-story-stats-30d`. Все пути — от корня репо.

## Волна 1 — реализация

- [x] 1. Модель и миграция
  - `src/storage/models.py`: в `Usage` после `model_size` добавить
    `language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)`
    с комментарием «Stage 3».
  - Миграция `alembic/versions/<rev>_add_language_to_usage.py`,
    `down_revision = "b1c2d3e4f5a6"`: add column `language` VARCHAR(16)
    nullable в `usage`; downgrade — drop column.
  - Проверка: `TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -q` зелёный.
- [x] 2. Репозиторий
  - `src/storage/repositories.py`:
    - `UsageRepository.create(...)` и `.update(...)`: параметр
      `language: Optional[str] = None` (update — только если не None),
      по образцу `model_size`.
    - Дата-класс `UsagePeriodStats(total_count: int,
      total_duration_seconds: float,
      languages: list[tuple[Optional[str], int]])`.
    - Метод `get_period_stats(user_id, since)` — один запрос
      `select(Usage.language, func.count(Usage.id),
      func.sum(Usage.voice_duration_seconds))` c фильтрами:
      `user_id`, `created_at >= since`, `parent_usage_id IS NULL`,
      `transcription_length IS NOT NULL`, GROUP BY language.
      Агрегация в Python → UsagePeriodStats. Сортировка языков по убыванию
      количества.
- [x] 3. Сохранение языка при транскрипции
  - `src/services/transcription_orchestrator.py` (~строка 869, Stage-3
    update): добавить `language=result.language`.
  - `src/bot/retranscribe_handlers.py` (~строка 252, child create):
    добавить `language=result.language`.
  - `src/bot/handlers.py` (benchmark-режим, usage_repo.create):
    добавить `language=best_result.language`.
- [x] 4. Команда /stats
  - `src/bot/handlers.py`, `stats_command`: переписать вывод:
    - Заголовок «📊 Статистика за последние 30 дней».
    - Сообщений обработано, длительность аудио (человеческий формат),
      языки списком с названиями.
    - Строка «Всего за всё время: N сообщений» (существующие
      count_by_user_id + get_user_total_duration).
    - Дата регистрации остаётся.
    - Ветка: all-time 0 → старое сообщение «нет обработанных».
    - Ветка: 30 дней пусто, all-time > 0 → сообщить про пустое окно
      + all-time строка.
  - Хелперы (module-level или статические, с тестами):
    `_format_duration(seconds: float) -> str` → «1 ч 23 мин 45 сек»
    (секунды опускаются, если 0; минуты-часы только из остатка);
    `_language_display(code: Optional[str]) -> str`: словарь код→русское
    название (ru Русский, en Английский, uk Украинский, de Немецкий,
    fr Французский, es Испанский, it Итальянский, pt Португальский,
    pl Польский, tr Турецкий, kk Казахский, ky Кыргызский, uz Узбекский,
    az Азербайджанский, be Белорусский, zh Китайский, ja Японский,
    ko Корейский, ar Арабский, hi Хинди), fallback — сам код;
    None/"unknown" → «не определён».
  - get_session в stats_command уже вызывается напрямую — сохранить
    существующий паттерн (в тестах мокается src.bot.handlers.get_session).
- [x] 5. Тесты
  - `tests/unit/test_handlers.py` TestStatsCommand: обновить под новый
    вывод (мок `get_period_stats`), добавить случаи: 30 дней пусто при
    all-time > 0; языки NULL → «не определён»; форматирование длительности.
  - Репозиторные тесты (файл с существующими UsageRepository-тестами;
    если нет — `tests/unit/test_usage_stats_repo.py`, in-memory SQLite по
    conftest): окно 30 дней (старые записи не считаются), child-записи
    (parent_usage_id) исключаются, incomplete (transcription_length NULL)
    исключаются, группировка языков, create/update пишут language.
- [x] 6. Линтеры и типы
  - `uv run ruff check src/ tests/`; `uv run black src/ tests/`;
    `uv run mypy src/` — чисто.
  - `TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -q` — зелёный.

## Волна 2 — проверка и оформление

- [x] 7. Верификация оркестратором
  - Ревью диффа, прогон тестов/линтеров своими руками, smoke:
    `uv run alembic upgrade head` на временной SQLite.
- [x] 8. Канон-артефакты
  - Чекбоксы плана, отчёт verify, статусы: in-progress → verify.
  - `kanon/STATUS.md` — строка фичи.
- [ ] 9. PR в main (шаблон репо, без личных данных), тестовый стенд —
  решение оператора. Релиз создаст build-and-tag (код меняется — тег
  будет), постдеплой-проверка отдельным шагом после мержа.
