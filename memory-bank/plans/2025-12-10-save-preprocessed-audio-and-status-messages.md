# План: Сохранение обработанного аудио + улучшение статусных сообщений

**Дата:** 2025-12-10
**Статус:** Утвержден
**Приоритет:** Средний

---

## Проблема

### Проблема 1: Неоптимальная ретранскрибация
Сейчас при ретранскрибации используется оригинальное аудио (без preprocessing), что приводит к:
- Более медленной обработке (не используются оптимизации: моно, ускорение, Opus)
- Нелогичности: preprocessing применяется при первой транскрипции, но не используется при повторной

**Текущий flow:**
1. Загрузка оригинала → Сохранение оригинала (`save_audio_file_for_retranscription`)
2. Применение preprocessing → Транскрипция обработанного файла
3. При ретранскрибации: загрузка оригинала → preprocessing заново

### Проблема 2: Неинформативные статусные сообщения
После загрузки файла пользователь видит статус "📥 Загружаю файл...", который не обновляется во время preprocessing.

**Текущий flow статусов:**
```
"📥 Загружаю файл..."
  → (загрузка)
  → (preprocessing - статус не меняется!)
  → "⚙️ Начинаю обработку..." (или прогресс-бар)
```

---

## Решение

### Часть 1: Сохранять обработанный файл вместо оригинала

**Подход:** Переместить сохранение файла из `voice_message_handler` в `_process_transcription` после preprocessing.

### Часть 2: Добавить статус "Оптимизирую аудио"

**Подход:** Обновлять статусное сообщение перед вызовом `preprocess_audio()`.

---

## Детальный план реализации

### Шаг 1: Убрать сохранение оригинала из `voice_message_handler`

**Файл:** `src/bot/handlers.py`

**Изменения:**

1. **Удалить вызов сохранения после загрузки voice message** (строки ~500-502):
   ```python
   # УДАЛИТЬ ЭТИ СТРОКИ:
   persistent_path = save_audio_file_for_retranscription(
       Path(file_path), usage.id, voice.file_id
   )
   ```

2. **Удалить обновление БД с original_file_path** (строки ~507-511):
   ```python
   # УДАЛИТЬ параметр original_file_path:
   await usage_repo.update(
       usage_id=usage.id,
       voice_duration_seconds=duration_seconds,
       # original_file_path=str(persistent_path) if persistent_path else None,  # УДАЛИТЬ
   )
   ```

3. **Повторить для audio_message_handler** (аналогичные изменения в строках ~830-843):
   - Удалить вызов `save_audio_file_for_retranscription`
   - Удалить параметр `original_file_path` в `usage_repo.update`

**Итого:** 4 удаления в двух хэндлерах (voice и audio)

---

### Шаг 2: Добавить сохранение обработанного файла в `_process_transcription`

**Файл:** `src/bot/handlers.py`, метод `_process_transcription` (строка ~1237)

**Добавить код после preprocessing** (после строки ~1272):

```python
# === PREPROCESSING: Apply audio transformations ===
processed_path = request.file_path
try:
    # 1. Update status before preprocessing
    await request.status_message.edit_text("🔧 Оптимизирую аудио...")

    # 2. Apply preprocessing
    processed_path = self.audio_handler.preprocess_audio(request.file_path)
    if processed_path != request.file_path:
        logger.info(f"Audio preprocessed: {processed_path.name}")
except Exception as e:
    logger.warning(f"Audio preprocessing failed: {e}, using original")
    processed_path = request.file_path

# 3. Save preprocessed file for retranscription (если включено)
persistent_path = None
if settings.enable_retranscribe and processed_path != request.file_path:
    # Save preprocessed (optimized) file instead of original
    try:
        persistent_path = save_audio_file_for_retranscription(
            processed_path, request.usage_id, request.file_path.stem  # file_id из stem
        )

        # Update database with preprocessed file path
        async with get_session() as session:
            usage_repo = UsageRepository(session)
            await usage_repo.update(
                usage_id=request.usage_id,
                original_file_path=str(persistent_path) if persistent_path else None,
            )
        logger.info(f"Saved preprocessed audio for retranscription: {persistent_path}")
    except Exception as e:
        logger.error(f"Failed to save preprocessed audio: {e}", exc_info=True)
elif settings.enable_retranscribe and processed_path == request.file_path:
    # No preprocessing applied, save original as before
    try:
        persistent_path = save_audio_file_for_retranscription(
            request.file_path, request.usage_id, request.file_path.stem
        )

        async with get_session() as session:
            usage_repo = UsageRepository(session)
            await usage_repo.update(
                usage_id=request.usage_id,
                original_file_path=str(persistent_path) if persistent_path else None,
            )
        logger.info(f"Saved original audio for retranscription: {persistent_path}")
    except Exception as e:
        logger.error(f"Failed to save original audio: {e}", exc_info=True)
```

