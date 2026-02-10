# Code Quality Audit Report: telegram-voice2text-bot

**Дата:** 2026-02-09
**Ревьюер:** Code Quality Reviewer
**Оценка:** 6/10

---

## 1. ДУПЛИКАЦИЯ КОДА

### [SEVERITY: HIGH] Массивная дупликация voice/audio/document/video handlers
- **Файл**: `src/bot/handlers.py`, строки 355-1396
- **Описание**: 4 обработчика с ~80% идентичным кодом:
  - Валидация длительности (~10 строк x4)
  - Проверка размера файла (~30 строк x4)
  - Проверка очереди (~10 строк x4)
  - Создание usage записи (~15 строк x4)
  - Загрузка файла (~20 строк x4)
  - TranscriptionRequest и enqueue (~50 строк x4)
  - Форматирование wait_time (~15 строк x4)
  - Обработка BadRequest (~20 строк x3)
- **Impact**: handlers.py = 2182 строки, ~60% дупликация. Любое изменение — 4 места.
- **Рекомендация**: Выделить `_handle_media_message(update, context, media_type, file_obj)`.

### [SEVERITY: HIGH] Дупликация форматирования wait_time
- **Файл**: `src/bot/handlers.py`, строки 197-209, 616-629, 938-951, 1163-1178, 1364-1376
- **Описание**: Блок форматирования повторяется 5 раз.
- **Рекомендация**: Создать `format_wait_time(seconds: float) -> str`.

### [SEVERITY: HIGH] Дупликация benchmark-кода
- **Файл**: `src/bot/handlers.py`, строки 526-573 и 850-898
- **Описание**: Идентичная benchmark-логика (~48 строк x2).
- **Рекомендация**: Вынести в `_handle_benchmark_result()`.

### [SEVERITY: MEDIUM] Дупликация генерации вариантов в callbacks.py
- **Файл**: `src/bot/callbacks.py`, строки 356-687
- **Описание**: Паттерн structured/summary/magic — ~100 строк x3.
- **Рекомендация**: Вынести в `_generate_variant()`.

### [SEVERITY: MEDIUM] Дупликация mode_labels dict
- **Файл**: `src/bot/callbacks.py`, строки 110-115 и 168-173
- **Рекомендация**: Вынести в константу модуля.

### [SEVERITY: MEDIUM] Дупликация PDF fallback-логики
- **Файлы**: `src/bot/callbacks.py:134-144, 184-194`; `src/bot/handlers.py:1570-1580, 1644-1655`
- **Описание**: Паттерн "PDF, при ошибке TXT" повторяется 4 раза.
- **Рекомендация**: Вынести в `create_file_object()`.

---

## 2. ДЛИНА ФУНКЦИЙ И COMPLEXITY

### [SEVERITY: HIGH] _process_transcription — 500+ строк
- **Файл**: `src/bot/handlers.py`, строки 1665-2167
- **Описание**: Вложенность до 6 уровней.
- **Рекомендация**: Разбить на _preprocess_audio(), _save_for_retranscription(), _handle_structure_strategy(), _handle_hybrid_strategy(), _handle_direct_result(), _finalize_transcription().

### [SEVERITY: HIGH] voice_message_handler — 327 строк
- **Файл**: `src/bot/handlers.py`, строки 355-681

### [SEVERITY: MEDIUM] handle_mode_change — 415 строк
- **Файл**: `src/bot/callbacks.py`, строки 291-725
- **Рекомендация**: Разбить по режимам.

---

## 3. datetime.utcnow() DEPRECATED

### [SEVERITY: MEDIUM] 30+ вхождений deprecated datetime.utcnow()
- **Файлы**: `src/storage/models.py` (строки 42, 44, 103, 106, 153, 189, 204, 233, 267); `src/storage/repositories.py` (строки 66, 67, 81, 92, 99, 106, 156, 157, 213, 266, 319, 335, 342, 386, 387, 423, 462, 463, 495, 561)
- **Описание**: Deprecated в Python 3.12. Возвращает naive datetime без timezone.
- **Рекомендация**: Заменить на `datetime.now(timezone.utc)`.

---

## 4. ИМЕНОВАНИЕ

### [SEVERITY: MEDIUM] whisper_service vs transcription_router
- **Файл**: `src/bot/handlers.py`, строка 152
- **Описание**: Параметр `whisper_service` -> `self.transcription_router`. Семантическое рассогласование.
- **Рекомендация**: Переименовать параметр.

