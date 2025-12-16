# Structure Strategy Implementation Plan

**Дата:** 2025-12-15
**Статус:** Планирование
**Ветка:** `feature/structure-strategy`

## Обзор

Реализация новой стратегии транскрипции `StructureStrategy`, которая автоматически структурирует текст после транскрибации.

### Поведение

1. Пользователь отправляет аудио
2. Аудио транскрибируется одной моделью (аналогично single mode)
3. **Сохраняется вариант с mode='original'** в БД
4. **Для длинных аудио (≥20 сек):**
   - Показывается черновик: `✅ Черновик готов:\n\n{draft_text}\n\n🔄 Улучшаю текст...`
   - Запускается структурирование (LLM)
   - Показывается структурированный результат
5. **Для коротких аудио (<20 сек):**
   - Сразу структурируется без показа черновика
   - Показывается только структурированный результат
6. **Сохраняется вариант с mode='structured'** в БД
7. **Fallback:** Если структурирование не удалось → показать оригинал

### Параметры стратегии

- `provider_name` - провайдер транскрипции (faster-whisper, openai)
- `model` - модель для транскрипции (medium, large-v3, whisper-1)
- `draft_threshold_seconds` - порог для показа черновика (по умолчанию: 20)
- `emoji_level` - уровень эмодзи для структурирования (0-3, по умолчанию: 1)

---

## Технические требования

### Новые переменные окружения

```bash
# .env
TRANSCRIPTION_STRATEGY=structure  # single, fallback, benchmark, hybrid, structure

# Настройки для StructureStrategy
STRUCTURE_PROVIDER=faster-whisper
STRUCTURE_MODEL=medium
STRUCTURE_DRAFT_THRESHOLD=20  # секунды, порог для показа черновика
STRUCTURE_EMOJI_LEVEL=1  # 0-3, уровень эмодзи в структурированном тексте
```

### Изменения в БД

**НЕТ изменений в схеме БД** - используем существующие таблицы:
- `transcription_variants` с `mode='original'` и `mode='structured'`
- Все необходимые поля уже есть

---

## Детальный план реализации

### Этап 1: Создание StructureStrategy

**Файл:** `src/transcription/routing/strategies.py`
**Изменения:** Добавить новый класс (~100 строк)

```python
class StructureStrategy(RoutingStrategy):
    """
    Стратегия с автоматическим структурированием текста.

    Процесс:
    1. Транскрибирует аудио одной моделью
    2. Для длинных аудио (≥draft_threshold): показывает черновик → структурирует
    3. Для коротких аудио (<draft_threshold): сразу структурирует
    4. При ошибке структурирования → показывает оригинал

    Attributes:
        provider_name: Провайдер транскрипции (faster-whisper, openai)
        model: Модель для транскрипции
        draft_threshold: Порог в секундах для показа черновика
        emoji_level: Уровень эмодзи для структурирования (0-3)
    """

    def __init__(
        self,
        provider_name: str,
        model: str,
        draft_threshold_seconds: int = 20,
        emoji_level: int = 1,
    ):
        """
        Initialize structure strategy.

        Args:
            provider_name: Provider to use (faster-whisper, openai)
            model: Model name (medium, large-v3, whisper-1)
            draft_threshold_seconds: Duration threshold for showing draft (default: 20)
            emoji_level: Emoji level for structuring (0-3, default: 1)
        """
        self.provider_name = provider_name
        self.model = model
        self.draft_threshold = draft_threshold_seconds
        self.emoji_level = emoji_level

        logger.info(
            f"StructureStrategy initialized: provider={provider_name}, "
            f"model={model}, draft_threshold={draft_threshold_seconds}s, "
            f"emoji_level={emoji_level}"
        )

    async def select_provider(
        self,
        context: TranscriptionContext,
        providers: dict[str, TranscriptionProvider],
    ) -> str:
        """
        Always return configured provider.

        Args:
            context: Transcription context
            providers: Available providers

        Returns:
            Provider name to use

        Raises:
            ValueError: If provider not available
        """
        if self.provider_name not in providers:
            raise ValueError(
                f"Provider '{self.provider_name}' not available. "
                f"Available: {list(providers.keys())}"
            )
        return self.provider_name

    def get_model_name(self) -> str:
        """Get model name for transcription."""
        return self.model

    def requires_structuring(self) -> bool:
        """
        Check if strategy requires automatic structuring.

        Returns:
            True (always structure in this strategy)
        """
        return True

    def should_show_draft(self, duration_seconds: float) -> bool:
        """
        Check if should show draft before structuring.

        Args:
            duration_seconds: Audio duration in seconds

        Returns:
            True if duration >= draft_threshold
        """
        return duration_seconds >= self.draft_threshold

    def get_emoji_level(self) -> int:
        """Get emoji level for structuring."""
        return self.emoji_level
```

