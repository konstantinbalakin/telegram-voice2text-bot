# Provider-Aware Audio Format Conversion

**Дата:** 2025-12-15
**Статус:** Планирование
**Приоритет:** Высокий
**Ветка:** `feature/provider-aware-audio-format`

## Проблема

### Описание

OpenAI запустили новые улучшенные модели транскрипции `gpt-4o-transcribe` и `gpt-4o-mini-transcribe`, которые имеют ограниченную поддержку форматов аудио по сравнению со старой моделью `whisper-1`.

**Текущая ситуация:**
- Telegram отправляет голосовые сообщения в формате `.oga` (Ogg контейнер с Opus кодеком, mono)
- Текущий код в `audio_handler.py:402-404` определяет, что файл уже mono + opus, и **пропускает конвертацию**
- При попытке использовать `gpt-4o-transcribe` получаем ошибку: `"Unsupported file format oga"`

**Поддерживаемые форматы:**

| Модель | Поддерживаемые форматы | Лимит |
|--------|----------------------|-------|
| `gpt-4o-transcribe` | mp3, mp4, mpeg, mpga, m4a, wav, webm | 25 MB |
| `gpt-4o-mini-transcribe` | mp3, mp4, mpeg, mpga, m4a, wav, webm | 25 MB |
| `whisper-1` (старая) | flac, m4a, mp3, mp4, mpeg, mpga, **oga**, ogg, wav, webm | 25 MB |
| `faster-whisper` (локальная) | Все форматы через ffmpeg (включая oga, opus) | Без лимита |

### Воздействие

- ❌ Невозможно использовать новые улучшенные модели OpenAI
- ❌ Блокировка тестирования производительности новых моделей
- ❌ Потенциальная потеря качества транскрипции

### Кейсы использования

1. **Обычные голосовые (< 20 MB):** Telegram Bot API → `.oga` формат
2. **Большие файлы (> 20 MB):** Telethon Client API → `.oga` формат
3. **Перетранскрипция:** Сохраненные файлы в `data/audio_files/` → `.oga`
4. **Routing стратегии:**
   - Single: один провайдер
   - Fallback: OpenAI → FasterWhisper (при ошибке)
   - Benchmark: тестирование производительности

## Выбранное решение: Гибридный подход (Вариант 3)

### Обоснование

После анализа трех вариантов (адаптивный, простой MP3, гибридный) выбран **гибридный подход** по следующим причинам:

✅ **Полная совместимость**: работает со всеми моделями OpenAI и FasterWhisper
✅ **Оптимальная производительность**: каждый провайдер получает оптимальный формат
✅ **Размер файлов**: FasterWhisper использует компактный OGA, OpenAI получает MP3 только при необходимости
✅ **Качество аудио**: минимизируется двойная компрессия
✅ **Гибкость**: легко добавить поддержку новых моделей/провайдеров
✅ **Настраиваемость**: можно выбрать MP3 или WAV для OpenAI через config

### Архитектурное решение

**Принцип:** Provider-aware preprocessing - препроцессинг аудио с учетом целевого провайдера.

**Логика выбора формата:**
```
IF провайдер == "openai":
    IF модель in ["gpt-4o-transcribe", "gpt-4o-mini-transcribe"]:
        → Конвертировать в MP3 (16 kHz, mono, 64 kbps)
    ELSE (whisper-1):
        → Оставить OGA (или конвертировать mono Opus)
ELSE IF провайдер == "faster-whisper":
    → Оставить OGA (оптимально для локальной обработки)
ELSE:
    → Fallback: конвертировать mono Opus (как раньше)
```

## План реализации

### Этап 1: Конфигурация

**Файл:** `src/config.py`

**Изменения:**
1. Добавить настройку предпочитаемого формата для OpenAI:
   ```python
   openai_preferred_format: str = Field(
       default="mp3",
       description="Preferred audio format for OpenAI API (mp3, wav)"
   )
   ```

2. Добавить константу маппинга совместимости:
   ```python
   OPENAI_FORMAT_REQUIREMENTS = {
       "gpt-4o-transcribe": ["mp3", "wav"],  # Требует конвертации
       "gpt-4o-mini-transcribe": ["mp3", "wav"],  # Требует конвертации
       "whisper-1": None,  # Поддерживает OGA
   }
   ```

