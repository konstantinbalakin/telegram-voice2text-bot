# Implementation Plan: Обрезка ответа DeepSeek при обработке длинных текстов

**Track ID:** llm-output-truncation_20260221
**Spec:** [spec.md](./spec.md)
**Created:** 2026-02-21
**Status:** [~] In Progress

## Overview

Поэтапное решение проблемы обрезки ответов DeepSeek API при обработке длинных транскрипций. Фаза 1 — базовые улучшения (max_tokens + детекция обрезки). Фаза 2 — выбор модели через ENV. Фаза 3 — стратегии для сверхдлинных текстов (только для `deepseek-chat`).

## Phase 1: Базовые улучшения (max_tokens + finish_reason)

Увеличить лимит output-токенов до максимума модели и добавить обработку обрезки.

### Tasks

- [x] Task 1.1: Написать тесты для детекции `finish_reason == "length"` в `DeepSeekProvider.refine_text()`
  - Тест: при `finish_reason == "length"` метод возвращает результат + логирует warning
  - Тест: при `finish_reason == "stop"` метод работает как раньше
  - Файл: `tests/unit/test_llm_service.py`

- [x] Task 1.2: Добавить обработку `finish_reason` в `DeepSeekProvider.refine_text()`
  - В `src/services/llm_service.py`: после парсинга ответа проверить `choices[0].finish_reason`
  - Если `"length"` — залогировать `logger.warning(...)` с деталями (input/output tokens, text_length)
  - Возвращать `refine_text` результат с метаданными о truncation (dataclass или named tuple)

- [x] Task 1.3: Увеличить `llm_max_tokens` по умолчанию с 4000 до 8192
  - В `src/config.py`: изменить `default=4000` → `default=8192`

- [x] Task 1.4: Обновить `text_processor.py` для обработки truncation-метаданных
  - Если `finish_reason == "length"` — добавить в конец текста пометку `"\n\n⚠️ Текст был обрезан из-за ограничений модели"`
  - Применить ко всем режимам кроме summary (summary не затронут обрезкой)

### Verification

- [ ] Тесты на finish_reason проходят
- [ ] При max_tokens=8192 длинные тексты обрабатываются полностью (ручная проверка)
- [ ] При обрезке пользователь видит предупреждение

## Phase 2: Выбор модели DeepSeek через ENV

Добавить возможность переключения между `deepseek-chat` и `deepseek-reasoner` через конфигурацию.

### Tasks

- [x] Task 2.1: Написать тесты для конфигурации модели
  - Тест: `LLM_MODEL=deepseek-reasoner` корректно парсится
  - Тест: `DeepSeekProvider` использует правильную модель из конфигурации
  - Тест: max_tokens адаптируется к модели (8192 для chat, 64000 для reasoner)

- [x] Task 2.2: Обновить конфигурацию в `src/config.py`
  - Добавить `llm_max_tokens_reasoner: int = Field(default=64000)` — отдельный лимит для reasoner
  - Добавить валидацию: если `llm_model == "deepseek-reasoner"`, использовать `llm_max_tokens_reasoner`
  - Обновить описания полей для ясности

- [x] Task 2.3: Обновить `DeepSeekProvider` для поддержки разных моделей
  - `max_tokens` должен автоматически подбираться в зависимости от модели
  - Если модель `deepseek-reasoner` — использовать `max_tokens_reasoner` из конфига
  - Если модель `deepseek-chat` — использовать `max_tokens` из конфига (8192)

- [x] Task 2.4: Обновить конфигурационные файлы и документацию
  - Обновить `.env.example` — добавить новые переменные с комментариями
  - Обновить `.env.example.short` — добавить новые переменные
  - Обновить `.github/workflows/deploy.yml` — добавить новые ENV-переменные в workflow
  - Описать разницу между chat и reasoner (лимиты, стоимость, качество)

### Verification

- [ ] Тесты конфигурации проходят
- [ ] Переключение модели через `.env` работает корректно
- [ ] При `deepseek-reasoner` используется лимит 64K

## Phase 3: Стратегии для сверхдлинных текстов (только deepseek-chat)

