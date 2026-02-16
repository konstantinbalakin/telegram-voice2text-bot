# Матрица задач аудита: цикл разработки и зависимости

**Дата:** 2026-02-09
**Обновлено:** 2026-02-16 (ревизия 7 — Волна 5: 4 задачи выполнены, ветка test/audit-wave5)

## Легенда: типы цикла разработки

| Тип | Описание | Примерный объём |
|-----|----------|-----------------|
| **QF** | Quick Fix — механическая правка, агент-разработчик в один проход | 1-20 строк, без новых файлов |
| **D+T** | Dev + Test — разработка + написание/обновление тестов | Новый код + тесты |
| **A+D+T** | Analysis + Dev + Test — нужен предварительный анализ, потом разработка и тесты | Анализ кода → реализация → тесты |
| **FULL** | Full Cycle — анализ, проектирование, разработка, тестирование, ревью | Архитектурное изменение, затрагивает много файлов |

## Легенда: приоритет

| Приоритет | Описание |
|-----------|----------|
| **P0** | Немедленно — безопасность, data loss |
| **P1** | Высокий — критичный performance, memory leak |
| **P2** | Средний — качество кода, maintainability |
| **P3** | Низкий — nice to have, косметика |

## Легенда: статус

| Статус | Описание |
|--------|----------|
| **NEW** | Задача создана, ещё не начата |
| **IN_PROGRESS** | Задача в работе |
| **DONE** | Задача выполнена и проверена |
| **SKIP** | Задача отменена или поглощена другой |

---

## Замечания по ревизии (исправления после анализа)

1. **A1 НЕ блокирует T2** — `split_text()` является standalone-функцией, её тесты не зависят от рефакторинга handlers. Зависимость убрана.
2. **S2 и P1 пересекаются** — обе задачи затрагивают `subprocess.run()` в `audio_handler.py`. S2 добавляет timeout, P1 переписывает на async. Если делать P1, то S2 входит в состав. Добавлена пометка.
3. **A6 повышен до D+T** — 30+ замен `datetime.utcnow()` → `datetime.now(timezone.utc)` по 2 файлам. Нужно прогнать тесты после замены, чтобы убедиться что сравнения naive vs aware datetime не сломались.
4. **A8 конфликтует с A1** — обе задачи меняют `handlers.py`. Рекомендация: делать A8 ДО A1 (или включить в состав A1). Помечено.
5. **A9 конфликтует с A4** — обе задачи меняют `callbacks.py`. Аналогично: A9 до A4 или включить в A4.
6. **A5 рекомендуется до A1-A4** — создать иерархию исключений ДО рефакторинга, чтобы использовать их в новом коде.
7. **P8 повышен до D+T** — PDFGenerator singleton требует изменения конструкторов BotHandlers и CallbackHandlers + передачу через main.py (3 файла).
8. **Исправлен подсчёт**: 54 задачи (не 56), A+D+T = 8 (не 10).

---

## Фаза 1 — Безопасность