**Тестирование:**
```python
# tests/unit/test_structure_strategy.py
def test_structure_strategy_init():
    strategy = StructureStrategy("faster-whisper", "medium", 20, 1)
    assert strategy.provider_name == "faster-whisper"
    assert strategy.model == "medium"
    assert strategy.draft_threshold == 20
    assert strategy.emoji_level == 1

def test_structure_strategy_select_provider():
    strategy = StructureStrategy("faster-whisper", "medium")
    providers = {"faster-whisper": Mock(), "openai": Mock()}
    assert await strategy.select_provider(context, providers) == "faster-whisper"

def test_structure_strategy_should_show_draft():
    strategy = StructureStrategy("faster-whisper", "medium", draft_threshold_seconds=20)
    assert strategy.should_show_draft(25) == True  # Long audio
    assert strategy.should_show_draft(15) == False  # Short audio
```

---

### Этап 2: Обновление конфигурации

**Файл:** `src/config.py`
**Изменения:** Добавить настройки StructureStrategy (~20 строк)

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # ========================================
    # Structure Strategy Settings
    # ========================================
    structure_provider: str = Field(
        default="faster-whisper",
        description="Provider for structure strategy (faster-whisper, openai)"
    )
    structure_model: str = Field(
        default="medium",
        description="Model for structure strategy transcription"
    )
    structure_draft_threshold: int = Field(
        default=20,
        ge=0,
        le=3600,
        description="Duration threshold (seconds) for showing draft before structuring"
    )
    structure_emoji_level: int = Field(
        default=1,
        ge=0,
        le=3,
        description="Emoji level for structured text (0=none, 1=few, 2=moderate, 3=many)"
    )
```

**Файл:** `.env.example`
**Изменения:** Документировать новые переменные

```bash
# ===========================================
# TRANSCRIPTION STRATEGY
# ===========================================
# Available strategies: single, fallback, benchmark, hybrid, structure
# - single: Single provider/model
# - fallback: Primary + fallback provider
# - benchmark: Test all models (expensive!)
# - hybrid: Smart routing (short=quality, long=draft+LLM)
# - structure: Auto-structure after transcription (NEW)
TRANSCRIPTION_STRATEGY=single

# ... existing strategy configs ...

# -------------------------------------------
# Structure Strategy (TRANSCRIPTION_STRATEGY=structure)
# -------------------------------------------
# Automatically structures transcription with LLM
# - Short audio (<threshold): Transcribe → Structure → Show result
# - Long audio (≥threshold): Transcribe → Show draft → Structure → Show result

STRUCTURE_PROVIDER=faster-whisper
STRUCTURE_MODEL=medium
STRUCTURE_DRAFT_THRESHOLD=20  # Seconds - show draft for audio ≥ this duration
STRUCTURE_EMOJI_LEVEL=1  # 0=no emojis, 1=few, 2=moderate, 3=many
```

**Файл:** `.env.example.short`
**Изменения:** Добавить короткий пример

```bash
# Structure strategy example (auto-structure transcriptions)
# TRANSCRIPTION_STRATEGY=structure
# STRUCTURE_PROVIDER=faster-whisper
# STRUCTURE_MODEL=medium
# STRUCTURE_DRAFT_THRESHOLD=20
# STRUCTURE_EMOJI_LEVEL=1
```

---

### Этап 3: Фабрика стратегий

**Файл:** `src/transcription/factory.py`
**Изменения:** Добавить создание StructureStrategy (~30 строк)

Найти функцию `create_strategy()` и добавить:

```python
def create_strategy(settings: Settings) -> RoutingStrategy:
    """Create routing strategy from settings."""
    strategy_type = settings.transcription_strategy.lower()

    # ... existing strategies ...

    elif strategy_type == "structure":
        # Validate LLM is enabled
        if not settings.llm_enabled:
            raise ValueError(
                "StructureStrategy requires LLM to be enabled. "
                "Set LLM_ENABLED=true in .env"
            )

        logger.info(
            f"Creating StructureStrategy: provider={settings.structure_provider}, "
            f"model={settings.structure_model}, "
            f"draft_threshold={settings.structure_draft_threshold}s, "
            f"emoji_level={settings.structure_emoji_level}"
        )

        return StructureStrategy(
            provider_name=settings.structure_provider,
            model=settings.structure_model,
            draft_threshold_seconds=settings.structure_draft_threshold,
            emoji_level=settings.structure_emoji_level,
        )

    else:
        raise ValueError(
            f"Unknown strategy: {strategy_type}. "
            f"Available: single, fallback, benchmark, hybrid, structure"
        )
