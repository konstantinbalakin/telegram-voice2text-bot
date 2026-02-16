"""
Centralized logging configuration with structured JSON logging and deployment tracking.

Supports:
- File-based logging with rotation
- Structured JSON format with version/timestamp
- Deployment event tracking
- Optional remote syslog integration
"""

import json
import logging
import logging.handlers
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pythonjsonlogger import jsonlogger


class SensitiveDataFilter(logging.Filter):
    """Mask sensitive patterns (tokens, API keys) in log messages."""

    def __init__(self, patterns: list[str] | None = None):
        super().__init__()
        self._patterns: list[str] = []
        if patterns:
            self._patterns = [p for p in patterns if p]

    def add_pattern(self, pattern: str) -> None:
        if pattern and pattern not in self._patterns:
            self._patterns.append(pattern)

    def filter(self, record: logging.LogRecord) -> bool:
        if self._patterns:
            # Use fully formatted message to catch tokens in non-string args
            # (e.g. httpx.URL objects that contain the bot token)
            formatted = record.getMessage()
            needs_redaction = False
            for pattern in self._patterns:
                if pattern in formatted:
                    redacted = pattern[:4] + "***REDACTED***"
                    formatted = formatted.replace(pattern, redacted)
                    needs_redaction = True
            if needs_redaction:
                record.msg = formatted
                record.args = None
        return True


class VersionEnrichmentFilter(logging.Filter):
    """Add version and container info to all log records."""

    def __init__(self, version: str, container_id: str | None = None):
        super().__init__()
        self.version = version
        self.version_short = version[:7] if version else "unknown"
        self.container_id = container_id or socket.gethostname()

    def filter(self, record: logging.LogRecord) -> bool:
        record.version = self.version_short  # type: ignore
        record.container_id = self.container_id  # type: ignore
        return True


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with timestamp and context."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        # Add ISO timestamp
        log_record["timestamp"] = datetime.fromtimestamp(
            record.created, tz=timezone.utc
        ).isoformat()

        # Add level name
        log_record["level"] = record.levelname

        # Add logger name
        log_record["logger"] = record.name

        # Extract context from extra fields
        context = {}
        for key, value in message_dict.items():
            if key not in ["message", "timestamp", "level", "logger", "version", "container_id"]:
                context[key] = value

        if context:
            log_record["context"] = context


def setup_logging(
    log_dir: Path,
    version: str = "unknown",
    log_level: str = "INFO",
    enable_syslog: bool = False,
    syslog_host: str | None = None,
    syslog_port: int = 514,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,  # Keep 5 backup files
    sensitive_patterns: list[str] | None = None,
) -> None:
    """
    Configure application logging with file rotation and optional remote syslog.

    Rotation strategy:
    - By size: When log file reaches max_bytes, rotate to backup
    - Retention: Keep backup_count old files (e.g., app.log, app.log.1, ..., app.log.5)
    - If logs are generated slowly, they will be kept longer

    Args:
        log_dir: Directory for log files
        version: Application version (git SHA)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_syslog: Enable remote syslog handler
        syslog_host: Syslog server hostname
        syslog_port: Syslog server port
        max_bytes: Maximum size per log file before rotation (default: 10MB)
        backup_count: Number of backup files to keep (default: 5)
        sensitive_patterns: List of sensitive strings to mask in log output
    """
    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create formatters
    json_formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(logger)s %(version)s %(container_id)s %(message)s"
    )

    # Add version enrichment filter
    version_filter = VersionEnrichmentFilter(version=version)

    # Create sensitive data filter
    sensitive_filter = SensitiveDataFilter(patterns=sensitive_patterns)

    # File handler for all logs (JSON format, rotating by size)
    app_log_file = log_dir / "app.log"
    app_handler = logging.handlers.RotatingFileHandler(
        app_log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    app_handler.setLevel(getattr(logging, log_level.upper()))  # Respect configured log level
    app_handler.setFormatter(json_formatter)
    app_handler.addFilter(version_filter)
    app_handler.addFilter(sensitive_filter)
    root_logger.addHandler(app_handler)

    # File handler for errors only (JSON format, rotating by size)
    error_log_file = log_dir / "errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=max_bytes // 2,  # 5MB for errors
        backupCount=backup_count,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(json_formatter)
    error_handler.addFilter(version_filter)
    error_handler.addFilter(sensitive_filter)
    root_logger.addHandler(error_handler)

    # Console handler for development (human-readable)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))  # Respect configured log level
    console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(sensitive_filter)
    root_logger.addHandler(console_handler)

    # Debug handler for detailed logging (only in DEBUG mode)
    if log_level.upper() == "DEBUG":
        debug_log_file = log_dir / "debug.log"
        debug_handler = logging.handlers.RotatingFileHandler(
            debug_log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding="utf-8",
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(json_formatter)
        debug_handler.addFilter(version_filter)
        debug_handler.addFilter(sensitive_filter)
        root_logger.addHandler(debug_handler)

    # Optional: Remote syslog handler
    if enable_syslog and syslog_host:
        try:
            syslog_handler = logging.handlers.SysLogHandler(
                address=(syslog_host, syslog_port),
                socktype=socket.SOCK_STREAM,
            )
            syslog_handler.setLevel(logging.INFO)
            syslog_handler.setFormatter(json_formatter)
            syslog_handler.addFilter(version_filter)
            syslog_handler.addFilter(sensitive_filter)
            root_logger.addHandler(syslog_handler)

            logging.info(f"Remote syslog enabled: {syslog_host}:{syslog_port}")
        except Exception as e:
            logging.warning(f"Failed to setup remote syslog: {e}. Continuing with file logging.")

    logging.info(f"Logging configured: level={log_level}, log_dir={log_dir}, version={version[:7]}")


def log_deployment_event(
    log_dir: Path,
    event: str,
    version: str,
    config: dict[str, Any] | None = None,
    **extra_fields: Any,
) -> None:
    """
    Log a deployment event to deployments.jsonl.

    Args:
        log_dir: Directory for log files
        event: Event type (startup, shutdown, ready, etc.)
        version: Application version (git SHA)
        config: Optional configuration summary
        **extra_fields: Additional fields to include
    """
    deployment_log = log_dir / "deployments.jsonl"

    event_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "version": version,
        "version_short": version[:7] if version else "unknown",
        "container_id": socket.gethostname(),
        **extra_fields,
    }

    if config:
        event_data["config"] = config

    # Append to deployments.jsonl
    try:
        with open(deployment_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data) + "\n")
    except Exception as e:
        logging.error(f"Failed to write deployment event: {e}")


def get_config_summary() -> dict[str, Any]:
    """
    Get a summary of current configuration for deployment logging.

    Returns:
        Dictionary with key configuration values
    """
    from src.config import Settings

    settings = Settings()  # type: ignore[call-arg]

    return {
        "bot_mode": settings.bot_mode,
        "database_url": (
            settings.database_url.split("///")[-1] if "///" in settings.database_url else "postgres"
        ),
        "whisper_providers": settings.whisper_providers,
        "primary_provider": settings.primary_provider,
        "routing_strategy": settings.whisper_routing_strategy,
        "max_queue_size": settings.max_queue_size,
        "max_concurrent_workers": settings.max_concurrent_workers,
        "transcription_timeout": settings.transcription_timeout,
        "max_voice_duration": settings.max_voice_duration_seconds,
    }