| ID | Задача | Тип | Приоритет | Статус | Файлы | Блокирует | Зависит от | Комментарий |
|----|--------|-----|-----------|--------|-------|-----------|------------|-------------|
| S1 | IDOR: добавить проверку владельца в callback queries | D+T | P0 | DONE | `callbacks.py`, тест | T3 | — | Проверка `user_id` в `handle_callback_query` через `UserRepository`. Тест: `test_idor_check.py` (3 теста). PR #98 |
| S2 | Добавить timeout ко всем subprocess.run() | QF | P0 | DONE | `audio_handler.py` | — | — | Механическая правка: `timeout=300` к ~10 вызовам. PR #96. **Поглощено P1** — все subprocess заменены на async с timeout |
| S3 | Per-user rate limiting | A+D+T | P0 | DONE | `handlers.py`, `config.py`, тесты | — | — | Метод `_check_quota()` + `enable_quota_check` в config (по умолчанию выключен). Тест: `test_quota_check.py` (9 тестов). PR #98 |
| S4 | Фильтрация bot token из DEBUG логов | D+T | P1 | DONE | `logging_config.py`, `main.py`, тест | — | — | `SensitiveDataFilter` маскирует токены во всех log handlers. Тест: `test_logging_filter.py` (7 тестов). PR #98 |
| S5 | Маскировать database URL в логах | QF | P1 | DONE | `main.py` | — | — | Заменить `{settings.database_url}` на маскированную версию. 1 строка |
| S6 | Маскировать API key (показывать меньше символов) | QF | P2 | DONE | `llm_service.py:122` | — | — | Заменить `[:8]` на `[:4]`. 1 строка |
| S7 | Валидация callback_data в decode_callback_data | D+T | P2 | DONE | `keyboards.py`, тест | — | — | Валидация action, usage_id, параметров mode/length/emoji. Тесты в `test_keyboards.py`. PR #98 |
| S8 | Проверка лимита вариантов транскрипции | D+T | P2 | DONE | `callbacks.py`, `repositories.py`, тест | — | — | `_check_variant_limit()` + `count_by_usage_id()` в repos. Проверяет `max_cached_variants_per_transcription`. PR #98 |
| S9 | Исправить Docker HEALTHCHECK | QF | P2 | DONE | `Dockerfile` | — | — | Заменить заглушку на `CMD python -m src.health_check`. 1 строка |
| S10 | Telethon session — минимальные права на файл | QF | P3 | DONE | `telegram_client.py` | — | — | Добавить `os.chmod(session_path, 0o600)` после создания |
| S11 | Предсказуемые имена persistent файлов → UUID | QF | P3 | DONE | `handlers.py:134` | — | — | Заменить `{usage_id}_{file_identifier}` на UUID. Путь сохраняется в DB, поэтому формат имени не влияет на lookup |
| S12 | HTML санитизация текста транскрипции | A+D+T | P2 | DONE | `handlers.py`, `callbacks.py`, `html_utils.py`, тест | — | — | `escape_html()` для raw Whisper text, `sanitize_html()` для LLM text в `update_transcription_display()` и error recovery. Ветка fix/audit-wave3 |
| S13 | DEBUG handler только при DEBUG level | QF | P3 | DONE | `main.py:177-188` | — | — | Обернуть в `if settings.log_level == "DEBUG"`. 2 строки |

---

## Фаза 2 — Performance