```

---

### Этап 4: Модификация обработчика транскрипции

**Файл:** `src/bot/handlers.py`
**Метод:** `_process_transcription()`
**Изменения:** Добавить обработку StructureStrategy (~100 строк)

**Место вставки:** После блока обработки HybridStrategy (около строки 1320-1450)

```python
async def _process_transcription(self, request: TranscriptionRequest) -> TranscriptionResult:
    """Process transcription request (called by queue worker)."""

    # ... existing code: preprocessing, transcription ...

    # === TRANSCRIPTION: Get draft or final transcription ===
    result = await self.transcription_router.transcribe(
        processed_path,
        request.context,
    )

    # Stop progress updates
    await progress.stop()

    # === CHECK STRATEGY TYPE ===

    # HYBRID STRATEGY: Check if LLM refinement needed
    needs_refinement = False
    if isinstance(self.transcription_router.strategy, HybridStrategy):
        # ... existing hybrid logic ...

    # STRUCTURE STRATEGY: Check if structuring needed (NEW)
    needs_structuring = False
    show_draft = False
    emoji_level = 0

    if hasattr(self.transcription_router.strategy, 'requires_structuring'):
        strategy = self.transcription_router.strategy
        needs_structuring = strategy.requires_structuring()

        if needs_structuring:
            show_draft = strategy.should_show_draft(request.duration_seconds)
            emoji_level = strategy.get_emoji_level()
            logger.info(
                f"StructureStrategy: needs_structuring={needs_structuring}, "
                f"show_draft={show_draft}, emoji_level={emoji_level}"
            )

    final_text = result.text

    # === STRUCTURE STRATEGY FLOW ===
    if needs_structuring and self.text_processor:
        try:
            # Save ORIGINAL variant to DB
            async with get_session() as session:
                variant_repo = TranscriptionVariantRepository(session)
                await variant_repo.save_variant(
                    usage_id=request.usage_id,
                    mode="original",
                    length_level="default",
                    emoji_level=0,
                    timestamps_enabled=False,
                    text_content=result.text,
                    generated_by="whisper",
                    llm_model=None,
                    processing_time_seconds=result.processing_time,
                )
                logger.info(f"Saved original variant: usage_id={request.usage_id}")

            # STAGE 1: Show draft if needed (long audio)
            if show_draft:
                draft_text = result.text
                await self._send_draft_messages(request, draft_text)
                logger.info("Draft messages sent, starting structuring...")

            # STAGE 2: Structure with LLM
            structure_start = time.time()

            # Create structured text with emoji_level
            structured_text = await self.text_processor.create_structured(
                original_text=result.text,
                length_level="default",
                emoji_level=emoji_level,
            )

            structure_time = time.time() - structure_start
            logger.info(f"Structuring completed in {structure_time:.2f}s")

            final_text = structured_text

            # Save STRUCTURED variant to DB
            async with get_session() as session:
                variant_repo = TranscriptionVariantRepository(session)
                await variant_repo.save_variant(
                    usage_id=request.usage_id,
                    mode="structured",
                    length_level="default",
                    emoji_level=emoji_level,
                    timestamps_enabled=False,
                    text_content=structured_text,
                    generated_by="llm",
                    llm_model=settings.llm_model,
                    processing_time_seconds=structure_time,
                )
                logger.info(f"Saved structured variant: usage_id={request.usage_id}")

            # STAGE 3: Delete draft messages if any
            if show_draft:
                for msg in request.draft_messages:
                    try:
                        await msg.delete()
                        logger.debug(f"Deleted draft message: request_id={request.id}")
                    except Exception as e:
                        logger.warning(f"Failed to delete draft message: {e}")
            else:
                # Short audio: delete status message
                try:
                    await request.status_message.delete()
                except Exception as e:
                    logger.warning(f"Failed to delete status message: {e}")

            # STAGE 4: Send structured result
            # Create keyboard
            keyboard = await self._create_interactive_state_and_keyboard(
                usage_id=request.usage_id,
                message_id=0,  # Will be updated after sending
                chat_id=request.user_message.chat_id,
                result=result,
                final_text=structured_text,
                active_mode="structured",  # NEW: Set initial mode to structured
                emoji_level=emoji_level,  # NEW: Set emoji level
            )

            # Send structured text (as text or file based on length)
            main_msg, file_msg = await self._send_transcription_result(
                request=request,
                text=structured_text,
                keyboard=keyboard,
                usage_id=request.usage_id,
                prefix="",
            )

            # Update state with correct message IDs
            if keyboard:
                async with get_session() as session:
                    state_repo = TranscriptionStateRepository(session)
                    state = await state_repo.get_by_usage_id(request.usage_id)
                    if state:
                        state.message_id = main_msg.message_id
                        state.is_file_message = file_msg is not None
                        state.file_message_id = file_msg.message_id if file_msg else None
                        await state_repo.update(state)
                        logger.debug(
                            f"Updated state: message_id={main_msg.message_id}, "
                            f"is_file={file_msg is not None}"
                        )

        except Exception as e:
            logger.error(f"Structuring failed: {e}", exc_info=True)

            # FALLBACK: Show original text
            logger.warning("Falling back to original text")
            final_text = result.text

            # Delete draft if any
            if show_draft:
                for msg in request.draft_messages:
                    try:
                        await msg.delete()
                    except Exception:
                        pass

            # Delete status message
            try:
                await request.status_message.delete()
            except Exception:
                pass

            # Send original with error notice
            keyboard = await self._create_interactive_state_and_keyboard(
                usage_id=request.usage_id,
                message_id=0,
                chat_id=request.user_message.chat_id,
                result=result,
                final_text=result.text,
            )

            main_msg, file_msg = await self._send_transcription_result(
                request=request,
                text=result.text + "\n\nℹ️ (структурирование недоступно)",
                keyboard=keyboard,
                usage_id=request.usage_id,
                prefix="",
            )

            # Update state
            if keyboard:
                async with get_session() as session:
                    state_repo = TranscriptionStateRepository(session)
                    state = await state_repo.get_by_usage_id(request.usage_id)
                    if state:
                        state.message_id = main_msg.message_id
                        state.is_file_message = file_msg is not None
                        state.file_message_id = file_msg.message_id if file_msg else None
                        await state_repo.update(state)

    elif needs_refinement and self.llm_service:
        # ... existing hybrid logic ...

    else:
        # ... existing direct result logic ...

    # ... rest of the method ...
