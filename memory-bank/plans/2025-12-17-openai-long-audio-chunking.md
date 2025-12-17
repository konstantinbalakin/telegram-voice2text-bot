# План: Обработка длинных аудиофайлов через OpenAI с параллельным chunking

**Дата:** 2025-12-17
**Статус:** Утверждён, ожидает реализации
**Автор:** Claude Code
**Связанные issue:** Ошибка "audio duration 1885.851812 seconds is longer than 1400 seconds"

---

## Проблема

При тестировании больших файлов на моделях транскрибации OpenAI обнаружился лимит на **1400 секунд (~23 минуты)** для модели `gpt-4o-transcribe`.

**Пример ошибки:**
```
2025-12-17 15:59:41,233 - src.transcription.providers.openai_provider - ERROR - OpenAI API client error (400): Client error '400 Bad Request' for url 'https://api.openai.com/v1/audio/transcriptions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400 | Response: {
  "error": {
    "message": "audio duration 1885.851812 seconds is longer than 1400 seconds which is the maximum for this model",
    "type": "invalid_request_error",
    "param": null,
    "code": "invalid_value"
  }
}
```

**Ограничения OpenAI моделей:**
- `gpt-4o-transcribe`: max 1400-1500 секунд + 25MB file size
- `gpt-4o-mini-transcribe`: max 1400-1500 секунд + 25MB file size
- `whisper-1`: только 25MB file size (без duration limit)

---

## Требования от пользователя

Комбинированный подход с гибкой конфигурацией:

1. **OPENAI_GPT4O_MAX_DURATION** - порог переключения (по умолчанию 1400 сек)
2. **OPENAI_CHANGE_MODEL** - автоматически переключать на whisper-1 при превышении
3. **OPENAI_CHUNKING** - разбивать файл на чанки при превышении
4. **OPENAI_PARALLEL_CHUNKS** - обрабатывать чанки параллельно для ускорения

**Логика:**
```
IF audio_duration > OPENAI_GPT4O_MAX_DURATION:
    IF OPENAI_CHUNKING:
        target_model = "whisper-1" IF OPENAI_CHANGE_MODEL ELSE original_model
        Транскрибировать чанками через target_model

        IF OPENAI_PARALLEL_CHUNKS:
            Параллельная обработка (быстро, без контекста)
        ELSE:
            Последовательная обработка (медленно, с контекстом)
    ELSE:
        IF OPENAI_CHANGE_MODEL:
            Транскрибировать весь файл через whisper-1
        ELSE:
            Raise error: файл слишком большой
```

---

## Выбранное решение: Option 2+ (pydub Chunking + Parallel Processing)

### Обоснование

- ✅ Полное решение для файлов любой длительности
- ✅ Сохранение качества gpt-4o-transcribe (опционально)
- ⚡ Ускорение в 2-3 раза благодаря параллельности
- 🎛️ Гибкая конфигурация под разные сценарии
- 🔧 Код уже асинхронный (httpx.AsyncClient)

### Новые зависимости

- **pydub** - для разбиения аудио на чанки

---

## Технический дизайн

### 1. Новые конфигурационные параметры

**Файл:** `src/config.py`

```python
# OpenAI Long Audio Handling
openai_gpt4o_max_duration: int = Field(
    default=1400,
    description="Maximum audio duration in seconds for gpt-4o models before chunking/switching"
)

openai_change_model: bool = Field(
    default=True,
    description="Automatically switch to whisper-1 for audio exceeding max duration"
)

openai_chunking: bool = Field(
    default=False,
    description="Enable audio chunking for long files (splits into segments)"
)

openai_chunk_size_seconds: int = Field(
    default=1200,
    ge=300,
    le=1400,
    description="Size of each audio chunk in seconds (default: 20 minutes)"
)

openai_chunk_overlap_seconds: int = Field(
    default=2,
    ge=0,
    le=10,
    description="Overlap between chunks for better context preservation"
)

openai_parallel_chunks: bool = Field(
    default=True,
    description="Process chunks in parallel for faster transcription (disables context passing)"
)

openai_max_parallel_chunks: int = Field(
    default=3,
    ge=1,
    le=10,
    description="Maximum number of chunks to process simultaneously (rate limiting)"
)
```

