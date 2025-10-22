# Repository Guidelines

## Project Structure & Module Organization
- `src/`: Async Telegram bot core (`bot/`, `processing/`, `transcription/`, `storage/`, `quota/`) with `main.py` as the entry point.
- `tests/`: Pytest suites split into `unit/` and `integration/`; mirrors package layout and shares fixtures via `conftest.py`.
- `alembic/`: Database migrations; keep migration heads in sync with `storage` models.
- `docker/`, `.devcontainer/`, `scripts/`: Local/remote dev tooling, Compose configs, and helper utilities.

## Build, Test, and Development Commands
- `poetry install`: Install Python dependencies into the managed virtualenv.
- `poetry run python -m src.main`: Launch the bot locally; requires a configured `.env`.
- `poetry run pytest --cov=src`: Run the full test suite with coverage.
- `poetry run mypy src`: Static type checks for the application code.
- `poetry run ruff check src`: Linting pass; add `--fix` for auto-fixes.
- `docker compose up --build`: Build and run the bot plus service dependencies inside containers.
- `make build` / `make up` / `make down`: Shortcut wrappers for Compose workflows.

## Coding Style & Naming Conventions
- Python 3.11+, 4-space indentation, line length capped at 100 (Black/Ruff config).
- Modules and functions use `snake_case`; classes use `CamelCase`; constants use `SCREAMING_SNAKE_CASE`.
- Keep async/await flows explicit; prefer dataclasses or Pydantic models for structured data.
- Run `poetry run black src tests` before committing if formatting drifts.

## Testing Guidelines
- Use Pytest with async support; place new tests under the matching `tests/unit` or `tests/integration` subtree.
- Name files `test_<module>.py` and functions `test_<behavior>()`; group scenario-specific helpers in fixtures.
- Target coverage >80% for new features; justify any gaps in the PR description.
- Mock external APIs (Telegram, Whisper providers) via fixtures in `tests/conftest.py`.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`feat(bot): …`, `fix(storage): …`, `chore(ci): …`) to keep history searchable.
- One logical change per commit; include updates to tests, docs, and configs in the same PR.
- PRs must include: summary, linked issue (if applicable), testing evidence (`pytest` output or manual steps), and any deployment/config notes.
- Rebase onto `main` before opening; resolve conflicts locally and ensure CI (pytest/mypy/ruff/black) passes.

## Security & Configuration Tips
- Never commit secrets; copy `configs/.env.example` to `.env` and load via environment variables.
- Rotate Telegram tokens and speech-provider keys regularly; document rotations in `docs/` as needed.
- Validate new third-party integrations using the Docker sandbox before enabling in production.

## Additional Context Resources
- Load supplementary project context from `memory-bank/!memory-bank.md` when initializing agents.
