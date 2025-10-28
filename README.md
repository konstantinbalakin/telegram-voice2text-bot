# Telegram Voice2Text Bot

Telegram бот для транскрибации голосовых сообщений с использованием локальной модели Whisper.

[![CI](https://github.com/konstantinbalakin/telegram-voice2text-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/konstantinbalakin/telegram-voice2text-bot/actions/workflows/ci.yml)
[![Build and Deploy](https://github.com/konstantinbalakin/telegram-voice2text-bot/actions/workflows/build-and-deploy.yml/badge.svg)](https://github.com/konstantinbalakin/telegram-voice2text-bot/actions/workflows/build-and-deploy.yml)

## ✨ Особенности

- ✅ **Локальная транскрибация** - faster-whisper (без API, без затрат)
- ✅ **Высокая скорость** - RTF ~0.3x (в 3 раза быстрее длины аудио)
- ✅ **Качественное распознавание** - отличное качество для русского и других языков
- ✅ **Асинхронная архитектура** - обработка множества пользователей
- ✅ **База данных** - хранение истории и статистики
- ✅ **Docker** - простое развертывание
- ✅ **CI/CD** - автоматический деплой на VPS

## 🚀 Quick Start

### С Docker (рекомендуется)

```bash
# Клонировать репозиторий
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git
cd telegram-voice2text-bot

# Настроить .env
cp .env.example .env
nano .env  # Указать BOT_TOKEN

# Запустить
docker-compose up -d
```

**Готово!** Бот работает. Отправьте ему `/start` в Telegram.

### Локальная разработка

```bash
# Установить зависимости
poetry install

# Настроить .env
cp .env.example .env
nano .env  # Указать BOT_TOKEN

# Запустить
poetry run python -m src.main
```

**Подробнее:** [📖 Installation Guide](docs/getting-started/installation.md)

## 📚 Документация

**Новичок?** Начните с [Getting Started Guide](docs/getting-started/installation.md)

### 📖 Основные разделы

- **[Getting Started](docs/README.md#-getting-started)** - Установка, настройка, быстрый старт
- **[Development](docs/README.md#-development)** - Архитектура, тестирование, Git workflow
- **[Deployment](docs/README.md#-deployment)** - Docker, VPS, CI/CD

**Полная документация:** [docs/README.md](docs/README.md)

## 🛠 Технологии

- **Python 3.11+**
- **faster-whisper 1.2.0** - локальная транскрибация (4x быстрее openai-whisper)
- **python-telegram-bot 22.5** - Telegram Bot API
- **SQLAlchemy + SQLite/PostgreSQL** - хранение данных
- **Docker + Docker Compose** - контейнеризация
- **GitHub Actions** - CI/CD pipeline

### Production Configuration

**Рекомендуемая конфигурация** (протестирована на production):
- **Модель**: faster-whisper medium / int8
- **Скорость**: RTF ~0.3x (в 3 раза быстрее аудио)
- **Память**: ~2GB RAM peak
- **Качество**: Отличное для русского языка

**Примеры времени обработки:**
- 7 сек аудио → ~2 сек обработки
- 30 сек аудио → ~10 сек обработки
- 60 сек аудио → ~20 сек обработки

## 📋 Команды бота

- `/start` - Начать работу и зарегистрироваться
- `/help` - Показать справку
- `/stats` - Посмотреть статистику использования

## 🧪 Разработка

### Тестирование

```bash
# Запустить все тесты
pytest

# С coverage
pytest --cov=src --cov-report=html

# Только unit тесты
pytest tests/unit/
```

**Подробнее:** [Testing Guide](docs/development/testing.md)

### Управление зависимостями

```bash
# Добавить зависимость
poetry add <package>

# Обновить requirements.txt для Docker
./scripts/update-requirements.sh

# Закоммитить изменения
git add pyproject.toml poetry.lock requirements.txt
git commit -m "feat: add <package> dependency"
```

**Подробнее:** [Dependencies Guide](docs/development/dependencies.md)

### Git Workflow

```bash
# Создать feature branch
git checkout -b feature/my-feature

# Сделать изменения и закоммитить
git commit -m "feat: add my feature"

# Создать Pull Request
gh pr create
```

**Подробнее:** [Git Workflow Guide](docs/development/git-workflow.md)

## 🐳 Docker

### Быстрый старт

```bash
docker-compose up -d
```

### Управление

```bash
# Логи
docker-compose logs -f bot

# Перезапуск
docker-compose restart

# Остановка
docker-compose down
```

**Подробнее:** [Docker Guide](docs/deployment/docker.md)

## 🚀 Deployment

### VPS Deployment

Automated deployment to VPS with GitHub Actions:

```bash
# Push to main → автоматический деплой
git push origin main
```

**Setup guides:**
- [VPS Setup](docs/deployment/vps-setup.md) - Настройка VPS сервера
- [CI/CD Pipeline](docs/deployment/cicd.md) - GitHub Actions

## 📁 Структура проекта

```
telegram-voice2text-bot/
├── src/
│   ├── bot/              # Telegram bot handlers
│   ├── transcription/    # Whisper integration
│   ├── storage/          # Database models
│   ├── config.py         # Configuration
│   └── main.py           # Entry point
├── tests/                # Unit and integration tests
├── docs/                 # Documentation
├── alembic/              # Database migrations
├── memory-bank/          # Claude Code context
└── .github/workflows/    # CI/CD pipelines
```

**Детали:** [Architecture Guide](docs/development/architecture.md)

## 📈 Roadmap

- [x] **Phase 1**: Project Setup
- [x] **Phase 2**: Core Functionality (Database, Whisper, Bot)
- [x] **Phase 3**: Docker & CI/CD
- [x] **Phase 4**: VPS Deployment
- [ ] **Phase 5**: Advanced Features (Quotas, Billing, Summarization)

## 🤝 Contributing

1. Fork репозиторий
2. Создать feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'feat: add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Открыть Pull Request

Следуйте [Conventional Commits](https://www.conventionalcommits.org/) для commit сообщений.

**Workflow guide:** [Git Workflow](docs/development/git-workflow.md)

## 📄 Лицензия

MIT

## 👤 Автор

Konstantin Balakin - [@konstantinbalakin](https://github.com/konstantinbalakin)

## 🙏 Благодарности

- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - за отличную библиотеку транскрибации
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - за удобный Bot API wrapper
