# Testing Audit Report: telegram-voice2text-bot

**Дата:** 2026-02-09
**Ревьюер:** Testing Reviewer
**Оценка:** 3/10

---

## 1. ПОКРЫТИЕ КОДА

### [SEVERITY: CRITICAL] handlers.py (2182 строки) — НЕ покрыт тестами
- **Файл**: `src/bot/handlers.py`
- **Описание**: Самый большой модуль бота (BotHandlers, split_text, voice/audio/document/video handlers, _process_transcription, start/help/stats commands) — ни одного теста.
- **Impact**: Любое изменение в основной логике — полностью без регрессионной защиты. split_text (строки 43-107) — чистая логика, легко тестируемая, но тоже не покрыта.
- **Рекомендация**: Тесты для split_text(), save_audio_file_for_retranscription(), voice_message_handler(), _process_transcription().

### [SEVERITY: CRITICAL] callbacks.py (1296 строк) — НЕ покрыт тестами
- **Файл**: `src/bot/callbacks.py`
- **Описание**: Весь интерактивный функционал — ни одного теста. LEVEL_TRANSITIONS (строки 32-37) — критическая бизнес-логика.
- **Рекомендация**: Тесты на LEVEL_TRANSITIONS, handle_callback_query routing, handle_mode_change, update_transcription_display.

### [SEVERITY: HIGH] retranscribe_handlers.py (357 строк) — НЕ покрыт
### [SEVERITY: HIGH] keyboards.py (309 строк) — НЕ покрыт
- **Описание**: Чистые функции encode/decode_callback_data, create_transcription_keyboard — идеально для юнит-тестов. 64-байтный лимит Telegram не тестируется.

### [SEVERITY: HIGH] queue_manager.py (424 строки) — НЕ покрыт
- **Описание**: Вся система очередей — без тестов. Конкурентность, семафоры, оценка времени.

### [SEVERITY: HIGH] progress_tracker.py (211 строк) — НЕ покрыт
### [SEVERITY: HIGH] telegram_client.py (124 строки) — НЕ покрыт

### [SEVERITY: MEDIUM] router.py (354 строки) — НЕ покрыт
### [SEVERITY: MEDIUM] factory.py (442 строки) — НЕ покрыт
### [SEVERITY: MEDIUM] config.py (360 строк) — НЕ покрыт
- **Описание**: ~60 полей, валидаторы — только mock_settings в conftest с 6 полями.

### [SEVERITY: MEDIUM] main.py (316 строк) — НЕ покрыт
### [SEVERITY: MEDIUM] database.py (181 строка) — НЕ покрыт
### [SEVERITY: LOW] db_retry.py (64 строки) — НЕ покрыт
### [SEVERITY: LOW] health_check.py (196 строк) — НЕ покрыт

---

## 2. ИЗОЛЯЦИЯ ТЕСТОВ

### [SEVERITY: LOW] Тесты хорошо изолированы
- **Описание**: Каждый файл самодостаточен. pytest.fixture для setup/teardown, tmp_path, async_session с rollback.

---

## 3. КАЧЕСТВО МОКОВ

### [SEVERITY: MEDIUM] OpenAI provider — пустой тест transcribe_success
- **Файл**: `tests/unit/test_openai_provider.py:75-79`
- **Описание**: `test_transcribe_success` содержит `pass`. Основная функция не тестируется.
- **Рекомендация**: Написать тест с моком OpenAI client или пометить `pytest.skip()`.

### [SEVERITY: LOW] Моки корректны в целом
- test_llm_service.py — правильный mock deepseek_provider.client.post.
- test_audio_preprocessing.py — правильный mock subprocess.run.
- Паттерн patch.object для точного мокирования.

### [SEVERITY: LOW] test_text_processor_* тестирует мок вместо логики
- **Файл**: `tests/unit/test_text_processor_length.py`
- **Описание**: По сути проверяют, что mock refine_text вызывается. Реальная логика (промпт, sanitize_html) не проверяется.

---

## 4. EDGE-CASES

### [SEVERITY: MEDIUM] split_text — нет тестов
- **Файл**: `src/bot/handlers.py:43-107`
- **Описание**: Сложная логика (по абзацам, строкам, предложениям, словам, force-split). Граничные случаи не тестируются.
- **Рекомендация**: 8-10 тестов: пустая строка, 4096, без пробелов, Unicode.

### [SEVERITY: MEDIUM] Нет тестирования больших файлов
- **Описание**: Нет тестов для файлов на границе 20 MB, 2 GB (Telethon), пустых файлов.

