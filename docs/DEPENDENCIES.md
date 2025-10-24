# Dependency Management

This project uses **Poetry** for Python dependency management, but also maintains `requirements.txt` files for Docker builds.

## Poetry Workflow (Development)

### Adding Dependencies

```bash
# Add a regular dependency
poetry add <package>

# Add a development dependency
poetry add --group dev <package>

# Add an optional dependency
poetry add --optional <package>
```

### Installing Dependencies

```bash
# Install all dependencies
poetry install

# Install with specific extras (providers)
poetry install --extras "faster-whisper"
poetry install --extras "all-providers"
```

## Docker Workflow (Production)

### Updating requirements.txt

After modifying `pyproject.toml`, update the requirements files:

```bash
./scripts/update-requirements.sh
```

This generates:
- `requirements.txt` - Base dependencies only
- `requirements-docker.txt` - Base + faster-whisper (recommended for Docker)

### Dockerfile Configuration

Update `Dockerfile` to use the appropriate requirements file:

```dockerfile
COPY requirements-docker.txt requirements.txt
RUN pip install -r requirements.txt
```

## Available Provider Extras

The project supports two transcription providers as optional extras:

### faster-whisper (Recommended - Production Default)
```bash
poetry install --extras "faster-whisper"
```
- Fast local transcription using CTranslate2
- Low memory usage with quantization support (int8)
- Production configuration: medium/int8/beam1 (RTF ~0.3x)
- Best for production deployment on CPU
- ~1.5GB model size for medium

### openai-api
```bash
poetry install --extras "openai-api"
```
- Uses OpenAI's Whisper API
- Requires API key and internet connection
- Best quality but costs $0.006 per minute
- Useful as fallback or reference

## Package Versions

### Core Dependencies
- Python: ^3.11
- python-telegram-bot: ^22.5
- SQLAlchemy: ^2.0.44
- pydantic: ^2.10

### Transcription Providers
- faster-whisper: ^1.2.0 (production default)
- openai: ^1.50.0 (optional)

## Common Tasks

### Update all dependencies
```bash
poetry update
./scripts/update-requirements.sh
```

### Check for outdated packages
```bash
poetry show --outdated
```

### Add a new provider
1. Add to `pyproject.toml` as optional dependency
2. Add to `[tool.poetry.extras]` section
3. Run `poetry lock`
4. Run `./scripts/update-requirements.sh`
5. Update this documentation

## Troubleshooting

### "Module not found" errors
```bash
# Ensure you've installed the right extras
poetry install --extras "faster-whisper"

# Or reinstall all dependencies
poetry install --sync
```

### Docker build failures
```bash
# Regenerate requirements.txt
./scripts/update-requirements.sh

# Rebuild Docker image
docker build --no-cache -t telegram-voice2text-bot .
```

### Wrong whisper package installed
The package name is `openai-whisper`, not `whisper` (which is a different package).

If you see errors like `module 'whisper' has no attribute 'load_model'`:
1. Uninstall wrong package: `poetry remove whisper`
2. Add correct package: `poetry add --optional openai-whisper`
3. Update requirements: `./scripts/update-requirements.sh`