| ID | Задача | Тип | Приоритет | Статус | Файлы | Блокирует | Зависит от | Комментарий |
|----|--------|-----|-----------|--------|-------|-----------|------------|-------------|
| P1 | subprocess.run() → asyncio.create_subprocess_exec() | A+D+T | P0 | DONE | `audio_handler.py` (~10 вызовов), тесты | — | — | Async хелпер `_run_subprocess()`, все 10 методов async, тесты обновлены (50/50). `await` добавлен в handlers.py. **Поглощает S2.** Ветка fix/audit-wave3 |
| P2 | pydub chunking → ffmpeg streaming chunking | A+D+T | P1 | DONE | `openai_provider.py:339-395`, тест | — | — | pydub заменён на ffmpeg: `_get_duration_seconds()` + `_extract_chunk()`. Тест T10 исправлен. 7/7 тестов. Ветка fix/audit-wave3 |
| P3 | Очистка _results dict в queue_manager | D+T | P1 | DONE | `queue_manager.py`, тест | — | — | `_schedule_cleanup()` удаляет результат через 300с. Тесты в `test_queue_manager.py`. PR #98 |
| P4 | SQL SUM вместо загрузки всех записей | QF | P1 | DONE | `repositories.py:229-233` | P5 | — | Заменить `select(Usage)` + Python sum на `select(func.sum(...))`. 5 строк |
| P5 | Исправить stats_command (limit=10 → агрегации) | D+T | P1 | DONE | `handlers.py`, `repositories.py` | — | P4 | SQL `COUNT`/`SUM` через `count_by_user_id()` и `get_user_total_duration()`. PR #98 |
| P6 | Убрать UPDATE last_accessed_at при каждом SELECT | QF | P2 | DONE | `repositories.py:493-496` | P11 | — | Удалить 3 строки auto-update. last_accessed_at нигде не используется для логики, только для потенциального будущего LRU |
| P7 | Bulk DELETE вместо N+1 для вариантов | QF | P2 | DONE | `repositories.py:509-527` | — | — | Заменить цикл на `delete(TranscriptionVariant).where(...)`. По аналогии с segments |
| P8 | PDFGenerator — singleton вместо пересоздания | D+T | P2 | DONE | `pdf_generator.py` | — | — | Module-level lazy singleton `_get_pdf_generator()`, без изменений конструкторов handlers/callbacks. PR #98 |
| P9 | httpx клиент — connection pooling | QF | P2 | DONE | `audio_handler.py:147-161` | — | — | Создать `self._http_client` в `__init__`, переиспользовать. Не забыть `aclose()` в cleanup |
| P10 | Кеширование segments в callbacks | QF | P2 | SKIP | `callbacks.py` (несколько мест) | — | — | Строки 453 и 711 в разных code paths (error handler vs normal flow), дупликация не подтверждена |
| P11 | Двойной get_variant → UPSERT | D+T | P2 | DONE | `callbacks.py:410-416`, `repositories.py`, тест | — | P6 | `get_or_create_variant()` с IntegrityError handling. 3 места в callbacks заменены. Тест `test_variant_upsert.py` (3 теста). Ветка fix/audit-wave3 |
| P12 | Progress tracker — увеличить интервал, rate limiter | D+T | P2 | DONE | `progress_tracker.py`, `config.py`, тест | — | — | Default 5→10с, global rate limiter (0.5с), RetryAfter пропускает обновление. Тест `test_progress_tracker.py` (27 тестов). Ветка fix/audit-wave3 |
| P13 | Составной индекс для variant queries | QF | P2 | DONE | Alembic миграция | — | — | Новая миграция: `Index('ix_variant_lookup', 'usage_id', 'mode', 'length_level', 'emoji_level', 'timestamps_enabled')` |
| P14 | max_tokens=4000 → настраиваемый | QF | P3 | DONE | `llm_service.py:139`, `config.py` | — | — | Добавить поле в Settings, использовать в llm_service |
| P15 | init_db sync engine → asyncio.to_thread | QF | P3 | DONE | `database.py:140-148` | — | — | Обернуть в asyncio.to_thread(). 3 строки |

---

## Фаза 3 — Архитектура и качество кода

