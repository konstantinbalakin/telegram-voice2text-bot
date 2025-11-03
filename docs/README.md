# Documentation

Welcome to Telegram Voice2Text Bot documentation!

## Quick Navigation

### 🚀 Getting Started

New to the project? Start here:

- **[Installation](getting-started/installation.md)** - Set up development environment
- **[Configuration](getting-started/configuration.md)** - Configure the bot
- **[Quick Start](getting-started/quick-start.md)** - Run your first bot

### 💻 Development

For contributors and developers:

- **[Architecture](development/architecture.md)** - System design and components
- **[Database Migrations](development/database-migrations.md)** - Creating and testing migrations
- **[Dependencies](development/dependencies.md)** - Managing Python packages
- **[Logging](development/logging.md)** - Centralized logging and version tracking
- **[Testing](development/testing.md)** - Local testing and benchmarks
- **[Git Workflow](development/git-workflow.md)** - Branching and PR process

### 🚢 Deployment

Deploy to production:

- **[Docker Guide](deployment/docker.md)** - Containerized deployment
- **[VPS Setup](deployment/vps-setup.md)** - Deploy to VPS server
- **[CI/CD Pipeline](deployment/cicd.md)** - Automated deployment with GitHub Actions
- **[Migration Runbook](deployment/migration-runbook.md)** - Database migration operations

### 📊 Research

Performance and benchmarking:

- **[Benchmarks](research/benchmarks/)** - Model quality comparisons

## Documentation by Role

### I'm a User

**Want to run the bot?**

1. [Install](getting-started/installation.md) - Choose Docker (easiest) or local setup
2. [Configure](getting-started/configuration.md) - Get Telegram bot token
3. [Start](getting-started/quick-start.md) - Run and test

### I'm a Developer

**Want to contribute or modify?**

1. [Install locally](getting-started/installation.md#method-1-local-development-poetry)
2. Read [Architecture](development/architecture.md) - Understand the system
3. Follow [Git Workflow](development/git-workflow.md) - Make changes
4. Run [Tests](development/testing.md) - Validate your changes
5. [Create Migrations](development/database-migrations.md) - If changing database schema

### I'm deploying to Production

**Want to deploy on a server?**

1. **Simple deployment**: Use [Docker](deployment/docker.md)
2. **VPS deployment**: Follow [VPS Setup](deployment/vps-setup.md)
3. **Automated deployment**: Setup [CI/CD](deployment/cicd.md)

## Documentation Structure

```
docs/
├── README.md (you are here)       # Documentation index
│
├── getting-started/               # For new users
│   ├── installation.md            # Setup instructions
│   ├── configuration.md           # Environment configuration
│   └── quick-start.md             # 5-minute start guide
│
├── development/                   # For developers
│   ├── architecture.md            # System architecture
│   ├── database-migrations.md     # Database migrations
│   ├── dependencies.md            # Package management
│   ├── logging.md                 # Centralized logging
│   ├── testing.md                 # Testing guide
│   └── git-workflow.md            # Git and PR workflow
│
├── deployment/                    # For operators
│   ├── docker.md                  # Docker deployment
│   ├── vps-setup.md               # VPS setup guide
│   ├── cicd.md                    # CI/CD pipeline
│   └── migration-runbook.md       # Migration operations
│
└── research/                      # Performance data
    └── benchmarks/                # Model benchmarks
```

## Additional Resources

### Project Files

- **[Main README](../README.md)** - Project overview
- **[.env.example](../.env.example)** - Configuration template
- **[pyproject.toml](../pyproject.toml)** - Python dependencies
- **[Dockerfile](../Dockerfile)** - Docker image definition

### Claude Code Resources

- **[CLAUDE.md](../CLAUDE.md)** - Claude Code guidance
- **[Memory Bank](../memory-bank/)** - Project context for AI

### GitHub Resources

- **[GitHub Repository](https://github.com/konstantinbalakin/telegram-voice2text-bot)**
- **[GitHub Actions](https://github.com/konstantinbalakin/telegram-voice2text-bot/actions)** - CI/CD status
- **[Issues](https://github.com/konstantinbalakin/telegram-voice2text-bot/issues)** - Bug reports and features

## Common Tasks

### Run bot locally
```bash
poetry run python -m src.main
```
See: [Quick Start](getting-started/quick-start.md)

### Run tests
```bash
pytest
```
See: [Testing Guide](development/testing.md)

### Deploy to Docker
```bash
docker-compose up -d
```
See: [Docker Guide](deployment/docker.md)

### Add a dependency
```bash
poetry add <package>
./scripts/update-requirements.sh
```
See: [Dependencies](development/dependencies.md)

### Create a PR
```bash
git checkout -b feature/my-feature
# make changes
git commit -m "feat: add my feature"
gh pr create
```
See: [Git Workflow](development/git-workflow.md)

## Getting Help

- **Documentation Issues**: Check this documentation first
- **Bug Reports**: [GitHub Issues](https://github.com/konstantinbalakin/telegram-voice2text-bot/issues)
- **Questions**: See existing issues or create new one

## Contributing to Documentation

Documentation improvements are welcome!

1. Edit markdown files in `docs/`
2. Follow existing structure and style
3. Update navigation links if adding new files
4. Submit PR with your changes

See: [Git Workflow](development/git-workflow.md)

---

**Need to go back?** [← Main README](../README.md)
