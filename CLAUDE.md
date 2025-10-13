# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram Voice2Text Bot - A Telegram bot for working with voice messages. Currently in initial setup stage.

**GitHub Repository**: `konstantinbalakin/telegram-voice2text-bot`

## Memory Bank System

This project uses the Claude Code Memory Bank system located in `.claude/`. The Memory Bank maintains project context across sessions through structured documentation files.

### Key Memory Bank Files

Located in `.claude/memory-bank/`:

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

## Git Workflow

This project uses **Feature Branch Workflow** with protected main branch. See `.github/WORKFLOW.md` for complete details.

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

⚠️ **Current Phase**: Phase 1 Complete (Project Setup)

**Next Steps**:
1. Install dependencies: `poetry install`
2. Create feature branch for database work
3. Begin Phase 2: Database Models & Whisper Service

**Project Structure**: ✅ Ready
**Dependencies**: ✅ Configured (not yet installed)
**Configuration**: ✅ Implemented (src/config.py)
**Entry Point**: ✅ Ready (src/main.py)

## Additional Instructions
- @.claude/claude-memory-bank.md