### [SEVERITY: LOW] Dict из typing вместо встроенного dict
- **Файлы**: `src/services/prompt_loader.py:5`, `src/utils/logging_config.py:17-18`
- **Рекомендация**: `dict[str, str]` для Python 3.9+.

---

## 5. MAGIC NUMBERS

### [SEVERITY: MEDIUM] 2 * 1024 * 1024 * 1024 (2 GB) повторяется 4 раза
- **Файл**: `src/bot/handlers.py`
- **Рекомендация**: `TELEGRAM_CLIENT_API_MAX_FILE_SIZE`.

### [SEVERITY: MEDIUM] 25 MB для OpenAI захардкожен
- **Файл**: `src/transcription/providers/openai_provider.py:125`
- **Рекомендация**: `OPENAI_MAX_FILE_SIZE_MB = 25`.

### [SEVERITY: LOW] 4096 вместо TELEGRAM_MAX_MESSAGE_LENGTH
- **Файл**: `src/bot/handlers.py`, строки 554, 570, 879, 895
- **Рекомендация**: Использовать существующую константу.

### [SEVERITY: LOW] 224 (tokens) захардкожен
- **Файл**: `src/transcription/providers/openai_provider.py:512`
- **Рекомендация**: `OPENAI_CONTEXT_TOKENS = 224`.

---

## 6. ТИПИЗАЦИЯ

### [SEVERITY: MEDIUM] bare list без типа элементов
- **Файл**: `src/services/text_processor.py`, строки 500, 550
- **Описание**: `format_with_timestamps(segments: list, ...)` без типа.
- **Рекомендация**: `list[TranscriptionSegment]`.

### [SEVERITY: LOW] Смешанные стили Optional[X] и X | None
- **Описание**: Преобладает Optional[], но database.py использует X | None.

---

## 7. МЁРТВЫЙ КОД

### [SEVERITY: LOW] Transaction model и TransactionRepository
- **Файлы**: `src/storage/models.py:125-160`, `src/storage/repositories.py:295-354`
- **Описание**: Определены, но нигде не используются (биллинг = "Next Phase").
- **Рекомендация**: Оставить как подготовку, добавить комментарий.

---

## 8. DOCSTRINGS И КОММЕНТАРИИ

### [SEVERITY: INFO] Хорошее покрытие docstrings
- Практически все публичные методы задокументированы (Args, Returns, Raises). Сильная сторона.

### [SEVERITY: INFO] Нет TODO/FIXME/HACK комментариев
- Чистый код без явного технического долга.

### [SEVERITY: LOW] Устаревший комментарий
- **Файл**: `src/services/text_processor.py:35-36`
- **Описание**: "Phase 3 - not yet implemented" — Phase 3 уже реализована.

---

## 9. ОРГАНИЗАЦИЯ ИМПОРТОВ

### [SEVERITY: LOW] Импорт внутри функций (обоснованно)
- `src/storage/database.py:90-96` — lazy imports для init_db
- `src/storage/repositories.py:246-247, 263-264` — func, Path, timedelta
- `src/bot/retranscribe_handlers.py:287` — circular import avoidance

---

## 10. КОНСИСТЕНТНОСТЬ СТИЛЯ

### [SEVERITY: LOW] Смешанные стили конкатенации строк
- **Файл**: `src/bot/handlers.py`, строки 669, 994
- **Описание**: Неявная конкатенация строк. Корректный Python, но может быть неочевидно.

### [SEVERITY: INFO] Единообразное форматирование
- Black + ruff. Стиль консистентен.

---

## 11. КОНФИГУРАЦИЯ ЛИНТЕРОВ

### [SEVERITY: INFO] Конфигурация адекватная
- ruff: line-length=100, правила E, F, W, I, N, UP, B, A, S, T20, SIM
- Black: line-length=100
- Mypy: disallow_untyped_defs=true

---

## СВОДКА

| Severity | Количество |
|----------|-----------|
| CRITICAL | 0 |
| HIGH | 5 |
| MEDIUM | 9 |
| LOW | 10 |
| INFO | 4 |

**Сильные стороны**: docstrings, нет TODO/FIXME/HACK, адекватные линтеры, consistent стиль, грамотные type hints, Repository pattern.

**Главные проблемы**: дупликация handlers.py (~800 строк), сверхдлинные методы (500+), дупликация callbacks.py (~300 строк), deprecated datetime.utcnow() (30+), magic numbers.