### Этап 2: Base Provider Interface

**Файл:** `src/transcription/providers/base.py`

**Изменения:**
1. Добавить abstract property для имени провайдера:
   ```python
   @property
   @abstractmethod
   def provider_name(self) -> str:
       """Unique provider identifier (e.g., 'openai', 'faster-whisper')"""
       pass
   ```

2. Добавить метод для получения предпочитаемого формата:
   ```python
   def get_preferred_format(self) -> Optional[str]:
       """
       Get preferred audio format for this provider.
       Returns None if provider accepts any format.
       """
       return None
   ```

### Этап 3: OpenAI Provider

**Файл:** `src/transcription/providers/openai_provider.py`

**Изменения:**
1. Добавить property `provider_name`:
   ```python
   @property
   def provider_name(self) -> str:
       return "openai"
   ```

2. Добавить метод получения предпочитаемого формата:
   ```python
   def get_preferred_format(self) -> Optional[str]:
       """Get preferred format based on model."""
       from src.config import settings, OPENAI_FORMAT_REQUIREMENTS

       if self.model in OPENAI_FORMAT_REQUIREMENTS:
           required = OPENAI_FORMAT_REQUIREMENTS[self.model]
           if required:  # Требует конвертации
               return settings.openai_preferred_format
       return None  # whisper-1 или другие - без требований
   ```

### Этап 4: FasterWhisper Provider

**Файл:** `src/transcription/providers/faster_whisper_provider.py`

**Изменения:**
1. Добавить property `provider_name`:
   ```python
   @property
   def provider_name(self) -> str:
       return "faster-whisper"
   ```

2. Метод `get_preferred_format()` наследуется от базового (возвращает None)

### Этап 5: Transcription Router

**Файл:** `src/transcription/routing/router.py`

**Изменения:**
1. Добавить метод получения активного провайдера:
   ```python
   def get_active_provider(self) -> Optional[TranscriptionProvider]:
       """Get the provider that will be used for next transcription."""
       provider_name = self.strategy.select_provider(
           TranscriptionContext(duration_seconds=0)
       )
       return self.providers.get(provider_name)

   def get_active_provider_name(self) -> Optional[str]:
       """Get name of the active provider."""
       provider = self.get_active_provider()
       return provider.provider_name if provider else None
   ```

### Этап 6: Audio Handler (Ключевые изменения)

**Файл:** `src/transcription/audio_handler.py`

**Изменения:**

1. **Модифицировать `preprocess_audio()`:**
   ```python
   def preprocess_audio(
       self,
       audio_path: Path,
       target_provider: Optional[str] = None
   ) -> Path:
       """
       Apply intelligent audio preprocessing pipeline.

       Args:
           audio_path: Original audio file
           target_provider: Target provider name for format optimization

       Returns:
           Path to preprocessed audio (or original if no preprocessing needed)
       """
       logger.debug(
           f"preprocess_audio: input={audio_path.name}, "
           f"provider={target_provider}, "
           f"mono_enabled={settings.audio_convert_to_mono}, "
           f"speed={settings.audio_speed_multiplier}x"
       )

       path = audio_path

       # Format optimization based on provider
       if target_provider:
           try:
               path = self._optimize_for_provider(path, target_provider)
               if path != audio_path:
                   logger.info(f"Optimized for {target_provider}: {path.name}")
           except Exception as e:
               logger.warning(
                   f"Provider optimization failed: {e}, using original"
               )
               path = audio_path

       # Mono conversion (if not already done by optimization)
       if settings.audio_convert_to_mono and path == audio_path:
           try:
               path = self._convert_to_mono(path)
               if path != audio_path:
                   logger.info(f"Converted to mono: {path.name}")
           except Exception as e:
               logger.warning(f"Mono conversion failed: {e}, using original")
               path = audio_path

       # Speed adjustment
       if settings.audio_speed_multiplier != 1.0:
           try:
               path = self._adjust_speed(path)
               logger.info(
                   f"Adjusted speed {settings.audio_speed_multiplier}x: "
                   f"{path.name}"
               )
           except Exception as e:
               logger.warning(f"Speed adjustment failed: {e}, using original")

       if path == audio_path:
           logger.debug("No preprocessing applied, using original file")
       else:
           logger.debug(f"Preprocessing complete: {path}")

       return path
   ```

