# Python Style Guide

Основан на текущих конфигурациях проекта (pyproject.toml).

## Formatting

### Black

- **Line length**: 100
- **Target version**: Python 3.11

```toml
[tool.black]
line-length = 100
target-version = ["py311"]
```

### Ruff

- **Line length**: 100
- **Target version**: Python 3.11

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
```

## Type Checking

### mypy

- **Python version**: 3.11
- **Strict mode**: `disallow_untyped_defs = true`
- Warn on return any: enabled
- Warn on unused configs: enabled

```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

### Правила типизации

- Все функции и методы должны иметь полные аннотации типов
- Используйте `typing` модуль для сложных типов
- `Optional[X]` вместо `X | None` для совместимости
- Generics: `list[str]`, `dict[str, Any]` (Python 3.11+ синтаксис)

## Code Organization

### Импорты

Порядок (обеспечивается Ruff):

1. Standard library
2. Third-party packages
3. Local imports

### Модули

- Каждый модуль начинается с `logger = logging.getLogger(__name__)`
- Все I/O операции — async (`async def`, `await`)
- Конфигурация через Pydantic Settings (`.env` → `config.py`)

## Naming Conventions

| Entity | Convention | Example |
| ------ | ---------- | ------- |
| Modules | snake_case | `queue_manager.py` |
| Classes | PascalCase | `QueueManager` |
| Functions | snake_case | `process_voice_message` |
| Constants | UPPER_SNAKE | `MAX_FILE_SIZE` |
| Private | _prefix | `_internal_helper` |
| Type vars | PascalCase | `MessageT` |

## Async Patterns

- Все I/O через `async`/`await`
- `asyncio.Semaphore` для контроля конкурентности
- `AsyncMock` в тестах для async-методов
- Никаких блокирующих вызовов в async-контексте

## Error Handling

- Кастомные исключения в `exceptions.py`
- Каждое исключение имеет поле `user_message`
- Иерархия: `BotError` → специализированные исключения
- Логирование ошибок через `logger.exception()`

## Testing

- Framework: pytest + pytest-asyncio
- Async mode: `auto` (все async-тесты запускаются автоматически)
- DB тесты: in-memory SQLite
- Моки: `unittest.mock.AsyncMock` для async
- Покрытие: pytest-cov

```bash
# Запуск тестов
TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v

# С покрытием
TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ --cov=src -v
```

## Documentation

- Docstrings не обязательны для очевидного кода
- Комментарии только там, где логика неочевидна
- Type annotations заменяют документацию типов