**Важные детали:**
- Сохраняем файл **после** preprocessing, чтобы сохранить оптимизированную версию
- Проверяем `processed_path != request.file_path` чтобы понять, был ли preprocessing
- Если preprocessing не применялся (disabled или ошибка), сохраняем оригинал
- Обновляем БД сразу после сохранения
- Используем `request.file_path.stem` для извлечения file_id из имени файла

**Альтернатива:** Если хотите сохранять оригинал в любом случае:
```python
# Save file for retranscription (preprocessed if available, original otherwise)
if settings.enable_retranscribe:
    file_to_save = processed_path if processed_path != request.file_path else request.file_path
    # ... rest of the code
```

---

### Шаг 3: Исправить сигнатуру `save_audio_file_for_retranscription`

**Проблема:** Функция ожидает `file_id: str`, но у нас есть только `processed_path`.

**Решение:** Использовать уникальный идентификатор из `usage_id` вместо `file_id`.

**Файл:** `src/bot/handlers.py`, функция `save_audio_file_for_retranscription` (строка ~109)

**Вариант 1: Изменить сигнатуру (рекомендуется)**

```python
def save_audio_file_for_retranscription(
    temp_file_path: Path, usage_id: int, file_identifier: str
) -> Optional[Path]:
    """Save audio file to persistent storage for retranscription.

    Args:
        temp_file_path: Temporary file path (original or preprocessed)
        usage_id: Usage record ID
        file_identifier: File identifier (telegram file_id or unique suffix)

    Returns:
        Path to saved file or None if saving failed or retranscription is disabled
    """
    if not settings.enable_retranscribe:
        logger.debug("Retranscription disabled, skipping file save")
        return None

    try:
        # Create persistent directory if doesn't exist
        persistent_dir = Path(settings.persistent_audio_dir)
        persistent_dir.mkdir(parents=True, exist_ok=True)

        # Create unique filename
        file_extension = temp_file_path.suffix or ".opus"  # Default to .opus for preprocessed
        permanent_path = persistent_dir / f"{usage_id}_{file_identifier}{file_extension}"

        # Copy file to permanent storage
        shutil.copy2(temp_file_path, permanent_path)
        logger.info(f"Audio file saved for retranscription: {permanent_path}")

        return permanent_path

    except Exception as e:
        logger.error(f"Failed to save audio file for retranscription: {e}", exc_info=True)
        return None
```

**Вариант 2: Извлечь file_id из имени временного файла**

Если имя файла содержит file_id (формат: `{file_id}_{uuid}.ext`), можно извлечь его:
```python
file_id = temp_file_path.stem.split('_')[0]  # Extract file_id from filename
```

Но это менее надежно. Лучше передавать явно.

---

### Шаг 4: Обновить вызовы в `_process_transcription`

**Используем обновленную сигнатуру:**

```python
# После preprocessing (в блоке кода из Шага 2):
persistent_path = save_audio_file_for_retranscription(
    processed_path,
    request.usage_id,
    f"preprocessed_{uuid.uuid4().hex[:8]}"  # Уникальный идентификатор
)
```

Или, если хотите использовать оригинальный file_id:
```python
# Извлечь file_id из имени оригинального файла
original_file_id = request.file_path.stem.split('_')[0]

persistent_path = save_audio_file_for_retranscription(
    processed_path,
    request.usage_id,
    original_file_id
)
```

**Рекомендация:** Использовать `original_file_id`, чтобы связать с оригинальным файлом Telegram.

---

### Шаг 5: Улучшить статусные сообщения (Часть 2)

**Файл:** `src/bot/handlers.py`, метод `_process_transcription` (строка ~1237)