Реализовать эвристическую оценку токенов и стратегии обработки при превышении 8K output. Актуально только если основная модель — `deepseek-chat`.

### Tasks

- [x] Task 3.1: Написать тесты для эвристической оценки токенов
  - Тест: функция `estimate_output_tokens(text, prompt)` возвращает приблизительное количество токенов
  - Тест: для русского текста ~1 токен ≈ 2-4 символа (калибровка по реальным данным из логов)
  - Тест: для текста 22396 символов оценка близка к реальным 16047 токенам (из логов)
  - Файл: `tests/unit/test_token_estimator.py`

- [x] Task 3.2: Реализовать функцию оценки токенов
  - Новый модуль `src/services/token_estimator.py`
  - Функция `estimate_tokens(text: str) -> int` — эвристика по символам
  - Функция `will_exceed_output_limit(text: str, prompt: str, max_output_tokens: int) -> bool`
  - Эвристика: для русского текста ~1 токен ≈ 3 символа (с запасом)

- [x] Task 3.3: Написать тесты для chunking
  - Тест: `split_text_into_chunks(text, max_chars)` корректно разбивает текст
  - Тест: разбиение происходит на границах предложений (по `.`, `!`, `?`)
  - Тест: каждый чанк не превышает `max_chars`
  - Тест: склейка чанков `merge_processed_chunks(chunks)` не теряет текст
  - Файл: `tests/unit/test_text_chunking.py`

- [x] Task 3.4: Реализовать chunking
  - Новый модуль `src/services/text_chunking.py`
  - `split_text_into_chunks(text: str, max_chars: int) -> list[str]` — разбиение по символам с выравниванием на границы предложений
  - `merge_processed_chunks(chunks: list[str]) -> str` — склейка обработанных чанков
  - Без семантического анализа — чисто по количеству символов

- [x] Task 3.5: Написать тесты для стратегии обработки длинных текстов
  - Тест: при `deepseek-chat` + длинный текст + стратегия "reasoner" → переключение на reasoner
  - Тест: при `deepseek-chat` + длинный текст + стратегия "chunking" → разбиение на чанки
  - Тест: при `deepseek-reasoner` → стратегии не применяются (bypass)
  - Тест: при режиме summary → стратегии не применяются (bypass)

- [x] Task 3.6: Добавить конфигурацию стратегии в `src/config.py` и ENV-файлы
  - `llm_long_text_strategy: str = Field(default="reasoner", description="Strategy for long texts: reasoner, chunking")`
  - `llm_chunk_max_chars: int = Field(default=8000, description="Max chars per chunk for chunking strategy")`
  - Обновить `.env.example`, `.env.example.short`, `.github/workflows/deploy.yml`

- [x] Task 3.7: Интегрировать стратегии в `text_processor.py`
  - Перед вызовом `_refine_with_custom_prompt()` проверять `will_exceed_output_limit()`
  - Если превышает и модель `deepseek-chat`:
    - Стратегия "reasoner": переключить модель на `deepseek-reasoner` для этого запроса
    - Стратегия "chunking": разбить текст, обработать каждый чанк, склеить
  - Если модель `deepseek-reasoner` или режим summary — не применять стратегии

### Verification

- [ ] Тесты оценки токенов проходят
- [ ] Тесты chunking проходят
- [ ] Тесты стратегий проходят
- [ ] Текст 22396 символов корректно обрабатывается через chunking (ручная проверка)
- [ ] При переключении на reasoner для длинного текста — полный результат без обрезки

## Phase 4: Обновить CLAUDE.md

### Tasks

- [x] Task 4.1: добавь инфу, что по переменным нужно добавлять не только в .env.example, но и в .env.example.short и в .github/workflows/deploy.yml

## Final Verification

- [ ] Все acceptance criteria из spec.md выполнены
- [ ] Все тесты проходят (`uv run pytest tests/unit/ -v`)
- [ ] Линтеры чистые (`uv run ruff check src/`, `uv run black --check src/ tests/`)
- [ ] Типы верные (`uv run mypy src/`)
- [ ] Документация обновлена
- [ ] Ready for review

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