2. **Добавить новый метод `_optimize_for_provider()`:**
   ```python
   def _optimize_for_provider(
       self,
       input_path: Path,
       provider_name: str
   ) -> Path:
       """
       Optimize audio format for specific provider.

       Args:
           input_path: Input audio file
           provider_name: Target provider (e.g., 'openai', 'faster-whisper')

       Returns:
           Path to optimized audio file (or original if no optimization needed)
       """
       from src.config import settings, OPENAI_FORMAT_REQUIREMENTS

       # OpenAI provider optimization
       if provider_name == "openai":
           # Determine if conversion needed based on model
           model = settings.openai_model
           required_formats = OPENAI_FORMAT_REQUIREMENTS.get(model)

           if required_formats:
               # New models (gpt-4o-*) - require MP3/WAV
               current_ext = input_path.suffix.lower()

               if current_ext in [".oga", ".ogg", ".opus"]:
                   # Convert to preferred format
                   target_format = settings.openai_preferred_format

                   if target_format == "mp3":
                       return self._convert_to_mp3(input_path)
                   elif target_format == "wav":
                       return self._convert_to_wav(input_path)
                   else:
                       logger.warning(
                           f"Unknown format {target_format}, using mp3"
                       )
                       return self._convert_to_mp3(input_path)
               else:
                   logger.debug(
                       f"Format {current_ext} already supported by {model}"
                   )
                   return input_path
           else:
               # Old model (whisper-1) - supports OGA
               logger.debug(f"Model {model} supports OGA format")
               return input_path

       # FasterWhisper - prefer OGA (efficient)
       elif provider_name == "faster-whisper":
           # OGA is optimal for local processing, keep as is
           logger.debug("FasterWhisper: using original format (optimal)")
           return input_path

       # Unknown provider - no optimization
       else:
           logger.debug(f"No optimization for provider: {provider_name}")
           return input_path
   ```

3. **Добавить метод `_convert_to_mp3()`:**
   ```python
   def _convert_to_mp3(self, input_path: Path) -> Path:
       """
       Convert audio to MP3 format optimized for speech recognition.

       Args:
           input_path: Input audio file

       Returns:
           Path to MP3 audio file

       Raises:
           subprocess.CalledProcessError: If ffmpeg fails
       """
       original_size = input_path.stat().st_size
       original_size_mb = original_size / (1024 * 1024)

       output_path = input_path.parent / f"{input_path.stem}_converted.mp3"

       logger.info(
           f"Converting to MP3: {input_path.name} "
           f"({original_size_mb:.2f}MB)"
       )

       # Convert to MP3 with speech-optimized settings
       subprocess.run(
           [
               "ffmpeg",
               "-y",  # Overwrite
               "-i", str(input_path),
               "-ac", "1",  # Mono
               "-ar", "16000",  # 16kHz sample rate (optimal for Whisper)
               "-b:a", "64k",  # 64 kbps bitrate (good quality for speech)
               "-acodec", "libmp3lame",  # MP3 codec
               "-q:a", "2",  # Quality level (2 = high quality)
               str(output_path),
           ],
           check=True,
           capture_output=True,
           text=True,
       )

       converted_size = output_path.stat().st_size
       converted_size_mb = converted_size / (1024 * 1024)
       size_ratio = (converted_size / original_size * 100) if original_size > 0 else 0

       logger.info(
           f"MP3 conversion complete: "
           f"original={original_size_mb:.2f}MB, "
           f"converted={converted_size_mb:.2f}MB "
           f"({size_ratio:.1f}% of original)"
       )

       # Warn if approaching 25MB limit
       if converted_size_mb > 20:
           logger.warning(
               f"Converted file size {converted_size_mb:.2f}MB "
               f"approaching OpenAI limit (25MB)"
           )

       return output_path
   ```

