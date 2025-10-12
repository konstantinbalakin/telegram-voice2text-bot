# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram Voice2Text Bot - A Telegram bot for working with voice messages. Currently in initial draft stage.

## Memory Bank System

This project uses the Claude Code Memory Bank system located in `.claude/`. The Memory Bank maintains project context across sessions through structured documentation files.

### Key Memory Bank Files

- `projectbrief.md` - Core requirements and project goals
- `productContext.md` - Problem statement and user experience goals
- `activeContext.md` - Current work focus, recent changes, and next steps
- `systemPatterns.md` - Architecture and technical decisions
- `techContext.md` - Technologies, dependencies, and development setup
- `progress.md` - Current status, what works, and what's left to build

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

## Development Status

⚠️ Project is in initial draft stage. Build system, dependencies, and core functionality are not yet implemented.

## Additional Instructions
- @.claude/claude-memory-bank.md