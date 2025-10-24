# Telegram Voice2Text Bot

Telegram бот для транскрибации голосовых сообщений с использованием локальной модели Whisper.

## ✨ Особенности

- ✅ Локальная транскрибация через faster-whisper (без API, без затрат)
- ✅ Поддержка русского и других языков
- ✅ Асинхронная архитектура
- ✅ База данных для хранения истории транскрибаций
- ✅ Статистика использования
- 🚧 Система квот (60 сек/день бесплатно) - планируется
- 🚧 Суммаризация текста - планируется
- 🚧 Система биллинга - планируется

## 🛠 Технологии

- **Python 3.11+**
- **faster-whisper 1.2.0** - локальная транскрибация (4x быстрее openai-whisper)
- **python-telegram-bot 22.5** - Telegram Bot API
- **SQLAlchemy + SQLite/PostgreSQL** - хранение данных
- **asyncio** - асинхронная обработка

### 🎯 Production Configuration

**Рекомендуемая конфигурация** (основана на результатах benchmark):
- **Модель**: faster-whisper medium / int8 / beam1
- **Скорость**: RTF ~0.3x (в 3 раза быстрее длины аудио)
- **Память**: ~2GB RAM peak (tested in production)
- **Качество**: Отличное для русского языка

Примеры времени обработки:
- 7 сек аудио → ~2 сек обработки
- 30 сек аудио → ~10 сек обработки
- 60 сек аудио → ~20 сек обработки

## 🚀 Быстрый старт

### 1. Подготовка

```bash
# Клонировать репозиторий
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git
cd telegram-voice2text-bot

# Убедиться что Python 3.11+ установлен
python3 --version

## Если меньше, чем 3.11, то установить
brew install python@3.11

## Сбросить кэш zsh для python3
hash -r

## Перепроверить версию. Должна быть больше 3.11
python3 --version
`

### 2. Установка зависимостей

С Poetry (рекомендуется):
```bash
# Установить Poetry если еще не установлен
curl -sSL https://install.python-poetry.org | python3 -

# После установки добавь в ~/.zshrc (если не добавилось автоматически)
export PATH="$HOME/.local/bin:$PATH"

# И проверь
poetry --version

# Затем
poetry env use /opt/homebrew/bin/python3.11
или
poetry env use /opt/homebrew/bin/python3

# Установить зависимости
poetry install

# Активировать виртуальное окружение
poetry shell
```

**Без Poetry (с pip):**
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или venv\Scripts\activate  # Windows
pip install -e .
```

### 3. Получение Telegram Bot Token

1. Открыть Telegram и найти [@BotFather](https://t.me/BotFather)
2. Отправить команду `/newbot`
3. Следовать инструкциям для создания бота
4. Скопировать полученный токен (формат: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 4. Конфигурация

```bash
# Скопировать шаблон конфигурации
cp .env.example .env

# Отредактировать .env и указать токен
nano .env  # или любой редактор
```

Минимальная конфигурация в `.env`:
```env
BOT_TOKEN=your_bot_token_here
```

### 5. Запуск бота

```bash
# С Poetry
poetry run python -m src.main

