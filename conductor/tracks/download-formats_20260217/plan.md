# Implementation Plan: Download Transcription in Multiple Formats

**Track ID:** download-formats_20260217
**Spec:** [spec.md](./spec.md)
**Created:** 2026-02-17
**Status:** [x] Complete

## Overview

Реализация кнопки "Скачать" с выбором формата (MD, TXT, PDF, DOCX). Используем существующий паттерн: кнопка → подменю → действие → отправка файла. Новый сервис `ExportService` генерирует файлы, callback-обработчики управляют UI.

## Phase 1: Foundation — Зависимости, конфиг, actions

Добавить зависимость python-docx, feature flag, и зарегистрировать новые callback actions.

### Tasks

- [x] Task 1.1: Добавить `python-docx` в зависимости проекта (`pyproject.toml`)
- [x] Task 1.2: Добавить feature flag `enable_download_button: bool = False` в `src/config.py` (секция Interactive Transcription Features)
- [x] Task 1.3: Добавить `"download"` и `"download_fmt"` в `_VALID_ACTIONS` в `src/bot/keyboards.py`
- [x] Task 1.4: Добавить валидацию `_VALID_DOWNLOAD_FORMATS = frozenset(["md", "txt", "pdf", "docx"])` в `src/bot/keyboards.py` и проверку в `decode_callback_data()`

### Verification

- [x] `uv sync` проходит без ошибок
- [x] `python -c "import docx"` работает
- [x] Unit-тесты keyboards проходят (encode/decode новых actions)

## Phase 2: Export Service — Генерация файлов в 4 форматах

Создать сервис экспорта, который принимает текст и возвращает файл в нужном формате. TDD: тесты → реализация.

### Tasks

- [x] Task 2.1: Написать тесты для `ExportService` (`tests/unit/test_export_service.py`): генерация MD, TXT, PDF, DOCX; проверка содержимого; обработка пустого текста
- [x] Task 2.2: Создать `src/services/export_service.py` с классом `ExportService`:
  - `export_md(text, filename) -> io.BytesIO` — текст как есть в .md
  - `export_txt(text, filename) -> io.BytesIO` — текст с удалённой markdown-разметкой (strip **bold**, *italic*, #headers, bullet points → plain text)
  - `export_pdf(text, filename) -> io.BytesIO` — через существующий `PDFGenerator`
  - `export_docx(text, filename) -> io.BytesIO` — markdown → docx (заголовки, списки, параграфы) через `python-docx`
  - `export(text, format, filename) -> io.BytesIO` — диспетчер по формату
- [x] Task 2.3: Реализовать метод `_strip_markdown(text) -> str` для TXT-формата (удаление **, *, #, •, нумерации списков, inline code)
- [x] Task 2.4: Реализовать метод `_markdown_to_docx(text, filename) -> io.BytesIO` для DOCX-формата (парсинг markdown → python-docx: заголовки H1-H3, bullet lists, numbered lists, bold, italic, параграфы)
- [x] Task 2.5: Убедиться, что все тесты проходят

### Verification

- [x] `TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/test_export_service.py -v` — все тесты зелёные
- [x] Каждый формат корректно генерирует BytesIO с установленным `.name`

## Phase 3: Keyboard & UI — Кнопка "Скачать" и подменю

Добавить кнопку в основную клавиатуру и создать подменю выбора формата.

### Tasks

- [x] Task 3.1: Написать/обновить тесты клавиатуры для кнопки "Скачать" и подменю форматов (`tests/unit/test_keyboards.py`)
- [x] Task 3.2: Добавить кнопку "📥 Скачать" в `create_transcription_keyboard()` (Row 7, перед retranscribe, условие: `settings.enable_download_button`)
- [x] Task 3.3: Создать функцию `create_download_format_keyboard(usage_id: int) -> InlineKeyboardMarkup` в `keyboards.py`:
  - 4 кнопки в 2 ряда: `[📄 TXT] [📝 MD]` / `[📕 PDF] [📘 DOCX]`
  - Кнопка "◀ Назад" внизу (action=`back`)
  - callback_data: `download_fmt:{usage_id}:fmt=txt` и т.д.
- [x] Task 3.4: Убедиться, что callback_data укладывается в 64 байта для всех форматов

### Verification

- [x] Unit-тесты keyboards проходят
- [x] Кнопка появляется в правильной позиции
- [x] Подменю содержит 4 формата + "Назад"

## Phase 4: Callback Handlers — Обработка нажатий

Реализовать обработчики для действий `download` и `download_fmt`.

### Tasks

- [x] Task 4.1: Написать тесты для callback-обработчиков скачивания (`tests/unit/test_callbacks_download.py`): нажатие "Скачать" показывает подменю; выбор формата отправляет файл; кнопка "Назад" возвращает основную клавиатуру
- [x] Task 4.2: Добавить метод `handle_download_menu()` в `CallbackHandlers`:
  - Получить state и текущий текст
  - Заменить клавиатуру на подменю форматов (`create_download_format_keyboard`)
  - Ответить `query.answer("Выберите формат")`
- [x] Task 4.3: Добавить метод `handle_download_format()` в `CallbackHandlers`:
  - Декодировать формат из callback_data (`fmt` параметр)
  - Получить текущий активный вариант текста из `variant_repo`
  - Вызвать `ExportService.export(text, format, filename)`
  - Отправить файл через `context.bot.send_document()`
  - Вернуть основную клавиатуру
- [x] Task 4.4: Зарегистрировать новые actions в роутере `handle_callback_query()` (блок if/elif для `"download"` и `"download_fmt"`)
- [x] Task 4.5: Передать `ExportService` в `CallbackHandlers.__init__()` (опциональный параметр)

### Verification

- [x] Unit-тесты callback-обработчиков проходят
- [x] Подменю показывается при нажатии "Скачать"
- [x] Файл отправляется в правильном формате
- [x] После отправки файла возвращается основная клавиатура

## Phase 5: Integration — DI-wiring и E2E

Подключить всё в main.py и провести интеграционное тестирование.

### Tasks

- [x] Task 5.1: Создать экземпляр `ExportService` в `main.py` и передать в `callback_query_wrapper`
- [x] Task 5.2: Обновить `callback_query_wrapper` для передачи `ExportService` в `CallbackHandlers`
- [x] Task 5.3: Добавить `ENABLE_DOWNLOAD_BUTTON=true` в `.env.example` и `.env.example.short`
- [x] Task 5.4: Запустить полный набор проверок: ruff, black, mypy, pytest
- [x] Task 5.5: Обновить документацию: добавить описание кнопки "Скачать" в README или docs

### Verification

- [x] `uv run ruff check src/` — чисто
- [x] `uv run black --check src/ tests/` — чисто
- [x] `uv run mypy src/` — чисто
- [x] `TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v` — все тесты зелёные

## Final Verification

- [x] All acceptance criteria met
- [x] Tests passing
- [x] Documentation updated
- [x] Ready for review

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