```

**Важные изменения:**

1. **Сохранение оригинала:** Добавить сохранение варианта с `mode='original'` ПЕРЕД структурированием
2. **Сохранение структурированного:** Добавить сохранение варианта с `mode='structured'` ПОСЛЕ структурирования
3. **Обработка emoji_level:** Передать emoji_level в `create_structured()` и в состояние
4. **Fallback:** При ошибке структурирования показать оригинал с уведомлением

---

### Этап 5: Обновление TextProcessor

**Файл:** `src/services/text_processor.py`
**Метод:** `create_structured()`
**Изменения:** Добавить поддержку emoji_level (~30 строк)

Найти метод `create_structured()` и обновить сигнатуру:

```python
async def create_structured(
    self,
    original_text: str,
    length_level: str = "default",
    emoji_level: int = 0,  # NEW parameter
) -> str:
    """
    Structure raw transcription text.

    Args:
        original_text: Raw transcription text
        length_level: Length level (Phase 3 - not yet implemented)
        emoji_level: Emoji level (0=none, 1=few, 2=moderate, 3=many)

    Returns:
        Structured text with proper formatting
    """
    if length_level != "default":
        raise NotImplementedError(
            f"Length variations will be available in Phase 3. Got: {length_level}"
        )

    # Load prompt from file
    try:
        prompt_template = load_prompt("structured")
    except (FileNotFoundError, IOError) as e:
        logger.error(f"Failed to load structured prompt: {e}")
        # Fallback to inline prompt
        prompt_template = """..."""

    # Modify prompt based on emoji_level (NEW)
    if emoji_level == 0:
        # No emojis: modify prompt to exclude emoji instruction
        prompt_template = prompt_template.replace(
            "10. Добавь немного эмодзи в тему, но чтобы не перегружало. "
            "И не используй несколько эмодзи подряд.",
            "10. НЕ используй эмодзи."
        )
    elif emoji_level == 2:
        prompt_template = prompt_template.replace(
            "10. Добавь немного эмодзи в тему, но чтобы не перегружало.",
            "10. Добавь эмодзи в тему умеренно (1-2 на абзац)."
        )
    elif emoji_level == 3:
        prompt_template = prompt_template.replace(
            "10. Добавь немного эмодзи в тему, но чтобы не перегружало.",
            "10. Добавь эмодзи активно для выразительности."
        )
    # emoji_level == 1: use default prompt (few emojis)

    prompt = prompt_template.format(text=original_text)
    logger.info(
        f"Creating structured text ({len(original_text)} chars, emoji_level={emoji_level})..."
    )

    # ... rest of the method ...