| ID | Задача | Тип | Приоритет | Статус | Файлы | Блокирует | Зависит от | Комментарий |
|----|--------|-----|-----------|--------|-------|-----------|------------|-------------|
| A1 | Объединить 4 media handlers в _handle_media_message() | FULL | P2 | DONE | `handlers.py` | A2, T4 | A8 (рек.) | MediaInfo dataclass + `_extract_media_info()` + `_handle_media_message()` + 4 тонкие обёртки. handlers.py: 2239→786 строк (−65%). PR #100 |
| A2 | Разбить _process_transcription на 4-5 методов | FULL | P2 | DONE | `handlers.py` | T4 | A1 | Разбит на `_preprocess_audio`, `_run_transcription`, `_apply_structuring`, `_apply_refinement`, `_finalize_and_send` + оркестратор. PR #100 |
| A3 | Выделить TranscriptionOrchestrator в сервисный слой | FULL | P2 | DONE | Новый `services/transcription_orchestrator.py`, `handlers.py`, `main.py` | T5, T13 | A1, A2 | Бизнес-логика транскрипции вынесена в `TranscriptionOrchestrator` (792 строки). handlers.py отвечает только за приём сообщений. PR #100 |
| A4 | Объединить дупликацию генерации вариантов в callbacks | FULL | P2 | DONE | `callbacks.py` | T3 | A9 (рек.) | `_generate_variant()` + `MODE_LABELS` константа. callbacks.py: 1295→1154 строк (−11%). PR #100 |
| A5 | Создать иерархию бизнес-исключений | D+T | P2 | DONE | `exceptions.py` (новый), тест | — | — | `BotError` → `TranscriptionError`, `QuotaExceededError`, `FileProcessingError`, `LLMProcessingError`, `AuthorizationError`, `VariantLimitError`, `StateNotFoundError`. Тест: `test_exceptions.py` (7 тестов). PR #98 |
| A6 | datetime.utcnow() → datetime.now(timezone.utc) | D+T | P2 | DONE | `models.py`, `repositories.py` | — | — | ~30 замен в models (default/onupdate lambda) и repositories. Все тесты проходят. PR #98 |
| A7 | Вынести magic numbers в константы | QF | P3 | DONE | `handlers.py`, `openai_provider.py` | — | — | 2GB, 25MB, 224 tokens → именованные константы |
| A8 | format_wait_time() — убрать дупликацию | QF | P2 | DONE | `handlers.py` | A1 (рек.) | — | Выделить функцию из 5 копий. **Рекомендация:** делать ДО A1, чтобы A1 уже работал с готовой функцией |
| A9 | PDF fallback — выделить create_file_object() | QF | P2 | DONE | `handlers.py`, `callbacks.py`, `pdf_generator.py` | A4 (рек.) | — | Выделить утилиту из 4 копий. **Рекомендация:** делать ДО A4 |
| A10 | Переименовать whisper_service → transcription_router | QF | P3 | DONE | `handlers.py:152`, `main.py` | — | — | Rename параметра. 2 строки |
| A11 | Dict → dict, Optional → X \| None (стиль) | QF | P3 | DONE | `prompt_loader.py`, `logging_config.py` | — | — | Механическая замена типов |
| A12 | Убрать устаревший комментарий "Phase 3 not implemented" | QF | P3 | DONE | `text_processor.py:35` | — | — | 1 строка |
| A13 | Унифицировать lifecycle сервисов (async init/shutdown) | A+D+T | P3 | DONE | Несколько файлов providers, services | — | — | `AsyncService` Protocol в `src/services/lifecycle.py`. `TranscriptionProvider.initialize()` стал async. Сервисы адаптированы. Тесты: `test_lifecycle.py` (195 строк). PR #100 |

---

## Фаза 4 — Тестирование

| ID | Задача | Тип | Приоритет | Статус | Файлы | Блокирует | Зависит от | Комментарий |
|----|--------|-----|-----------|--------|-------|-----------|------------|-------------|
| T1 | Тесты для keyboards.py (encode/decode/create) | D+T | P1 | DONE | `tests/unit/test_keyboards.py` (новый) | — | — | 32 теста: roundtrip, 64-byte limit, invalid data, action validation, create_keyboard. PR #98 |
| T2 | Тесты для split_text() | D+T | P1 | DONE | `tests/unit/test_split_text.py` (новый) | — | — | 14 тестов: пустая строка, лимит, Unicode, emoji, разбиение по границам предложений/слов. PR #98 |
| T3 | Тесты для CallbackHandlers | A+D+T | P1 | DONE | `tests/unit/test_callbacks.py` (новый) | — | S1, A4 | 46 тестов: routing, mode change, length change, emoji toggle, timestamps toggle, back, _generate_variant, _check_variant_limit, update_transcription_display (4 cases). Ветка test/audit-wave5 |
| T4 | Тесты для handlers (после рефакторинга) | A+D+T | P2 | DONE | `tests/unit/test_handlers.py` (новый) | — | A1, A2 | 34 теста: MediaInfo, format_wait_time, _extract_media_info, _check_quota, start/help/stats commands, media wrappers, _handle_media_message (validation, enqueue, errors), error_handler. Ветка test/audit-wave5 |
| T5 | Тесты для TranscriptionOrchestrator | D+T | P2 | DONE | `tests/unit/test_orchestrator.py` (новый) | — | A3 | 30 тестов: save_audio_file, preprocess, run_transcription, apply_structuring, apply_refinement, create_interactive_state, send_result, send_draft, process_transcription (all strategies + fallback). Ветка test/audit-wave5 |
| T6 | Тесты для QueueManager | D+T | P1 | DONE | `tests/unit/test_queue_manager.py` (новый) | — | — | Async-тесты: init, enqueue, QueueFull, start/stop worker, get_stats, position, wait time. PR #98 |
| T7 | Тесты для config.py (валидаторы) | D+T | P2 | DONE | `tests/unit/test_config.py` (новый) | — | — | 83 теста: defaults, validators, env override, field constraints, model config. Ветка fix/audit-wave3 |
| T8 | Тесты для progress_tracker | D+T | P2 | DONE | `tests/unit/test_progress_tracker.py` (новый) | — | — | 27 тестов: format_time, progress bar, init, start/stop, rate limiter, RetryAfter, Telegram errors. Ветка fix/audit-wave3 |
| T9 | Тесты для db_retry decorator | D+T | P3 | DONE | `tests/unit/test_db_retry.py` (новый) | — | — | 20 тестов: retry on locked, max_attempts, backoff, non-retriable errors, custom params. Ветка fix/audit-wave3 |
| T10 | Исправить пустой test_transcribe_success | D+T | P2 | DONE | `tests/unit/test_openai_provider.py:75` | — | — | Реальный тест с моком httpx.AsyncClient.post, проверка text/language/provider/model/time. Ветка fix/audit-wave3 |
| T11 | Вынести audio_handler fixture в conftest | QF | P3 | DONE | `tests/unit/conftest.py` | — | — | Перенести из 3 файлов в общий conftest |
| T12 | Исправить asyncio.run() антипаттерн | QF | P3 | DONE | `tests/unit/test_faster_whisper_provider.py:45` | — | — | Заменить на @pytest_asyncio.fixture + await |
| T13 | Интеграционный тест: полный pipeline | A+D+T | P2 | DONE | `tests/integration/test_pipeline.py` (новый) | — | A3 | 11 тестов: orchestrator с реальной DB, callback mode switch, queue→orchestrator pipeline, error recovery, variant caching, timestamps toggle, IDOR, variant limit, full roundtrip. Ветка test/audit-wave5 |