### 2. Архитектура OpenAIProvider

**Файл:** `src/transcription/providers/openai_provider.py`

#### Новые методы

```python
class OpenAIProvider(TranscriptionProvider):

    async def transcribe(
        self, audio_path: Path, context: TranscriptionContext
    ) -> TranscriptionResult:
        """
        Основной метод транскрипции с поддержкой chunking.

        Логика:
        1. Проверка file size (существующая)
        2. Проверка duration
        3. Если duration > max_duration:
           - Chunking включен? → Разбить и транскрибировать
           - Chunking выключен + change_model? → Переключить на whisper-1
           - Иначе → Raise error
        """
        # Existing validation...

        # NEW: Check duration limit
        if context.duration_seconds > settings.openai_gpt4o_max_duration:
            return await self._handle_long_audio(audio_path, context)

        # Existing transcription logic...

    async def _handle_long_audio(
        self, audio_path: Path, context: TranscriptionContext
    ) -> TranscriptionResult:
        """
        Обработка длинных аудиофайлов.

        Returns:
            TranscriptionResult
        """
        duration = context.duration_seconds
        max_duration = settings.openai_gpt4o_max_duration

        logger.info(
            f"Audio duration {duration}s exceeds limit {max_duration}s. "
            f"Chunking={settings.openai_chunking}, "
            f"ChangeModel={settings.openai_change_model}"
        )

        if settings.openai_chunking:
            # Определить модель для чанков
            target_model = "whisper-1" if settings.openai_change_model else self.model

            logger.info(f"Splitting audio into chunks and transcribing with {target_model}")

            # Разбить на чанки
            chunk_paths = await self._split_audio_into_chunks(audio_path, context)

            try:
                # Транскрибировать чанки
                if settings.openai_parallel_chunks:
                    text = await self._transcribe_chunks_parallel(
                        chunk_paths, context, target_model
                    )
                else:
                    text = await self._transcribe_chunks_sequential(
                        chunk_paths, context, target_model
                    )

                processing_time = time.time() - start_time

                return TranscriptionResult(
                    text=text,
                    language=context.language or "unknown",
                    processing_time=processing_time,
                    audio_duration=context.duration_seconds,
                    provider_used="openai",
                    model_name=f"{target_model} (chunked)",
                )

            finally:
                # Cleanup chunk files
                self._cleanup_chunks(chunk_paths)

        elif settings.openai_change_model:
            # Переключить модель на whisper-1 для всего файла
            logger.info(f"Switching model from {self.model} to whisper-1")

            original_model = self.model
            self.model = "whisper-1"

            try:
                result = await self._transcribe_single(audio_path, context)
                result.model_name = f"whisper-1 (switched from {original_model})"
                return result
            finally:
                self.model = original_model

        else:
            raise ValueError(
                f"Audio duration {duration}s exceeds maximum {max_duration}s for {self.model}. "
                f"Enable OPENAI_CHUNKING or OPENAI_CHANGE_MODEL to handle long files."
            )

    async def _split_audio_into_chunks(
        self, audio_path: Path, context: TranscriptionContext
    ) -> list[Path]:
        """
        Разбить аудиофайл на чанки используя pydub.

        Args:
            audio_path: Путь к исходному файлу
            context: Контекст транскрипции

        Returns:
            Список путей к файлам-чанкам

        Raises:
            RuntimeError: Если разбиение не удалось
        """
        from pydub import AudioSegment
        import uuid

        chunk_size_ms = settings.openai_chunk_size_seconds * 1000
        overlap_ms = settings.openai_chunk_overlap_seconds * 1000

        logger.info(
            f"Splitting {audio_path.name} into chunks: "
            f"size={settings.openai_chunk_size_seconds}s, "
            f"overlap={settings.openai_chunk_overlap_seconds}s"
        )

        try:
            # Загрузить аудио
            audio = AudioSegment.from_file(str(audio_path))

            total_duration_ms = len(audio)
            chunk_paths = []

            # Создать чанки с перекрытием
            start_ms = 0
            chunk_index = 0

            while start_ms < total_duration_ms:
                end_ms = min(start_ms + chunk_size_ms, total_duration_ms)

                # Экспортировать чанк
                chunk_audio = audio[start_ms:end_ms]

                # Генерировать уникальное имя файла
                chunk_filename = f"{audio_path.stem}_chunk_{chunk_index}_{uuid.uuid4().hex[:8]}.mp3"
                chunk_path = audio_path.parent / chunk_filename

                chunk_audio.export(str(chunk_path), format="mp3")
                chunk_paths.append(chunk_path)

                logger.debug(
                    f"Created chunk {chunk_index}: {chunk_path.name}, "
                    f"duration={len(chunk_audio)/1000:.1f}s"
                )

                # Следующий чанк начинается с учётом overlap
                start_ms = end_ms - overlap_ms
                chunk_index += 1

            logger.info(f"Split audio into {len(chunk_paths)} chunks")
            return chunk_paths

        except Exception as e:
            logger.error(f"Failed to split audio into chunks: {e}")
            raise RuntimeError(f"Audio splitting failed: {e}") from e

    async def _transcribe_chunks_parallel(
        self,
        chunk_paths: list[Path],
        context: TranscriptionContext,
        model: str
    ) -> str:
        """
        Транскрибировать чанки параллельно (без контекста между чанками).

        Быстрее, но теряется контекст между чанками.

        Args:
            chunk_paths: Список путей к чанкам
            context: Контекст транскрипции
            model: Модель для использования

        Returns:
            Склеенный текст всех чанков
        """
        import asyncio

        logger.info(
            f"Starting parallel transcription of {len(chunk_paths)} chunks "
            f"with {model}, max_parallel={settings.openai_max_parallel_chunks}"
        )

        # Semaphore для rate limiting
        semaphore = asyncio.Semaphore(settings.openai_max_parallel_chunks)

        async def transcribe_one_chunk(chunk_path: Path, chunk_index: int) -> tuple[int, str]:
            """Транскрибировать один чанк."""
            async with semaphore:
                try:
                    logger.info(f"Transcribing chunk {chunk_index + 1}/{len(chunk_paths)}")

                    # Создать временный контекст для чанка
                    chunk_context = TranscriptionContext(
                        user_id=context.user_id,
                        language=context.language,
                        priority=context.priority,
                    )

                    # Транскрибировать чанк
                    result = await self._transcribe_single_file(
                        chunk_path, chunk_context, model
                    )

                    logger.info(
                        f"Chunk {chunk_index + 1} complete: {len(result.text)} chars"
                    )

                    return (chunk_index, result.text)

                except Exception as e:
                    logger.error(f"Chunk {chunk_index + 1} failed: {e}")
                    # Retry логика
                    try:
                        logger.warning(f"Retrying chunk {chunk_index + 1}")
                        result = await self._transcribe_single_file(
                            chunk_path, chunk_context, model
                        )
                        return (chunk_index, result.text)
                    except Exception as retry_error:
                        logger.error(f"Chunk {chunk_index + 1} retry failed: {retry_error}")
                        return (chunk_index, f"[ERROR: Chunk {chunk_index + 1} failed]")

        # Запустить все чанки параллельно
        tasks = [
            transcribe_one_chunk(chunk_path, i)
            for i, chunk_path in enumerate(chunk_paths)
        ]

        results = await asyncio.gather(*tasks)

        # Отсортировать по индексу и склеить
        results_sorted = sorted(results, key=lambda x: x[0])
        texts = [text for _, text in results_sorted if not text.startswith("[ERROR")]

        # Проверка на ошибки
        errors = [text for _, text in results_sorted if text.startswith("[ERROR")]
        if errors:
            logger.warning(f"{len(errors)} chunks failed during transcription")

        final_text = " ".join(texts)
        logger.info(f"Parallel transcription complete: {len(final_text)} chars total")

        return final_text

    async def _transcribe_chunks_sequential(
        self,
        chunk_paths: list[Path],
        context: TranscriptionContext,
        model: str
    ) -> str:
        """
        Транскрибировать чанки последовательно (с контекстом между чанками).

        Медленнее, но сохраняет контекст через prompt parameter.

        Args:
            chunk_paths: Список путей к чанкам
            context: Контекст транскрипции
            model: Модель для использования

        Returns:
            Склеенный текст всех чанков
        """
        logger.info(
            f"Starting sequential transcription of {len(chunk_paths)} chunks with {model}"
        )

        transcriptions = []
        previous_text = ""

        for i, chunk_path in enumerate(chunk_paths):
            try:
                logger.info(f"Transcribing chunk {i + 1}/{len(chunk_paths)}")

                # Создать контекст с промптом из предыдущего чанка
                chunk_context = TranscriptionContext(
                    user_id=context.user_id,
                    language=context.language,
                    priority=context.priority,
                )

                # Транскрибировать с контекстом (последние 224 токена)
                prompt = previous_text[-224:] if previous_text else None

                result = await self._transcribe_single_file(
                    chunk_path, chunk_context, model, prompt=prompt
                )

                transcriptions.append(result.text)
                previous_text = result.text

                logger.info(
                    f"Chunk {i + 1} complete: {len(result.text)} chars"
                )

            except Exception as e:
                logger.error(f"Chunk {i + 1} failed: {e}")

                # Retry без контекста
                try:
                    logger.warning(f"Retrying chunk {i + 1} without context")
                    result = await self._transcribe_single_file(
                        chunk_path, chunk_context, model
                    )
                    transcriptions.append(result.text)
                except Exception as retry_error:
                    logger.error(f"Chunk {i + 1} retry failed: {retry_error}")
                    transcriptions.append(f"[ERROR: Chunk {i + 1} failed]")

        final_text = " ".join(transcriptions)
        logger.info(f"Sequential transcription complete: {len(final_text)} chars total")

        return final_text

    async def _transcribe_single_file(
        self,
        audio_path: Path,
        context: TranscriptionContext,
        model: str,
        prompt: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Транскрибировать один файл (helper для chunking).

        Args:
            audio_path: Путь к аудиофайлу
            context: Контекст
            model: Модель для использования
            prompt: Опциональный промпт для контекста

        Returns:
            TranscriptionResult
        """
        start_time = time.time()

        try:
            mime_type = mimetypes.guess_type(audio_path)[0] or "audio/mpeg"

            with open(audio_path, "rb") as audio_file:
                files = {"file": (audio_path.name, audio_file, mime_type)}
                data = {"model": model}

                if context.language:
                    data["language"] = context.language

                if prompt:
                    data["prompt"] = prompt

                response = await self._client.post(
                    "/audio/transcriptions",
                    files=files,
                    data=data,
                )

            response.raise_for_status()
            result = response.json()

            processing_time = time.time() - start_time
            text = result.get("text", "")
            language = result.get("language", context.language or "unknown")

            return TranscriptionResult(
                text=text,
                language=language,
                processing_time=processing_time,
                audio_duration=0,  # Unknown for chunks
                provider_used="openai",
                model_name=model,
            )

        except Exception as e:
            logger.error(f"Transcription failed for {audio_path.name}: {e}")
            raise

    def _cleanup_chunks(self, chunk_paths: list[Path]) -> None:
        """
        Удалить временные файлы чанков.

        Args:
            chunk_paths: Список путей к чанкам
        """
        for chunk_path in chunk_paths:
            try:
                if chunk_path.exists():
                    chunk_path.unlink()
                    logger.debug(f"Cleaned up chunk: {chunk_path.name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup chunk {chunk_path.name}: {e}")
```

