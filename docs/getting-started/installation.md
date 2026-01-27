# Installation Guide

[← Back to Documentation](../README.md)

## Prerequisites

- **Python 3.11+**
- **Git**
- **ffmpeg** (required for audio processing features like mono conversion and speed adjustment)
- **2GB+ RAM** (for Whisper medium model)
- **10GB+ disk space** (for models and dependencies)

## Method 1: Local Development (uv)

### 1. Install System Dependencies

#### ffmpeg (Required)

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y ffmpeg

# Verify installation
ffmpeg -version
```

### 2. Install Python 3.11+

```bash
# Check current version
python3 --version

# If < 3.11, install (macOS):
brew install python@3.11

# Reset zsh cache
hash -r

# Verify
python3 --version  # Should be 3.11+
```

### 3. Clone Repository

```bash
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git
cd telegram-voice2text-bot
```

### 4. Install uv

```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (if not auto-added)
# Add to ~/.zshrc:
export PATH="$HOME/.local/bin:$PATH"

# Verify
uv --version
```

### 5. Setup Python Environment

```bash
# Install Python 3.11 via uv (optional, if not installed)
uv python install 3.11

# Install dependencies (creates .venv automatically)
uv sync --all-extras

# Run commands via uv run
uv run python -m src.main
```

## Method 2: Local Development (pip)

```bash
# Install ffmpeg first (see Method 1 for instructions)
# macOS: brew install ffmpeg
# Ubuntu/Debian: sudo apt-get install -y ffmpeg

# Clone repository
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git
cd telegram-voice2text-bot

# Create virtual environment
python3 -m venv venv

# Activate
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -e .
```

## Method 3: Docker (Recommended for Production)

```bash
# Clone repository
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git
cd telegram-voice2text-bot

# Configure environment
cp .env.example .env
nano .env  # Set BOT_TOKEN

# Start with Docker Compose
docker-compose up -d
```

See [Docker Guide](../deployment/docker.md) for details.

## Verify Installation

### Local Installation

```bash
# Run a quick check
uv run python -c "import sqlalchemy, httpx; print('Dependencies OK')"

# Or if using venv directly
source venv/bin/activate
python -c "import sqlalchemy, httpx; print('Dependencies OK')"
```

### Docker Installation

```bash
# Check container status
docker-compose ps

# Should show: telegram-voice2text-bot Up (healthy)
```

## Next Steps

1. [Configure the bot](configuration.md) - Set up environment variables
2. [Quick Start](quick-start.md) - Run your first bot
3. [Development Guide](../development/testing.md) - Start developing

## Troubleshooting

### uv not found

```bash
# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"

# Or reinstall
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Python version mismatch

```bash
# Install specific Python version via uv
uv python install 3.11

# Use specific Python for sync
uv sync --python 3.11
```

### Dependency installation fails

```bash
# Clear cache and retry
uv cache clean
uv sync --all-extras
```

### ffmpeg not found

If you see warnings about "Mono conversion failed" or "ffmpeg: command not found":

```bash
# Check if ffmpeg is installed
which ffmpeg

# If not found, install:
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y ffmpeg

# Verify
ffmpeg -version
```

**Note**: Some audio processing features (mono conversion, speed adjustment) require ffmpeg. The bot will work without it but those features will be disabled.

### Docker installation fails

See [Docker Troubleshooting](../deployment/docker.md#troubleshooting)