**Текущий код** (строка ~1264):
```python
try:
    # === PREPROCESSING: Apply audio transformations ===
    processed_path = request.file_path
    try:
        processed_path = self.audio_handler.preprocess_audio(request.file_path)
        if processed_path != request.file_path:
            logger.info(f"Audio preprocessed: {processed_path.name}")
    except Exception as e:
        logger.warning(f"Audio preprocessing failed: {e}, using original")
        processed_path = request.file_path
```

**Улучшенный код:**
```python
try:
    # === PREPROCESSING: Apply audio transformations ===
    processed_path = request.file_path
    try:
        # Update status before preprocessing
        should_preprocess = (
            settings.audio_convert_to_mono or
            settings.audio_speed_multiplier != 1.0
        )

        if should_preprocess:
            await request.status_message.edit_text("🔧 Оптимизирую аудио...")
            logger.info("Starting audio preprocessing...")

        processed_path = self.audio_handler.preprocess_audio(request.file_path)

        if processed_path != request.file_path:
            logger.info(f"Audio preprocessed: {processed_path.name}")
    except Exception as e:
        logger.warning(f"Audio preprocessing failed: {e}, using original")
        processed_path = request.file_path

    # [ШАГ 2: Сохранение файла - вставить здесь код из Шага 2]

    # Update status before transcription
    await request.status_message.edit_text("⚙️ Обрабатываю запись...")

    # === TRANSCRIPTION: Get draft or final transcription ===
    result = await self.transcription_router.transcribe(
        processed_path,
        request.context,
    )
```

**Что изменилось:**
1. Добавлена проверка `should_preprocess` чтобы не показывать статус если preprocessing отключен
2. Статус "🔧 Оптимизирую аудио..." показывается перед preprocessing
3. Статус "⚙️ Обрабатываю запись..." показывается перед транскрипцией
4. Добавлено логирование "Starting audio preprocessing..."

**Flow статусов после изменений:**
```
"📥 Загружаю файл..."
  → (загрузка завершена)
  → "🔧 Оптимизирую аудио..."
  → (preprocessing)
  → "⚙️ Обрабатываю запись..."
  → (прогресс-бар от ProgressTracker)
```

---

### Шаг 6: Проверить ретранскрибацию

**Файл:** `src/bot/retranscribe_handlers.py`

**Убедиться, что код корректно работает с обработанным файлом** (строки ~145-150):

```python
# Check file exists on disk
audio_path = Path(usage.original_file_path)
if not audio_path.exists():
    logger.error(f"Audio file not found: {audio_path}")
    await query.answer("Аудио файл не найден", show_alert=True)
    return
```

**Комментарий:** Несмотря на название поля `original_file_path`, теперь там будет путь к **обработанному** файлу. Это ожидаемое поведение.

**Опционально:** Можно добавить логирование для ясности:
```python
logger.info(
    f"Loading audio for retranscription: {audio_path} "
    f"(preprocessed: {audio_path.suffix == '.opus'})"
)
```

---

## Итоговая структура изменений

### Файлы для изменения:

1. **`src/bot/handlers.py`** (основной файл):
   - Функция `save_audio_file_for_retranscription` (строка ~109): изменить сигнатуру
   - Метод `voice_message_handler` (строки ~500-512): удалить сохранение оригинала
   - Метод `audio_message_handler` (строки ~830-843): удалить сохранение оригинала
   - Метод `_process_transcription` (строки ~1264-1278): добавить статусы и сохранение обработанного

2. **`src/bot/retranscribe_handlers.py`** (опционально):
   - Функция `handle_retranscribe` (строки ~145-150): добавить логирование

---

## Порядок внесения изменений

1. **Шаг 3 (сигнатура):** Изменить `save_audio_file_for_retranscription` - основа для остальных изменений
2. **Шаг 1 (удаление):** Убрать сохранение из `voice_message_handler` и `audio_message_handler`
3. **Шаг 5 (статусы):** Добавить статус "Оптимизирую аудио..." в `_process_transcription`
4. **Шаг 2 (сохранение):** Добавить сохранение обработанного файла в `_process_transcription`
5. **Шаг 6 (проверка):** Добавить логирование в `handle_retranscribe` (опционально)

---

## Тестирование

### Ручные тесты:

1. **Тест 1: Первая транскрипция с preprocessing**
   - Отправить голосовое сообщение
   - **Ожидается:**
     - Статус "Загружаю файл..." → "Оптимизирую аудио..." → "Обрабатываю запись..."
     - В `./data/audio_files/` должен появиться файл с расширением `.opus` (если применялся preprocessing)
     - В БД `usages.original_file_path` должен быть путь к `.opus` файлу