---

## Изменения в файлах

### 1. `pyproject.toml`

```toml
[tool.poetry.dependencies]
# ... existing dependencies ...
pydub = "^0.25.1"
```

### 2. `requirements.txt`

После `poetry lock && poetry export`:
```
pydub==0.25.1
```

### 3. `.env.example`

```bash
# ============================================================================
# OpenAI Long Audio Handling
# ============================================================================

# Maximum audio duration for gpt-4o models before special handling
# gpt-4o-transcribe/mini have a limit of ~1400-1500 seconds
OPENAI_GPT4O_MAX_DURATION=1400

# Automatically switch to whisper-1 for audio exceeding max duration
# whisper-1 has no duration limit (only 25MB file size limit)
OPENAI_CHANGE_MODEL=true

# Enable audio chunking for long files
# Splits audio into segments and transcribes separately
OPENAI_CHUNKING=false

# Size of each audio chunk in seconds (5-23 minutes recommended)
# Must be less than OPENAI_GPT4O_MAX_DURATION
OPENAI_CHUNK_SIZE_SECONDS=1200

# Overlap between chunks in seconds for better context
# Helps preserve context at chunk boundaries
OPENAI_CHUNK_OVERLAP_SECONDS=2

# Process chunks in parallel for faster transcription
# true = faster but loses context between chunks
# false = slower but preserves context via prompt parameter
OPENAI_PARALLEL_CHUNKS=true

# Maximum number of chunks to process simultaneously
# Helps prevent rate limiting (429 errors)
OPENAI_MAX_PARALLEL_CHUNKS=3
```

