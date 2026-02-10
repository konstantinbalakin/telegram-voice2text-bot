# Performance Audit Report: telegram-voice2text-bot

**Дата:** 2026-02-09
**Ревьюер:** Performance Reviewer
**Оценка:** 5/10

---

## HIGH

### 1. [SEVERITY: HIGH] Множественные DB-сессии на один запрос — handlers.py
- **Файл**: `src/bot/handlers.py`, строки 450-514, 1802, 1839, 1855, 1903, 1979, 2026, 2110, 2125
- **Описание**: В `_process_transcription` открывается до **7-8 отдельных DB-сессий** (через `async with get_session()`) за один запрос на транскрипцию. Каждая сессия — отдельное подключение к SQLite, транзакция, commit, close.
- **Impact**: Каждая SQLite-транзакция — WAL checkpoint + fsync. При одновременных пользователях — lock contention.
- **Рекомендация**: Объединить операции в одну сессию. Рассмотреть unit-of-work паттерн.

### 2. [SEVERITY: HIGH] Блокирующие вызовы subprocess в async-контексте — audio_handler.py
- **Файл**: `src/transcription/audio_handler.py`, строки 260-824
- **Описание**: Все вызовы `subprocess.run()` (ffmpeg, ffprobe) — **блокирующие** в async-контексте. При обработке аудио 30+ минут ffmpeg блокирует event loop на десятки секунд.
- **Impact**: **Критический** для concurrency. Бот перестаёт отвечать всем пользователям.
- **Рекомендация**: Заменить на `asyncio.create_subprocess_exec()` или `asyncio.to_thread()`.

### 3. [SEVERITY: HIGH] Загрузка всего аудио в память при chunking — openai_provider.py
- **Файл**: `src/transcription/providers/openai_provider.py`, строки 339-395
- **Описание**: `AudioSegment.from_file()` (pydub) **загружает весь аудиофайл в память** как PCM. Для файлов до 2 ГБ (Telethon) — многие гигабайты RAM.
- **Impact**: OOM при обработке больших файлов. Crash сервера.
- **Рекомендация**: Использовать ffmpeg для разбиения на чанки (`ffmpeg -ss start -t duration`).

### 4. [SEVERITY: HIGH] Утечка результатов в _results dict — queue_manager.py
- **Файл**: `src/services/queue_manager.py`, строки 72, 296-300
- **Описание**: Результаты хранятся в `self._results: dict`. `wait_for_result()` **нигде не вызывается**. Результаты **накапливаются бесконечно**.
- **Impact**: Медленная утечка памяти. За месяцы работы — значительное потребление.
- **Рекомендация**: Добавить очистку `_results` после обработки или TTL-based cleanup.

---

## MEDIUM

### 5. [SEVERITY: MEDIUM] PDFGenerator создаётся заново на каждый callback
- **Файл**: `src/bot/callbacks.py:135-136, 183-184`
- **Описание**: `PDFGenerator()` создаётся при каждом вызове. Конструктор инициализирует WeasyPrint FontConfiguration (сканирование системных шрифтов).
- **Impact**: 50-200ms overhead на каждый PDF.
- **Рекомендация**: Переиспользовать единый экземпляр PDFGenerator.

### 6. [SEVERITY: MEDIUM] Повторные DB-запросы segments в callbacks
- **Файл**: `src/bot/callbacks.py`, строки 453-454, 711, 553, 868, 1078, 1104, 1157, 1269
- **Описание**: Segments запрашиваются **дважды** в каждом callback handler.
- **Impact**: Лишние SQL-запросы при каждом нажатии кнопки.
- **Рекомендация**: Кешировать результат в локальной переменной.

### 7. [SEVERITY: MEDIUM] get_user_total_duration загружает все записи
- **Файл**: `src/storage/repositories.py`, строки 229-233
- **Описание**: Загружаются **все Usage-объекты** пользователя, суммируется одно поле.
- **Impact**: Лишнее потребление памяти при большом количестве records.
- **Рекомендация**: Использовать `select(func.sum(Usage.voice_duration_seconds))`.

### 8. [SEVERITY: MEDIUM] stats_command показывает неполные данные
- **Файл**: `src/bot/handlers.py`, строки 328-341
- **Описание**: `get_by_user_id` имеет `limit=10`, поэтому `total_count` всегда <= 10. Статистика **неправильная**.
- **Impact**: Некорректные данные для пользователей с >10 транскрипциями.
- **Рекомендация**: Использовать `count_by_user_id()` и SQL SUM.

