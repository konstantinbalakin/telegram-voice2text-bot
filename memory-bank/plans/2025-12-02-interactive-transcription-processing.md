# План реализации: Интерактивная обработка транскрипций

**Дата создания:** 2025-12-02
**Статус:** Утверждён
**Стратегия:** Фазовый MVP подход (Вариант 1)
**Целевой срок:** 13-18 дней разработки

---

## Содержание

1. [Обзор проекта](#обзор-проекта)
2. [Архитектурные решения](#архитектурные-решения)
3. [Схема базы данных](#схема-базы-данных)
4. [Структура модулей](#структура-модулей)
5. [Детальный план по фазам](#детальный-план-по-фазам)
6. [Критерии успеха](#критерии-успеха)
7. [Риски и митигации](#риски-и-митигации)

---

## Обзор проекта

### Цель
Добавить интерактивную обработку результатов транскрипции через inline-кнопки в Telegram, позволяя пользователям:
- Переключаться между режимами просмотра (исходный/структурированный/резюме)
- Изменять длину текста (короче/длиннее)
- Добавлять эмодзи
- Включать/выключать таймкоды
- Запрашивать повторную транскрипцию с лучшим качеством

### Принципиальная схема UI

```
┌─────────────────────────────────────┐
│ 📝 Расшифровка готова!              │
│ [Исходный текст]                    │  ← Ряд 1: Базовые режимы
│ [Структурировать]                   │  ← Ряд 2: Структурирование
│ [О чем текст?]                      │  ← Ряд 3: Резюме
│ [😊 Смайлы]                         │  ← Ряд 4: Опция смайлов
│ [⏱ Таймкоды]                        │  ← Ряд 5: Опция таймкодов
│ [⚡ Могу лучше]                      │  ← Ряд 6: Повтор транскрипции
└─────────────────────────────────────┘
```

**Динамическое изменение кнопок:**
```
Режим "Структурировать" активен:
┌─────────────────────────────────────┐
│ [Исходный текст]                    │
│ [Короче] [📝] [Длиннее]             │  ← 3 кнопки вместо одной
│ [О чем текст?]                      │
│ [Меньше] [😊] [Больше]              │  ← Если смайлы активны
└─────────────────────────────────────┘
```

---

## Архитектурные решения

### Ключевые решения

| Аспект | Решение | Обоснование |
|--------|---------|-------------|
| **База данных** | SQLite (текущая) | Достаточно для нагрузки, проще в разработке |
| **Хранение состояния** | PostgreSQL/SQLite таблица + in-memory кэш | Нет необходимости в Redis для MVP |
| **LLM промпты** | Расширение существующего LLMService | Переиспользование инфраструктуры |
| **Файлы (>4096 символов)** | Гибридный подход: текст + документ | Обход ограничений Telegram API |
| **Сегменты faster-whisper** | Сохранение в БД при транскрипции | Данные уже есть, просто сохраняем |
| **Feature flags** | Environment variables через Settings | Гибкое управление функциональностью |
| **Callback data** | Компактное кодирование (JSON, base64) | Лимит 64 байта Telegram |

### Стратегия генерации вариантов

**Базовый принцип:** Инкрементальная генерация от базового уровня

```
Исходный текст
    ↓
    ├─→ Структурированный (default)
    │   ├─→ short (промпт: сделать короче на 20%)
    │   │   └─→ shorter (от short, ещё -20%)
    │   ├─→ long (промпт: сделать длиннее на 20%)
    │   │   └─→ longer (от long, ещё +20%)
    │
    └─→ Резюме (default)
        ├─→ short
        │   └─→ shorter
        ├─→ long
        │   └─→ longer
```

**Модификаторы (применимы к любому уровню):**
- Смайлы: 0 → 1-2 emoji → 3-5 emoji
- Таймкоды: off → on (форматирование существующих данных)

### Кэширование стратегия

1. **Генерация по требованию:** Не генерируем все 90 вариантов сразу
2. **Сохранение в БД:** Каждый сгенерированный вариант сохраняется
3. **TTL:** Удаление старых вариантов через `VARIANT_CACHE_TTL_DAYS` (default: 7 дней)
4. **Лимит:** Максимум `MAX_CACHED_VARIANTS_PER_TRANSCRIPTION` (default: 10)

---

## Схема базы данных

### Новые таблицы

#### 1. `transcription_states`
Текущее состояние UI для каждого сообщения с транскрипцией.

```sql
CREATE TABLE transcription_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Связи
    usage_id INTEGER NOT NULL,  -- FK to usage.id
    message_id INTEGER NOT NULL,  -- Telegram message ID with transcription
    chat_id INTEGER NOT NULL,  -- Telegram chat ID

    -- Текущее состояние UI
    active_mode VARCHAR(20) NOT NULL DEFAULT 'original',  -- original/structured/summary
    length_level VARCHAR(10) NOT NULL DEFAULT 'default',  -- default/short/shorter/long/longer
    emoji_level INTEGER NOT NULL DEFAULT 0,  -- 0/1/2
    timestamps_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    -- Метаданные
    is_file_message BOOLEAN NOT NULL DEFAULT FALSE,  -- Текст в файле или в сообщении
    file_message_id INTEGER NULL,  -- ID сообщения с файлом (если is_file_message=true)

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Индексы
    FOREIGN KEY (usage_id) REFERENCES usage(id) ON DELETE CASCADE,
    UNIQUE(message_id, chat_id)  -- Одно сообщение = одно состояние
);

CREATE INDEX idx_transcription_states_usage_id ON transcription_states(usage_id);
CREATE INDEX idx_transcription_states_message_chat ON transcription_states(message_id, chat_id);
```

#### 2. `transcription_variants`
Кэш сгенерированных вариантов текста.

```sql
CREATE TABLE transcription_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Связи
    usage_id INTEGER NOT NULL,  -- FK to usage.id

    -- Параметры варианта (составной ключ)
    mode VARCHAR(20) NOT NULL,  -- original/structured/summary
    length_level VARCHAR(10) NOT NULL,  -- default/short/shorter/long/longer
    emoji_level INTEGER NOT NULL,  -- 0/1/2
    timestamps_enabled BOOLEAN NOT NULL,

    -- Содержимое
    text_content TEXT NOT NULL,  -- Текст варианта

    -- Метаданные генерации
    generated_by VARCHAR(50),  -- llm/formatting (original не генерируется)
    llm_model VARCHAR(100) NULL,  -- Модель LLM если generated_by=llm
    processing_time_seconds FLOAT NULL,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Индексы
    FOREIGN KEY (usage_id) REFERENCES usage(id) ON DELETE CASCADE,
    UNIQUE(usage_id, mode, length_level, emoji_level, timestamps_enabled)
);

CREATE INDEX idx_transcription_variants_usage_id ON transcription_variants(usage_id);
CREATE INDEX idx_transcription_variants_last_accessed ON transcription_variants(last_accessed_at);
```

#### 3. `transcription_segments`
Сегменты с таймкодами из faster-whisper (для длинных аудио).

```sql
CREATE TABLE transcription_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Связи
    usage_id INTEGER NOT NULL,  -- FK to usage.id

    -- Сегмент данные
    segment_index INTEGER NOT NULL,  -- Порядковый номер (0, 1, 2, ...)
    start_time FLOAT NOT NULL,  -- Секунды
    end_time FLOAT NOT NULL,  -- Секунды
    text TEXT NOT NULL,  -- Текст сегмента

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Индексы
    FOREIGN KEY (usage_id) REFERENCES usage(id) ON DELETE CASCADE,
    UNIQUE(usage_id, segment_index)
);

CREATE INDEX idx_transcription_segments_usage_id ON transcription_segments(usage_id);
```

### Миграции Alembic

**Файл:** `alembic/versions/YYYYMMDD_add_interactive_transcription_tables.py`

Порядок создания:
1. Phase 1: Создать `transcription_states` и `transcription_segments`
2. Phase 2: Создать `transcription_variants`
3. Rollback поддержка: DROP TABLE в обратном порядке

---

## Структура модулей

### Новые файлы

```
src/
├── bot/
│   ├── callbacks.py          # NEW: Обработка callback queries
│   ├── keyboards.py           # NEW: Генерация inline клавиатур
│   └── handlers.py            # MODIFIED: Добавить inline кнопки после транскрипции
│
├── services/
│   ├── text_processor.py      # NEW: LLM операции над текстом
│   └── llm_service.py         # MODIFIED: Расширить для разных промптов
│
├── storage/
│   ├── models.py              # MODIFIED: Добавить новые модели
│   └── repositories.py        # MODIFIED: Репозитории для новых таблиц
│
├── transcription/
│   └── providers/
│       └── faster_whisper_provider.py  # MODIFIED: Сохранять segments
│
├── config.py                  # MODIFIED: Feature flags
└── main.py                    # MODIFIED: Зарегистрировать callback handler
```

### Примеры сигнатур

#### `src/bot/callbacks.py`
```python
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

class CallbackHandlers:
    """Обработка callback queries от inline кнопок."""

    async def handle_mode_change(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Переключение режима (original/structured/summary)."""
        pass

    async def handle_length_change(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Изменение длины (shorter/longer)."""
        pass

    async def handle_emoji_toggle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Добавление/удаление смайлов."""
        pass

    async def handle_timestamps_toggle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Включение/выключение таймкодов."""
        pass
```

#### `src/bot/keyboards.py`
```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.storage.models import TranscriptionState
from src.config import Settings

def create_transcription_keyboard(
    state: TranscriptionState,
    has_segments: bool,
    settings: Settings
) -> InlineKeyboardMarkup:
    """Создать inline клавиатуру на основе текущего состояния."""
    pass

def encode_callback_data(
    action: str,
    usage_id: int,
    **params
) -> str:
    """Кодировать данные в callback_data (макс 64 байта)."""
    # Формат: "action:usage_id:param1=val1,param2=val2"
    pass

def decode_callback_data(data: str) -> dict:
    """Декодировать callback_data обратно в словарь."""
    pass
```

#### `src/services/text_processor.py`
```python
from src.services.llm_service import LLMService
from src.storage.models import TranscriptionVariant

class TextProcessor:
    """Обработка текста транскрипции через LLM."""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    async def create_structured(
        self,
        original_text: str,
        length_level: str = "default"
    ) -> str:
        """Структурировать текст (абзацы, пунктуация, списки)."""
        pass

    async def create_summary(
        self,
        original_text: str,
        length_level: str = "default"
    ) -> str:
        """Создать резюме 'О чем текст?'."""
        pass

    async def adjust_length(
        self,
        current_text: str,
        direction: str,  # "shorter" or "longer"
        current_level: str
    ) -> str:
        """Изменить длину текста (±20%)."""
        pass

    async def add_emojis(
        self,
        text: str,
        emoji_level: int
    ) -> str:
        """Добавить эмодзи в текст."""
        pass

    def format_with_timestamps(
        self,
        segments: list,
        base_text: str
    ) -> str:
        """Добавить таймкоды в текст из сегментов."""
        # Формат: [00:15] Текст сегмента...
        pass
```

---

## Детальный план по фазам

### **Фаза 1: Базовая инфраструктура** (2-3 дня)

**Цели:**
- Создать БД модели и миграции
- Сохранять segments из faster-whisper
- Базовый callback query handler
- Feature flags инфраструктура
- Один режим: "Исходный текст" (кнопка-заглушка)

**Шаги:**

1. **Database Schema** (4-6 часов)
   - [ ] Создать модели `TranscriptionState`, `TranscriptionSegment`, `TranscriptionVariant` в `src/storage/models.py`
   - [ ] Создать Alembic миграцию
   - [ ] Запустить миграцию локально: `alembic upgrade head`
   - [ ] Создать репозитории в `src/storage/repositories.py`:
     - `TranscriptionStateRepository`
     - `TranscriptionSegmentRepository`
     - `TranscriptionVariantRepository`

2. **Feature Flags** (2-3 часа)
   - [ ] Добавить флаги в `src/config.py`:
     ```python
     # Interactive Features
     interactive_mode_enabled: bool = Field(default=False)
     enable_structured_mode: bool = Field(default=False)
     enable_summary_mode: bool = Field(default=False)
     enable_emoji_option: bool = Field(default=False)
     enable_timestamps_option: bool = Field(default=False)
     enable_length_variations: bool = Field(default=False)
     enable_retranscribe: bool = Field(default=False)

     # Limits
     max_cached_variants_per_transcription: int = Field(default=10)
     variant_cache_ttl_days: int = Field(default=7)
     timestamps_min_duration: int = Field(default=300)  # 5 минут
     ```
   - [ ] Обновить `.env.example` с документацией флагов

3. **Segments сохранение** (3-4 часа)
   - [ ] Изменить `src/transcription/providers/faster_whisper_provider.py`:
     - Вернуть segments вместе с текстом в `TranscriptionResult`
     - Добавить поле `segments: list[dict]` в `TranscriptionResult`
   - [ ] Изменить `src/transcription/models.py`:
     ```python
     @dataclass
     class TranscriptionSegment:
         start: float
         end: float
         text: str

     @dataclass
     class TranscriptionResult:
         # ... existing fields ...
         segments: Optional[list[TranscriptionSegment]] = None
     ```
   - [ ] Сохранять segments в БД после транскрипции (`src/bot/handlers.py`)

4. **Базовый Callback Handler** (4-5 часов)
   - [ ] Создать `src/bot/callbacks.py`:
     ```python
     class CallbackHandlers:
         async def handle_callback_query(self, update: Update, context):
             """Роутер для всех callback queries."""
             query = update.callback_query
             await query.answer()  # Acknowledge

             data = decode_callback_data(query.data)
             action = data['action']

             if action == 'mode':
                 await self.handle_mode_change(update, context)
             # ... другие действия
     ```
   - [ ] Создать `src/bot/keyboards.py`:
     ```python
     def create_transcription_keyboard(state, has_segments, settings):
         keyboard = []

         # Ряд 1: Исходный текст (всегда показывается если interactive_mode_enabled)
         if settings.interactive_mode_enabled:
             label = "Исходный текст (вы здесь)" if state.active_mode == "original" else "Исходный текст"
             keyboard.append([
                 InlineKeyboardButton(
                     label,
                     callback_data=encode_callback_data("mode", state.usage_id, mode="original")
                 )
             ])

         return InlineKeyboardMarkup(keyboard) if keyboard else None
     ```
   - [ ] Зарегистрировать handler в `src/main.py`:
     ```python
     from telegram.ext import CallbackQueryHandler

     callback_handlers = CallbackHandlers(...)
     application.add_handler(CallbackQueryHandler(callback_handlers.handle_callback_query))
     ```

5. **Интеграция с handlers** (3-4 часа)
   - [ ] Изменить `src/bot/handlers.py`:
     - После успешной транскрипции создать `TranscriptionState`
     - Добавить inline кнопки к сообщению с результатом
     - Для длинных текстов (>4096): создать два сообщения
   - [ ] Сохранять segments если `duration > timestamps_min_duration`

**Критерии успеха Фазы 1:**
- ✅ Миграции применяются без ошибок
- ✅ Segments сохраняются в БД для длинных аудио (>5 мин)
- ✅ После транскрипции показывается кнопка "Исходный текст"
- ✅ Нажатие на кнопку ничего не меняет (заглушка работает)
- ✅ Feature flag `INTERACTIVE_MODE_ENABLED=false` убирает все кнопки
- ✅ Все существующие тесты проходят

**Тестирование:**
```bash
# 1. Запустить миграции
alembic upgrade head

# 2. Тест 1: Короткое аудио (<5 мин)
# Отправить голосовое сообщение 30 сек
# Ожидание: Кнопка "Исходный текст" появляется, segments не сохраняются

# 3. Тест 2: Длинное аудио (>5 мин)
# Отправить 6-минутное аудио
# Ожидание: Кнопка появляется, segments сохраняются в БД

# 4. Тест 3: Feature flag
# .env: INTERACTIVE_MODE_ENABLED=false
# Ожидание: Кнопок нет вообще, работает как раньше

# 5. Проверка БД
sqlite3 data/bot.db "SELECT * FROM transcription_states LIMIT 1;"
sqlite3 data/bot.db "SELECT COUNT(*) FROM transcription_segments;"
```

---

### **Фаза 2: Режим "Структурировать"** (2-3 дня)

**Цели:**
- LLM промпты для структурирования (базовый уровень)
- Генерация и кэширование вариантов
- Переключение "Исходный" ↔ "Структурировать"

**Шаги:**

1. **TextProcessor сервис** (4-5 часов)
   - [ ] Создать `src/services/text_processor.py`
   - [ ] Реализовать `create_structured()`:
     ```python
     async def create_structured(self, original_text: str, length_level: str = "default") -> str:
         if length_level != "default":
             raise NotImplementedError("Length variations in Phase 3")

         prompt = """
         Твоя задача: структурировать текст голосовой транскрипции.

         Исходный текст (сырая транскрипция):
         {text}

         Требования:
         1. Исправить грамматические ошибки и опечатки
         2. Добавить правильную пунктуацию
         3. Разбить на абзацы по смыслу
         4. Выделить списки буллетами если уместно (•)
         5. Сохранить весь смысл и все детали
         6. НЕ добавлять ничего от себя
         7. НЕ сокращать (это не резюме)

         Верни ТОЛЬКО исправленный текст, без пояснений.
         """

         result = await self.llm.refine_transcription(
             original_text,
             prompt=prompt.format(text=original_text)
         )
         return result
     ```

2. **Кэширование вариантов** (3-4 часа)
   - [ ] В `src/storage/repositories.py`:
     ```python
     class TranscriptionVariantRepository:
         async def get_variant(
             self,
             usage_id: int,
             mode: str,
             length_level: str = "default",
             emoji_level: int = 0,
             timestamps_enabled: bool = False
         ) -> Optional[TranscriptionVariant]:
             """Получить вариант из кэша."""
             pass

         async def save_variant(
             self,
             usage_id: int,
             mode: str,
             text_content: str,
             length_level: str = "default",
             emoji_level: int = 0,
             timestamps_enabled: bool = False,
             generated_by: str = "llm",
             llm_model: Optional[str] = None,
             processing_time: Optional[float] = None
         ) -> TranscriptionVariant:
             """Сохранить сгенерированный вариант."""
             pass

         async def cleanup_old_variants(self, ttl_days: int) -> int:
             """Удалить варианты старше TTL."""
             pass
     ```

3. **Обновление CallbackHandlers** (5-6 часов)
   - [ ] В `src/bot/callbacks.py`:
     ```python
     async def handle_mode_change(self, update: Update, context):
         query = update.callback_query
         data = decode_callback_data(query.data)

         usage_id = data['usage_id']
         new_mode = data['mode']

         # Получить текущее состояние
         state = await state_repo.get_by_usage_id(usage_id)

         # Получить исходный текст из Usage
         usage = await usage_repo.get_by_id(usage_id)
         original_text = usage.get_original_text()  # Нужно добавить это

         # Получить или сгенерировать вариант
         variant = await variant_repo.get_variant(usage_id, new_mode)

         if not variant:
             # Генерация нового варианта
             if new_mode == "structured":
                 text = await text_processor.create_structured(original_text)
                 variant = await variant_repo.save_variant(
                     usage_id, new_mode, text,
                     generated_by="llm",
                     llm_model=settings.llm_model
                 )

         # Обновить состояние
         state.active_mode = new_mode
         await state_repo.update(state)

         # Обновить клавиатуру
         keyboard = create_transcription_keyboard(state, has_segments, settings)

         # Обновить сообщение
         if state.is_file_message:
             # Обновить файл (Фаза 7)
             pass
         else:
             await query.edit_message_text(
                 text=variant.text_content,
                 reply_markup=keyboard
             )
     ```

4. **Добавление кнопки в клавиатуру** (2 часа)
   - [ ] В `src/bot/keyboards.py`:
     ```python
     # Ряд 2: Структурировать
     if settings.enable_structured_mode:
         label = "Структурировать (вы здесь)" if state.active_mode == "structured" else "Структурировать"
         keyboard.append([
             InlineKeyboardButton(
                 label,
                 callback_data=encode_callback_data("mode", state.usage_id, mode="structured")
             )
         ])
     ```

5. **Сохранение оригинального текста** (1-2 часа)
   - [ ] Проблема: Сейчас в `Usage` только `transcription_length`, а не сам текст
   - [ ] Решение: Сохранять исходный текст как вариант с `mode=original`:
     ```python
     # В handlers.py после транскрипции:
     await variant_repo.save_variant(
         usage_id=usage.id,
         mode="original",
         text_content=transcription_text,
         generated_by="transcription"
     )
     ```

**Критерии успеха Фазы 2:**
- ✅ Появляется кнопка "Структурировать" (если флаг включен)
- ✅ При нажатии генерируется структурированный текст через LLM
- ✅ Повторное нажатие берёт из кэша (быстро)
- ✅ Переключение обратно на "Исходный текст" работает
- ✅ Кнопка показывает "(вы здесь)" для активного режима
- ✅ Сгенерированные варианты сохраняются в БД

**Тестирование:**
```bash
# 1. Включить feature flag
# .env: ENABLE_STRUCTURED_MODE=true

# 2. Отправить голосовое сообщение
# Ожидание: Две кнопки: "Исходный текст (вы здесь)" и "Структурировать"

# 3. Нажать "Структурировать"
# Ожидание: Текст изменился, кнопка стала "Структурировать (вы здесь)"

# 4. Нажать "Исходный текст"
# Ожидание: Вернулся оригинальный текст

# 5. Снова нажать "Структурировать"
# Ожидание: Быстрый ответ (из кэша), тот же текст

# 6. Проверка БД
sqlite3 data/bot.db "SELECT mode, generated_by FROM transcription_variants WHERE usage_id=X;"
# Ожидание: original (transcription), structured (llm)
```

---

### **Фаза 3: Вариации длины** (2 дня)

**Цели:**
- Промпты для изменения длины текста
- Динамические кнопки (1 → 3 при активации режима)
- Инкрементальная генерация (short от default, shorter от short)

**Шаги:**

1. **Промпты для длины** (3-4 часа)
   - [ ] В `src/services/text_processor.py`:
     ```python
     async def adjust_length(
         self,
         current_text: str,
         direction: str,  # "shorter" or "longer"
         current_level: str,
         mode: str  # "structured" or "summary"
     ) -> str:
         if direction == "shorter":
             prompt = """
             Твоя задача: сократить текст примерно на 20%, сохраняя ключевую информацию.

             Текущий текст ({mode}):
             {text}

             Требования:
             1. Убрать менее важные детали
             2. Сохранить основной смысл
             3. Сократить примерно на 20% по длине
             4. Сохранить структуру (абзацы, списки)
             5. НЕ добавлять ничего нового

             Верни ТОЛЬКО сокращённый текст.
             """
         else:  # longer
             prompt = """
             Твоя задача: расширить текст примерно на 20%, добавляя детали.

             Текущий текст ({mode}):
             {text}

             Требования:
             1. Развернуть ключевые мысли подробнее
             2. Добавить уточнения где уместно
             3. Увеличить примерно на 20% по длине
             4. Сохранить исходный смысл
             5. НЕ выдумывать факты

             Верни ТОЛЬКО расширенный текст.
             """

         result = await self.llm.refine_transcription(
             current_text,
             prompt=prompt.format(mode=mode, text=current_text)
         )
         return result
     ```

2. **Логика уровней** (2-3 часа)
   - [ ] Определить порядок: shorter ← short ← default → long → longer
   - [ ] В `src/bot/callbacks.py`:
     ```python
     LEVEL_TRANSITIONS = {
         "default": {"shorter": "short", "longer": "long"},
         "short": {"shorter": "shorter", "longer": "default"},
         "shorter": {"longer": "short"},  # Нет дальше shorter
         "long": {"shorter": "default", "longer": "longer"},
         "longer": {"shorter": "long"},  # Нет дальше longer
     }

     async def handle_length_change(self, update: Update, context):
         query = update.callback_query
         data = decode_callback_data(query.data)

         usage_id = data['usage_id']
         direction = data['direction']  # "shorter" or "longer"

         state = await state_repo.get_by_usage_id(usage_id)
         current_level = state.length_level

         # Проверка границ
         if direction not in LEVEL_TRANSITIONS[current_level]:
             await query.answer("Достигнут предел!", show_alert=True)
             return

         new_level = LEVEL_TRANSITIONS[current_level][direction]

         # Получить или сгенерировать
         variant = await variant_repo.get_variant(
             usage_id, state.active_mode, new_level, state.emoji_level, state.timestamps_enabled
         )

         if not variant:
             # Получить текущий текст (базу для изменения)
             current_variant = await variant_repo.get_variant(
                 usage_id, state.active_mode, current_level, state.emoji_level, state.timestamps_enabled
             )

             # Генерация
             new_text = await text_processor.adjust_length(
                 current_variant.text_content,
                 direction,
                 current_level,
                 state.active_mode
             )

             variant = await variant_repo.save_variant(
                 usage_id, state.active_mode, new_text,
                 length_level=new_level,
                 emoji_level=state.emoji_level,
                 timestamps_enabled=state.timestamps_enabled,
                 generated_by="llm"
             )

         # Обновить состояние
         state.length_level = new_level
         await state_repo.update(state)

         # Обновить UI
         keyboard = create_transcription_keyboard(state, has_segments, settings)
         await query.edit_message_text(variant.text_content, reply_markup=keyboard)
     ```

3. **Динамические кнопки** (3-4 часа)
   - [ ] В `src/bot/keyboards.py`:
     ```python
     # Ряд 2: Структурировать
     if settings.enable_structured_mode:
         if state.active_mode == "structured" and settings.enable_length_variations:
             # 3 кнопки: Короче | 📝 | Длиннее
             row = []

             # Кнопка "Короче"
             if state.length_level in ["short", "default", "long", "longer"]:
                 row.append(InlineKeyboardButton(
                     "Короче",
                     callback_data=encode_callback_data("length", state.usage_id, direction="shorter")
                 ))

             # Индикатор (не кликабельный)
             level_emoji = {
                 "shorter": "📝-",
                 "short": "📝↓",
                 "default": "📝",
                 "long": "📝↑",
                 "longer": "📝+"
             }
             row.append(InlineKeyboardButton(
                 level_emoji[state.length_level],
                 callback_data="noop"  # Игнорируем нажатие
             ))

             # Кнопка "Длиннее"
             if state.length_level in ["shorter", "short", "default", "long"]:
                 row.append(InlineKeyboardButton(
                     "Длиннее",
                     callback_data=encode_callback_data("length", state.usage_id, direction="longer")
                 ))

             keyboard.append(row)
         else:
             # Одна кнопка
             label = "Структурировать (вы здесь)" if state.active_mode == "structured" else "Структурировать"
             keyboard.append([InlineKeyboardButton(
                 label,
                 callback_data=encode_callback_data("mode", state.usage_id, mode="structured")
             )])
     ```

4. **Обработка "noop"** (0.5 часа)
   - [ ] В `src/bot/callbacks.py`:
     ```python
     async def handle_callback_query(self, update: Update, context):
         query = update.callback_query

         if query.data == "noop":
             await query.answer()  # Просто acknowledge, ничего не делаем
             return

         # ... остальные обработчики
     ```

**Критерии успеха Фазы 3:**
- ✅ При активации режима "Структурировать" появляются 3 кнопки
- ✅ Кнопка "Короче" генерирует более короткий текст
- ✅ Кнопка "Длиннее" генерирует более длинный текст
- ✅ На границах (shorter/longer) кнопка не показывается или disabled
- ✅ Центральная кнопка (индикатор) не реагирует на клики
- ✅ Переключение на "Исходный текст" сбрасывает на 1 кнопку

**Тестирование:**
```bash
# 1. Включить флаги
# .env: ENABLE_STRUCTURED_MODE=true, ENABLE_LENGTH_VARIATIONS=true

# 2. Активировать режим "Структурировать"
# Ожидание: Три кнопки: [Короче] [📝] [Длиннее]

# 3. Нажать "Короче"
# Ожидание: Текст короче, индикатор [📝↓], доступны обе кнопки

# 4. Нажать "Короче" снова
# Ожидание: Ещё короче, индикатор [📝-], кнопка "Короче" исчезла

# 5. Нажать "Длиннее" дважды
# Ожидание: Вернулись к default [📝]

# 6. Переключиться на "Исходный текст"
# Ожидание: Одна кнопка "Исходный текст (вы здесь)"
```

---

### **Фаза 4: Режим "О чем текст?"** (1-2 дня)

**Цели:**
- LLM промпт для создания резюме
- Третий режим с аналогичными вариациями длины
- Переключение между всеми тремя режимами

**Шаги:**

1. **Промпт для резюме** (2-3 часа)
   - [ ] В `src/services/text_processor.py`:
     ```python
     async def create_summary(
         self,
         original_text: str,
         length_level: str = "default"
     ) -> str:
         if length_level == "default":
             prompt = """
             Твоя задача: создать краткое резюме текста, отвечая на вопрос "О чем этот текст?"

             Исходный текст:
             {text}

             Требования:
             1. Выделить главную тему/идею
             2. Перечислить ключевые моменты (3-5 пунктов)
             3. Объём: примерно 25-30% от оригинала
             4. Структура: краткое введение + буллеты
             5. Сохранить важные детали
             6. НЕ выдумывать

             Формат ответа:
             О чем текст: <краткое описание темы>

             Ключевые моменты:
             • <пункт 1>
             • <пункт 2>
             • ...

             Верни ТОЛЬКО резюме в таком формате.
             """
         elif length_level in ["short", "shorter"]:
             # Более краткое резюме
             prompt = """... ещё короче, 2-3 пункта, 15-20% от оригинала ..."""
         else:  # long, longer
             # Более подробное резюме
             prompt = """... более подробно, 5-7 пунктов, 35-40% от оригинала ..."""

         result = await self.llm.refine_transcription(
             original_text,
             prompt=prompt.format(text=original_text)
         )
         return result
     ```

2. **Добавление кнопки** (1 час)
   - [ ] В `src/bot/keyboards.py`:
     ```python
     # Ряд 3: О чем текст?
     if settings.enable_summary_mode:
         if state.active_mode == "summary" and settings.enable_length_variations:
             # 3 кнопки аналогично structured
             row = []
             if state.length_level in ["short", "default", "long", "longer"]:
                 row.append(InlineKeyboardButton("Короче", ...))
             row.append(InlineKeyboardButton("💡" if state.active_mode=="summary" else "📋", ...))
             if state.length_level in ["shorter", "short", "default", "long"]:
                 row.append(InlineKeyboardButton("Длиннее", ...))
             keyboard.append(row)
         else:
             label = "О чем текст? (вы здесь)" if state.active_mode == "summary" else "О чем текст?"
             keyboard.append([InlineKeyboardButton(label, ...)])
     ```

3. **Обновление handle_mode_change** (1 час)
   - [ ] В `src/bot/callbacks.py`:
     ```python
     # В handle_mode_change добавить случай "summary":
     if new_mode == "summary":
         text = await text_processor.create_summary(original_text, state.length_level)
         # ... сохранение варианта
     ```

4. **Тестирование промптов** (2-3 часа)
   - [ ] Ручное тестирование качества резюме на разных текстах
   - [ ] Тюнинг промптов если нужно

**Критерии успеха Фазы 4:**
- ✅ Появляется кнопка "О чем текст?"
- ✅ Генерируется краткое резюме в формате "О чем + буллеты"
- ✅ Вариации длины работают (короче/длиннее)
- ✅ Переключение между всеми 3 режимами работает корректно
- ✅ При смене режима length_level сбрасывается на default

**Тестирование:**
```bash
# 1. Включить флаг
# .env: ENABLE_SUMMARY_MODE=true

# 2. Активировать "О чем текст?"
# Ожидание: Краткое резюме с буллетами

# 3. Проверить вариации длины
# Ожидание: Работает как в режиме "Структурировать"

# 4. Переключаться между режимами
# Ожидание: Корректная смена текста и кнопок
```

---

### **Фаза 5: Опция "Смайлы"** (1-2 дня)

**Цели:**
- Промпт для добавления эмодзи
- 3 уровня (0 / 1-2 emoji / 3-5 emoji)
- Применяется к любому активному режиму

**Шаги:**

1. **Промпт для смайлов** (2 часа)
   - [ ] В `src/services/text_processor.py`:
     ```python
     async def add_emojis(self, text: str, emoji_level: int) -> str:
         if emoji_level == 1:
             prompt = """
             Добавь 1-2 подходящих эмодзи в текст.

             Текст:
             {text}

             Требования:
             1. Эмодзи должны подчеркивать смысл
             2. Размещать в начале абзацев или перед важными фразами
             3. Не переборщить: 1-2 emoji на весь текст
             4. НЕ менять сам текст

             Верни текст с добавленными эмодзи.
             """
         elif emoji_level == 2:
             prompt = """
             Добавь 3-5 подходящих эмодзи в текст.

             Текст:
             {text}

             Требования:
             1. Эмодзи усиливают восприятие
             2. Размещать перед ключевыми идеями
             3. Умеренно: 3-5 emoji на текст
             4. Разнообразие эмодзи
             5. НЕ менять текст

             Верни текст с эмодзи.
             """
         else:
             return text  # Level 0 - без изменений

         result = await self.llm.refine_transcription(text, prompt=prompt.format(text=text))
         return result
     ```

2. **Callback handler** (3-4 часа)
   - [ ] В `src/bot/callbacks.py`:
     ```python
     async def handle_emoji_toggle(self, update: Update, context):
         query = update.callback_query
         data = decode_callback_data(query.data)

         usage_id = data['usage_id']
         direction = data.get('direction', 'increase')  # increase/decrease

         state = await state_repo.get_by_usage_id(usage_id)
         current_emoji = state.emoji_level

         # Вычислить новый уровень
         if direction == "increase":
             new_emoji = min(current_emoji + 1, 2)
             if new_emoji == current_emoji:
                 await query.answer("Больше смайлов нельзя!", show_alert=True)
                 return
         else:  # decrease
             new_emoji = max(current_emoji - 1, 0)

         # Получить базовый текст (без смайлов)
         base_variant = await variant_repo.get_variant(
             usage_id, state.active_mode, state.length_level, emoji_level=0, timestamps_enabled=state.timestamps_enabled
         )

         if new_emoji == 0:
             # Убрать смайлы = вернуться к базовому
             text = base_variant.text_content
         else:
             # Проверить кэш
             variant = await variant_repo.get_variant(
                 usage_id, state.active_mode, state.length_level, new_emoji, state.timestamps_enabled
             )

             if not variant:
                 # Генерация с эмодзи
                 text = await text_processor.add_emojis(base_variant.text_content, new_emoji)
                 variant = await variant_repo.save_variant(
                     usage_id, state.active_mode, text,
                     length_level=state.length_level,
                     emoji_level=new_emoji,
                     timestamps_enabled=state.timestamps_enabled
                 )
             text = variant.text_content

         # Обновить состояние
         state.emoji_level = new_emoji
         await state_repo.update(state)

         # Обновить UI
         keyboard = create_transcription_keyboard(state, has_segments, settings)
         await query.edit_message_text(text, reply_markup=keyboard)
     ```

3. **Динамические кнопки смайлов** (2-3 часа)
   - [ ] В `src/bot/keyboards.py`:
     ```python
     # Ряд 4: Смайлы
     if settings.enable_emoji_option:
         if state.emoji_level > 0:
             # 3 кнопки: Меньше/Убрать | 😊 | Больше
             row = []

             # Кнопка уменьшения
             label = "Убрать" if state.emoji_level == 1 else "Меньше"
             row.append(InlineKeyboardButton(
                 label,
                 callback_data=encode_callback_data("emoji", state.usage_id, direction="decrease")
             ))

             # Индикатор
             emoji_indicator = ["😊", "😊😊"][state.emoji_level - 1]
             row.append(InlineKeyboardButton(emoji_indicator, callback_data="noop"))

             # Кнопка увеличения
             if state.emoji_level < 2:
                 row.append(InlineKeyboardButton(
                     "Больше",
                     callback_data=encode_callback_data("emoji", state.usage_id, direction="increase")
                 ))

             keyboard.append(row)
         else:
             # Одна кнопка
             keyboard.append([InlineKeyboardButton(
                 "😊 Смайлы",
                 callback_data=encode_callback_data("emoji", state.usage_id, direction="increase")
             )])
     ```

**Критерии успеха Фазы 5:**
- ✅ Кнопка "😊 Смайлы" появляется для всех режимов
- ✅ При нажатии появляются 1-2 смайла в тексте
- ✅ Повторное нажатие "Больше" добавляет 3-5 смайлов
- ✅ "Убрать" возвращает к тексту без смайлов
- ✅ Смайлы применяются к текущему режиму и length_level
- ✅ Переключение режимов сохраняет emoji_level

**Тестирование:**
```bash
# 1. Включить флаг
# .env: ENABLE_EMOJI_OPTION=true

# 2. В режиме "Исходный текст" нажать "😊 Смайлы"
# Ожидание: 1-2 emoji добавлены, три кнопки [Убрать] [😊] [Больше]

# 3. Нажать "Больше"
# Ожидание: 3-5 emoji, две кнопки [Меньше] [😊😊]

# 4. Переключиться на "Структурировать"
# Ожидание: Структурированный текст С смайлами (emoji_level сохранился)

# 5. Убрать смайлы
# Ожидание: Одна кнопка "😊 Смайлы"
```

---

### **Фаза 6: Таймкоды** (2 дня)

**Цели:**
- Форматирование segments в читаемый вид
- Опция вкл/выкл таймкодов
- Работа только для длинных аудио (>5 мин)

**Шаги:**

1. **Форматирование таймкодов** (3-4 часа)
   - [ ] В `src/services/text_processor.py`:
     ```python
     def format_with_timestamps(
         self,
         segments: list[TranscriptionSegment],
         base_text: str,
         mode: str
     ) -> str:
         """
         Добавить таймкоды в текст.

         Формат:
         [00:15] Текст первого сегмента...
         [01:23] Текст второго сегмента...
         """

         if mode == "summary":
             # Для резюме: только таймкод первого упоминания каждого пункта
             return self._format_timestamps_summary(segments, base_text)
         else:
             # Для исходного/структурированного: каждый сегмент
             lines = []
             for seg in segments:
                 timestamp = self._format_time(seg.start_time)
                 lines.append(f"[{timestamp}] {seg.text}")
             return "\n".join(lines)

     def _format_time(self, seconds: float) -> str:
         """Форматировать секунды в MM:SS или HH:MM:SS."""
         hours = int(seconds // 3600)
         minutes = int((seconds % 3600) // 60)
         secs = int(seconds % 60)

         if hours > 0:
             return f"{hours:02d}:{minutes:02d}:{secs:02d}"
         else:
             return f"{minutes:02d}:{secs:02d}"

     def _format_timestamps_summary(self, segments, summary_text):
         """
         Для резюме: попытаться сопоставить буллеты с сегментами.
         Это эвристика, может быть неточной.
         """
         # Упрощённая версия: добавить таймкод первого сегмента перед резюме
         first_timestamp = self._format_time(segments[0].start_time)
         return f"[{first_timestamp}] {summary_text}"
     ```

2. **Callback handler** (2-3 часа)
   - [ ] В `src/bot/callbacks.py`:
     ```python
     async def handle_timestamps_toggle(self, update: Update, context):
         query = update.callback_query
         data = decode_callback_data(query.data)

         usage_id = data['usage_id']
         state = await state_repo.get_by_usage_id(usage_id)

         # Проверка: есть ли segments?
         segments = await segment_repo.get_by_usage_id(usage_id)
         if not segments:
             await query.answer("Таймкоды недоступны для этого аудио", show_alert=True)
             return

         new_timestamps = not state.timestamps_enabled

         # Получить базовый текст (без таймкодов)
         base_variant = await variant_repo.get_variant(
             usage_id, state.active_mode, state.length_level, state.emoji_level, timestamps_enabled=False
         )

         if new_timestamps:
             # Добавить таймкоды
             variant = await variant_repo.get_variant(
                 usage_id, state.active_mode, state.length_level, state.emoji_level, timestamps_enabled=True
             )

             if not variant:
                 # Генерация с таймкодами
                 text = text_processor.format_with_timestamps(
                     segments, base_variant.text_content, state.active_mode
                 )
                 variant = await variant_repo.save_variant(
                     usage_id, state.active_mode, text,
                     length_level=state.length_level,
                     emoji_level=state.emoji_level,
                     timestamps_enabled=True,
                     generated_by="formatting"
                 )
             text = variant.text_content
         else:
             # Убрать таймкоды
             text = base_variant.text_content

         # Обновить состояние
         state.timestamps_enabled = new_timestamps
         await state_repo.update(state)

         # Обновить UI
         keyboard = create_transcription_keyboard(state, has_segments=len(segments) > 0, settings)
         await query.edit_message_text(text, reply_markup=keyboard)
     ```

3. **Кнопка таймкодов** (1-2 часа)
   - [ ] В `src/bot/keyboards.py`:
     ```python
     # Ряд 5: Таймкоды (только если есть segments)
     if settings.enable_timestamps_option and has_segments:
         label = "Убрать таймкоды" if state.timestamps_enabled else "⏱ Таймкоды"
         keyboard.append([InlineKeyboardButton(
             label,
             callback_data=encode_callback_data("timestamps", state.usage_id)
         )])
     ```

4. **Сохранение segments при транскрипции** (1-2 часа)
   - [ ] Убедиться что в Фазе 1 корректно сохраняются segments для аудио >5 мин
   - [ ] Проверить что `has_segments` корректно передаётся в `create_transcription_keyboard`

**Критерии успеха Фазы 6:**
- ✅ Кнопка "⏱ Таймкоды" показывается только если есть segments
- ✅ При нажатии добавляются таймкоды в формате [MM:SS]
- ✅ Таймкоды корректно форматируются для всех режимов
- ✅ "Убрать таймкоды" возвращает к тексту без них
- ✅ Segments сохраняются только для аудио >5 мин

**Тестирование:**
```bash
# 1. Короткое аудио (<5 мин)
# Ожидание: Кнопка "⏱ Таймкоды" НЕ показывается

# 2. Длинное аудио (>5 мин)
# Ожидание: Кнопка показывается

# 3. Нажать "⏱ Таймкоды"
# Ожидание: Текст с [MM:SS] перед каждым сегментом

# 4. Переключиться на "О чем текст?"
# Ожидание: Таймкод в начале резюме

# 5. "Убрать таймкоды"
# Ожидание: Текст без таймкодов

# 6. Проверка БД
sqlite3 data/bot.db "SELECT COUNT(*) FROM transcription_segments WHERE usage_id=X;"
```

---

### **Фаза 7: Работа с файлами** (1-2 дня)

**Цели:**
- Гибридный подход: текст <4096 в сообщении, >4096 в файле
- Обновление файлов при изменении вариантов
- Корректная работа inline кнопок с файлами

**Шаги:**

1. **Определение порога** (0.5 часа)
   - [ ] В `src/config.py`:
     ```python
     file_threshold_chars: int = Field(default=4096, description="Текст длиннее отправляется файлом")
     ```

2. **Отправка файлов** (3-4 часа)
   - [ ] В `src/bot/handlers.py` после транскрипции:
     ```python
     async def send_transcription_result(
         self,
         chat_id: int,
         user_message_id: int,
         text: str,
         keyboard: InlineKeyboardMarkup,
         usage_id: int
     ) -> tuple[int, Optional[int]]:
         """
         Отправить результат транскрипции.

         Returns:
             (message_id, file_message_id)
         """

         if len(text) <= settings.file_threshold_chars:
             # Короткий текст - в сообщение
             msg = await context.bot.send_message(
                 chat_id=chat_id,
                 text=text,
                 reply_to_message_id=user_message_id,
                 reply_markup=keyboard
             )
             return (msg.message_id, None)
         else:
             # Длинный текст - в файл
             # Сообщение 1: Информация + кнопки
             msg1 = await context.bot.send_message(
                 chat_id=chat_id,
                 text="📝 Транскрипция готова! Файл ниже ↓",
                 reply_to_message_id=user_message_id,
                 reply_markup=keyboard
             )

             # Сообщение 2: Файл
             file_obj = io.BytesIO(text.encode('utf-8'))
             file_obj.name = f"transcription_{usage_id}.txt"

             msg2 = await context.bot.send_document(
                 chat_id=chat_id,
                 document=file_obj,
                 filename=file_obj.name,
                 caption=f"📄 Исходный текст ({len(text)} символов)"
             )

             return (msg1.message_id, msg2.message_id)
     ```

3. **Обновление файлов в callbacks** (4-5 часов)
   - [ ] В `src/bot/callbacks.py`:
     ```python
     async def update_transcription_display(
         self,
         query: CallbackQuery,
         state: TranscriptionState,
         new_text: str,
         keyboard: InlineKeyboardMarkup
     ):
         """Обновить отображение (текст или файл)."""

         if not state.is_file_message:
             # Простой случай: редактировать текст
             await query.edit_message_text(new_text, reply_markup=keyboard)
         else:
             # Сложный случай: работа с файлами
             chat_id = query.message.chat_id

             # 1. Обновить сообщение с кнопками (режим изменился)
             mode_label = {
                 "original": "Исходный текст",
                 "structured": "Структурированный",
                 "summary": "Резюме"
             }[state.active_mode]

             await query.edit_message_text(
                 f"📝 Транскрипция готова! Файл ниже ↓\n\n"
                 f"Режим: {mode_label}",
                 reply_markup=keyboard
             )

             # 2. Удалить старый файл
             if state.file_message_id:
                 try:
                     await context.bot.delete_message(chat_id, state.file_message_id)
                 except Exception as e:
                     logger.warning(f"Could not delete old file: {e}")

             # 3. Отправить новый файл
             file_obj = io.BytesIO(new_text.encode('utf-8'))
             file_obj.name = f"transcription_{state.usage_id}_{state.active_mode}.txt"

             new_file_msg = await context.bot.send_document(
                 chat_id=chat_id,
                 document=file_obj,
                 filename=file_obj.name,
                 caption=f"📄 {mode_label} ({len(new_text)} символов)"
             )

             # 4. Обновить state с новым file_message_id
             state.file_message_id = new_file_msg.message_id
             await state_repo.update(state)
     ```

4. **Сохранение is_file_message в state** (1 час)
   - [ ] В `src/bot/handlers.py` после отправки результата:
     ```python
     # Создать state
     message_id, file_message_id = await send_transcription_result(...)

     state = await state_repo.create(
         usage_id=usage.id,
         message_id=message_id,
         chat_id=chat_id,
         is_file_message=(file_message_id is not None),
         file_message_id=file_message_id
     )
     ```

**Критерии успеха Фазы 7:**
- ✅ Текст ≤4096 символов отправляется в сообщении
- ✅ Текст >4096 отправляется как файл .txt
- ✅ Inline кнопки работают с файлами
- ✅ При изменении варианта файл обновляется (удаляется старый, отправляется новый)
- ✅ Caption файла показывает режим и длину

**Тестирование:**
```bash
# 1. Короткая транскрипция (~1000 символов)
# Ожидание: Текст в сообщении с кнопками

# 2. Длинная транскрипция (>4096 символов)
# Ожидание: Два сообщения - информация+кнопки, затем файл

# 3. Переключить режим (файл)
# Ожидание: Старый файл удалён, новый отправлен, кнопки обновлены

# 4. Добавить смайлы (файл)
# Ожидание: Файл обновлён с эмодзи
```

---

### **Фаза 8: Повторная транскрипция** (2-3 дня)

**Цели:**
- Сохранение оригинального аудио файла
- Кнопка "⚡ Могу лучше" с двумя вариантами
- Новое сообщение с результатом более качественной транскрипции

**Шаги:**

1. **Сохранение оригинального файла** (3-4 часа)
   - [ ] Добавить в `Usage` модель:
     ```python
     # В src/storage/models.py
     class Usage(Base):
         # ... existing fields ...

         # Original file path for retranscription
         original_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
     ```
   - [ ] Создать миграцию для добавления поля
   - [ ] В `src/bot/handlers.py`:
     ```python
     # После скачивания файла:
     # Вместо временного пути, сохранить в постоянное хранилище

     persistent_dir = Path(settings.persistent_audio_dir)  # NEW config
     persistent_dir.mkdir(exist_ok=True)

     permanent_path = persistent_dir / f"{usage.id}_{file_id}.ogg"
     shutil.copy(temp_audio_file, permanent_path)

     # Сохранить путь в Usage
     usage.original_file_path = str(permanent_path)
     await usage_repo.update(usage)
     ```

2. **Конфигурация хранения** (1 час)
   - [ ] В `src/config.py`:
     ```python
     # File storage
     persistent_audio_dir: str = Field(
         default="./data/audio_files",
         description="Directory for storing audio files for retranscription"
     )
     persistent_audio_ttl_days: int = Field(
         default=7,
         description="How long to keep audio files"
     )

     # Retranscription options
     retranscribe_quality_model: str = Field(default="medium")  # Уже используем medium
     retranscribe_paid_provider: str = Field(default="openai")
     retranscribe_paid_cost_per_minute: float = Field(default=1.0)  # рублей
     ```

3. **Кнопка "Могу лучше"** (2 часа)
   - [ ] В `src/bot/keyboards.py`:
     ```python
     # Ряд 6: Могу лучше (только если enable_retranscribe)
     if settings.enable_retranscribe:
         keyboard.append([InlineKeyboardButton(
             "⚡ Могу лучше",
             callback_data=encode_callback_data("retranscribe_menu", state.usage_id)
         )])
     ```

4. **Подменю выбора метода** (3-4 часа)
   - [ ] В `src/bot/callbacks.py`:
     ```python
     async def handle_retranscribe_menu(self, update: Update, context):
         """Показать меню выбора метода ретранскрипции."""
         query = update.callback_query
         data = decode_callback_data(query.data)

         usage_id = data['usage_id']
         usage = await usage_repo.get_by_id(usage_id)

         # Проверка: есть ли файл?
         if not usage.original_file_path or not Path(usage.original_file_path).exists():
             await query.answer("Файл недоступен для повторной обработки", show_alert=True)
             return

         # Расчёт параметров
         duration_min = usage.voice_duration_seconds / 60
         quality_time = duration_min * 0.6  # RTF 0.6x для medium
         paid_cost = duration_min * settings.retranscribe_paid_cost_per_minute

         # Клавиатура выбора
         keyboard = InlineKeyboardMarkup([
             [InlineKeyboardButton(
                 f"Дольше (~{int(quality_time)}с)",
                 callback_data=encode_callback_data("retranscribe", usage_id, method="quality")
             )],
             [InlineKeyboardButton(
                 f"Быстро, но платно (~{paid_cost:.1f}₽)",
                 callback_data=encode_callback_data("retranscribe", usage_id, method="paid")
             )],
             [InlineKeyboardButton(
                 "❌ Отмена",
                 callback_data="noop"
             )]
         ])

         await query.edit_message_reply_markup(reply_markup=keyboard)

     async def handle_retranscribe(self, update: Update, context):
         """Запустить повторную транскрипцию."""
         query = update.callback_query
         data = decode_callback_data(query.data)

         usage_id = data['usage_id']
         method = data['method']  # "quality" or "paid"

         usage = await usage_repo.get_by_id(usage_id)

         # Отправить "Обрабатываю..." в новое сообщение
         status_msg = await context.bot.send_message(
             chat_id=query.message.chat_id,
             text="🔄 Запускаю повторную транскрипцию...",
             reply_to_message_id=query.message.message_id
         )

         # Транскрипция
         if method == "quality":
             # Использовать medium модель (уже дефолт)
             result = await transcription_router.transcribe(
                 Path(usage.original_file_path),
                 context=TranscriptionContext(...)
             )
         else:  # paid
             # Использовать OpenAI API
             # TODO: Интеграция с OpenAI Whisper API
             # Пока заглушка
             await status_msg.edit_text("💰 Платный метод пока в разработке")
             return

         # Создать новый Usage record
         new_usage = await usage_repo.create(
             user_id=usage.user_id,
             voice_file_id=usage.voice_file_id + "_retranscribed",
             voice_duration_seconds=usage.voice_duration_seconds,
             model_size=result.model_name,
             processing_time_seconds=result.processing_time,
             transcription_length=len(result.text),
             original_file_path=usage.original_file_path  # Переиспользовать файл
         )

         # Сохранить новый оригинальный вариант
         await variant_repo.save_variant(
             new_usage.id, "original", result.text, generated_by="transcription"
         )

         # Создать state и отправить результат как новое сообщение
         keyboard = create_transcription_keyboard(new_state, ...)

         await status_msg.delete()

         # Отправить результат
         message_id, file_message_id = await send_transcription_result(
             chat_id=query.message.chat_id,
             user_message_id=query.message.message_id,
             text=result.text,
             keyboard=keyboard,
             usage_id=new_usage.id
         )

         # Создать новый state
         await state_repo.create(
             usage_id=new_usage.id,
             message_id=message_id,
             chat_id=query.message.chat_id,
             is_file_message=(file_message_id is not None),
             file_message_id=file_message_id
         )

         # Вернуть оригинальную клавиатуру на первое сообщение
         original_state = await state_repo.get_by_usage_id(usage_id)
         original_keyboard = create_transcription_keyboard(original_state, ...)
         await query.edit_message_reply_markup(reply_markup=original_keyboard)
     ```

5. **Cleanup старых файлов** (2 часа)
   - [ ] Создать фоновую задачу для удаления файлов старше TTL:
     ```python
     # В src/storage/repositories.py
     class UsageRepository:
         async def cleanup_old_audio_files(self, ttl_days: int) -> int:
             """Удалить аудио файлы старше TTL."""
             cutoff_date = datetime.utcnow() - timedelta(days=ttl_days)

             old_usages = await self.session.execute(
                 select(Usage).where(
                     Usage.created_at < cutoff_date,
                     Usage.original_file_path.isnot(None)
                 )
             )

             count = 0
             for usage in old_usages.scalars():
                 if usage.original_file_path:
                     try:
                         Path(usage.original_file_path).unlink(missing_ok=True)
                         usage.original_file_path = None
                         count += 1
                     except Exception as e:
                         logger.error(f"Failed to delete file {usage.original_file_path}: {e}")

             await self.session.commit()
             return count
     ```
   - [ ] Запускать cleanup периодически (например, раз в день через asyncio task)

**Критерии успеха Фазы 8:**
- ✅ Аудио файлы сохраняются в `./data/audio_files/`
- ✅ Кнопка "⚡ Могу лучше" показывается
- ✅ При нажатии появляется подменю с двумя вариантами
- ✅ "Дольше" запускает транскрипцию с medium моделью в новом сообщении
- ✅ Результат появляется как отдельное сообщение со своими кнопками
- ✅ Старые файлы удаляются через TTL дней

**Тестирование:**
```bash
# 1. Отправить голосовое сообщение
# Проверить: файл сохранён в ./data/audio_files/

# 2. Нажать "⚡ Могу лучше"
# Ожидание: Подменю с расчётами времени и стоимости

# 3. Выбрать "Дольше"
# Ожидание: Новое сообщение с результатом, свои кнопки

# 4. Проверить через 8 дней
# Ожидание: Старые файлы удалены
```

---

## Критерии успеха

### Общие критерии успешной реализации

**Технические:**
- ✅ Все миграции БД применяются без ошибок
- ✅ Все существующие тесты (97 unit tests) проходят
- ✅ Код проходит проверки: mypy, ruff, black
- ✅ Feature flags корректно включают/выключают функциональность
- ✅ Нет регрессий в текущем функционале

**Функциональные:**
- ✅ Все 6 рядов кнопок работают согласно требованиям
- ✅ Динамические кнопки корректно меняются
- ✅ Кэширование вариантов работает (повторные запросы мгновенны)
- ✅ Работа с длинными текстами через файлы
- ✅ Таймкоды показываются для длинных аудио

**UX критерии:**
- ✅ Время ответа на callback <2 секунд (если есть в кэше)
- ✅ LLM генерация укладывается в 5-10 секунд
- ✅ Inline кнопки интуитивно понятны
- ✅ Индикаторы (смайлики-статусы) не реагируют на клики
- ✅ При границах (shorter/longer) корректные сообщения

**Производительность:**
- ✅ БД запросы оптимизированы (индексы используются)
- ✅ Cleanup старых вариантов работает
- ✅ Не более 10 вариантов на транскрипцию в кэше

---

## Риски и митигации

### Высокий риск

**Риск 1: Качество LLM промптов**
- **Описание:** Промпты могут генерировать некачественные результаты
- **Митигация:**
  - Тестировать промпты на каждой фазе с реальными данными
  - Итеративный тюнинг
  - Возможность отключить через feature flags

**Риск 2: Стоимость LLM**
- **Описание:** Много вариантов = много запросов к LLM
- **Митигация:**
  - Агрессивное кэширование
  - Генерация только по требованию
  - Лимиты на количество вариантов
  - Мониторинг затрат

### Средний риск

**Риск 3: Callback data limit (64 байта)**
- **Описание:** Может не хватить для кодирования всех параметров
- **Митигация:**
  - Компактное кодирование (сокращения, base64)
  - Хранить usage_id, остальное брать из state в БД

**Риск 4: Сложность работы с файлами**
- **Описание:** Удаление/отправка файлов может быть нестабильной
- **Митигация:**
  - Обработка ошибок Telegram API
  - Retry логика
  - Логирование всех операций с файлами

### Низкий риск

**Риск 5: Миграции БД**
- **Описание:** Проблемы при применении миграций
- **Митигация:**
  - Тестирование локально
  - Тестирование в CI (уже есть)
  - Rollback процедуры

---

## Следующие шаги

**После утверждения плана:**

1. **Создать feature branch:**
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/interactive-transcription
   ```

2. **Начать с Фазы 1:**
   - Следовать детальным шагам из плана
   - Тестировать каждый шаг
   - Коммитить прогресс регулярно

3. **После завершения каждой фазы:**
   - Запускать полный набор тестов
   - Создавать PR для ревью (или мержить напрямую если solo)
   - Обновлять Memory Bank (activeContext.md, progress.md)
   - Переходить к следующей фазе

4. **Финальная интеграция (после Фазы 8):**
   - Полное end-to-end тестирование
   - Обновление документации (.env.example, README)
   - Production deployment

---

## Приложения

### Примеры промптов (детально)

**Структурирование (default):**
```
Твоя задача: структурировать текст голосовой транскрипции.

Исходный текст (сырая транскрипция):
{text}

Требования:
1. Исправить грамматические ошибки и опечатки
2. Добавить правильную пунктуацию (точки, запятые, вопросительные/восклицательные знаки)
3. Разбить на абзацы по смыслу (каждая новая мысль - новый абзац)
4. Выделить списки буллетами если уместно (символ •)
5. Сохранить весь смысл и все детали из оригинала
6. НЕ добавлять ничего от себя, только исправления
7. НЕ сокращать текст (это не резюме, а структурирование)
8. Сохранить стиль речи (неформальный/формальный)

Верни ТОЛЬКО исправленный текст, без пояснений и комментариев.
```

**Резюме (default):**
```
Твоя задача: создать краткое резюме текста, отвечая на вопрос "О чем этот текст?"

Исходный текст:
{text}

Требования:
1. Выделить главную тему/идею одним предложением
2. Перечислить ключевые моменты (3-5 пунктов буллетами)
3. Объём резюме: примерно 25-30% от оригинала
4. Структура:
   - Первая строка: "О чем текст: <краткое описание темы>"
   - Пустая строка
   - "Ключевые моменты:"
   - Буллеты (•) с основными пунктами
5. Сохранить важные детали и факты
6. НЕ выдумывать информацию

Формат ответа:
О чем текст: <краткое описание>

Ключевые моменты:
• <пункт 1>
• <пункт 2>
• <пункт 3>

Верни ТОЛЬКО резюме в таком формате.
```

### Структура callback_data

**Формат:** `action:usage_id[:param1=val1,param2=val2]`

**Примеры:**
- `mode:123:mode=original` - переключение на исходный текст
- `mode:123:mode=structured` - переключение на структурированный
- `length:123:direction=shorter` - сделать короче
- `emoji:123:direction=increase` - добавить смайлов
- `timestamps:123` - переключить таймкоды
- `retranscribe_menu:123` - показать меню ретранскрипции
- `retranscribe:123:method=quality` - запустить качественную транскрипцию

**Кодирование/декодирование:**
```python
def encode_callback_data(action: str, usage_id: int, **params) -> str:
    parts = [action, str(usage_id)]
    if params:
        param_str = ",".join(f"{k}={v}" for k, v in params.items())
        parts.append(param_str)

    result = ":".join(parts)

    # Проверка лимита
    if len(result.encode('utf-8')) > 64:
        raise ValueError(f"Callback data too long: {len(result)} bytes")

    return result

def decode_callback_data(data: str) -> dict:
    parts = data.split(":")
    result = {
        "action": parts[0],
        "usage_id": int(parts[1])
    }

    if len(parts) > 2:
        for param in parts[2].split(","):
            key, value = param.split("=")
            result[key] = value

    return result
```

---

**Конец плана. Готов к реализации после утверждения.**
