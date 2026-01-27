# Configuration Guide

[← Back to Documentation](../README.md)

## Overview

Bot configuration is managed through environment variables in `.env` file. This guide covers the **production configuration** using OpenAI Whisper API + DeepSeek for text processing.

## Quick Setup

```bash
# Copy template
cp .env.example .env

# Edit configuration
nano .env
```

**Minimum required settings for production:**
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
OPENAI_API_KEY=sk-your-openai-key
LLM_API_KEY=sk-your-deepseek-key
```

## Required Settings

### 1. Telegram Bot Token

**Required**. Get from [@BotFather](https://t.me/BotFather):

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

**How to get:**
1. Open Telegram, find @BotFather
2. Send `/newbot`
3. Follow instructions
4. Copy token

### 2. OpenAI API Key

**Required** for transcription. Get from [OpenAI Platform](https://platform.openai.com/api-keys):

```env
OPENAI_API_KEY=sk-proj-...your_key_here
```

**Cost**: ~$0.006-0.012 per minute of audio

**How to get:**
1. Sign up at https://platform.openai.com
2. Go to API keys section
3. Create new secret key
4. Copy and save it (shown once!)

### 3. DeepSeek API Key

**Required** for text processing (структурирование, резюме, "сделать красиво"). Get from [DeepSeek Platform](https://platform.deepseek.com/api_keys):

```env
LLM_API_KEY=sk-...your_deepseek_key_here
```

**Cost**: ~$0.0002 per structured text (30x cheaper than OpenAI)

**How to get:**
1. Sign up at https://platform.deepseek.com
2. Go to API Keys section
3. Create new key
4. $5 free credit included!

## Production Configuration

### Transcription Provider

```env
# Use OpenAI for production (recommended)
WHISPER_PROVIDERS=["openai"]
PRIMARY_PROVIDER=openai

# Model selection
# whisper-1: $0.006/min, supports all formats
# gpt-4o-transcribe: $0.012/min, better quality
# gpt-4o-mini-transcribe: $0.012/min, faster
OPENAI_MODEL=whisper-1
```

### Routing Strategy

```env
# Production default: automatic structuring
WHISPER_ROUTING_STRATEGY=structure

# Structure strategy settings
STRUCTURE_PROVIDER=openai
STRUCTURE_MODEL=whisper-1
STRUCTURE_DRAFT_THRESHOLD=20  # Show draft for audio ≥20s
STRUCTURE_EMOJI_LEVEL=1  # 0=none, 1=few, 2=moderate, 3=many
```

### LLM Text Processing

```env
# Enable LLM features (REQUIRED for interactive buttons)
LLM_REFINEMENT_ENABLED=true
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com
```

### Interactive Features

```env
# Enable interactive mode (production default)
INTERACTIVE_MODE_ENABLED=true

# Enable production buttons
ENABLE_STRUCTURED_MODE=true     # 📝 Структурировать
ENABLE_MAGIC_MODE=true          # 🪄 Сделать красиво
ENABLE_SUMMARY_MODE=true        # 📋 О чем этот текст

# Optional features (disabled by default)
ENABLE_LENGTH_VARIATIONS=false
ENABLE_EMOJI_OPTION=false
ENABLE_TIMESTAMPS_OPTION=false
ENABLE_RETRANSCRIBE=false
```

## Large Files Support

For files >20 MB (up to 2 GB), enable Telethon:

```env
TELETHON_ENABLED=true
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash_here
```

**How to get Telegram API credentials:**
1. Visit https://my.telegram.org
2. Login with your phone number
3. Go to "API development tools"
4. Create new application
5. Copy `api_id` and `api_hash`

## Performance & Limits

```env
# Queue settings
MAX_QUEUE_SIZE=10
MAX_CONCURRENT_WORKERS=1  # Sequential processing
MAX_VOICE_DURATION_SECONDS=120  # 2 minutes max

# Progress tracking
PROGRESS_UPDATE_INTERVAL=5  # Update every 5 seconds
```

## Database

```env
# SQLite (default, recommended for <1000 users/day)
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db

# PostgreSQL (for scale)
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
```

## Logging

```env
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

## Example Configurations

### Production (API-based) ⭐

```env
# Required
TELEGRAM_BOT_TOKEN=your_token
OPENAI_API_KEY=sk-your-openai-key
LLM_API_KEY=sk-your-deepseek-key

# Providers
WHISPER_PROVIDERS=["openai"]
WHISPER_ROUTING_STRATEGY=structure
PRIMARY_PROVIDER=openai
OPENAI_MODEL=whisper-1

# LLM
LLM_REFINEMENT_ENABLED=true
LLM_PROVIDER=deepseek

# Interactive features
INTERACTIVE_MODE_ENABLED=true
ENABLE_STRUCTURED_MODE=true
ENABLE_MAGIC_MODE=true
ENABLE_SUMMARY_MODE=true

# Large files (optional)
TELETHON_ENABLED=true
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_hash
```

### Local Development (no API costs)

```env
# Required
TELEGRAM_BOT_TOKEN=your_token

# Local transcription
WHISPER_PROVIDERS=["faster-whisper"]
WHISPER_ROUTING_STRATEGY=single
PRIMARY_PROVIDER=faster-whisper
FASTER_WHISPER_MODEL_SIZE=medium
FASTER_WHISPER_COMPUTE_TYPE=int8

# Disable LLM features
LLM_REFINEMENT_ENABLED=false
INTERACTIVE_MODE_ENABLED=false
```

## Cost Estimation

**Per 60 seconds of audio:**
- OpenAI Whisper (whisper-1): $0.006
- OpenAI gpt-4o models: $0.012
- DeepSeek structuring: $0.0002
- **Total**: ~$0.006-0.012 per minute

**Monthly costs** (example):
- 100 minutes/day × 30 days = 3000 minutes/month
- 3000 × $0.006 = **$18/month** (whisper-1)
- 3000 × $0.0002 = **$0.60/month** (DeepSeek)
- **Total**: ~$18-19/month for 100 min/day

See [Costs Guide](../deployment/costs.md) for detailed breakdown.

## Validation

Verify configuration loads correctly:

```bash
uv run python -c "from src.config import settings; print(f'Bot configured: {settings.telegram_bot_token[:10]}...')"
```

## Troubleshooting

### "OPENAI_API_KEY not set"
- Check `.env` file exists
- Verify `OPENAI_API_KEY=sk-...` (no spaces, no quotes needed)
- Restart bot after changes

### "LLM_API_KEY required for structure strategy"
- Add `LLM_API_KEY=sk-...` to `.env`
- Or switch to `WHISPER_ROUTING_STRATEGY=single` and `LLM_REFINEMENT_ENABLED=false`

### Interactive buttons don't work
- Verify `INTERACTIVE_MODE_ENABLED=true`
- Verify `LLM_REFINEMENT_ENABLED=true`
- Check LLM_API_KEY is valid

## Next Steps

- [Quick Start](quick-start.md) - Run the bot
- [Costs Guide](../deployment/costs.md) - Understand API costs
- [Interactive Features](../features/interactive-modes.md) - Learn about buttons

## Related Documentation

- [.env.example](../../.env.example) - Full configuration template with all options
- [Architecture](../development/architecture.md) - System design
- [Docker Deployment](../deployment/docker.md) - Production deployment
