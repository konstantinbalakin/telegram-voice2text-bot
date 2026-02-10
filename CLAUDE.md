# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram Voice2Text Bot - Production-ready Telegram bot for voice transcription with AI-powered text processing.

**Tech Stack**: OpenAI Whisper API (transcription) + DeepSeek V3 (text processing) + Interactive buttons

**GitHub Repository**: `konstantinbalakin/telegram-voice2text-bot`

## Memory Bank System

This project uses the Claude Code Memory Bank system located in `/memory-bank/`. The Memory Bank maintains project context across sessions through structured documentation files.

### Key Memory Bank Files

Located in `/memory-bank/`:

- `projectbrief.md` - Core requirements and project goals
- `productContext.md` - Problem statement and user experience goals
- `activeContext.md` - Current work focus, recent changes, and next steps
- `systemPatterns.md` - Architecture and technical decisions
- `techContext.md` - Technologies, dependencies, and development setup
- `progress.md` - Current status, what works, and what's left to build
- `plans/` - Detailed implementation plans

### Workflow

1. **Session Start**: Review Memory Bank context to understand current project state
2. **Task Assessment**: Analyze complexity and approach
3. **Plan & Decompose** (for complex tasks): Break down into manageable subtasks
4. **Execute**: Implement solution
5. **Memory Update**: Document significant changes and learnings

### When to Update Memory Bank

- After implementing significant features
- When discovering new architectural patterns
- At natural project milestones
- When context needs clarification for future sessions

Use the `/workflow:update-memory` slash command to update the Memory Bank.

## Documentation

**Main documentation** is located in `/docs/` directory:
- `/docs/README.md` - Documentation index and navigation
- `/docs/getting-started/` - Installation, configuration, quick start
- `/docs/development/` - Architecture, testing, git workflow, dependencies
- `/docs/deployment/` - Docker, VPS setup, CI/CD pipeline
- `/docs/research/` - Performance benchmarks

## Git Workflow

This project uses **Trunk Based Development** with protected main branch. See `docs/development/git-workflow.md` for complete details.

### CRITICAL RULES

- **NEVER commit or push directly to `main` or `master`**. Always create a feature branch first.
- All changes go through PRs: feature branch → PR → merge to main.
- Pre-commit hooks enforce this rule (see `.pre-commit-config.yaml`).

### Quick Reference

**Start Feature**:
```bash
git checkout main
git pull origin main
git checkout -b feature/your-feature-name
```

**Commit Changes** (use Conventional Commits):
```bash
git add <files>
git commit -m "feat: add something"
git push origin feature/your-feature-name
```

**Create PR**:
```bash
gh pr create --title "feat: description" --body "..."
```

**Commit Types**:
- `feat:` - New functionality
- `fix:` - Bug fixes
- `refactor:` - Code refactoring
- `docs:` - Documentation
- `test:` - Tests
- `chore:` - Maintenance

**Slash Command Integration**:
- Use `/commit` for automatic commit message generation
- Push manually after commit: `git push origin <branch-name>`

### Pre-commit / Pre-push Hooks

This project uses `pre-commit` framework. Hooks are installed automatically:

```bash
uv run pre-commit install   # installs both pre-commit and pre-push hooks
```

**Pre-commit** (every `git commit`): no-commit-to-branch, ruff, black
**Pre-push** (every `git push`): mypy, pytest

Before pushing, ensure ALL CI checks pass locally:
```bash
uv run ruff check src/
uv run black --check src/ tests/
uv run mypy src/
TELEGRAM_BOT_TOKEN=test uv run pytest tests/unit/ -v
```

## Development Commands

This project uses **uv** for Python package management:

```bash
# Install dependencies
uv sync --all-extras --all-groups

# Run bot
uv run python -m src.main

# Run tests
uv run pytest tests/unit/ -v

# Run linting/formatting
uv run ruff check src/
uv run black src/
uv run mypy src/

# Database migrations
uv run alembic upgrade head

# Export requirements for Docker
make deps
```

## Development Status

✅ **Current Status**: Production-ready, Phase 10.14 complete

**Completed Phases**:
- Phase 1-6: Project Setup, Core Functionality, Docker, VPS, Queue System ✅
- Phase 7-9: Logging, Hybrid Transcription, Large Files (Telethon) ✅
- Phase 10: Interactive Transcription System (all 14 sub-phases) ✅

**Production Configuration**:
- **Bot**: ✅ Live on Telegram, free during user acquisition
- **Transcription**: ✅ OpenAI Whisper API (gpt-4o models + whisper-1)
- **Text Processing**: ✅ DeepSeek V3 (структурирование, резюме, "сделать красиво")
- **Interactive Features**: ✅ 3 buttons - Структурировать, Сделать красиво, О чем этот текст
- **Large Files**: ✅ Telethon support up to 2 GB
- **Database**: ✅ SQLite with variant caching
- **Docker**: ✅ Automated builds and deployments
- **CI/CD**: ✅ GitHub Actions pipeline active

**Next Phase**: Analytics dashboard, quotas & billing, multi-language

## Additional Instructions
- @memory-bank/!memory-bank.md