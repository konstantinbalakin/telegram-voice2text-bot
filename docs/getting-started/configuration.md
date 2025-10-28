# Configuration Guide

[← Back to Documentation](../README.md)

## Overview

Bot configuration is managed through environment variables in `.env` file or system environment.

## Setup .env File

```bash
# Copy template
cp .env.example .env

# Edit configuration
nano .env  # or use your preferred editor
```

## Required Settings

### Telegram Bot Token

**Required**. Get from [@BotFather](https://t.me/BotFather):

```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

**How to get:**
1. Open Telegram, find @BotFather
2. Send `/newbot`
3. Follow instructions
4. Copy token

## Core Settings

### Bot Mode

```env
BOT_MODE=polling  # or webhook
```

- `polling` - For development and VPS (default)
- `webhook` - For production with domain + SSL

### Database

```env
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
```

**Options:**
- SQLite (default): `sqlite+aiosqlite:///./data/bot.db`
- PostgreSQL: `postgresql+asyncpg://user:pass@host:5432/dbname`

## Whisper Configuration

### Model Size

```env
WHISPER_MODEL_SIZE=medium
```

**Options:**
- `tiny` - Fastest, lowest quality (~75MB)
- `base` - Fast, good quality (~140MB)
- `small` - Balanced (~480MB)
- `medium` - **Recommended** for production (~1.5GB)
- `large-v3` - Best quality, slowest (~3GB)

**Recommendation**: `medium` for production (RTF ~0.3x on CPU)

### Device

```env
WHISPER_DEVICE=cpu  # or cuda
```

- `cpu` - For servers without GPU (default)
- `cuda` - For GPU acceleration (requires CUDA)

### Compute Type

```env
WHISPER_COMPUTE_TYPE=int8
```

**Options:**
- `int8` - **Recommended** (4x less memory, minimal quality loss)
- `float16` - GPU only
- `float32` - Highest quality, most memory

### Performance

```env
TRANSCRIPTION_TIMEOUT=120
MAX_CONCURRENT_WORKERS=3
```

- `TRANSCRIPTION_TIMEOUT` - Max seconds for transcription (default: 120)
- `MAX_CONCURRENT_WORKERS` - Concurrent transcriptions (default: 3)

## Logging

```env
LOG_LEVEL=INFO
```

**Options:**
- `DEBUG` - Verbose logging (development)
- `INFO` - Standard logging (production)
- `WARNING` - Warnings only
- `ERROR` - Errors only

## All Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `BOT_TOKEN` | - | **Required**. Telegram Bot Token |
| `BOT_MODE` | `polling` | `polling` or `webhook` |
| `WHISPER_MODEL_SIZE` | `base` | Whisper model size |
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | Quantization type |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/bot.db` | Database connection string |
| `LOG_LEVEL` | `INFO` | Logging level |
| `TRANSCRIPTION_TIMEOUT` | `120` | Max transcription time (seconds) |
| `MAX_CONCURRENT_WORKERS` | `3` | Concurrent transcriptions |

## Example Configurations

### Development (Fast)

```env
BOT_TOKEN=your_token_here
BOT_MODE=polling
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
LOG_LEVEL=DEBUG
```

### Production (Quality)

```env
BOT_TOKEN=your_token_here
BOT_MODE=polling
WHISPER_MODEL_SIZE=medium
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
DATABASE_URL=postgresql+asyncpg://botuser:password@postgres:5432/telegram_bot
LOG_LEVEL=INFO
TRANSCRIPTION_TIMEOUT=300
MAX_CONCURRENT_WORKERS=2
```

### GPU Server

```env
BOT_TOKEN=your_token_here
BOT_MODE=polling
WHISPER_MODEL_SIZE=large-v3
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
LOG_LEVEL=INFO
MAX_CONCURRENT_WORKERS=5
```

## Environment-Specific Setup

### Docker

Environment variables are set in `docker-compose.yml`:

```yaml
environment:
  - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
  - WHISPER_MODEL_SIZE=medium
```

### VPS Deployment

CI/CD sets environment via GitHub Secrets. See [CI/CD Guide](../deployment/cicd.md).

## Validation

```bash
# Verify configuration loads correctly
poetry run python -c "from src.config import settings; print(f'Bot configured: {settings.bot_token[:10]}...')"
```

## Next Steps

- [Quick Start](quick-start.md) - Run the bot
- [Development](../development/testing.md) - Testing and development
- [Deployment](../deployment/docker.md) - Deploy to production

## Related Documentation

- [.env.example](../../.env.example) - Full configuration template
- [Dependencies](../development/dependencies.md) - Package management