### [SEVERITY: LOW] Хорошие boundary тесты в некоторых модулях
- test_structure_strategy.py — пороговые значения (0.0, 19.9, 20.0, 3600.0).
- test_audio_preprocessing.py — speed multiplier (0.3, 0.5, 2.0, 2.5).

---

## 5. ИНТЕГРАЦИОННЫЕ ТЕСТЫ

### [SEVERITY: CRITICAL] tests/integration/ — пустой каталог
- **Описание**: 0 интеграционных тестов. Нет тестов полного pipeline.
- **Рекомендация**: Приоритетные тесты:
  1. Voice message -> transcription (с моком Telegram API и Whisper)
  2. Callback flow: mode change -> state update -> variant cache -> display
  3. Queue: enqueue -> process -> result с реальным asyncio
  4. Database: полный CRUD lifecycle

---

## 6. ERROR PATHS

### [SEVERITY: HIGH] Необработанные ошибки в handlers.py не тестируются
- **Описание**: Обширная обработка ошибок (BadRequest, QueueFull, RuntimeError в строках 652-681), ни один error path не тестируется.
- **Рекомендация**: Тесты для каждого except-блока.

### [SEVERITY: MEDIUM] LLM Service — хорошие error path тесты
- **Описание**: timeout, HTTP 401, unexpected error, fallback to draft. Хорошая модель.

---

## 7. ASYNC ТЕСТИРОВАНИЕ

### [SEVERITY: LOW] pytest-asyncio используется корректно
### [SEVERITY: INFO] Антипаттерн asyncio.run() в fixture teardown
- **Файл**: `tests/unit/test_faster_whisper_provider.py:45`
- **Рекомендация**: Использовать @pytest_asyncio.fixture с await.

---

## 8. FIXTURES

### [SEVERITY: LOW] Дублирование audio_handler fixture в 3 файлах
- test_audio_preprocessing.py, test_audio_handler.py, test_audio_extraction.py — идентичная реализация.
- **Рекомендация**: Вынести в conftest.py.

---

## 9. ТЕСТИРОВАНИЕ КОНФИГУРАЦИИ

### [SEVERITY: MEDIUM] config.py — только mock_settings в conftest
- **Описание**: mock_settings с 6 полями из ~60. Валидаторы не тестируются.
- **Рекомендация**: Тесты для валидаторов, default значений.

### [SEVERITY: LOW] test_file_size_validation.py — зависит от реального settings
- **Описание**: `MAX_FILE_SIZE = settings.max_file_size_bytes` — хрупкий тест.

---

## 10. COVERAGE GAPS — ранжирование по риску

| # | Модуль | Строк | Риск | Причина |
|---|--------|-------|------|---------|
| 1 | handlers.py | 2182 | **CRITICAL** | Ядро бота |
| 2 | callbacks.py | 1296 | **CRITICAL** | Вся интерактивность |
| 3 | queue_manager.py | 424 | **HIGH** | Конкурентность |
| 4 | keyboards.py | 309 | **HIGH** | Чистые функции, легко тестировать |
| 5 | retranscribe_handlers.py | 357 | **HIGH** | Пользовательская фича |
| 6 | text_processor.py | 591 | **MEDIUM** | Частично покрыт |
| 7 | router.py | 354 | **MEDIUM** | Маршрутизация |
| 8 | factory.py | 442 | **MEDIUM** | Сложная фабрика |
| 9 | config.py | 360 | **MEDIUM** | Валидаторы |
| 10 | progress_tracker.py | 211 | **MEDIUM** | Async прогресс-бар |

---

## ИТОГОВАЯ СТАТИСТИКА

- **Покрыто тестами**: ~8 модулей из ~20 основных
- **НЕ покрыто**: ~12 модулей (handlers, callbacks, retranscribe, keyboards, queue_manager, progress_tracker, telegram_client, router, factory, config, database, db_retry, health_check, main)
- **Оценочное покрытие строк**: ~25-30%
- **Интеграционные тесты**: 0
- **Количество тестов**: ~120 (оценочно)
- **Качество существующих тестов**: ХОРОШЕЕ

## ТОП-5 РЕКОМЕНДАЦИЙ

1. Тесты для keyboards.py — чистые функции, быстро написать
2. Тесты для split_text в handlers.py — чистая функция, критическая логика
3. Тесты для CallbackHandlers — LEVEL_TRANSITIONS, routing
4. Тесты для QueueManager — конкурентность, race conditions
5. Хотя бы 1 интеграционный тест полного pipeline
