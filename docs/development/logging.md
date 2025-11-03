# Centralized Logging

The Telegram Voice2Text Bot uses a centralized logging system that preserves logs across deployments and tracks application versions.

## Overview

**Logging Architecture:**
- **File-based logging** with JSON format for structured data
- **Deployment tracking** in `deployments.jsonl`
- **Log rotation** to prevent disk exhaustion
- **Optional remote syslog** for centralized log aggregation

## Log Files

All logs are stored in `/app/logs/` (Docker) or `./logs/` (local development):

### Application Logs

**`app.log`**
- All INFO+ level logs in JSON format
- **Rotates when file reaches 10MB** (keeps 5 backups: app.log.1, app.log.2, ..., app.log.5)
- Total max size: ~60MB (current + 5 backups)
- If bot generates few logs, files will be kept for longer periods
- Includes version, timestamp, logger name, context

Example:
```json
{
  "timestamp": "2025-11-03T15:00:05.123Z",
  "level": "INFO",
  "logger": "src.bot.handlers",
  "version": "09f9af8",
  "container_id": "e3f297d9fe90",
  "message": "Processing voice message",
  "context": {
    "user_id": 123456,
    "duration": 45.2,
    "file_size": 128000
  }
}
```

**`errors.log`**
- ERROR and CRITICAL level logs only
- **Rotates when file reaches 5MB** (keeps 5 backups)
- Total max size: ~30MB
- Same JSON format as app.log

**`deployments.jsonl`**
- Deployment lifecycle events (startup, ready, shutdown)
- **Never rotated** (grows indefinitely, but minimal size)
- One event per line in JSON format

Example:
```json
{"timestamp": "2025-11-03T15:00:00.000Z", "event": "startup", "version": "09f9af862eb834b3f62a4aa3acf3bb4e32e2aa83", "version_short": "09f9af8", "container_id": "e3f297d9fe90", "config": {"bot_mode": "polling", "whisper_model": "medium", ...}}
{"timestamp": "2025-11-03T15:00:05.123Z", "event": "ready", "version": "09f9af8", "container_id": "e3f297d9fe90"}
```

## Configuration

### Environment Variables

**Required:**
- `APP_VERSION` - Application version (git SHA), set automatically by CI/CD
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

**Optional (Remote Syslog):**
- `SYSLOG_ENABLED` - Enable remote syslog (true/false, default: false)
- `SYSLOG_HOST` - Syslog server hostname
- `SYSLOG_PORT` - Syslog server port (default: 514)

### Docker Compose

Version is automatically passed from GitHub Actions:

```yaml
environment:
  - APP_VERSION=${APP_VERSION:-unknown}
  - LOG_LEVEL=INFO
  # Optional remote logging
  - SYSLOG_ENABLED=${SYSLOG_ENABLED:-false}
  - SYSLOG_HOST=${SYSLOG_HOST:-}
```

### CI/CD

The `.env` file is created during deployment with:

```bash
APP_VERSION=${{ github.sha }}
```

This ensures every deployment is tagged with the exact git commit.

## Deployment Tracking

### Startup Event

Logged when the bot starts:
- Application version (full SHA + short)
- Configuration summary
- Container ID

### Ready Event

Logged when the bot is fully initialized and ready to accept requests.

### Shutdown Event

Logged during graceful shutdown (SIGINT, SIGTERM).

## Usage

### Viewing Logs

**Recent logs (tail):**
```bash
# Via SSH on VPS
docker logs telegram-voice2text-bot --tail 100

# Or via docker-compose
docker compose -f docker-compose.prod.yml logs --tail 100 bot
```

**Follow live logs:**
```bash
docker logs telegram-voice2text-bot -f
```

**Access log files directly:**
```bash
# On VPS
ssh telegram-bot "cat /opt/telegram-voice2text-bot/logs/app.log"

# View deployments history
ssh telegram-bot "cat /opt/telegram-voice2text-bot/logs/deployments.jsonl"
```

### Searching Logs

**Find logs for specific version:**
```bash
grep '"version":"09f9af8"' logs/app.log
```

**Find all errors:**
```bash
grep '"level":"ERROR"' logs/app.log
```

**Find logs for specific user:**
```bash
grep '"user_id":123456' logs/app.log
```

**View all deployments:**
```bash
cat logs/deployments.jsonl | jq .
```

**Get version of last deployment:**
```bash
tail -1 logs/deployments.jsonl | jq -r '.version_short'
```

### Analyzing with jq

Parse JSON logs with `jq`:

```bash
# Get all error messages
cat logs/errors.log | jq -r '.message'

# Count errors by logger
cat logs/errors.log | jq -r '.logger' | sort | uniq -c

# Find slowest transcriptions
cat logs/app.log | jq 'select(.message | contains("Transcription")) | .context.duration' | sort -rn | head -10
```

