# План: Multi-Part Draft Messages для Hybrid Mode

**Дата**: 2025-11-24
**Статус**: Утверждён, готов к реализации
**Связано**: Phase 8 (Hybrid Transcription), PR #44

---

## Проблема

В hybrid mode длинный draft текст не может обновиться на refined текст:
- Draft показывается в одном `status_message`
- Если draft > 4096 символов → ошибка Telegram
- Refined показывается в нескольких новых сообщениях
- Нет способа обновить несуществующие draft сообщения

**Пример проблемы**:
```
1. Draft (длинный) → edit_text на status_message → CRASH (>4096 chars)
2. Refined (длинный) → delete status_message → send multiple messages → OK
```

---

## Решение

**Выбранный подход**: Вариант 1 - Добавить `draft_messages: list[Message]` в TranscriptionRequest

### Ключевые Изменения

1. **Структура данных**: Добавить tracking для draft сообщений
2. **Draft отправка**: Разбить длинный draft на части, отправить с заголовками
3. **Refinement**: Удалить все draft сообщения, отправить refined части
4. **Форматирование**:
   - Заголовок каждой части: "📝 Черновик - Часть 1/3"
   - Индикатор в каждой части: "🔄 Улучшаю текст..."

---

## Требования Пользователя

1. ✅ Добавить tracking для draft сообщений в TranscriptionRequest
2. ✅ Показывать draft части с заголовками "📝 Черновик - Часть 1/3"
3. ✅ Показывать "🔄 Улучшаю текст..." в каждой части

---

## Технические Детали

### Изменения в TranscriptionRequest

**Файл**: `src/services/queue_manager.py`

```python
@dataclass
class TranscriptionRequest:
    """Request for transcription processing."""

    id: str
    user_id: int
    file_path: Path
    duration_seconds: int
    context: TranscriptionContext
    status_message: Message
    user_message: Message
    usage_id: int
    draft_messages: list[Message] = field(default_factory=list)  # НОВОЕ
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
```

**Обоснование**:
- `draft_messages` хранит ссылки на все draft сообщения
- Используется только в hybrid mode для длинных текстов
- Легко очистить перед отправкой refined версии
- Не влияет на существующие flow (short audio, non-hybrid)

---

### Новый Helper Метод

**Файл**: `src/bot/handlers.py`

```python
async def _send_draft_messages(
    self,
    request: TranscriptionRequest,
    draft_text: str,
) -> None:
    """Send draft text in multiple messages if needed.

    Args:
        request: Transcription request (will populate draft_messages)
        draft_text: Draft transcription text to send
    """
    text_chunks = split_text(draft_text)

    if len(text_chunks) == 1:
        # Short draft: use status_message as before
        await request.status_message.edit_text(
            f"✅ Черновик готов:\n\n{draft_text}\n\n🔄 Улучшаю текст..."
        )
    else:
        # Long draft: send multiple messages
        # Delete status message first
        try:
            await request.status_message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete status message: {e}")

        # Send each chunk
        for i, chunk in enumerate(text_chunks, 1):
            header = f"📝 Черновик - Часть {i}/{len(text_chunks)}\n\n"
            footer = "\n\n🔄 Улучшаю текст..."
            message = await request.user_message.reply_text(header + chunk + footer)
            request.draft_messages.append(message)
            if i < len(text_chunks):
                await asyncio.sleep(0.1)  # Rate limit protection
```

---

### Обновление Логики Refinement

**Файл**: `src/bot/handlers.py`, метод `_process_transcription`

**Было** (lines 824-862):
```python
if needs_refinement and self.llm_service:
    draft_text = result.text
    # Show draft in status_message
    await request.status_message.edit_text(f"✅ Черновик готов:\n\n{draft_text}\n\n🔄 Улучшаю текст...")

    refined_text = await self.llm_service.refine_transcription(draft_text)
    final_text = refined_text

    # Split and send refined
    text_chunks = split_text(refined_text)
    if len(text_chunks) == 1:
        await request.status_message.edit_text(f"✨ Готово!\n\n{refined_text}")
    else:
        await request.status_message.delete()
        for chunk in text_chunks:
            await request.user_message.reply_text(...)
```

