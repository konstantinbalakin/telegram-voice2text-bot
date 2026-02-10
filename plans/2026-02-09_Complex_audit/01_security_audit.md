# Security Audit Report: telegram-voice2text-bot

**Дата:** 2026-02-09
**Ревьюер:** Security Reviewer
**Оценка:** 7/10

---

## КРИТИЧЕСКИЕ (CRITICAL)

### 1. [SEVERITY: CRITICAL] Утечка Database URL в логи при старте
- **Файл**: `src/main.py:74`
- **Код**: `logger.info(f"Database: {settings.database_url}")`
- **Проблема**: Database URL может содержать пароль (например, `postgresql+asyncpg://user:password@host/db`). Логируется при каждом запуске.
- **Impact**: Утечка credentials базы данных в логи и системы сбора логов.
- **Рекомендация**: Маскировать database URL при логировании. Для SQLite это не критично, но при миграции на PostgreSQL (что указано в .env.example) credentials утекут.

---

## ВЫСОКИЕ (HIGH)

### 2. [SEVERITY: HIGH] Утечка Bot Token в логах при DEBUG-уровне
- **Файл**: `.env.example:345-357`, `src/utils/logging_config.py`
- **Проблема**: В .env.example явно указано: "DEBUG level shows full HTTP request URLs including bot token". При LOG_LEVEL=DEBUG библиотека python-telegram-bot логирует все HTTP-запросы к Telegram API, URL которых содержат bot token (`https://api.telegram.org/bot<TOKEN>/...`).
- **Impact**: Компрометация bot token позволяет полностью перехватить управление ботом.
- **Рекомендация**: Фильтровать URL-ы Telegram API в логгере, заменяя token на маску. Добавить кастомный logging filter.

### 3. [SEVERITY: HIGH] Отсутствие авторизации пользователей callback queries (IDOR)
- **Файл**: `src/bot/callbacks.py:234-289`
- **Проблема**: В `handle_callback_query` нет проверки, что пользователь, отправивший callback query, является владельцем транскрипции. Callback data содержит `usage_id` в открытом виде (`mode:123:mode=structured`). Злоумышленник может создать поддельный callback с чужим `usage_id` и:
  - Просматривать чужие транскрипции (при переключении режимов текст отправляется пользователю)
  - Менять состояние чужих транскрипций
  - Инициировать LLM-обработку чужих текстов (потребление ресурсов)
- **Impact**: Несанкционированный доступ к данным других пользователей, IDOR-уязвимость.
- **Рекомендация**: Добавить проверку `user_id` из callback query против owner'а usage записи. Сравнивать `query.from_user.id` с `usage.user_id -> user.telegram_id`.

### 4. [SEVERITY: HIGH] Отсутствие per-user rate limiting
- **Файл**: `src/bot/handlers.py:355-681`
- **Проблема**: Нет ограничения на количество запросов от одного пользователя. Единственная защита - общий размер очереди (`max_queue_size`). Один пользователь может заполнить всю очередь, блокируя остальных.
- **Impact**: Denial of Service для других пользователей. Одна учётная запись может полностью загрузить бота. Также это ведёт к неконтролируемым расходам на OpenAI API.
- **Рекомендация**: Добавить per-user rate limit (например, max N запросов в минуту/час). Использовать `default_daily_quota_seconds` (уже есть в config, но не применяется).

### 5. [SEVERITY: HIGH] Предсказуемые имена временных файлов
- **Файл**: `src/bot/handlers.py:134`
- **Код**: `permanent_path = persistent_dir / f"{usage_id}_{file_identifier}{file_extension}"`
- **Проблема**: Имена файлов формируются из предсказуемых usage_id и file_identifier. В Docker контейнере это менее критично, но при запуске без Docker на shared hosting может привести к перезаписи файлов.
- **Impact**: Потенциальная перезапись/чтение чужих аудиофайлов при предсказуемых ID.
- **Рекомендация**: Использовать UUID в именах файлов вместо sequential ID.

