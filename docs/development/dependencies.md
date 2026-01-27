# Dependency Management

This project uses **uv** for Python dependency management and maintains `requirements.txt` files for Docker builds.

## uv Workflow (Development)

### Adding Dependencies

```bash
# Add a regular dependency
uv add <package>

# Add a development dependency
uv add --group dev <package>

# Add an optional dependency (to an extra)
uv add --optional faster-whisper <package>
```

### Installing Dependencies

```bash
# Install all dependencies (creates .venv automatically)
uv sync

# Install with specific extras (providers)
uv sync --extra faster-whisper
uv sync --all-extras

# Install with dev dependencies
uv sync --all-extras --all-groups
```

## Docker Workflow (Production)

### Updating requirements.txt

After modifying `pyproject.toml`, update the requirements file:

```bash
make deps
# or manually:
uv export --no-dev --extra faster-whisper --extra openai-api -o requirements.txt
```

### Dockerfile Configuration

The `Dockerfile` uses requirements.txt:

```dockerfile
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
```

## Available Provider Extras

The project supports two transcription providers as optional extras:

### faster-whisper (Recommended - Production Default)
```bash
uv sync --extra faster-whisper
```
- Fast local transcription using CTranslate2
- Low memory usage with quantization support (int8)
- Production configuration: medium/int8/beam1 (RTF ~0.3x)
- Best for production deployment on CPU
- ~1.5GB model size for medium

### openai-api
```bash
uv sync --extra openai-api
```
- Uses OpenAI's Whisper API
- Requires API key and internet connection
- Best quality but costs $0.006 per minute
- Useful as fallback or reference

## Package Versions

### Core Dependencies
- Python: >=3.11,<4.0
- python-telegram-bot: >=22.5,<23.0
- SQLAlchemy: >=2.0.44,<3.0.0
- pydantic: >=2.10,<3.0

### Transcription Providers
- faster-whisper: >=1.2.1,<2.0.0 (production default)
- openai: >=1.50.0,<2.0.0 (optional)

## Common Tasks

### Update all dependencies
```bash
uv lock --upgrade
uv sync --all-extras --all-groups
make deps  # Export requirements.txt
```

### Check lock file
```bash
# Verify lock file is up to date
uv lock --check
```

### Add a new provider
1. Add to `pyproject.toml` as optional dependency in `[project.optional-dependencies]`
2. Run `uv lock`
3. Run `make deps`
4. Update this documentation

## Troubleshooting

### "Module not found" errors
```bash
# Ensure you've installed the right extras
uv sync --extra faster-whisper

# Or reinstall all dependencies
uv sync --all-extras --all-groups
```

### Docker build failures
```bash
# Regenerate requirements.txt
make deps

# Rebuild Docker image
docker build --no-cache -t telegram-voice2text-bot .
```

### Lock file out of date
```bash
# Regenerate lock file
uv lock

# Then sync
uv sync --all-extras
```

### Wrong whisper package installed
The package name is `openai-whisper`, not `whisper` (which is a different package).

If you see errors like `module 'whisper' has no attribute 'load_model'`:
1. Check pyproject.toml has correct package
2. Run `uv lock` to regenerate lock
3. Run `uv sync --all-extras` to reinstall