```

**Альтернативный подход (рекомендуется):**
Вместо модификации промпта в коде, создать отдельные файлы промптов:
- `prompts/structured_no_emoji.md` (emoji_level=0)
- `prompts/structured.md` (emoji_level=1, существующий)
- `prompts/structured_moderate_emoji.md` (emoji_level=2)
- `prompts/structured_many_emoji.md` (emoji_level=3)

И загружать нужный:
```python
prompt_file = {
    0: "structured_no_emoji",
    1: "structured",
    2: "structured_moderate_emoji",
    3: "structured_many_emoji",
}.get(emoji_level, "structured")

prompt_template = load_prompt(prompt_file)
```

---

### Этап 6: Обновление _create_interactive_state_and_keyboard()

**Файл:** `src/bot/handlers.py`
**Метод:** `_create_interactive_state_and_keyboard()`
**Изменения:** Добавить параметры для начального состояния (~20 строк)

Найти метод и обновить сигнатуру:

```python
async def _create_interactive_state_and_keyboard(
    self,
    usage_id: int,
    message_id: int,
    chat_id: int,
    result: TranscriptionResult,
    final_text: str,
    active_mode: str = "original",  # NEW: Allow setting initial mode
    emoji_level: int = 0,  # NEW: Allow setting initial emoji level
) -> Optional[InlineKeyboardMarkup]:
    """
    Create interactive state and keyboard for transcription.

    Args:
        usage_id: Usage record ID
        message_id: Telegram message ID
        chat_id: Telegram chat ID
        result: Transcription result
        final_text: Final transcription text
        active_mode: Initial active mode (default: "original")
        emoji_level: Initial emoji level (default: 0)

    Returns:
        Inline keyboard markup or None
    """
    if not settings.interactive_mode_enabled:
        return None

    try:
        async with get_session() as session:
            # ... existing code ...

            # Create state with custom initial values
            state = await state_repo.create(
                usage_id=usage_id,
                message_id=message_id,
                chat_id=chat_id,
                active_mode=active_mode,  # Use parameter instead of hardcoded "original"
                length_level="default",
                emoji_level=emoji_level,  # Use parameter instead of hardcoded 0
                timestamps_enabled=False,
                is_file_message=False,
                file_message_id=None,
            )

            # ... rest of the method ...
```

**Обновить вызовы метода:**
- В блоке StructureStrategy: передать `active_mode="structured"` и `emoji_level=strategy.emoji_level`
- В остальных местах: оставить значения по умолчанию

---

### Этап 7: Обновление документации

**Файл:** `docs/development/architecture.md`
**Раздел:** Transcription Strategies
**Изменения:** Добавить описание StructureStrategy

```markdown
## Transcription Strategies

### Available Strategies

#### 5. StructureStrategy (NEW - Phase 9)

**Purpose:** Automatically structure transcription with LLM formatting

**Behavior:**
- Transcribes audio with single provider/model
- For short audio (<20 sec): Transcribe → Structure → Show result
- For long audio (≥20 sec): Transcribe → Show draft → Structure → Show result
- Saves both original and structured variants to database
- Fallback to original if structuring fails

**Configuration:**
```bash
TRANSCRIPTION_STRATEGY=structure
STRUCTURE_PROVIDER=faster-whisper
STRUCTURE_MODEL=medium
STRUCTURE_DRAFT_THRESHOLD=20  # seconds
STRUCTURE_EMOJI_LEVEL=1  # 0-3
```

**Use Cases:**
- Users who always want structured output
- Professional transcription with consistent formatting
- When raw Whisper output is too messy

**Pros:**
- ✅ Consistent formatting
- ✅ Better readability
- ✅ Preserves both original and structured versions
- ✅ Configurable emoji level