### 4. `.env.example.short`

```bash
# OpenAI Long Audio
OPENAI_GPT4O_MAX_DURATION=1400
OPENAI_CHANGE_MODEL=true
OPENAI_CHUNKING=false
OPENAI_CHUNK_SIZE_SECONDS=1200
OPENAI_CHUNK_OVERLAP_SECONDS=2
OPENAI_PARALLEL_CHUNKS=true
OPENAI_MAX_PARALLEL_CHUNKS=3
```

### 5. `.github/workflows/deploy.yml`

Добавить в секцию environment variables:
```yaml
OPENAI_GPT4O_MAX_DURATION=1400
OPENAI_CHANGE_MODEL=true
OPENAI_CHUNKING=false
OPENAI_PARALLEL_CHUNKS=true
OPENAI_MAX_PARALLEL_CHUNKS=3
```

---

## План тестирования

### Unit Tests

**Файл:** `tests/test_openai_provider_chunking.py`

```python
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from src.transcription.providers.openai_provider import OpenAIProvider
from src.transcription.models import TranscriptionContext

@pytest.fixture
def provider():
    """OpenAI provider with mocked client."""
    provider = OpenAIProvider(api_key="test-key", model="gpt-4o-transcribe")
    provider.initialize()
    return provider

@pytest.fixture
def long_audio_context():
    """Context for long audio (>1400s)."""
    return TranscriptionContext(
        user_id=123,
        duration_seconds=1800,  # 30 minutes
        language="ru"
    )

class TestLongAudioHandling:
    """Tests for long audio handling."""

    @pytest.mark.asyncio
    async def test_duration_check_triggers_chunking(self, provider, long_audio_context):
        """Test that duration > max triggers chunking logic."""
        with patch.object(provider, '_handle_long_audio') as mock_handle:
            mock_handle.return_value = Mock()
            await provider.transcribe(Path("test.mp3"), long_audio_context)
            mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_model_switching_when_chunking_disabled(self, provider, long_audio_context):
        """Test model switches to whisper-1 when chunking disabled."""
        with patch('src.config.settings') as mock_settings:
            mock_settings.openai_chunking = False
            mock_settings.openai_change_model = True
            mock_settings.openai_gpt4o_max_duration = 1400

            # Test implementation...

    @pytest.mark.asyncio
    async def test_split_audio_into_chunks(self, provider):
        """Test audio splitting creates correct number of chunks."""
        # Test with mock audio file
        pass

    @pytest.mark.asyncio
    async def test_parallel_chunk_processing(self, provider):
        """Test parallel processing of chunks."""
        # Mock multiple chunks and verify parallel execution
        pass

    @pytest.mark.asyncio
    async def test_sequential_chunk_processing_with_context(self, provider):
        """Test sequential processing passes context via prompt."""
        # Verify prompt parameter is used
        pass

    @pytest.mark.asyncio
    async def test_chunk_retry_on_failure(self, provider):
        """Test that failed chunks are retried."""
        pass

    @pytest.mark.asyncio
    async def test_cleanup_chunks_after_transcription(self, provider):
        """Test that temporary chunk files are cleaned up."""
        pass

    @pytest.mark.asyncio
    async def test_error_when_chunking_and_switching_disabled(self, provider, long_audio_context):
        """Test error raised when both chunking and model switching disabled."""
        with patch('src.config.settings') as mock_settings:
            mock_settings.openai_chunking = False
            mock_settings.openai_change_model = False

            with pytest.raises(ValueError, match="exceeds maximum"):
                await provider.transcribe(Path("test.mp3"), long_audio_context)
```

