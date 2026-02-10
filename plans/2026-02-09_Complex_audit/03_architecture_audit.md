# Architecture Audit Report: telegram-voice2text-bot

**Дата:** 2026-02-09
**Ревьюер:** Architecture Reviewer
**Оценка:** 6/10

---

## 1. SOLID принципы

### [SEVERITY: HIGH] SRP: handlers.py — God Object (2182 строки)
- **Файл**: `src/bot/handlers.py`
- **Описание**: Класс `BotHandlers` совмещает минимум 6 ответственностей:
  1. Обработка команд (start, help, stats)
  2. Обработка 4 типов сообщений (voice, audio, document, video)
  3. Управление очередью (_update_queue_messages)
  4. Бизнес-логика транскрипции (_process_transcription — 500+ строк)
  5. Отправка результатов (_send_transcription_result, _send_draft_messages)
  6. Управление интерактивным состоянием (_create_interactive_state_and_keyboard)
- **Impact**: Крайне сложно модифицировать и тестировать.
- **Рекомендация**: Выделить CommandHandlers, MediaHandlers, TranscriptionService, ResultSender.

### [SEVERITY: HIGH] SRP: Массивная дупликация в voice/audio/document/video handlers
- **Файл**: `src/bot/handlers.py`, строки 355-1396
- **Описание**: ~80% идентичного кода в 4 обработчиках.
- **Рекомендация**: Создать единый `_handle_media_message(update, context, media_info)`.

### [SEVERITY: MEDIUM] OCP: Добавление нового провайдера
- **Файл**: `src/transcription/factory.py`, строки 134-167
- **Описание**: If/elif цепочка. Добавление нового провайдера — модификация в 3-4 местах.
- **Рекомендация**: Реестр провайдеров (dict mapping name -> class).

### [SEVERITY: LOW] LSP: Иерархия TranscriptionProvider — корректная
- **Файл**: `src/transcription/providers/base.py`
- **Описание**: ABC с 4 методами. Оба подкласса корректно реализуют интерфейс.

### [SEVERITY: LOW] ISP: Интерфейсы адекватны
- **Описание**: TranscriptionProvider (4 метода), LLMProvider (2 метода), RoutingStrategy (6 методов с default-реализациями). Не перегружены.

### [SEVERITY: MEDIUM] DIP: Прямые зависимости от конкретных классов
- **Файл**: `src/bot/handlers.py`, строки 26-27, 1768
- **Описание**: Принимает TranscriptionRouter напрямую. `isinstance(self.transcription_router.strategy, HybridStrategy)` — прямая зависимость.
- **Рекомендация**: Использовать Protocol/ABC; вместо isinstance — полиморфные методы.

---

## 2. Coupling / Cohesion

### [SEVERITY: HIGH] Tight Coupling: handlers.py зависит от ВСЕГО
- **Файл**: `src/bot/handlers.py`, строки 16-35
- **Описание**: 15+ импортов из всех слоёв системы. Handlers знает о каждом модуле.
- **Рекомендация**: Ввести TranscriptionOrchestrator.

### [SEVERITY: MEDIUM] Прямой доступ к БД из обработчиков
- **Файл**: `src/bot/handlers.py`, строки 240, 316, 450, 509, 773, 834
- **Описание**: Обработчики напрямую открывают `async with get_session()`. 7 сессий в _process_transcription.
- **Рекомендация**: Вынести в сервисный слой.

### [SEVERITY: LOW] Хорошая cohesion в services/ и storage/
- **Описание**: Чистый Repository Pattern. Хорошие сервисы.

---

## 3. Паттерны проектирования

### [SEVERITY: INFO] Repository Pattern — реализован корректно
- **Файл**: `src/storage/repositories.py`
- **Описание**: 6 репозиториев. Каждый принимает AsyncSession. Чистая реализация.

### [SEVERITY: INFO] Strategy Pattern — реализован корректно
- **Файл**: `src/transcription/routing/strategies.py`
- **Описание**: ABC RoutingStrategy с 5 конкретными стратегиями.

### [SEVERITY: INFO] Factory Pattern — реализован
- **Файл**: `src/transcription/factory.py`
- **Описание**: create_transcription_router() и LLMFactory.create_provider().