2. **Тест 2: Ретранскрибация использует обработанный файл**
   - Нажать кнопку "Переобработать"
   - Выбрать метод (free/paid)
   - **Ожидается:**
     - Ретранскрибация начинается сразу (без повторного preprocessing)
     - В логах: "Loading audio for retranscription: .../123_file_id.opus (preprocessed: True)"
     - Скорость ретранскрибации соответствует обработанному файлу

3. **Тест 3: Первая транскрипция без preprocessing**
   - Установить `AUDIO_CONVERT_TO_MONO=false`, `AUDIO_SPEED_MULTIPLIER=1.0`
   - Отправить голосовое сообщение
   - **Ожидается:**
     - Статус "Загружаю файл..." → "Обрабатываю запись..." (без "Оптимизирую")
     - В `./data/audio_files/` должен быть оригинальный файл (`.ogg` или другой формат)

4. **Тест 4: Ретранскрибация отключена**
   - Установить `ENABLE_RETRANSCRIBE=false`
   - Отправить голосовое сообщение
   - **Ожидается:**
     - Файл НЕ сохраняется в `./data/audio_files/`
     - В БД `usages.original_file_path` = NULL

### Проверка логов:

Искать в логах:
```
✅ Успешные кейсы:
- "Audio preprocessed: {file}_mono.opus" или "{file}_speed1.2x.opus"
- "Saved preprocessed audio for retranscription: ./data/audio_files/123_file_id.opus"
- "Loading audio for retranscription: ./data/audio_files/123_file_id.opus (preprocessed: True)"

❌ Ошибки:
- "Failed to save preprocessed audio: ..."
- "Audio file not found: ..."
```

---

## Риски и митигация

### Риск 1: Потеря оригинальных файлов
**Вероятность:** Средняя
**Влияние:** Низкое (preprocessing обратим)
**Митигация:**
- Preprocessing использует lossless операции (моно конверсия, ускорение)
- Можно восстановить из Telegram если критично
- Настройка `ENABLE_RETRANSCRIBE` позволяет отключить сохранение

### Риск 2: Ошибки при сохранении обработанного файла
**Вероятность:** Низкая
**Влияние:** Среднее (ретранскрибация недоступна)
**Митигация:**
- Обернуть в `try-except` с логированием
- Fallback: если сохранение не удалось, ретранскрибация просто не будет доступна
- Не влияет на основную транскрипцию

### Риск 3: Изменение размера файлов
**Вероятность:** Высокая (ожидаемое поведение)
**Влияние:** Положительное (меньше места на диске)
**Митигация:**
- Opus codec + mono + 32kbps = обычно меньше оригинала
- Monitoring: проверить размеры файлов в `./data/audio_files/` после деплоя

---

## Критерии успеха

✅ Статус "Оптимизирую аудио..." показывается перед preprocessing
✅ Обработанный файл сохраняется в `./data/audio_files/`
✅ Ретранскрибация использует обработанный файл (без повторного preprocessing)
✅ Все существующие тесты проходят
✅ Размер сохраненных файлов меньше оригинальных (при включенном preprocessing)
✅ Функционал ретранскрибации работает корректно с обработанными файлами

---

## Вопросы для уточнения

1. **Сохранение оригинала:** Точно уверены, что оригинал не нужен? (Рекомендация: Вариант 1 без оригинала)
2. **Naming:** Переименовать поле `original_file_path` → `stored_file_path` для ясности? (Опционально, требует миграции БД)
3. **Статус при отключенном preprocessing:** Показывать ли какой-то статус между загрузкой и транскрипцией? (Сейчас: нет)

---

## Следующие шаги после реализации

1. Задеплоить изменения на VPS
2. Мониторить логи на наличие ошибок сохранения файлов
3. Проверить размер директории `./data/audio_files/` через неделю
4. Собрать feedback от пользователей по скорости ретранскрибации
5. Рассмотреть возможность автоматической очистки старых файлов (>30 дней)

---

## Альтернативные решения (отклонены)

- **Вариант 2:** Сохранять оба файла - отклонено из-за удвоения места на диске
- **Вариант 3:** Повторный preprocessing при ретранскрибации - отклонено из-за неэффективности

---

**Автор плана:** Claude Code
**Дата создания:** 2025-12-10
**Версия:** 1.0
