# Implementation Plan: PR Review Fixes

**Track ID:** pr-review-fixes_20260219
**Spec:** [spec.md](./spec.md)
**Created:** 2026-02-19
**Status:** [x] Complete

## Overview

Исправления сгруппированы в 5 фаз по логическим областям: critical баги, обработка ошибок, комментарии/docstrings, тесты, код quality. Каждая фаза завершается прогоном тестов.

## Phase 1: Critical Bugs

Исправление багов, влияющих на корректность работы.

### Tasks

- [x] Task 1.1: Исправить fallback-промпт в `create_magic` (text_processor.py:371-373) — заменить HTML-инструкции на Markdown
- [x] Task 1.2: Исправить двойную конвертацию в `generate_pdf_from_text` (pdf_generator.py:298-324) — метод формирует HTML `<p>` теги, а `generate_pdf()` повторно пропускает через `convert_markdown_to_html()`. Нужно вызывать `create_styled_html` напрямую или передавать plain text минуя конвертер
- [x] Task 1.3: Заменить 3 пустых `except: pass` блока на логирование ошибок (callbacks.py:235-236, 750-751, 962-963)

### Verification

- [x] Все существующие тесты проходят
- [x] Fallback-промпт содержит Markdown-инструкции
- [x] `generate_pdf_from_text` не вызывает двойную конвертацию

## Phase 2: Error Handling

Улучшение обработки ошибок в ExportService и download-хендлерах.

### Tasks

- [x] Task 2.1: Добавить `ExportError` в exceptions.py и обработку ошибок в каждый метод ExportService (export_md, export_txt, export_pdf, export_docx)
- [x] Task 2.2: Разделить широкий `except Exception` в `handle_download_format`
- [x] Task 2.3: Исправить двойной `query.answer()` для download и download_fmt
- [x] Task 2.4: Добавить логирование в ExportService (done in 2.1)
- [x] Task 2.5: Добавить валидацию формата в `handle_download_format`
- [x] Task 2.6: Добавить `logger.warning` при fallback `file_number`
- [x] Task 2.7: Заменить `assert self.text_processor is not None` на graceful error
- [x] Task 2.8: Добавить `exc_info=True` к logger.error вызовам

### Verification

- [x] Все тесты проходят
- [x] ExportService логирует операции и ошибки
- [x] Пользователь получает информативные сообщения при ошибках экспорта

## Phase 3: Comments & Docstrings

Обновление устаревших комментариев и docstrings после миграции HTML -> Markdown.

### Tasks

- [x] Task 3.1: Обновить 4 комментария "Sanitize HTML" на актуальные
- [x] Task 3.2: Обновить docstring класса PDFGenerator
- [x] Task 3.3: Обновить docstring `export_pdf` (done in 2.1)
- [x] Task 3.4: Обновить docstring `_add_formatted_text` — добавить inline code
- [x] Task 3.5: Обновить docstring `handle_mode_change` — добавить "magic" и убрать "Phase 2"
- [x] Task 3.6: Обновить docstring `handle_back` — добавить "download formats"
- [x] Task 3.7: Добавить ссылку на Telegram API в комментарий `MARKDOWNV2_SPECIAL_CHARS`
- [x] Task 3.8: Обновить docstring `sanitize_markdown` — уточнить обработку `<u>`
- [x] Task 3.9: Добавить документацию незакрытых маркеров в docstring `escape_markdownv2`
- [x] Task 3.10: Удалить избыточные inline-комментарии в `_markdown_to_docx`
- [x] Task 3.11: Удалить избыточные комментарии Row 1/2/3 в `create_download_format_keyboard`

### Verification

- [x] Все комментарии соответствуют актуальному коду
- [x] Нет упоминаний HTML в docstrings новых функций

## Phase 4: Tests

Добавление недостающих тестов для error paths и edge cases.

### Tasks

- [x] Task 4.1: Добавить тесты маршрутизации `download` и `download_fmt`
- [x] Task 4.2: Добавить тест ошибки экспорта в `handle_download_format`
- [x] Task 4.3: Добавить тест ошибки `edit_message_text` в `handle_download_menu`
- [x] Task 4.4: Добавить тест `state_not_found` для `handle_download_format`
- [x] Task 4.5: Исправить неправильные имена настроек в тесте
- [x] Task 4.6: Добавить тесты вложенного markdown
- [x] Task 4.7: Добавить тест для вложенных HTML-тегов
- [x] Task 4.8: Добавить тест underline `__text__` для `convert_markdown_to_html`

### Verification

- [x] Все новые тесты проходят
- [x] Error paths в download-хендлерах покрыты тестами
- [x] mypy не выдаёт ошибок (2 pre-existing faster_whisper import-not-found — not related to this track)

## Phase 5: Code Quality

Мелкие улучшения качества кода.

### Tasks

- [x] Task 5.1: Внедрить DI для PDFGenerator в ExportService — принимать через конструктор, обновить main.py
- [x] Task 5.2: Защитить `convert_markdown_to_html` от `None` (pdf_generator.py:38) — `return text or ""` (done in Phase 1)
- [x] Task 5.3: Закрывать BytesIO после отправки в `handle_download_format` — использовать `try/finally: file_obj.close()` (done in Phase 2)
- [x] Task 5.4: Вынести дублирующиеся хелперы `_make_query`, `_make_update`, `_make_state`, `_make_variant`, `_make_usage`, `_make_user` из test_callbacks.py и test_callbacks_download.py в tests/conftest.py или tests/helpers.py
- [x] Task 5.5: Исправить fallback PDF→TXT: добавить пояснение в caption или возвращаемый формат-лейбл (pdf_generator.py:342-352)

### Verification

- [x] Все тесты проходят (726 passed)
- [x] ruff, black, mypy чистые (mypy: 2 pre-existing faster_whisper errors only)
- [x] Нет дублирования тест-хелперов

## Final Verification

- [x] Все acceptance criteria met
- [x] Все 726 тестов проходят
- [x] ruff check src/ — чисто
- [x] black --check src/ tests/ — чисто
- [x] mypy src/ — чисто (2 pre-existing faster_whisper import-not-found)
- [ ] Повторное ревью не выявляет новых critical issues

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