## Remote Logging (Optional)

### Setup with Papertrail

1. Sign up at [papertrailapp.com](https://papertrailapp.com) (free tier: 50MB/month)

2. Get your log destination (e.g., `logs.papertrailapp.com:12345`)

3. Update `.env` on VPS:
```bash
SYSLOG_ENABLED=true
SYSLOG_HOST=logs.papertrailapp.com
SYSLOG_PORT=12345
```

4. Restart bot:
```bash
docker compose -f docker-compose.prod.yml restart bot
```

### Graceful Fallback

If remote syslog is unavailable:
- Bot will log a warning
- File logging continues normally
- No impact on application functionality

## Log Retention

| Log Type | Rotation Trigger | Max Size | Retention Period |
|----------|------------------|----------|------------------|
| app.log | 10MB per file | 60MB total (6 files) | Based on log volume |
| errors.log | 5MB per file | 30MB total (6 files) | Based on log volume |
| deployments.jsonl | No rotation | Unlimited | Forever |

**How it works:**
- **Size-based rotation**: Logs rotate when reaching size limit, NOT by time
- **If few logs generated**: Files kept for weeks/months
- **If many logs generated**: Rotates more frequently
- **Predictable disk usage**: Never exceeds ~90MB total

**Disk usage estimation:**
- Application logs: ~60MB max
- Error logs: ~30MB max
- Deployment logs: ~1KB per deployment (~365KB/year for daily deploys)
- **Total**: ~90MB maximum (guaranteed)

## Structured Logging in Code

### Adding Context to Logs

Use the `extra` parameter to add structured context:

```python
import logging

logger = logging.getLogger(__name__)

logger.info(
    "Voice message processed",
    extra={
        "user_id": message.from_user.id,
        "duration": audio_duration,
        "file_size": file.file_size,
        "provider": "faster-whisper",
    }
)
```

This will appear in the JSON log as:
```json
{
  "timestamp": "...",
  "level": "INFO",
  "message": "Voice message processed",
  "context": {
    "user_id": 123456,
    "duration": 45.2,
    "file_size": 128000,
    "provider": "faster-whisper"
  }
}
```

### Logging Levels

Follow these guidelines:

- **DEBUG**: Detailed information for debugging (disabled in production)
- **INFO**: Normal operations (requests, transcriptions, status changes)
- **WARNING**: Degraded performance, quota limits, retries
- **ERROR**: Failed operations that don't crash the app
- **CRITICAL**: Service unavailable, data loss, requires immediate attention

## Troubleshooting

### Logs not appearing

**Check log directory exists:**
```bash
docker exec telegram-voice2text-bot ls -la /app/logs/
```

**Check permissions:**
```bash
# On VPS
ls -la /opt/telegram-voice2text-bot/logs/
# Should be owned by UID 1000 (appuser)
```

**Check volume mount:**
```bash
docker inspect telegram-voice2text-bot --format '{{json .Mounts}}' | jq .
```

### Disk space issues

**Check current usage:**
```bash
du -sh /opt/telegram-voice2text-bot/logs/
```

**Manually rotate logs:**
```bash
cd /opt/telegram-voice2text-bot/logs/
gzip app.log.5  # Compress oldest
rm app.log.5.gz  # Or remove if needed
```

### Version showing as "unknown"

**Check environment variable:**
```bash
docker inspect telegram-voice2text-bot --format '{{range .Config.Env}}{{println .}}{{end}}' | grep APP_VERSION
```

Should show: `APP_VERSION=<git-sha>`

If not, redeploy or set manually in `.env`.

## Best Practices

1. **Use structured logging** - Always add context via `extra` parameter
2. **Log user actions** - Track user_id for debugging and analytics
3. **Log performance metrics** - Duration, file sizes, queue lengths
4. **Don't log secrets** - Never log tokens, API keys, passwords
5. **Use appropriate levels** - Follow the level guidelines above
6. **Add correlation IDs** - For tracing requests across components

## Future Enhancements

Potential improvements for larger scale:

- **Grafana Loki** for log aggregation (requires more RAM)
- **ELK stack** for advanced analytics
- **S3 backup** for long-term log retention
- **Request ID correlation** across all components
- **Performance metrics** integration with Prometheus

## References

- [python-json-logger](https://github.com/madzak/python-json-logger) - JSON logging library
- [Papertrail](https://papertrailapp.com/) - Cloud log aggregation
- [jq Manual](https://jqlang.github.io/jq/manual/) - JSON query tool
- [Logging Best Practices](https://www.datadoghq.com/blog/python-logging-best-practices/)