**Станет**:
```python
if needs_refinement and self.llm_service:
    draft_text = result.text

    # === STAGE 1: Send draft (handles both short and long) ===
    await self._send_draft_messages(request, draft_text)

    try:
        # === STAGE 2: Refine with LLM ===
        refined_text = await self.llm_service.refine_transcription(draft_text)
        final_text = refined_text

        # === STAGE 3: Delete draft messages and send refined ===
        # Delete all draft messages (if any)
        for msg in request.draft_messages:
            try:
                await msg.delete()
            except Exception as e:
                logger.warning(f"Failed to delete draft message: {e}")

        # If short draft was in status_message, need to handle it too
        if not request.draft_messages:
            try:
                await request.status_message.delete()
            except Exception as e:
                logger.warning(f"Failed to delete status message: {e}")

        # Send refined in parts
        text_chunks = split_text(refined_text)
        for i, chunk in enumerate(text_chunks, 1):
            prefix = "✨ Готово!\n\n" if i == 1 else ""
            header = f"📝 Часть {i}/{len(text_chunks)}\n\n" if len(text_chunks) > 1 else ""
            await request.user_message.reply_text(prefix + header + chunk)
            if i < len(text_chunks):
                await asyncio.sleep(0.1)

    except Exception as e:
        logger.error(f"LLM refinement failed: {e}")
        # Fallback: draft already visible, just notify completion
        if request.draft_messages:
            # Draft is in multiple messages, send final message
            await request.user_message.reply_text(
                "✅ Готово\n\nℹ️ (улучшение текста недоступно)"
            )
        else:
            # Draft is in status_message, update it
            try:
                await request.status_message.edit_text(
                    f"✅ Готово:\n\n{draft_text}\n\nℹ️ (улучшение текста недоступно)"
                )
            except Exception:
                pass
        final_text = draft_text
```

---

## Обработка Граничных Случаев

### 1. Короткий Draft (<4096 chars)
- **Поведение**: Используется `status_message` как раньше
- **draft_messages**: Остаётся пустым
- **При refinement**: Удаляется `status_message`, отправляются refined части

### 2. Длинный Draft (>4096 chars)
- **Поведение**: Удаляется `status_message`, отправляются draft части
- **draft_messages**: Заполняется ссылками на все части
- **При refinement**: Удаляются все `draft_messages`, отправляются refined части

### 3. Ошибка LLM После Отправки Draft
- **Если draft короткий**: Обновить `status_message` с "(улучшение недоступно)"
- **Если draft длинный**: Отправить финальное сообщение "✅ Готово (улучшение недоступно)"
- **Результат**: Пользователь видит draft как финальный результат

### 4. Ошибка Удаления Сообщений
- **Поведение**: try/except для каждого сообщения
- **Логирование**: Предупреждения в лог
- **Продолжение**: Refined сообщения отправляются в любом случае
- **Результат**: Пользователь может видеть и draft и refined (не критично)

### 5. Очень Длинный Draft (>10 частей)
- **Поведение**: Работает как обычно (split_text обрабатывает)
- **Тестирование**: Проверить расчёт места для заголовков
- **Rate Limits**: 0.1s задержка между сообщениями

---

## План Реализации

### Фаза 1: Структура Данных (15 мин)
**Файлы**: `src/services/queue_manager.py`

- [ ] Добавить `draft_messages: list[Message] = field(default_factory=list)` в TranscriptionRequest
- [ ] Обновить imports (`from telegram import Message`)
- [ ] Добавить DEBUG логирование для tracking

### Фаза 2: Helper Метод (45 мин)
**Файлы**: `src/bot/handlers.py`

- [ ] Создать метод `_send_draft_messages(request, draft_text)`
- [ ] Реализовать логику разбивки с `split_text()`
- [ ] Добавить заголовки: "📝 Черновик - Часть {i}/{total}"
- [ ] Добавить footer: "\n\n🔄 Улучшаю текст..."
- [ ] Обработать короткий draft (status_message)
- [ ] Обработать длинный draft (draft_messages)
- [ ] Добавить DEBUG логирование

### Фаза 3: Обновление Refinement Логики (45 мин)
**Файлы**: `src/bot/handlers.py`

- [ ] Заменить прямую отправку draft на вызов `_send_draft_messages()`
- [ ] Добавить удаление всех draft_messages перед refined
- [ ] Обработать случай когда draft_messages пустой (короткий draft)
- [ ] Отправить refined части с заголовками
- [ ] Добавить DEBUG логирование

### Фаза 4: Обработка Ошибок (30 мин)
**Файлы**: `src/bot/handlers.py`