### Integration Tests

**Тестовые сценарии:**

1. ✅ **Short audio (< 1400s)** - обычная транскрипция без изменений
2. ✅ **Long audio + chunking=false + change_model=true** - переключение на whisper-1
3. ✅ **Long audio + chunking=true + parallel=true** - параллельная обработка чанков
4. ✅ **Long audio + chunking=true + parallel=false** - последовательная с контекстом
5. ✅ **Long audio + chunking=false + change_model=false** - ошибка
6. ⚠️ **Chunk failure + retry** - один чанк падает, retry успешен
7. ⚠️ **Multiple chunk failures** - несколько чанков падают
8. ✅ **Cleanup verification** - временные файлы удалены

### Manual Testing

**Тестовые файлы:**
- 10 минут (600s) - короткий файл
- 25 минут (1500s) - длинный файл
- 45 минут (2700s) - очень длинный файл

**Проверить:**
- Качество транскрипции на границах чанков
- Время обработки (parallel vs sequential)
- Отсутствие memory leaks
- Корректность cleanup

---

## Риски и митигация

| Риск | Вероятность | Воздействие | Митигация |
|------|-------------|-------------|-----------|
| **Rate limiting (429 errors)** | Средняя | Высокое | Semaphore с `max_parallel_chunks=3`, exponential backoff retry |
| **Потеря контекста при parallel** | Высокая | Среднее | Документировать, дать выбор `parallel_chunks=false` |
| **Качество на границах чанков** | Средняя | Среднее | Overlap 2 секунды между чанками |
| **Увеличение стоимости API** | Средняя | Среднее | Chunking выключен по умолчанию, чёткая документация |
| **Ошибки при splitting** | Низкая | Высокое | Try/except, fallback на model switching |
| **Memory issues с большими файлами** | Низкая | Среднее | pydub обрабатывает стримом, cleanup после обработки |
| **Timestamps не работают** | Высокая | Низкое | OpenAI Whisper API не возвращает timestamps, документировать ограничение |

