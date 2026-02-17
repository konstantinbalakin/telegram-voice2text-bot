# Workflow

## TDD Policy

**Уровень: Строгий**

Тесты обязательны перед реализацией. Каждая задача следует циклу:

1. **Red** — Написать тест, который падает
2. **Green** — Написать минимальный код для прохождения теста
3. **Refactor** — Улучшить код, сохраняя зелёные тесты

### Правила

- Тесты пишутся ДО кода реализации
- Нельзя мержить PR без прохождения всех тестов
- Покрытие отслеживается через pytest-cov
- Async-тесты используют pytest-asyncio с `asyncio_mode = "auto"`

## Commit Strategy

**Conventional Commits**

Формат: `<type>(<scope>): <description>`

### Типы коммитов

| Тип | Назначение |
| --- | ---------- |
| `feat` | Новая функциональность |
| `fix` | Исправление бага |
| `refactor` | Рефакторинг без изменения поведения |
| `test` | Добавление или изменение тестов |
| `docs` | Документация |
| `chore` | Обслуживание, зависимости |

### Правила

- Никогда не коммитить напрямую в `main`
- Всегда создавать feature branch
- Используйте `/commit` для автоматической генерации сообщений

## Code Review

**Обязательно для всех изменений**

- Все изменения проходят через Pull Request
- PR должен пройти CI проверки (ruff, black, mypy, pytest)
- Protected main branch — прямой push запрещён
- Pre-commit hooks обеспечивают базовое качество кода

### Чеклист PR

- [ ] Тесты написаны и проходят
- [ ] Линтеры не выдают ошибок
- [ ] mypy проходит без ошибок
- [ ] Описание PR содержит контекст изменений

## Verification Checkpoints

**Уровень: По завершении трека**

Ручная верификация требуется при завершении трека (фичи/задачи целиком). Промежуточные фазы и задачи проверяются автоматически через CI.

### Процесс верификации трека

1. Все тесты проходят (`uv run pytest tests/unit/ -v`)
2. Линтеры чистые (`uv run ruff check src/`, `uv run black --check src/`)
3. Типы верные (`uv run mypy src/`)
4. Ручное тестирование функциональности
5. PR создан и одобрен

## Task Lifecycle

```
pending → in_progress → completed
                ↓
            blocked → (resolve blocker) → in_progress
```

### Статусы задач

| Статус | Описание |
| ------ | -------- |
| `pending` | Задача создана, ожидает начала |
| `in_progress` | Активная работа над задачей |
| `blocked` | Заблокирована зависимостью |
| `completed` | Задача выполнена и проверена |

## Development Commands

```bash
# Тесты
TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v

# Линтинг
uv run ruff check src/
uv run black --check src/ tests/

# Типы
uv run mypy src/

# Все проверки перед push
uv run ruff check src/ && uv run black --check src/ tests/ && uv run mypy src/ && TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v
```