4. **Добавить метод `_convert_to_wav()` (опционально):**
   ```python
   def _convert_to_wav(self, input_path: Path) -> Path:
       """
       Convert audio to WAV format (PCM 16-bit).

       Args:
           input_path: Input audio file

       Returns:
           Path to WAV audio file

       Note:
           WAV files are larger than MP3 but avoid double compression.
           Use only if quality is critical and file size is small.
       """
       original_size_mb = input_path.stat().st_size / (1024 * 1024)
       output_path = input_path.parent / f"{input_path.stem}_converted.wav"

       logger.info(f"Converting to WAV: {input_path.name}")

       subprocess.run(
           [
               "ffmpeg",
               "-y",
               "-i", str(input_path),
               "-ac", "1",  # Mono
               "-ar", "16000",  # 16kHz
               "-acodec", "pcm_s16le",  # PCM 16-bit
               str(output_path),
           ],
           check=True,
           capture_output=True,
           text=True,
       )

       converted_size_mb = output_path.stat().st_size / (1024 * 1024)

       logger.info(
           f"WAV conversion complete: "
           f"{original_size_mb:.2f}MB → {converted_size_mb:.2f}MB"
       )

       if converted_size_mb > 20:
           logger.warning(
               f"WAV file {converted_size_mb:.2f}MB may exceed OpenAI limit"
           )

       return output_path
   ```

### Этап 7: Handler Integration

**Файл:** `src/bot/handlers.py`

**Изменения в `_process_transcription()`:**

Найти место вызова `preprocess_audio` (около строки 1264):

```python
# Before (текущий код):
processed_path = self.audio_handler.preprocess_audio(request.file_path)

# After (новый код):
# Get target provider for format optimization
target_provider = None
if self.transcription_router:
    target_provider = self.transcription_router.get_active_provider_name()
    logger.debug(f"Target provider for preprocessing: {target_provider}")

processed_path = self.audio_handler.preprocess_audio(
    request.file_path,
    target_provider=target_provider
)
```

## Тестирование

### Unit тесты

**Файл:** `tests/unit/test_audio_handler_provider_aware.py` (новый)

1. **Тест конвертации OGA → MP3 для gpt-4o-transcribe**
   - Mock настройки: `openai_model="gpt-4o-transcribe"`
   - Входной файл: `.oga`
   - Ожидаемый результат: `.mp3` файл

2. **Тест сохранения OGA для whisper-1**
   - Mock настройки: `openai_model="whisper-1"`
   - Входной файл: `.oga`
   - Ожидаемый результат: `.oga` файл (без конвертации)

3. **Тест сохранения OGA для faster-whisper**
   - Target provider: `"faster-whisper"`
   - Входной файл: `.oga`
   - Ожидаемый результат: `.oga` файл

4. **Тест fallback при отсутствии провайдера**
   - Target provider: `None`
   - Входной файл: `.oga`
   - Ожидаемый результат: mono conversion (текущее поведение)

5. **Тест размера MP3 файла**
   - Проверка, что 64kbps битрейт не превышает 25MB для типичных длительностей
   - Расчет: 64 kbps × 60 sec × 20 min / 8 = ~9.6 MB ✅

### Integration тесты

1. **E2E тест с OpenAI gpt-4o-transcribe**
   - Отправить голосовое сообщение через бота
   - Провайдер: OpenAI с моделью gpt-4o-transcribe
   - Проверить успешную транскрипцию

2. **E2E тест с FasterWhisper**
   - Тот же файл
   - Провайдер: FasterWhisper
   - Проверить, что использовался OGA (по логам)

3. **Тест fallback стратегии**
   - Стратегия: fallback (OpenAI → FasterWhisper)
   - Симулировать ошибку OpenAI
   - Проверить, что FasterWhisper получил файл и обработал

### Ручное тестирование

1. ✅ Короткое голосовое (10 сек) → gpt-4o-transcribe
2. ✅ Среднее голосовое (2 мин) → gpt-4o-transcribe
3. ✅ Длинное голосовое (10 мин) → gpt-4o-transcribe
4. ✅ Очень длинное (20+ мин) → проверка размера MP3 vs 25MB лимита
5. ✅ Перетранскрипция с другим провайдером

## Риски и минимизация

### Риск 1: Превышение лимита 25MB

**Проблема:** Длинные аудио (> 25 мин) в MP3 64kbps могут превысить лимит.

