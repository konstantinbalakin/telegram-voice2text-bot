# Telegram Voice2Text Bot

Telegram бот для транскрибации голосовых сообщений и интеллектуальной обработки текста с помощью AI.

[![CI](https://github.com/konstantinbalakin/telegram-voice2text-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/konstantinbalakin/telegram-voice2text-bot/actions/workflows/ci.yml)
[![Build and Deploy](https://github.com/konstantinbalakin/telegram-voice2text-bot/actions/workflows/build-and-deploy.yml/badge.svg)](https://github.com/konstantinbalakin/telegram-voice2text-bot/actions/workflows/build-and-deploy.yml)

## ✨ Особенности

### Транскрибация
- ✅ **OpenAI Whisper API** - высококачественное распознавание речи
- ✅ **Поддержка больших файлов** - до 2 GB через Telethon (MTProto Client API)
- ✅ **Работа с документами и видео** - обработка аудио из .aac, .flac, .mp4, .mov и других форматов
- ✅ **Качественное распознавание** - отличное качество для русского и других языков

### Интеллектуальная обработка (DeepSeek AI)
- ✅ **"Структурировать"** - автоматическое структурирование текста с заголовками и списками
- ✅ **"Сделать красиво"** - превращение в публикационный текст с сохранением вашего стиля
- ✅ **"О чем этот текст"** - краткое резюме ключевых моментов

### UX и производительность
- ✅ **Живой прогресс-бар** - визуальная обратная связь в реальном времени
- ✅ **Система очередей** - управление нагрузкой, до 10 запросов
- ✅ **Автоматическое структурирование** - для длинных аудио показываем черновик, затем структурируем

### Инфраструктура
- ✅ **База данных** - хранение истории и статистики с автоматическими миграциями
- ✅ **Docker** - простое развертывание
- ✅ **CI/CD** - автоматический деплой на VPS с тестированием
- ✅ **Асинхронная архитектура** - последовательная обработка для стабильности

### Статус
🆓 **Бесплатно** - пока набираем пользователей и тестируем функционал!

## 🚀 Quick Start

### С Docker (рекомендуется)

```bash
# Клонировать репозиторий
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git
cd telegram-voice2text-bot

# Настроить .env
cp .env.example .env
nano .env  # Указать TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, LLM_API_KEY

# Запустить
docker-compose up -d
```

**Готово!** Бот работает. Отправьте ему голосовое сообщение в Telegram.

**Требования:** API ключи от OpenAI (транскрибация) и DeepSeek (обработка текста). См. [Configuration Guide](docs/getting-started/configuration.md).

### Локальная разработка

```bash
# Установить uv (если не установлен)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Установить зависимости
uv sync --all-extras

# Настроить .env
cp .env.example .env
nano .env  # Указать BOT_TOKEN

# Запустить
uv run python -m src.main
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

### Core Stack
- **Python 3.11+** - асинхронная архитектура
- **OpenAI Whisper API** - транскрибация голоса (gpt-4o-transcribe, whisper-1)
- **DeepSeek V3** - интеллектуальная обработка текста (структурирование, резюме, оформление)
- **Telethon** - MTProto Client API для больших файлов (>20 MB)
- **python-telegram-bot 22.5** - Telegram Bot API

### Data & Infrastructure
- **SQLAlchemy + SQLite** - хранение истории и вариантов текста
- **Alembic** - автоматические миграции базы данных
- **Docker + Docker Compose** - контейнеризация
- **GitHub Actions** - CI/CD pipeline

### Optional (для локальной разработки)
- **faster-whisper** - альтернативная локальная транскрибация (без API)

### Production Configuration

**Текущая production конфигурация:**

**Транскрибация:**
- **Provider**: OpenAI Whisper API
- **Models**: gpt-4o-transcribe, gpt-4o-mini-transcribe, whisper-1
- **Стратегия**: `structure` - автоматическое структурирование текста
- **Поддержка больших файлов**: до 2 GB через Telethon

**Обработка текста:**
- **LLM**: DeepSeek V3 (deepseek-chat)
- **Режимы**: Структурирование, "Сделать красиво", Резюме
- **Emoji**: 4 уровня (0-3), по умолчанию умеренное количество

**Инфраструктура:**
- **VPS**: 3GB RAM, 4 CPU cores
- **Обработка**: Последовательная (1 запрос за раз)
- **Лимиты**: Максимум 120 сек аудио, очередь до 10 запросов
- **База данных**: SQLite с кешированием вариантов текста

**Производительность:**
- Транскрибация: ~5-15 секунд (зависит от длины аудио)
- Структурирование: +3-5 секунд (DeepSeek V3)
- Прогресс-бар: обновления каждые 5 секунд

**Стоимость на 60 сек аудио:**
- OpenAI Whisper: ~$0.006 (whisper-1) или ~$0.012 (gpt-4o models)
- DeepSeek структурирование: ~$0.0002
- **Итого**: ~$0.006-0.012 на минуту аудио

## 📋 Использование бота

### Команды
- `/start` - Начать работу и зарегистрироваться
- `/help` - Показать справку
- `/stats` - Посмотреть статистику использования

### Интерактивные кнопки
После транскрибации голосового сообщения появляются кнопки:
- **📝 Структурировать** - разбить текст на параграфы, заголовки и списки
- **🪄 Сделать красиво** - превратить в публикационный текст с сохранением стиля автора
- **📋 О чем этот текст** - получить краткое резюме ключевых моментов

Все варианты кешируются - повторное нажатие мгновенно показывает результат!

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
uv add <package>

# Обновить requirements.txt для Docker
make deps

# Закоммитить изменения
git add pyproject.toml uv.lock requirements.txt
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

- [x] **Phase 1-4**: Project Setup, Core Functionality, Docker & CI/CD, VPS Deployment
- [x] **Phase 5-6**: Production Validation, Queue System, Database Migrations
- [x] **Phase 7-9**: Logging & Versioning, Hybrid Transcription, Large File Support (Telethon)
- [x] **Phase 10**: Interactive Transcription System
  - [x] Phase 10.1-10.6: Infrastructure, Structured Mode, Length Variations, Summary, Emoji, Timestamps
  - [x] Phase 10.7-10.10: File Handling, Retranscription, HTML/PDF Generation
  - [x] Phase 10.11-10.13: OpenAI gpt-4o Support, StructureStrategy, Long Audio Chunking
  - [x] Phase 10.14: Magic Mode ("Сделать красиво")
- [ ] **Phase 11**: Analytics Dashboard
- [ ] **Phase 12**: User Quotas & Billing System
- [ ] **Phase 13**: Multi-language Support

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

- [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text) - за высококачественную транскрибацию
- [DeepSeek](https://www.deepseek.com/) - за мощную и доступную LLM для обработки текста
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - за удобный Bot API wrapper
- [Telethon](https://github.com/LonamiWebs/Telethon) - за MTProto Client API для больших файлов
- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - опциональная локальная транскрибация
