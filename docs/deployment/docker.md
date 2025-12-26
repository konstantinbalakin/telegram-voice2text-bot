# Docker Deployment Guide

[← Back to Documentation](../README.md)

Docker - самый простой способ запуска бота. Все зависимости автоматически устанавливаются в контейнере.

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git
cd telegram-voice2text-bot

# 2. Configure .env file
cp .env.example .env
nano .env  # Set TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, LLM_API_KEY

# 3. Start
docker-compose up -d

# 4. Check logs
docker-compose logs -f bot
```

**Required API keys:**
- `TELEGRAM_BOT_TOKEN` - from @BotFather
- `OPENAI_API_KEY` - from https://platform.openai.com/api-keys
- `LLM_API_KEY` - from https://platform.deepseek.com/api_keys

See [Configuration Guide](../getting-started/configuration.md) for detailed setup instructions.

## Container Management

### Starting the Bot

```bash
# Start in background
docker-compose up -d

# View logs
docker-compose logs -f bot

# Stop
docker-compose stop

# Restart
docker-compose restart

# Full stop and removal
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

## Docker Features

### Persistent Data

- **Database**: Stored in `./data`
- **Logs**: Stored in `./logs`
- **Whisper models**: Cached in volume `whisper-models`

### Resource Limits

Default configuration (in `docker-compose.yml`):
- CPU: 2 cores
- Memory: 2GB RAM

Adjust in `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
```

### Auto-Restart

Bot automatically restarts on failure:
```yaml
restart: unless-stopped
```

## PostgreSQL (Optional)

For production deployment, use PostgreSQL instead of SQLite:

1. Uncomment `postgres` service in `docker-compose.yml`
2. Update `DATABASE_URL` in `.env`:
   ```env
   DATABASE_URL=postgresql+asyncpg://botuser:botpassword@postgres:5432/telegram_bot
   ```
3. Restart: `docker-compose up -d`

## Health Checks

Check container health:

```bash
# Container status
docker-compose ps

# Should show: Up (healthy)

# Detailed health status
docker inspect telegram-voice2text-bot | grep Health

# Connect to container
docker-compose exec bot bash
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs bot

# Common issues:
# - Invalid BOT_TOKEN
# - Port already in use
# - Insufficient resources
```

### Out of Memory

```bash
# Check resource usage
docker stats telegram-voice2text-bot

# Solutions:
# 1. Increase memory limit in docker-compose.yml
# 2. Use smaller Whisper model (base instead of medium)
# 3. Reduce MAX_CONCURRENT_WORKERS in .env
```

### Model Download Issues

```bash
# Models are downloaded on first run
# Check logs for download progress
docker-compose logs -f bot | grep -i download

# Clear cache and retry
docker volume rm whisper-models
docker-compose up -d
```

## Production Deployment

For production VPS deployment with CI/CD:
- See [VPS Setup Guide](vps-setup.md)
- See [CI/CD Guide](cicd.md)

## Related Documentation

- [VPS Setup](vps-setup.md) - Deploy to VPS server
- [CI/CD Pipeline](cicd.md) - Automated deployment
- [Troubleshooting](../deployment/vps-setup.md#troubleshooting) - Common issues