**Минимизация:**
- Добавить предварительную проверку размера
- Логировать warning при размере > 20MB
- Документировать ограничение
- Рассмотреть использование VAD для обрезки тишины (будущее улучшение)

### Риск 2: Двойная компрессия (качество)

**Проблема:** Opus → MP3 = две lossy компрессии.

**Минимизация:**
- Использовать высокое качество MP3 (q:a 2, 64kbps)
- Альтернатива: опция конвертации в WAV (lossless)
- Протестировать WER (Word Error Rate) до/после конвертации

### Риск 3: Производительность конвертации

**Проблема:** Конвертация занимает время (особенно для длинных файлов).

**Минимизация:**
- ffmpeg очень быстрый (~5-10x realtime)
- Для 10 мин аудио: ~1-2 сек конвертации
- Асинхронная обработка уже реализована в queue_manager

### Риск 4: Проблемы с fallback

**Проблема:** При fallback OpenAI → FasterWhisper может потребоваться другой формат.

**Минимизация:**
- FasterWhisper поддерживает MP3 через ffmpeg
- Сохранять оригинальный файл для возможности повторной обработки
- Логировать все решения о формате

### Риск 5: Обратная совместимость

**Проблема:** Изменения могут сломать существующий функционал.

**Минимизация:**
- Параметр `target_provider` опциональный (None = старое поведение)
- Все изменения обратно совместимы
- Comprehensive unit и integration тесты
- Feature flag возможен (но пока не требуется)

## Критерии успеха

✅ **Функциональные:**
- OpenAI `gpt-4o-transcribe` успешно транскрибирует голосовые сообщения
- OpenAI `whisper-1` продолжает работать как раньше
- FasterWhisper продолжает использовать OGA (оптимально)
- Fallback стратегия работает корректно
- Перетранскрипция работает с разными провайдерами

✅ **Нефункциональные:**
- Время конвертации < 5 сек для 10-минутного аудио
- Размер MP3 не превышает 25MB для аудио до 25 минут
- Нет регрессий в производительности
- Все тесты проходят (unit + integration)

✅ **Документация:**
- План задокументирован в memory-bank/plans/
- Код содержит понятные комментарии
- Логи позволяют отследить все решения о конвертации

## Дальнейшие улучшения (Future Work)

Эти улучшения НЕ входят в текущий scope, но могут быть реализованы в будущем:

1. **Адаптивный битрейт:** Автоматически подбирать битрейт на основе длины аудио для оптимизации размера
2. **VAD-обрезка тишины:** Использовать Voice Activity Detection для удаления тишины и уменьшения размера файла
3. **Кеширование конвертации:** Сохранять конвертированные файлы для повторного использования
4. **Метрики качества:** Автоматическое сравнение WER до/после конвертации
5. **Batch конвертация:** Оптимизация для обработки нескольких файлов одновременно

## Timeline

**Общая оценка:** 3-4 часа разработки + 1-2 часа тестирования

1. **Этап 1-4:** Конфигурация и Provider Interface (30 мин)
2. **Этап 5:** Router методы (20 мин)
3. **Этап 6:** Audio Handler (2 часа) - самый сложный этап
4. **Этап 7:** Handler Integration (20 мин)
5. **Unit тесты:** 1 час
6. **Integration тесты:** 30 мин
7. **Ручное тестирование:** 30 мин

**Итого:** ~5-6 часов

## Заметки

- Все изменения изолированы в отдельных методах для легкого тестирования
- Логика выбора формата централизована в `_optimize_for_provider()`
- Fallback на оригинальный файл при любых ошибках
- Подробное логирование для отладки
- Опциональный параметр `target_provider` обеспечивает обратную совместимость

## Ссылки

- [OpenAI Audio API Reference](https://platform.openai.com/docs/api-reference/audio)
- [OpenAI Speech to Text Guide](https://platform.openai.com/docs/guides/speech-to-text)
- [gpt-4o-transcribe format issues](https://community.openai.com/t/gpt-4o-transcribe-unsupported-format-with-wav/1148957)
- [Whisper audio format support](https://github.com/openai/whisper/discussions/799)

---

**Статус:** ✅ Готов к реализации
**Следующий шаг:** Ожидание подтверждения для начала разработки