---

## СРЕДНИЕ (MEDIUM)

### 6. [SEVERITY: MEDIUM] API ключ частично логируется
- **Файл**: `src/services/llm_service.py:122-125`
- **Код**: `api_key_masked = self.api_key[:8] + "..." if self.api_key else "None"`
- **Проблема**: Первые 8 символов API-ключа логируются. Для DeepSeek ключи начинаются с `sk-`, так что реально маскируется `sk-XXXXX...`. Это снижает энтропию ключа.
- **Impact**: Частичное раскрытие API ключа, упрощающее brute-force.
- **Рекомендация**: Маскировать `self.api_key[:4] + "***"` или логировать только последние 4 символа.

### 7. [SEVERITY: MEDIUM] Health check не проверяет реальное состояние бота
- **Файл**: `Dockerfile:37-38`
- **Код**: `HEALTHCHECK ... CMD python -c "import sys; sys.exit(0)"`
- **Проблема**: Docker HEALTHCHECK всегда возвращает "healthy" — это заглушка. При этом существует полноценный `src/health_check.py` с проверкой БД и миграций, который не используется.
- **Impact**: Docker и оркестратор не могут обнаружить неработающий контейнер, автоматического перезапуска не будет.
- **Рекомендация**: Заменить на `CMD python -m src.health_check`.

### 8. [SEVERITY: MEDIUM] Отсутствие валидации callback_data
- **Файл**: `src/bot/keyboards.py:41-59`
- **Проблема**: `decode_callback_data` не валидирует входные данные. Если `parts[1]` не может быть конвертирован в int, или формат нарушен, то будет IndexError или ValueError. При этом exception обрабатывается в `callbacks.py:256-261`, но не все подвызовы защищены.
- **Impact**: Потенциальный crash при обработке crafted callback data.
- **Рекомендация**: Добавить строгую валидацию в `decode_callback_data`: проверку количества частей, типов и допустимых значений.

### 9. [SEVERITY: MEDIUM] subprocess вызовы без таймаутов
- **Файл**: `src/transcription/audio_handler.py:260, 292, 324, 458, 517, 622, 691, 737, 769, 807`
- **Проблема**: Все вызовы `subprocess.run()` (ffprobe, ffmpeg) не имеют параметра `timeout`. При обработке crafted аудиофайла ffmpeg может зависнуть навечно.
- **Impact**: Зависание worker'а, исчерпание ресурсов, фактический DoS при отправке специально подготовленного файла.
- **Рекомендация**: Добавить `timeout=300` (или настраиваемый) ко всем вызовам subprocess.run().

### 10. [SEVERITY: MEDIUM] Отсутствие ограничения на количество вариантов транскрипции
- **Файл**: `src/bot/callbacks.py:844, 1046` и `src/config.py:259`
- **Проблема**: Параметр `max_cached_variants_per_transcription=10` определён в config, но нигде не проверяется при создании вариантов. Пользователь может генерировать неограниченное количество LLM-вариантов.
- **Impact**: Неконтролируемый расход на LLM API, потенциальный DoS через массовую генерацию вариантов.
- **Рекомендация**: Проверять count вариантов перед созданием нового и отклонять при превышении лимита.

### 11. [SEVERITY: MEDIUM] Нет санитизации HTML в пользовательском тексте
- **Файл**: `src/bot/handlers.py:1554-1556`, `src/bot/callbacks.py:101, 225`
- **Проблема**: Транскрибированный текст отправляется с `parse_mode="HTML"`. Если OpenAI Whisper или DeepSeek вернут текст с HTML-тегами, это может сломать отображение сообщений.
- **Impact**: Telegram сам фильтрует опасные HTML теги, поэтому XSS невозможен, но невалидный HTML приведёт к ошибке BadRequest при отправке.
- **Рекомендация**: Экранировать спецсимволы HTML (`<`, `>`, `&`) в тексте транскрипции перед отправкой. Проверить использование `src/utils/html_utils.py`.