- [ ] Обработать LLM ошибку после длинного draft
- [ ] Обработать LLM ошибку после короткого draft
- [ ] Обработать ошибки удаления сообщений (try/except per message)
- [ ] Добавить fallback логику
- [ ] Добавить ERROR логирование

### Фаза 5: Тестирование (30 мин)

**Ручное тестирование**:
- [ ] Короткий draft (<4096), LLM успех
- [ ] Короткий draft (<4096), LLM ошибка
- [ ] Длинный draft (>4096, 2-3 части), LLM успех
- [ ] Длинный draft (>4096, 2-3 части), LLM ошибка
- [ ] Очень длинный draft (>10 частей), LLM успех
- [ ] Проверить заголовки и форматирование
- [ ] Проверить удаление draft сообщений
- [ ] Проверить rate limits (0.1s задержки)

---

## Критерии Успеха

1. ✅ Короткий draft (<4096) работает как раньше (status_message)
2. ✅ Длинный draft (>4096) разбивается на части с заголовками
3. ✅ Каждая draft часть показывает "🔄 Улучшаю текст..."
4. ✅ При refinement все draft сообщения удаляются
5. ✅ Refined текст отправляется в новых сообщениях
6. ✅ LLM ошибки обрабатываются gracefully (draft остаётся видимым)
7. ✅ Ошибки удаления сообщений не блокируют refined отправку
8. ✅ Нет регрессий в non-hybrid режиме
9. ✅ DEBUG логирование помогает отследить жизненный цикл сообщений

---

## Риски и Митигация

| Риск | Вероятность | Влияние | Митигация |
|------|------------|---------|-----------|
| Ошибки удаления draft сообщений | Средняя | Низкое | try/except per message, продолжить отправку refined |
| Rate limits при отправке множества сообщений | Низкая | Среднее | 0.1s задержка между сообщениями, обработка RetryAfter |
| LLM ошибка после отправки длинного draft | Средняя | Низкое | Fallback: оставить draft видимым, отправить финальное сообщение |
| Регрессия в non-hybrid режиме | Очень низкая | Высокое | draft_messages используется только в hybrid, тщательное тестирование |
| Проблемы с очень длинными текстами (>10 частей) | Низкая | Низкое | split_text уже обрабатывает, проверить расчёт заголовков |

---

## Связанные Файлы

**Изменяемые**:
- `src/services/queue_manager.py` - TranscriptionRequest dataclass
- `src/bot/handlers.py` - _send_draft_messages(), _process_transcription()

**Используемые**:
- `src/bot/handlers.py` - split_text() (существующая функция)
- `src/services/llm_service.py` - LLMService.refine_transcription()
- `src/transcription/routing/strategies.py` - HybridStrategy

**Документация**:
- `memory-bank/activeContext.md` - Обновить после завершения
- `memory-bank/progress.md` - Добавить Phase 8.3
- `memory-bank/systemPatterns.md` - Документировать паттерн multi-part messages

---

## Примеры Сообщений

### Короткий Draft (<4096)
```
✅ Черновик готов:

привет это короткий тестовый текст

🔄 Улучшаю текст...
```

### Длинный Draft (2 части)
```
Сообщение 1:
📝 Черновик - Часть 1/2

[первая часть длинного текста...]

🔄 Улучшаю текст...

---

Сообщение 2:
📝 Черновик - Часть 2/2

[вторая часть длинного текста...]

🔄 Улучшаю текст...
```

### Refined (2 части)
```
Сообщение 1:
✨ Готово!

📝 Часть 1/2

[первая часть refined текста...]

---

Сообщение 2:
📝 Часть 2/2

[вторая часть refined текста...]
```

---

## Команда для Запуска в Новом Чате

```
Продолжи реализацию плана из memory-bank/plans/2025-11-24-draft-messages-multi-part.md

Используй /workflow:execute для реализации.

План одобрен, можно сразу начинать с Фазы 1.
```

---

## Статус

- [x] План создан
- [x] План одобрен
- [ ] Фаза 1: Структура данных
- [ ] Фаза 2: Helper метод
- [ ] Фаза 3: Refinement логика
- [ ] Фаза 4: Обработка ошибок
- [ ] Фаза 5: Тестирование
- [ ] Документация обновлена
- [ ] PR создан

---

**Следующий шаг**: Реализация в новом чате через `/workflow:execute`
