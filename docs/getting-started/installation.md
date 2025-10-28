# Installation Guide

[← Back to Documentation](../README.md)

## Prerequisites

- **Python 3.11+**
- **Git**
- **2GB+ RAM** (for Whisper medium model)
- **10GB+ disk space** (for models and dependencies)

## Method 1: Local Development (Poetry)

### 1. Install Python 3.11+

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

### 2. Clone Repository

```bash
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git
cd telegram-voice2text-bot
```

### 3. Install Poetry

```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Add to PATH (if not auto-added)
# Add to ~/.zshrc:
export PATH="$HOME/.local/bin:$PATH"

# Verify
poetry --version
```

### 4. Setup Python Environment

```bash
# Configure Poetry to use Python 3.11
poetry env use /opt/homebrew/bin/python3.11
# or
poetry env use /opt/homebrew/bin/python3

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

## Method 2: Local Development (pip)

```bash
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
# Activate environment
poetry shell  # or source venv/bin/activate

# Check Python version
python --version

# Check main dependencies
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

### Poetry not found

```bash
# Add Poetry to PATH
export PATH="$HOME/.local/bin:$PATH"

# Or reinstall
curl -sSL https://install.python-poetry.org | python3 -
```

### Python version mismatch

```bash
# Specify exact Python version for Poetry
poetry env use python3.11

# Or use full path
poetry env use /usr/local/bin/python3.11
```

### Dependency installation fails

```bash
# Update Poetry
poetry self update

# Clear cache and retry
poetry cache clear pypi --all
poetry install
```

### Docker installation fails

See [Docker Troubleshooting](../deployment/docker.md#troubleshooting)