---

## Граф зависимостей (критический путь)

```
Независимые задачи (можно начинать сразу, всего 45 из 54):
════════════════════════════════════════════════════════════
Security:    S1, S2, S3, S4, S5, S6, S7, S8, S9, S10, S11, S12, S13
Performance: P1, P2, P3, P4, P6, P7, P9, P10, P12, P13, P14, P15
Archit.:     A5, A6, A7, A8, A9, A10, A11, A12, A13
Testing:     T1, T2, T6, T7, T8, T9, T10, T11, T12

Цепочки зависимостей (жёсткие):
═══════════════════════════════
P4 ──→ P5       (stats нуждается в SQL SUM из P4)
P6 ──→ P11      (UPSERT после убирания auto-update)
A1 ──→ A2 ──→ A3 ──→ T5   (рефакторинг handlers → orchestrator → тесты)
                A3 ──→ T13  (интеграционный тест)
A1 + A2 ──→ T4             (тесты handlers после рефакторинга)
S1 + A4 ──→ T3             (тесты callbacks после IDOR fix + рефакторинга)
P8 ──→ (затрагивает конструкторы handlers/callbacks — не параллелить с A1/A4)

Рекомендованный порядок (мягкие зависимости):
═════════════════════════════════════════════
A8 ──(рек.)──→ A1   (format_wait_time лучше до merge handlers)
A9 ──(рек.)──→ A4   (PDF fallback лучше до merge callbacks)
A5 ──(рек.)──→ A1-A4 (исключения лучше до рефакторинга)
S2 ──(поглощ.)──→ P1  (если P1 делается, S2 = SKIP)

Файловые конфликты (не параллелить!):
═════════════════════════════════════
handlers.py:  S3, S11, S12, P5, P8, A1, A2, A7, A8, A10
callbacks.py: S1, S8, S12, P8, P10, A4, A9
repositories.py: P4, P6, P7, P11, A6

Критический путь:
═════════════════
A5 → A8 → A1 → A2 → A3 → T5 + T13
```

---

## Рекомендованный порядок выполнения

