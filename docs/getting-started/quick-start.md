# Quick Start Guide

[← Back to Documentation](../README.md)

Get your bot running in 5 minutes!

## Prerequisites

- Completed [Installation](installation.md)
- [Configured](configuration.md) `.env` with `BOT_TOKEN`

## Option 1: Local Start (uv)

```bash
# Navigate to project directory
cd telegram-voice2text-bot

# Install/update dependencies
uv sync --all-extras

# Run database migrations
uv run alembic upgrade head

# Run bot
uv run python -m src.main
```

**Expected output:**
```
INFO:telegram.ext.Application:Application started
INFO:__main__:Bot started successfully in polling mode
INFO:__main__:Downloading Whisper model: medium...
```

**Note**: First run downloads Whisper model (~1.5GB for medium), takes 2-5 minutes.

## Option 2: Docker Start

```bash
# Navigate to project directory
cd telegram-voice2text-bot

# Ensure .env is configured
cat .env | grep BOT_TOKEN

# Start bot
docker-compose up -d

# View logs
docker-compose logs -f bot
```

## Test Your Bot

### 1. Open Telegram

Find your bot by username (from @BotFather) or use the t.me link.

### 2. Send /start

```
You: /start
Bot: 👋 Привет! Я бот для транскрибации голосовых сообщений.

     Отправь мне голосовое сообщение, и я переведу его в текст.
```

### 3. Send Voice Message

Record a short voice message (5-10 seconds) in Russian or English.

**Expected:**
- Bot shows "typing..." indicator
- After 2-10 seconds (depending on audio length)
- Bot replies with transcription text

### 4. Check Stats

```
You: /stats
Bot: 📊 Статистика за последние 30 дней

     Обработано сообщений: 1
     Длительность аудио: 7 сек
     Языки:
     • Русский — 1

     Всего за всё время: 1 сообщений
     Дата регистрации: 18.11.2026
```

## Available Commands

| Command | Description |
|---------|-------------|
| `/start` | Start bot and register |
| `/help` | Show help message |
| `/stats` | View your usage statistics |

## Common Issues

### Bot not responding

**Check logs:**
```bash
# Local (uv)
uv run python -m src.main

# Docker
docker-compose logs bot
```

**Common causes:**
- Invalid `BOT_TOKEN` in .env
- Network/firewall blocking Telegram API
- Bot still downloading Whisper model (wait)

### Model download stuck

```bash
# Check disk space
df -h

# Check network connection
curl -I https://huggingface.co

# Models download to: ~/.cache/huggingface/
```

### Transcription too slow

```bash
# Use smaller model in .env
WHISPER_MODEL_SIZE=base  # Instead of medium

# Restart bot
```

### "Module not found" errors

```bash
# Reinstall dependencies
uv sync --all-extras

# Or with pip
pip install -e .
```

## Performance Benchmarks

Typical transcription times (CPU, medium model):

| Audio Length | Processing Time | Real-Time Factor |
|--------------|-----------------|------------------|
| 7 seconds    | ~2 seconds      | 0.29x |
| 30 seconds   | ~10 seconds     | 0.33x |
| 60 seconds   | ~20 seconds     | 0.33x |

**RTF < 1.0 = faster than real-time** ✅

## Next Steps

### For Users
- Send longer voice messages
- Try different languages
- Check `/stats` periodically

### For Developers
- [Testing Guide](../development/testing.md) - Local testing
- [Architecture](../development/architecture.md) - System design
- [Git Workflow](../development/git-workflow.md) - Contributing

### For Deployment
- [Docker Guide](../deployment/docker.md) - Containerized deployment
- [VPS Setup](../deployment/vps-setup.md) - Deploy to server
- [CI/CD Pipeline](../deployment/cicd.md) - Automated deployment

## Related Documentation

- [Configuration](configuration.md) - Detailed settings
- [Installation](installation.md) - Setup instructions
- [Development](../development/testing.md) - Development guide