**Cons:**
- ⚠️ Requires LLM (costs)
- ⚠️ Slower than raw transcription
- ⚠️ Can fail (fallback to original)
```

**Файл:** `docs/getting-started/configuration.md`
Добавить примеры конфигурации StructureStrategy

**Файл:** `README.md`
Обновить список стратегий

---

## Критерии приемки

### Функциональные требования

- [x] **StructureStrategy создана** и работает как отдельная стратегия
- [x] **Короткие аудио (<20 сек):** Транскрибируются и сразу структурируются без черновика
- [x] **Длинные аудио (≥20 сек):** Показывается черновик → структурирование → финальный результат
- [x] **Сохранение вариантов:**
  - mode='original' сохраняется в БД
  - mode='structured' сохраняется в БД
- [x] **Настройки работают:**
  - STRUCTURE_DRAFT_THRESHOLD управляет порогом черновика
  - STRUCTURE_EMOJI_LEVEL управляет количеством эмодзи
- [x] **Fallback работает:** При ошибке структурирования показывается оригинал
- [x] **Интерактивность:** Кнопки "Исходный текст" и "Структурировать" работают

### Нефункциональные требования

- [x] **Логирование:** Все ключевые этапы логируются
- [x] **Обработка ошибок:** Graceful degradation при сбоях
- [x] **Производительность:** Не влияет на другие стратегии
- [x] **Совместимость:** Работает с существующими провайдерами

### Качество кода

- [x] **Тесты написаны:** Unit-тесты для StructureStrategy
- [x] **Документация обновлена:** README, architecture.md, configuration.md
- [x] **Код соответствует стилю:** Black, ruff проверки проходят
- [x] **Нет дублирования:** DRY принцип соблюден

---

## Тестирование

### Unit Tests

**Файл:** `tests/unit/test_structure_strategy.py` (NEW)

```python
"""Tests for StructureStrategy."""

import pytest
from unittest.mock import Mock, AsyncMock
from src.transcription.routing.strategies import StructureStrategy
from src.transcription.models import TranscriptionContext

@pytest.fixture
def strategy():
    return StructureStrategy(
        provider_name="faster-whisper",
        model="medium",
        draft_threshold_seconds=20,
        emoji_level=1,
    )

def test_init(strategy):
    """Test strategy initialization."""
    assert strategy.provider_name == "faster-whisper"
    assert strategy.model == "medium"
    assert strategy.draft_threshold == 20
    assert strategy.emoji_level == 1

@pytest.mark.asyncio
async def test_select_provider(strategy):
    """Test provider selection."""
    context = TranscriptionContext(user_id=1, duration_seconds=30)
    providers = {
        "faster-whisper": Mock(),
        "openai": Mock(),
    }

    result = await strategy.select_provider(context, providers)
    assert result == "faster-whisper"

@pytest.mark.asyncio
async def test_select_provider_not_available(strategy):
    """Test error when provider not available."""
    context = TranscriptionContext(user_id=1, duration_seconds=30)
    providers = {"openai": Mock()}

    with pytest.raises(ValueError, match="not available"):
        await strategy.select_provider(context, providers)

def test_requires_structuring(strategy):
    """Test requires_structuring always returns True."""
    assert strategy.requires_structuring() is True

def test_should_show_draft_long_audio(strategy):
    """Test should show draft for long audio."""
    assert strategy.should_show_draft(25) is True
    assert strategy.should_show_draft(20) is True  # Exactly at threshold

def test_should_show_draft_short_audio(strategy):
    """Test should not show draft for short audio."""
    assert strategy.should_show_draft(19) is False
    assert strategy.should_show_draft(5) is False

def test_get_emoji_level(strategy):
    """Test get_emoji_level returns configured level."""
    assert strategy.get_emoji_level() == 1

    strategy2 = StructureStrategy("faster-whisper", "medium", emoji_level=3)
    assert strategy2.get_emoji_level() == 3

def test_get_model_name(strategy):
    """Test get_model_name returns configured model."""
    assert strategy.get_model_name() == "medium"