# Без Poetry (в активированном venv)
python -m src.main
```

При первом запуске Whisper модель будет автоматически загружена (~1.5GB для модели `medium`).

### 6. Тестирование

1. Открыть бота в Telegram
2. Отправить команду `/start`
3. Отправить голосовое сообщение
4. Получить транскрибацию!

## 📋 Доступные команды

- `/start` - Начать работу с ботом и зарегистрироваться
- `/help` - Показать справку
- `/stats` - Посмотреть статистику использования

## 📁 Структура проекта

```
telegram-voice2text-bot/
├── src/
│   ├── bot/              # Telegram bot handlers
│   │   ├── handlers.py   # Command and message handlers
│   │   └── __init__.py
│   ├── transcription/    # Whisper integration
│   │   ├── whisper_service.py   # faster-whisper integration
│   │   ├── audio_handler.py     # Audio file management
│   │   └── __init__.py
│   ├── storage/          # Database models
│   │   ├── models.py     # SQLAlchemy models
│   │   ├── database.py   # Database connection
│   │   ├── repositories.py  # Repository pattern
│   │   └── __init__.py
│   ├── config.py         # Configuration (Pydantic Settings)
│   └── main.py           # Entry point
├── tests/
│   ├── unit/             # Unit tests
│   │   ├── test_models.py
│   │   ├── test_repositories.py
│   │   ├── test_whisper_service.py
│   │   └── test_audio_handler.py
│   ├── integration/      # Integration tests
│   └── conftest.py       # Pytest fixtures
├── alembic/              # Database migrations
├── .claude/              # Memory Bank documentation
├── .env.example          # Configuration template
├── pyproject.toml        # Dependencies (Poetry)
└── README.md
```

## 🧪 Разработка

### Управление зависимостями

Проект использует **Poetry** для управления зависимостями, но также поддерживает `requirements.txt` для Docker.

#### Обновление requirements.txt после изменения зависимостей

После изменения `pyproject.toml` всегда обновляйте requirements файлы:

```bash
./scripts/update-requirements.sh
```

Это создаст три файла:
- `requirements.txt` - базовые зависимости
- `requirements-docker.txt` - базовые + faster-whisper (для Docker)
- `requirements-full.txt` - все провайдеры (для бенчмарков)

#### Добавление новой зависимости

```bash
# 1. Добавить зависимость через Poetry
poetry add <package>

# 2. Обновить requirements.txt
./scripts/update-requirements.sh

# 3. Закоммитить изменения
git add pyproject.toml poetry.lock requirements*.txt
git commit -m "feat: add <package> dependency"
```

Подробнее: [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)

### Запуск тестов

```bash
# Запустить все тесты
pytest

# С coverage
pytest --cov=src --cov-report=html

# Только unit тесты
pytest tests/unit/

# Конкретный тест
pytest tests/unit/test_whisper_service.py
```

### Форматирование и линтинг

```bash
# Форматирование кода
black src/ tests/

# Линтинг
ruff check src/ tests/

# Type checking
mypy src/
```

### База данных

```bash
# Создать новую миграцию
alembic revision --autogenerate -m "description"

# Применить миграции
alembic upgrade head

# Откатить миграцию
alembic downgrade -1
```

## ⚙️ Конфигурация

Все настройки настраиваются через файл `.env` или переменные окружения:

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `BOT_TOKEN` | - | **Обязательно**. Telegram Bot Token от @BotFather |
| `BOT_MODE` | `polling` | Режим работы: `polling` или `webhook` |
| `WHISPER_MODEL_SIZE` | `base` | Размер модели: `tiny`, `base`, `small`, `medium`, `large` |
| `WHISPER_DEVICE` | `cpu` | Устройство: `cpu` или `cuda` |
| `DATABASE_URL` | `sqlite:///./data/bot.db` | URL базы данных |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `TRANSCRIPTION_TIMEOUT` | `120` | Таймаут транскрибации (секунды) |
| `MAX_CONCURRENT_WORKERS` | `3` | Максимум параллельных транскрибаций |

Полный список настроек см. в файле `.env.example`.

## 🐳 Docker

Docker - самый простой способ запуска бота. Все зависимости, включая Whisper модели, будут установлены автоматически.

### Быстрый старт с Docker

```bash
# 1. Клонировать репозиторий
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git
cd telegram-voice2text-bot

# 2. Настроить .env файл
cp .env.example .env
nano .env  # указать BOT_TOKEN

# 3. Запустить
docker-compose up -d
```

### Управление контейнером

```bash
# Запуск (фоновый режим)
docker-compose up -d

# Просмотр логов
docker-compose logs -f bot

# Остановка
docker-compose stop

# Перезапуск
docker-compose restart

# Полная остановка и удаление
docker-compose down

# Пересборка после изменения кода
docker-compose up -d --build
```

### Особенности Docker версии

- **Персистентность данных**: База данных и логи хранятся в `./data` и `./logs`
- **Кеширование моделей**: Whisper модели сохраняются в volume `whisper-models`
- **Resource limits**: По умолчанию: 2 CPU, 2GB RAM (настраивается в `docker-compose.yml`)
- **Auto-restart**: Бот автоматически перезапускается при падении

### Использование PostgreSQL (опционально)

Для production развертывания можно использовать PostgreSQL вместо SQLite:

1. Раскомментировать секцию `postgres` в `docker-compose.yml`
2. Обновить `DATABASE_URL` в `.env`:
   ```env
   DATABASE_URL=postgresql+asyncpg://botuser:botpassword@postgres:5432/telegram_bot
   ```
3. Перезапустить: `docker-compose up -d`

### Проверка статуса

```bash
# Проверить что контейнер работает
docker-compose ps

# Проверить здоровье контейнера
docker inspect telegram-voice2text-bot | grep Health

# Подключиться к контейнеру
docker-compose exec bot bash
```

## 📈 Roadmap

### Phase 1: MVP ✅ COMPLETE
- [x] Проектная структура
- [x] Database layer (SQLAlchemy + Alembic)
- [x] Whisper integration (faster-whisper)
- [x] Bot handlers (/start, /help, /stats)
- [x] Voice message transcription
- [x] Audio file support
- [x] Polling режим
- [x] Unit tests (45+ tests)

### Phase 2: Testing & Polish ✅ COMPLETE
- [x] Local testing with real bot
- [x] Bug fixes and improvements
- [x] Documentation updates

### Phase 3: Docker & Deployment ✅ COMPLETE
- [x] Dockerfile
- [x] Docker Compose
- [x] CI/CD Pipeline (GitHub Actions)
- [ ] VPS деплой
- [ ] Webhook режим
- [ ] PostgreSQL migration
- [ ] SSL сертификат

### Phase 4: Advanced Features
- [ ] Система квот
- [ ] Суммаризация текста
- [ ] Платежная интеграция
- [ ] Horizontal scaling

## 🚀 CI/CD & Production Deployment

Проект настроен для автоматического развертывания на VPS с zero-downtime deployment.

### Features

- ✅ **Automated Testing**: CI runs on every PR (pytest, mypy, ruff, black)
- ✅ **Docker Build**: Auto-build and push to Docker Hub on merge to main
- ✅ **Zero-Downtime Deployment**: Rolling updates with health checks
- ✅ **Secure Secret Management**: GitHub Secrets for sensitive data

### Quick Start

1. **Setup GitHub Secrets**:
   - `DOCKER_USERNAME` & `DOCKER_PASSWORD` - Docker Hub credentials
   - `TELEGRAM_BOT_TOKEN` - Telegram Bot Token
   - `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` - VPS access

2. **Workflow**:
   ```bash
   # Create feature branch
   git checkout -b feature/new-feature

   # Make changes and commit
   git commit -m "feat: add new feature"

   # Push and create PR
   git push origin feature/new-feature
   gh pr create

   # CI runs automatically
   # Merge PR → Auto-deploy to VPS
   ```

3. **Monitoring**:
   ```bash
   # Check deployment status
   # GitHub → Actions tab

   # SSH to VPS and view logs
   ssh user@your-vps
   cd /opt/telegram-voice2text-bot
   docker compose -f docker-compose.prod.yml logs -f bot
   ```

### Documentation

- 📖 **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete deployment guide
- 📋 **[Implementation Plan](.claude/memory-bank/plans/2025-10-17-cicd-pipeline-plan.md)** - Detailed CI/CD setup

---

## 📚 Документация

Подробная документация в директории `.claude/memory-bank/`:
- `projectbrief.md` - общее описание проекта и требования
- `productContext.md` - контекст продукта и пользователей
- `activeContext.md` - текущий статус и следующие шаги
- `techContext.md` - технологический стек и зависимости
- `systemPatterns.md` - архитектура системы
- `progress.md` - прогресс разработки и метрики
- `plans/` - детальные планы реализации

**Deployment**:
- `DEPLOYMENT.md` - Production deployment guide
- `.github/workflows/` - CI/CD workflows

## 🤝 Contributing

1. Fork репозиторий
2. Создать feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'feat: add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Открыть Pull Request

Следуйте [Conventional Commits](https://www.conventionalcommits.org/) для commit сообщений.

## 📄 Лицензия

MIT

## 👤 Автор

Konstantin Balakin - [@konstantinbalakin](https://github.com/konstantinbalakin)

## 🙏 Благодарности

- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - за отличную библиотеку транскрибации
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - за удобный Bot API wrapper