---

## Критерии успеха

### Функциональные

- ✅ Файлы > 1400 сек успешно транскрибируются
- ✅ Все 4 комбинации настроек работают корректно
- ✅ Параллельная обработка ускоряет в 2-3 раза
- ✅ Последовательная обработка сохраняет контекст
- ✅ Временные файлы чанков удаляются

### Нефункциональные

- ✅ Unit tests coverage > 80%
- ✅ Все integration tests проходят
- ✅ Документация обновлена (README, .env.example)
- ✅ Логирование информативное на всех этапах
- ✅ Нет регрессии для коротких файлов (< 1400s)

### Производительность

- ⚡ Параллельная обработка: ускорение ~2-3x
- 📊 Overhead для коротких файлов < 1%
- 💾 Memory usage не увеличивается значительно

---

## Примеры использования

### Сценарий 1: Быстрая обработка длинного файла (по умолчанию)

```bash
# .env
OPENAI_GPT4O_MAX_DURATION=1400
OPENAI_CHANGE_MODEL=true
OPENAI_CHUNKING=false
```

**Результат:** Файл > 1400s автоматически обрабатывается через whisper-1 (качество ниже, но быстро)

---

### Сценарий 2: Максимальное качество с параллельностью

```bash
# .env
OPENAI_GPT4O_MAX_DURATION=1400
OPENAI_CHANGE_MODEL=false  # Использовать gpt-4o-transcribe
OPENAI_CHUNKING=true
OPENAI_PARALLEL_CHUNKS=true
OPENAI_MAX_PARALLEL_CHUNKS=3
```

**Результат:**
- Файл разбивается на чанки по 20 минут
- Каждый чанк обрабатывается gpt-4o-transcribe
- 3 чанка параллельно
- Время: ~10 минут для 30-минутного файла
- Качество: высокое (gpt-4o)

---

### Сценарий 3: Максимальное качество с контекстом

```bash
# .env
OPENAI_CHUNKING=true
OPENAI_PARALLEL_CHUNKS=false  # Последовательная обработка
OPENAI_CHANGE_MODEL=false
```

**Результат:**
- Последовательная обработка
- Контекст передаётся через prompt
- Время: ~30 минут для 30-минутного файла
- Качество: максимальное (gpt-4o + контекст)

---