### [SEVERITY: HIGH] Anti-pattern: God Method — _process_transcription
- **Файл**: `src/bot/handlers.py`, строки 1665-2167
- **Описание**: **502 строки**. Preprocessing, транскрипция, HybridStrategy, StructureStrategy, draft messages, LLM refinement, DB updates (7 сессий), cleanup, error handling.
- **Impact**: Невозможно тестировать изолированно. Цикломатическая сложность крайне высокая.
- **Рекомендация**: Разбить на 4-5 методов.

### [SEVERITY: MEDIUM] Anti-pattern: Дупликация в callbacks.py
- **Файл**: `src/bot/callbacks.py`, строки 291-700
- **Описание**: 3 почти идентичных блока для structured/summary/magic (~400 строк).
- **Рекомендация**: Извлечь `_generate_variant(usage_id, mode, generator_fn)`.

---

## 4. Обработка ошибок

### [SEVERITY: MEDIUM] Нет иерархии бизнес-исключений
- **Описание**: Только ValueError, RuntimeError, Exception. Только llm_service.py имеет LLMError hierarchy.
- **Рекомендация**: Создать `src/exceptions.py`: BotError -> TranscriptionError, AudioProcessingError, QueueError, StorageError.

### [SEVERITY: LOW] Graceful degradation — реализован хорошо
- **Описание**: При сбое structuring — fallback на original. При сбое LLM — показ draft. При сбое PDF — fallback на TXT.

### [SEVERITY: LOW] User-facing ошибки — технические детали не утекают
- **Описание**: Пользователю — generic-сообщения на русском. Технические детали — в логи.

---

## 5. Dependency Injection

### [SEVERITY: MEDIUM] DI через manual wiring, с проблемами
- **Файл**: `src/main.py`, строки 60-240
- **Описание**: Manual wiring приемлем. Но CallbackHandlers пересоздаётся на каждый callback (строки 216-231).
- **Рекомендация**: Lazy session injection.

### [SEVERITY: LOW] Глобальные синглтоны
- **Файлы**: `src/config.py:358-360`, `src/storage/database.py:20-21`
- **Описание**: settings, _engine, _session_factory, _router_instance. Обычная практика для Telegram-бота.

---

## 6. Разделение слоёв

### [SEVERITY: HIGH] Нарушение: bot-слой содержит бизнес-логику
- **Файл**: `src/bot/handlers.py`
- **Описание**: `_process_transcription` — полноценный бизнес-процесс. Невозможно переиспользовать (например, для REST API).
- **Рекомендация**: Создать `src/services/transcription_orchestrator.py`.

### [SEVERITY: INFO] storage/ и transcription/ — хорошо изолированы

---

## 7. Config.py

### [SEVERITY: MEDIUM] Large Object (~80 настроек), но не God Object
- **Файл**: `src/config.py`, 360 строк
- **Описание**: Для Pydantic Settings обычный подход.
- **Рекомендация**: Опционально — вложенные модели (TelegramSettings, TranscriptionSettings, LLMSettings).

---

## 8. Расширяемость

### [SEVERITY: INFO] Новый провайдер транскрипции — умеренно просто
### [SEVERITY: MEDIUM] Новая интерактивная кнопка — сложно (5+ файлов)
### [SEVERITY: MEDIUM] Новый LLM-провайдер — просто (но LLMFactory поддерживает только deepseek)

---

## 9. Циклические зависимости

### [SEVERITY: LOW] Нет циклических зависимостей на уровне модулей
- Граф однонаправленный: main -> bot -> services -> storage.

### [SEVERITY: INFO] Мягкая зависимость callbacks -> handlers через TYPE_CHECKING

---

## 10. Единообразие API

### [SEVERITY: MEDIUM] Неконсистентность в lifecycle
- **Описание**: FastWhisperProvider.initialize() — sync. TelegramClientService.start() — async. LLMService — нет initialize().
- **Рекомендация**: Унифицировать async initialize() / shutdown() для всех сервисов.

### [SEVERITY: LOW] Неконсистентность именования
- whisper_service на самом деле TranscriptionRouter. voice_file_id хранит file_id для любого media.

---

## Итого

| Severity | Count |
|----------|-------|
| HIGH | 4 |
| MEDIUM | 8 |
| LOW | 6 |
| INFO | 5 |