### Волна 1 — Quick Fixes (всё параллельно)
Все задачи с типом **QF** — можно отдать агенту одним батчем. Группировать по файлам, чтобы избежать конфликтов:

**Группа A (handlers.py):** `S11, A7, A8, A10` — один агент
**Группа B (repositories.py):** `P4, P6, P7` — один агент
**Группа C (разные файлы):** `S2, S5, S6, S9, S10, S13, P9, P13, P14, P15, A11, A12, T11, T12` — можно параллельно
**Группа D (callbacks.py):** `P10` — один агент

### Волна 2 — Security + простые D+T (параллельно, после волны 1)
- `S1` — IDOR fix + тест (callbacks.py)
- `S3` — rate limiting (handlers.py)
- `S4` — bot token filter (logging_config.py)
- `S7` — callback_data validation (keyboards.py)
- `S8` — variant limit check (callbacks.py) — **не параллелить с S1**
- `T1` — тесты keyboards (новый файл)
- `T2` — тесты split_text (новый файл)
- `T6` — тесты QueueManager (новый файл)
- `P3` — cleanup _results (queue_manager.py)
- `P5` — fix stats (handlers.py, repos) — **не параллелить с S3**
- `P8` — PDFGenerator singleton (3 файла)
- `A5` — иерархия исключений (новый файл + обновления)
- `A6` — datetime.utcnow замена (models.py, repos)

### Волна 3 — Performance + тесты (параллельно)
- `P1` — async subprocess (audio_handler.py) → **S2 = SKIP**
- `P2` — ffmpeg chunking (openai_provider.py)
- `P11` — UPSERT variants (callbacks.py, repos)
- `P12` — progress tracker (progress_tracker.py)
- `S12` — HTML санитизация (handlers.py, callbacks.py)
- `T7, T8, T9, T10` — тесты (новые файлы)

### Волна 4 — Архитектурный рефакторинг (строго последовательно!)
- `A1` → `A2` → `A3` — **строго последовательно**, ревью после каждого
- `A4` — параллельно с A1-A3 (другой файл — callbacks.py)
- `A13` — параллельно (другие файлы — providers, services)

### Волна 5 — Тесты после рефакторинга
- `T3` — тесты callbacks (после S1 + A4)
- `T4` — тесты handlers (после A1 + A2)
- `T5` — тесты orchestrator (после A3)
- `T13` — интеграционный тест (после A3)

---

## Сводка по объёму

| Тип цикла | Количество задач | Описание |
|-----------|-----------------|----------|
| **QF** (Quick Fix) | 23 | Агент-разработчик, один проход |
| **D+T** (Dev + Test) | 19 | Разработка + тесты |
| **A+D+T** (Analysis + Dev + Test) | 8 | Анализ → реализация → тесты |
| **FULL** (Full Cycle) | 4 | A1, A2, A3, A4 — архитектурный рефакторинг с ревью |
| **Всего** | **54** | |

---

## Матрица файловых конфликтов

Задачи, затрагивающие один файл, **нельзя запускать параллельно**. Используй эту таблицу при планировании параллельной работы агентов:

| Файл | Задачи (в рекомендованном порядке) |
|------|------------------------------------|
| `handlers.py` | A8 → S11, A7, A10 → S3 → P5 → S12 → A1 → A2 → A3 |
| `callbacks.py` | P10 → S1 → S8 → A9 → S12 → P11 → A4 |
| `repositories.py` | P4 → P6, P7 → A6 → P11 |
| `audio_handler.py` | S2/P1 (выбрать одно), P9 |
| `config.py` | S3, S8, P12, P14 (мало пересечений, можно параллелить) |
| `main.py` | S5, S13, P8, A3 |
| `logging_config.py` | S4, A11 |
| `keyboards.py` | S7 |
| `openai_provider.py` | P2, A7 |
| `queue_manager.py` | P3 |
| `progress_tracker.py` | P12 |
| `llm_service.py` | S6, P14 |
| `database.py` | P15 |
| `models.py` | A6 |
| `text_processor.py` | A12 |
| `telegram_client.py` | S10 |
| `Dockerfile` | S9 |