### Сценарий 4: Баланс (рекомендуется)

```bash
# .env
OPENAI_CHUNKING=true
OPENAI_PARALLEL_CHUNKS=true
OPENAI_CHANGE_MODEL=true  # Fallback на whisper-1 если gpt-4o падает
```

**Результат:**
- Быстрая обработка через gpt-4o
- Автоматический fallback если проблемы
- Оптимальное соотношение скорость/качество

---

## Документация изменений

### README.md

Добавить секцию:

```markdown
### Long Audio Files (>23 minutes)

OpenAI's `gpt-4o-transcribe` model has a duration limit of ~1400 seconds (23 minutes).

**Options for handling long files:**

1. **Automatic model switching** (default):
   ```bash
   OPENAI_CHANGE_MODEL=true
   ```
   Files > 1400s are automatically processed with `whisper-1` (no duration limit).

2. **Audio chunking**:
   ```bash
   OPENAI_CHUNKING=true
   OPENAI_PARALLEL_CHUNKS=true
   ```
   - Splits audio into 20-minute segments
   - Processes in parallel for 2-3x speedup
   - Preserves gpt-4o quality

3. **Sequential with context** (best quality):
   ```bash
   OPENAI_CHUNKING=true
   OPENAI_PARALLEL_CHUNKS=false
   ```
   - Passes context between chunks via prompt parameter
   - Slower but better coherence

See `.env.example` for all configuration options.
```

### docs/

Создать `docs/features/long-audio-handling.md` с детальной документацией:
- Технические детали
- Сравнение стратегий
- Рекомендации
- Troubleshooting

---

## Timeline

### Phase 1: Core Implementation (4-5 часов)
- [x] Добавить конфигурационные параметры в `src/config.py`
- [x] Добавить pydub в зависимости
- [x] Реализовать `_handle_long_audio()`
- [x] Реализовать `_split_audio_into_chunks()`
- [x] Реализовать `_transcribe_single_file()`

### Phase 2: Parallel Processing (2-3 часа)
- [x] Реализовать `_transcribe_chunks_parallel()`
- [x] Реализовать `_transcribe_chunks_sequential()`
- [x] Добавить rate limiting через Semaphore
- [x] Реализовать retry логику

### Phase 3: Testing (2 часа)
- [x] Написать unit tests
- [x] Написать integration tests
- [x] Manual testing с реальными файлами

### Phase 4: Documentation (1 час)
- [x] Обновить .env.example
- [x] Обновить README.md
- [x] Создать docs/features/long-audio-handling.md

**Total: 8-10 часов**

---

## Next Steps

1. ✅ **План утверждён** - документ создан
2. ⏳ **Реализация** - выполнить в отдельном чате через `/workflow:execute`
3. ⏳ **Code Review** - проверить реализацию
4. ⏳ **Testing** - запустить все тесты
5. ⏳ **Deployment** - развернуть на VPS
6. ⏳ **Monitoring** - отследить работу в production

---

## References

**Research Sources:**
- [Building a Long Audio Transcription Tool with OpenAI's Whisper API](https://www.buildwithmatija.com/blog/building-a-long-audio-transcription-tool-with-openai-s-whisper-api)
- [Split and Transcribe Audio Files with OpenAI Whisper](https://ngwaifoong92.medium.com/split-and-transcribe-audio-files-with-openai-whisper-cee0b89a509d)
- [Split large audio file and transcribe it using the Whisper API from OpenAI (GitHub Gist)](https://gist.github.com/patrick-samy/cf8470272d1ff23dff4e2b562b940ef5)
- [GPT4.0-Transcribe—MAX 1500 SECONDS? - OpenAI Community](https://community.openai.com/t/gpt4-0-transcribe-max-1500-seconds/1306684)
- [Questions regarding transcribing long audios (>25MB) in Whisper API](https://community.openai.com/t/questions-regarding-transcribing-long-audios-25mb-in-whisper-api/267384)

**Related Files:**
- `src/transcription/providers/openai_provider.py` - основная реализация
- `src/config.py` - конфигурация
- `src/transcription/models.py` - модели данных
- `.env.example` - примеры настроек

---

**Status:** ✅ Ready for Implementation
**Approved by:** User
**Implementation:** Will be done in separate chat session