```

### Integration Tests

**Файл:** `tests/integration/test_structure_strategy_flow.py` (NEW)

```python
"""Integration tests for StructureStrategy end-to-end flow."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

@pytest.mark.asyncio
async def test_structure_strategy_short_audio():
    """Test structure strategy with short audio (<20 sec)."""
    # Setup
    audio_path = Path("tests/fixtures/short_audio.ogg")  # 10 seconds

    # Mock dependencies
    with patch('src.bot.handlers.BotHandlers') as mock_handlers:
        # ... configure mocks ...

        # Execute
        result = await process_transcription(audio_path)

        # Verify
        # 1. No draft shown (short audio)
        assert len(result.draft_messages) == 0

        # 2. Original variant saved
        assert result.variants["original"] is not None

        # 3. Structured variant saved
        assert result.variants["structured"] is not None

        # 4. Final result is structured
        assert result.active_mode == "structured"

@pytest.mark.asyncio
async def test_structure_strategy_long_audio():
    """Test structure strategy with long audio (≥20 sec)."""
    # Setup
    audio_path = Path("tests/fixtures/long_audio.ogg")  # 60 seconds

    # Mock dependencies
    with patch('src.bot.handlers.BotHandlers') as mock_handlers:
        # ... configure mocks ...

        # Execute
        result = await process_transcription(audio_path)

        # Verify
        # 1. Draft shown (long audio)
        assert len(result.draft_messages) > 0
        assert "Черновик готов" in result.draft_messages[0].text

        # 2. Both variants saved
        assert result.variants["original"] is not None
        assert result.variants["structured"] is not None

@pytest.mark.asyncio
async def test_structure_strategy_fallback():
    """Test fallback to original when structuring fails."""
    # Setup
    audio_path = Path("tests/fixtures/short_audio.ogg")

    # Mock text_processor to raise error
    with patch('src.services.text_processor.TextProcessor.create_structured') as mock_struct:
        mock_struct.side_effect = Exception("LLM error")

        # Execute
        result = await process_transcription(audio_path)

        # Verify
        # 1. Original shown as fallback
        assert result.active_mode == "original"

        # 2. Error message shown
        assert "структурирование недоступно" in result.final_message
```

### Manual Testing Checklist

**Короткие аудио (<20 сек):**
- [ ] Отправить аудио 5 сек → сразу показывается структурированный текст
- [ ] Отправить аудио 15 сек → сразу показывается структурированный текст
- [ ] Проверить в БД: есть оба варианта (original и structured)

**Длинные аудио (≥20 сек):**
- [ ] Отправить аудио 30 сек → показывается черновик → затем структурированный текст
- [ ] Отправить аудио 60 сек → показывается черновик → затем структурированный текст
- [ ] Проверить, что черновик удаляется после структурирования

**Настройки:**
- [ ] Изменить STRUCTURE_DRAFT_THRESHOLD=30 → проверить, что порог изменился
- [ ] Изменить STRUCTURE_EMOJI_LEVEL=0 → нет эмодзи в тексте
- [ ] Изменить STRUCTURE_EMOJI_LEVEL=3 → много эмодзи в тексте

**Fallback:**
- [ ] Отключить LLM → проверить, что показывается оригинал с сообщением об ошибке
- [ ] Сымитировать ошибку LLM → fallback работает

**Интерактивность:**
- [ ] Нажать "Исходный текст" → показывается оригинал
- [ ] Нажать "Структурировать" → показывается структурированный текст (из кэша)

**Другие стратегии (регрессия):**
- [ ] TRANSCRIPTION_STRATEGY=single → работает как раньше
- [ ] TRANSCRIPTION_STRATEGY=hybrid → работает как раньше

---

## Риски и митигация

### Риск 1: Конфликт с HybridStrategy

**Описание:** Логика обработки может конфликтовать, если оба `requires_refinement()` и `requires_structuring()` вернут True.

**Вероятность:** Низкая (стратегии взаимоисключающие)

**Воздействие:** Высокое (неправильное поведение)

**Митигация:**
- Использовать `isinstance()` для явной проверки типа стратегии
- Добавить валидацию в factory: нельзя создать обе стратегии одновременно
- Логировать тип стратегии на каждом этапе

### Риск 2: LLM недоступен

**Описание:** LLM может быть недоступен (API error, timeout), структурирование не удастся.

**Вероятность:** Средняя

**Воздействие:** Среднее (пользователь видит оригинал вместо структурированного)

**Митигация:**
- ✅ Реализован fallback на оригинал
- Добавить retry логику в text_processor
- Логировать все ошибки LLM
- Показать понятное сообщение пользователю

### Риск 3: Производительность

**Описание:** Дополнительный вызов LLM увеличивает время обработки.

**Вероятность:** Высокая

**Воздействие:** Среднее (пользователь ждет дольше)

**Митигация:**
- Показывать черновик быстро (пользователь видит прогресс)
- Использовать progress tracker
- Документировать, что strategy=structure медленнее single
- Рекомендовать для случаев, где качество важнее скорости

### Риск 4: Неправильное сохранение вариантов

**Описание:** Варианты могут сохраняться с неправильными параметрами (mode, emoji_level).

**Вероятность:** Средняя

**Воздействие:** Высокое (баги в интерактивном режиме)

**Митигация:**
- Писать тесты для каждого сохранения варианта
- Логировать все сохранения
- Проверять в БД после каждого теста

---

## Этапы реализации (рекомендуемый порядок)

### Шаг 1: Создание стратегии (1-2 часа)
- [ ] Создать класс StructureStrategy в strategies.py
- [ ] Написать unit-тесты для стратегии
- [ ] Проверить, что тесты проходят

### Шаг 2: Конфигурация (30 минут)
- [ ] Добавить настройки в config.py
- [ ] Обновить .env.example и .env.example.short
- [ ] Проверить, что настройки загружаются

### Шаг 3: Фабрика (30 минут)
- [ ] Добавить создание StructureStrategy в factory
- [ ] Добавить валидацию (LLM должен быть включен)
- [ ] Протестировать создание стратегии

### Шаг 4: Обработка в handlers.py (2-3 часа)
- [ ] Добавить проверку requires_structuring()
- [ ] Реализовать сохранение original варианта
- [ ] Реализовать показ черновика (для длинных аудио)
- [ ] Реализовать структурирование
- [ ] Реализовать сохранение structured варианта
- [ ] Реализовать fallback на оригинал
- [ ] Обновить _create_interactive_state_and_keyboard()

### Шаг 5: TextProcessor (1 час)
- [ ] Добавить параметр emoji_level в create_structured()
- [ ] Реализовать логику emoji_level (модификация промпта или разные файлы)
- [ ] Протестировать с разными уровнями эмодзи

### Шаг 6: Тестирование (2-3 часа)
- [ ] Написать integration тесты
- [ ] Провести manual testing
- [ ] Проверить все edge cases (короткие/длинные, ошибки LLM, etc.)
- [ ] Проверить регрессию (другие стратегии работают)

### Шаг 7: Документация (1 час)
- [ ] Обновить architecture.md
- [ ] Обновить configuration.md
- [ ] Обновить README.md
- [ ] Добавить примеры использования

### Шаг 8: Code review и cleanup (30 минут)
- [ ] Запустить black, ruff
- [ ] Проверить логирование
- [ ] Удалить debug код
- [ ] Финальная проверка

**Общее время:** ~8-12 часов

---

## Дополнительные улучшения (опционально)

### 1. Прогресс-индикатор для структурирования

Добавить специальный прогресс-трекер для LLM-обработки:
```python
await request.status_message.edit_text(
    f"✅ Черновик готов!\n\n{draft_text}\n\n"
    f"🔄 Улучшаю текст... [⬛⬛⬜⬜⬜] 40%"
)
```

### 2. Кэширование структурированных результатов

Проверять, есть ли уже структурированный вариант для этого usage_id перед вызовом LLM.

### 3. Batch processing

Для нескольких коротких аудио подряд — батчить запросы к LLM.

### 4. Метрики

Добавить метрики:
- Время структурирования
- Процент успешных структурирований
- Средний размер до/после структурирования

---

## Контрольный список перед merge

- [ ] Все тесты проходят (pytest)
- [ ] Линтеры проходят (black, ruff)
- [ ] Документация обновлена
- [ ] .env.example содержит все новые переменные
- [ ] Manual testing пройден
- [ ] Нет breaking changes в других стратегиях
- [ ] Логирование добавлено на всех критических этапах
- [ ] Обработка ошибок реализована
- [ ] Code review пройден
- [ ] Ветка актуальна с main (rebase если нужно)

---

## Справочная информация

### Связанные файлы

**Стратегии:**
- `src/transcription/routing/strategies.py` - Все стратегии
- `src/transcription/factory.py` - Создание стратегий из конфигурации

**Обработчики:**
- `src/bot/handlers.py` - Основной обработчик (_process_transcription)
- `src/services/text_processor.py` - LLM обработка текста

**Конфигурация:**
- `src/config.py` - Настройки приложения
- `.env.example` - Документация переменных окружения

**База данных:**
- `src/storage/models.py` - Модели БД (TranscriptionVariant)
- `src/storage/repositories.py` - Репозитории для работы с БД

### Существующие паттерны

**HybridStrategy flow (для справки):**
```
1. Transcribe → draft_text
2. If long audio:
   a. Show draft
   b. Refine with LLM → refined_text
   c. Delete draft
   d. Show refined
```

**StructureStrategy flow (новый):**
```
1. Transcribe → original_text
2. Save original variant (mode='original')
3. If long audio (≥20 sec):
   a. Show draft: "✅ Черновик готов: {original_text} 🔄 Улучшаю текст..."
   b. Structure with LLM → structured_text
   c. Delete draft
   d. Show structured
4. If short audio (<20 sec):
   a. Structure with LLM → structured_text
   b. Show structured (no draft)
5. Save structured variant (mode='structured')
6. On error: Fallback to original
```

---

## Примечания

- **emoji_level:** Реализация через модификацию промпта или отдельные файлы - решить на этапе 5
- **Порог 20 сек:** Вынесен в переменную, можно легко изменить
- **Fallback:** Критически важен для UX - всегда показываем хоть что-то
- **Кэширование:** Варианты сохраняются в БД, повторное нажатие кнопок берет из кэша

---

**Автор плана:** Claude Code
**Дата создания:** 2025-12-15
**Версия:** 1.0
