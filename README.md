# Telegram Voice2Text Bot

Telegram бот для транскрибации голосовых сообщений с использованием локальной модели Whisper.

## Особенности

- ✅ Локальная транскрибация через faster-whisper (без API, без затрат)
- ✅ Асинхронная архитектура с системой очередей
- ✅ Система квот (60 сек/день бесплатно)
- ✅ Безлимитный доступ для отдельных пользователей
- 🚧 Суммаризация текста (планируется)
- 🚧 Система биллинга (планируется)

## Технологии

- **Python 3.11+**
- **faster-whisper 1.2.0** - транскрибация (4x быстрее openai-whisper)
- **python-telegram-bot 22.5** - Telegram Bot API
- **SQLAlchemy + SQLite/PostgreSQL** - хранение данных
- **asyncio** - асинхронная обработка

## Быстрый старт

### 1. Подготовка

```bash
# Клонировать репозиторий
git clone <repo_url>
cd telegram-voice2text-bot

# Убедиться что Python 3.11+ установлен
python3 --version

# Установить Poetry (опционально)
curl -sSL https://install.python-poetry.org | python3 -
```

### 2. Установка зависимостей

**С Poetry:**
```bash
poetry install
poetry shell
```

**Без Poetry (с pip):**
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или venv\Scripts\activate  # Windows
pip install -e .
```

### 3. Конфигурация

```bash
# Скопировать шаблон конфигурации
cp .env.example .env

# Получить токен бота от @BotFather в Telegram

# Отредактировать .env и указать токен
nano .env  # или любой редактор
```

### 4. Запуск

```bash
python -m src.main
```

## Структура проекта

```
telegram-voice2text-bot/
├── src/
│   ├── bot/              # Telegram bot handlers
│   ├── processing/       # Queue and worker pool
│   ├── transcription/    # Whisper integration
│   ├── storage/          # Database models
│   ├── quota/            # Quota management
│   ├── config.py         # Configuration
│   └── main.py           # Entry point
├── tests/                # Tests
├── docker/               # Docker files
├── memory-bank/          # Project documentation
└── pyproject.toml        # Dependencies

## Разработка

### Тесты

```bash
# Запустить все тесты
pytest

# С coverage
pytest --cov=src --cov-report=html

# Только unit тесты
pytest tests/unit/
```

### Форматирование и линтинг

```bash
# Форматирование
black src/ tests/

# Линтинг
ruff check src/ tests/

# Type checking
mypy src/
```

## Docker

```bash
# Build
docker build -t telegram-voice-bot .

# Run
docker-compose up -d
```

## Roadmap

### Phase 1: MVP (Текущая)
- [x] Проектная структура
- [ ] Базовая транскрибация
- [ ] Система квот
- [ ] Polling режим

### Phase 2: Docker
- [ ] Контейнеризация
- [ ] Docker Compose
- [ ] Персистентное хранилище

### Phase 3: Production
- [ ] VPS деплой
- [ ] Webhook режим
- [ ] PostgreSQL
- [ ] SSL сертификат

### Phase 4: Features
- [ ] Суммаризация текста
- [ ] Платежная интеграция
- [ ] CI/CD pipeline

## Документация

Подробная документация в директории `.claude/memory-bank/`:
- `projectbrief.md` - общее описание проекта
- `productContext.md` - контекст продукта и пользователей
- `activeContext.md` - текущий статус и следующие шаги
- `techContext.md` - технологический стек
- `systemPatterns.md` - архитектура системы
- `progress.md` - прогресс разработки
- `plans/` - детальные планы реализации

## Лицензия

MIT
