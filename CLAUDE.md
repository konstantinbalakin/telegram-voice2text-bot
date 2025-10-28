# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram Voice2Text Bot - A Telegram bot for working with voice messages. Currently in initial setup stage.

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

This project uses **Feature Branch Workflow** with protected main branch. See `docs/development/git-workflow.md` for complete details.

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

## Development Status

✅ **Current Status**: Production-ready, deployed on VPS

**Completed Phases**:
- Phase 1: Project Setup ✅
- Phase 2: Core Functionality (Database, Whisper, Bot) ✅
- Phase 3: Docker & CI/CD ✅
- Phase 4: VPS Deployment ✅

**Project Status**:
- **Bot**: ✅ Live on Telegram, handling users
- **Transcription**: ✅ faster-whisper medium/int8 (RTF ~0.3x)
- **Database**: ✅ SQLite (ready for PostgreSQL migration)
- **Docker**: ✅ Automated builds and deployments
- **CI/CD**: ✅ GitHub Actions pipeline active

**Next Phase**: Advanced features (quotas, billing, summarization)

## Additional Instructions
- @memory-bank/!memory-bank.md