### 12. [SEVERITY: MEDIUM] Telethon session файл без шифрования
- **Файл**: `src/services/telegram_client.py:34-38`
- **Проблема**: Telethon создаёт `.session` файл (SQLite), содержащий auth key для Telegram MTProto. Файл хранится без шифрования.
- **Impact**: Компрометация session файла позволяет использовать Telegram Client API от имени бота.
- **Рекомендация**: Хранить session файл в защищённом каталоге с минимальными правами. В Docker — использовать Docker secrets или encrypted volumes.

---

## НИЗКИЕ (LOW)

### 13. [SEVERITY: LOW] Docker контейнер от non-root (хорошо), но pip остаётся
- **Файл**: `Dockerfile:30-33`
- **Проблема**: `useradd -m appuser` и `USER appuser` используется после установки зависимостей — корректный подход. Но pip, setuptools остаются в контейнере.
- **Impact**: Минимальный при правильной настройке.
- **Рекомендация**: В production удалять pip после установки зависимостей.

### 14. [SEVERITY: LOW] Устаревшее SIGINT handling
- **Файл**: `src/main.py:311-316`
- **Проблема**: Двойной try/except для KeyboardInterrupt.
- **Impact**: Потенциально неполная очистка ресурсов при SIGINT.
- **Рекомендация**: Использовать signal handlers для graceful shutdown.

### 15. [SEVERITY: LOW] DEBUG handler логирует все входящие сообщения
- **Файл**: `src/main.py:177-188`
- **Проблема**: `debug_all_updates` зарегистрирован ВСЕГДА (не только в DEBUG mode).
- **Impact**: Минимальное влияние на производительность.
- **Рекомендация**: Регистрировать debug handler только при `settings.log_level == "DEBUG"`.

### 16. [SEVERITY: LOW] Error handler раскрывает тип ошибки в логах
- **Файл**: `src/bot/handlers.py:2169-2182`
- **Проблема**: `error_handler` логирует полный stack trace. Пользователю — только generic-сообщение (хорошо).
- **Impact**: Минимальный — stack trace только в логах, не пользователю.
- **Рекомендация**: Убедиться, что логи не доступны публично.

---

## ИНФОРМАЦИОННЫЕ (INFO)

### 17. [SEVERITY: INFO] SQL Injection — не обнаружено
- **Файл**: `src/storage/repositories.py`
- **Описание**: Все SQL-запросы через SQLAlchemy ORM с параметризованными запросами. Единственные raw SQL — `PRAGMA` команды в `database.py:114-115` — не содержат пользовательского ввода.

### 18. [SEVERITY: INFO] Command Injection — низкий риск
- **Файл**: `src/transcription/audio_handler.py`
- **Описание**: Все subprocess.run() используют список аргументов (не строку). Пути формируются из Path объектов. Прямого пользовательского ввода в subprocess нет.

### 19. [SEVERITY: INFO] Secrets management через env variables
- **Файл**: `src/config.py`
- **Описание**: Все секреты загружаются из переменных окружения через pydantic-settings. Hardcoded секретов нет. `.env` в `.gitignore`.

### 20. [SEVERITY: INFO] Path Traversal — низкий риск
- **Файлы**: `src/transcription/audio_handler.py`, `src/bot/handlers.py`
- **Описание**: Файлы загружаются через Telegram API в фиксированный `temp_dir`. Имена из `file_id + uuid`. Без возможности выхода за пределы директории.

### 21. [SEVERITY: INFO] Зависимости — рекомендуется обновление
- **Файл**: `pyproject.toml`
- **Описание**: Зависимости используют широкие constraint'ы (`>=`). Рекомендуется регулярно проверять `pip-audit` или `safety check`.

### 22. [SEVERITY: INFO] docker-compose.prod.yml — секреты через env_file
- **Файл**: `docker-compose.prod.yml`
- **Описание**: Секреты через `env_file: .env`. Стандартный подход, но при Docker Swarm рекомендуется Docker Secrets.
