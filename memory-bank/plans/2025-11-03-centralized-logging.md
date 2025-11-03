# Centralized Logging Implementation Plan

**Date**: 2025-11-03
**Status**: Approved
**Type**: Infrastructure Enhancement

## Objective

Implement centralized logging system that:
- Preserves logs across deployments
- Tracks application versions (git SHA)
- Records restart timestamps
- Supports optional remote log aggregation

## Selected Approach: Hybrid (Option 3)

**Phase 1**: File-based structured logging with version tracking
**Phase 2**: Optional remote syslog integration

## Technical Design

### Architecture

```
┌─────────────────────────────────────────┐
│  Bot Application                        │
│  ┌──────────────────────────────────┐  │
│  │  Structured Logger                │  │
│  │  - JSON formatter                 │  │
│  │  - Version enrichment             │  │
│  │  - Request ID tracking            │  │
│  └────┬─────────────────────┬────────┘  │
│       │                     │            │
│       v                     v            │
│  ┌─────────┐        ┌──────────────┐   │
│  │  Files  │        │  Syslog      │   │
│  │ (always)│        │ (optional)   │   │
│  └────┬────┘        └──────┬───────┘   │
│       │                    │            │
└───────┼────────────────────┼────────────┘
        │                    │
        v                    v
   logs/ volume       Remote Service
   ├── app.log        (Papertrail/etc)
   ├── errors.log
   └── deployments.jsonl
```

### Log Structure

#### deployments.jsonl Format
```json
{
  "timestamp": "2025-11-03T15:00:00.000Z",
  "event": "startup",
  "version": "09f9af862eb834b3f62a4aa3acf3bb4e32e2aa83",
  "version_short": "09f9af8",
  "container_id": "e3f297d9fe90",
  "python_version": "3.11.x",
  "config": {
    "bot_mode": "polling",
    "whisper_model": "medium",
    "max_queue_size": 10
  }
}
```

#### Application Log Format (JSON Lines)
```json
{
  "timestamp": "2025-11-03T15:00:05.123Z",
  "level": "INFO",
  "logger": "src.bot.handlers",
  "version": "09f9af8",
  "message": "Processing voice message",
  "context": {
    "user_id": 123456,
    "duration": 45.2,
    "file_size": 128000
  }
}
```

### Retention Strategy

| Log Type | Rotation | Max Size | Retention |
|----------|----------|----------|-----------|
| app.log | 10MB | 50MB total (5 files) | 7 days |
| errors.log | 5MB | 25MB total (5 files) | 14 days |
| deployments.jsonl | No rotation | Unlimited | Forever |

## Implementation Steps

### Phase 1: File-based Logging (Priority 1)

1. **Create logging configuration module**
   - File: `src/utils/logging_config.py`
   - Implement JSON formatter
   - Setup rotating file handlers
   - Add deployment event logger

2. **Modify application startup**
   - File: `src/main.py`
   - Initialize logging on startup
   - Log deployment event with version/config
   - Log shutdown event (graceful)

3. **Add dependencies**
   - File: `pyproject.toml`
   - Add: `python-json-logger`

4. **Update deployment configuration**
   - File: `docker-compose.prod.yml`
   - Add: `APP_VERSION` environment variable
   - Ensure logs volume permissions

5. **Update CI/CD pipeline**
   - File: `.github/workflows/build-and-deploy.yml`
   - Pass `GITHUB_SHA` as `APP_VERSION`
   - Log deployment start/finish

### Phase 2: Remote Syslog (Priority 2)

1. **Extend logging configuration**
   - File: `src/utils/logging_config.py`
   - Add optional `SysLogHandler`
   - Implement graceful fallback

2. **Add environment configuration**
   - Optional env vars:
     - `SYSLOG_ENABLED=true/false`
     - `SYSLOG_HOST=logs.example.com`
     - `SYSLOG_PORT=514`

3. **Test with Papertrail**
   - Sign up for free tier
   - Configure endpoint
   - Verify log ingestion

## Files to Create/Modify

### New Files
- `src/utils/logging_config.py` - Logging configuration
- `memory-bank/plans/2025-11-03-centralized-logging.md` - This file

### Modified Files
- `src/main.py` - Initialize logging, log startup/shutdown
- `pyproject.toml` - Add logging dependencies
- `docker-compose.prod.yml` - Add APP_VERSION env var
- `.github/workflows/build-and-deploy.yml` - Pass version to container
- `docs/development/logging.md` - Documentation (new)

## Risk Mitigation

### Risk: Disk Space Exhaustion
**Mitigation**:
- Aggressive rotation (50MB max for app.log)
- Separate errors.log with longer retention
- Monitor disk usage in healthcheck

### Risk: Logging Performance Impact
**Mitigation**:
- Use `QueueHandler` for async logging
- Buffer writes to reduce I/O
- Disable DEBUG logs in production

### Risk: Remote Syslog Unavailable
**Mitigation**:
- Graceful degradation to file-only
- Connection timeout (5 seconds)
- Don't block application on syslog failure

### Risk: Log Volume Permissions
**Mitigation**:
- Create logs directory in Dockerfile
- Set ownership to appuser (UID 1000)
- Verify in healthcheck

## Success Criteria

- [ ] Logs persist across deployments
- [ ] deployments.jsonl contains version for each startup
- [ ] Can identify logs for specific version via grep
- [ ] Log rotation prevents disk exhaustion
- [ ] Application performance unchanged (<5ms overhead)
- [ ] Remote syslog optional and gracefully degrades
- [ ] Documentation updated

## Testing Strategy

### Local Testing
1. Run bot locally with file logging
2. Verify JSON format in logs/app.log
3. Test log rotation (create large logs)
4. Verify deployments.jsonl created on startup

### VPS Testing
1. Deploy to VPS
2. Verify logs persist after restart
3. Check version in deployments.jsonl
4. Test remote syslog (if enabled)
5. Monitor disk usage

### Integration Testing
1. Multiple deployments in sequence
2. Verify each deployment logged
3. Check logs accessible for old versions
4. Verify no disk space issues

## Rollback Plan

If issues arise:
1. Revert to stdout logging (current behavior)
2. Remove logging_config.py import from main.py
3. Keep logs volume (no harm)
4. Docker logs still available as fallback

## Future Enhancements

- Log aggregation UI (Grafana/Loki) if VPS upgraded
- Automated log shipping to S3/backup
- Request ID correlation across services
- Performance metrics in structured logs
- ELK stack integration for advanced analytics

## References

- Python logging: https://docs.python.org/3/library/logging.html
- python-json-logger: https://github.com/madzak/python-json-logger
- Papertrail: https://papertrailapp.com/
- Structured logging best practices: https://www.structlog.org/