### 9. [SEVERITY: MEDIUM] UPDATE last_accessed_at при каждом SELECT варианта
- **Файл**: `src/storage/repositories.py`, строки 493-496
- **Описание**: При **каждом** чтении варианта — UPDATE + flush. Один callback может вызвать get_variant 2-3 раза.
- **Impact**: Лишние write-операции, увеличение WAL, lock contention.
- **Рекомендация**: Убрать автоматическое обновление или обновлять только при активном использовании.

### 10. [SEVERITY: MEDIUM] N+1 при удалении вариантов
- **Файл**: `src/storage/repositories.py`, строки 509-527
- **Описание**: SELECT всех вариантов, затем N отдельных DELETE.
- **Impact**: Десятки DELETE-запросов вместо одного при ретранскрипции.
- **Рекомендация**: Использовать bulk DELETE как в TranscriptionSegmentRepository.

### 11. [SEVERITY: MEDIUM] httpx клиент без connection pooling
- **Файл**: `src/transcription/audio_handler.py`, строки 147-161
- **Описание**: Новый HTTP-клиент для каждого скачивания.
- **Impact**: Лишний overhead на TLS handshake.
- **Рекомендация**: Переиспользовать httpx клиент.

### 12. [SEVERITY: MEDIUM] Двойной get_variant перед записью
- **Файл**: `src/bot/callbacks.py`, строки 410-416, 522-528, 632-638
- **Описание**: Повторный get_variant для проверки race condition + UPDATE last_accessed_at.
- **Impact**: Дополнительные 2 UPDATE + 1 SELECT.
- **Рекомендация**: Использовать INSERT OR IGNORE (UPSERT) или try/except IntegrityError.

### 13. [SEVERITY: MEDIUM] Progress tracker может превысить Telegram rate limits
- **Файл**: `src/services/progress_tracker.py`, строки 67, 111
- **Описание**: update_interval=5с. При 10 одновременных транскрипциях = 2 edit/sec — на грани rate limit.
- **Impact**: Частые RetryAfter, устаревший прогресс-бар.
- **Рекомендация**: Увеличить до 7-10 секунд. Добавить глобальный rate limiter.

### 14. [SEVERITY: MEDIUM] Масштабная дупликация кода обработчиков
- **Файл**: `src/bot/handlers.py`
- **Описание**: voice/audio/document/video handlers содержат ~80% идентичного кода.
- **Impact**: Не прямой performance impact, но затрудняет оптимизации.
- **Рекомендация**: Извлечь `_handle_media_message()`.

---

## LOW

### 15. [SEVERITY: LOW] Синхронный init_db создаёт sync engine
- **Файл**: `src/storage/database.py`, строки 140-148
- **Impact**: Небольшое замедление старта (100-500ms).

### 16. [SEVERITY: LOW] Отсутствие индексов для variant queries
- **Файл**: `src/storage/repositories.py`, строки 480-490
- **Описание**: SELECT по 5 полям без составного индекса — full table scan.
- **Рекомендация**: Добавить составной индекс `(usage_id, mode, length_level, emoji_level, timestamps_enabled)`.

### 17. [SEVERITY: LOW] QueueManager линейный поиск
- **Файл**: `src/services/queue_manager.py`, строки 266-267, 324-325, 370-376, 421-423
- **Описание**: `_pending_requests` — list, remove/in — O(n).
- **Impact**: Минимальный при max_queue=50.

### 18. [SEVERITY: LOW] DeepSeek max_tokens=4000 hardcoded
- **Файл**: `src/services/llm_service.py`, строка 139
- **Описание**: Для длинных текстов ответ LLM будет обрезан.
- **Рекомендация**: Сделать настраиваемым или вычислять динамически.

---

## INFO

### 19. [SEVERITY: LOW] Blocking file cleanup в async
- **Файл**: `src/transcription/audio_handler.py`, строки 177-207
- **Рекомендация**: Обернуть в `asyncio.to_thread()`.

### 20. [SEVERITY: INFO] Health check создаёт отдельный engine
- **Файл**: `src/health_check.py`, строки 97-99
- **Impact**: Минимальный.

### 21. [SEVERITY: INFO] Debug handler на все updates
- **Файл**: `src/main.py`, строки 177-188
- **Рекомендация**: Регистрировать только при DEBUG.
