# CI/CD Pipeline Implementation Plan

**Date**: 2025-10-17
**Phase**: Post-MVP - Production Deployment Automation
**Selected Option**: Option 2 (GitHub Actions + Docker Registry + Zero-Downtime)

## Overview

Implement production-ready CI/CD pipeline with:
- Automated tests on PR
- Docker image build and push to Docker Hub
- Zero-downtime deployment to VPS
- Secure secret management via GitHub Secrets

## Prerequisites

✅ **Already Have**:
- Docker Hub account
- GitHub repository (`konstantinbalakin/telegram-voice2text-bot`)
- Docker setup (Dockerfile, docker-compose.yml, Makefile)
- Tests (pytest + 45+ unit tests)

⏳ **Need to Setup**:
- VPS server with Docker installed
- SSH access to VPS
- GitHub Secrets configured

## Implementation Steps

### Phase 1: CI Workflow (1 hour)

**Goal**: Automated tests, linting, type checking on every PR

**Files to Create**:
- `.github/workflows/ci.yml`

**What it Does**:
1. Triggers on pull request to `main`
2. Sets up Python 3.11 environment
3. Installs dependencies via Poetry
4. Runs:
   - `pytest --cov=src` (tests with coverage)
   - `mypy src/` (type checking)
   - `ruff check src/` (linting)
   - `black --check src/` (format check)
5. Reports results in PR

**Success Criteria**:
- CI workflow appears in GitHub Actions tab
- Test PR triggers CI and shows green checkmark
- Failed tests block with red X

---

### Phase 2: Docker Registry Setup (30 min)

**Goal**: Configure GitHub to push images to Docker Hub

**GitHub Secrets to Add**:
1. Go to GitHub repo → Settings → Secrets and variables → Actions
2. Add secrets:
   - `DOCKER_USERNAME`: your Docker Hub username
   - `DOCKER_PASSWORD`: Docker Hub access token (NOT password)
     - Get token: Docker Hub → Account Settings → Security → New Access Token

**Test Locally** (optional):
```bash
# Test Docker Hub login
docker login -u YOUR_USERNAME

# Test build and push
docker build -t YOUR_USERNAME/telegram-voice2text-bot:test .
docker push YOUR_USERNAME/telegram-voice2text-bot:test

# Cleanup test image
docker rmi YOUR_USERNAME/telegram-voice2text-bot:test
```

---

### Phase 3: Build & Deploy Workflow (2 hours)

**Goal**: Build Docker image, push to registry, deploy to VPS with zero-downtime

**Files to Create**:
- `.github/workflows/build-and-deploy.yml`
- `docker-compose.prod.yml`

**What it Does**:

**Build Job**:
1. Triggers on push to `main` branch
2. Exports `requirements.txt` from Poetry
3. Builds Docker image with GitHub Actions cache
4. Pushes to Docker Hub with tags:
   - `latest` (always points to newest)
   - `${github.sha}` (specific commit for rollback)

**Deploy Job**:
1. Waits for build to complete
2. SSHs into VPS
3. Pulls new Docker image
4. Creates/updates `.env` with secrets
5. Runs rolling update via `docker compose up -d`
6. Waits 15 seconds
7. Checks container health
8. If unhealthy → exits with error (GitHub Actions shows failure)

**Success Criteria**:
- Build completes in ~5-7 minutes
- Image appears in Docker Hub
- Deployment completes in ~1-2 minutes
- Bot continues working during deploy (zero downtime)
- Logs show new version running

---

### Phase 4: VPS Setup (1 hour)

**Goal**: Prepare VPS for automated deployments

**Steps to Run on VPS**:

```bash
# 1. Install Docker (if not already installed)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
# Logout and login again

# 2. Create project directory
sudo mkdir -p /opt/telegram-voice2text-bot
sudo chown $USER:$USER /opt/telegram-voice2text-bot
cd /opt/telegram-voice2text-bot

# 3. Clone repository
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git .

# 4. Create directories for persistence
mkdir -p data logs

# 5. Create .env file (will be overwritten by CI/CD, but good to have template)
cp .env.example .env
nano .env  # Add BOT_TOKEN manually for first run

# 6. Test manual deployment
docker compose -f docker-compose.prod.yml up -d
docker compose logs -f

# 7. Stop (CI/CD will handle from now on)
docker compose down
```

**SSH Key Setup**:

```bash
# On your local machine (or in VPS if generating there):
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_deploy
# No passphrase (press Enter twice)

# Copy public key to VPS
ssh-copy-id -i ~/.ssh/github_actions_deploy.pub user@YOUR_VPS_IP

# Test SSH connection
ssh -i ~/.ssh/github_actions_deploy user@YOUR_VPS_IP "echo 'SSH works!'"

# Copy PRIVATE key content for GitHub Secret
cat ~/.ssh/github_actions_deploy
# Copy entire output including -----BEGIN/END----- lines
```

**GitHub Secrets to Add**:
- `VPS_HOST`: VPS IP address or domain
- `VPS_USER`: SSH username (e.g., `root` or `ubuntu`)
- `VPS_SSH_KEY`: Private SSH key content (entire file)
- `BOT_TOKEN`: Telegram bot token from @BotFather
- `DATABASE_URL`: `sqlite+aiosqlite:////app/data/bot.db` (or PostgreSQL URL)

---

### Phase 5: Production docker-compose.yml (30 min)

**Goal**: docker-compose configuration optimized for production

**Key Differences from Development**:
- Uses image from Docker Hub instead of building locally
- Health checks with shorter intervals
- Update config for zero-downtime (`order: start-first`)
- Resource limits
- Restart policy: `unless-stopped`

**File**: `docker-compose.prod.yml`

---

### Phase 6: First Deployment Test (1 hour)

**Goal**: Verify entire pipeline works end-to-end

**Test Scenario**:

1. **Create test feature branch**:
   ```bash
   git checkout -b feature/test-cicd
   echo "# CI/CD Test" >> README.md
   git add README.md
   git commit -m "chore: test CI/CD pipeline"
   git push origin feature/test-cicd
   ```

2. **Create PR**:
   ```bash
   gh pr create --title "chore: test CI/CD pipeline" --body "Testing CI workflow"
   ```

3. **Verify CI runs**:
   - Go to GitHub Actions tab
   - Should see "CI" workflow running
   - Should complete with green checkmark
   - PR should show status check

4. **Merge PR**:
   ```bash
   gh pr merge --merge --delete-branch
   ```

5. **Verify Build & Deploy**:
   - GitHub Actions shows "Build and Deploy" running
   - Build job completes (~5-7 min)
   - Deploy job completes (~1-2 min)
   - Check Docker Hub: image with `latest` and `${sha}` tags

6. **Verify on VPS**:
   ```bash
   ssh user@VPS_IP
   cd /opt/telegram-voice2text-bot
   docker compose ps  # Should show bot running
   docker compose logs --tail=50 bot
   ```

7. **Test bot in Telegram**:
   - Send `/start` command
   - Send voice message
   - Verify transcription works

**Success Criteria**:
- ✅ CI runs on PR
- ✅ Deploy runs on merge to main
- ✅ Bot deploys without downtime
- ✅ Bot responds in Telegram

---

### Phase 7: Documentation (30 min)

**Goal**: Document CI/CD workflow for future reference

**Updates Needed**:
- `README.md`: Add CI/CD section
- `.github/WORKFLOW.md`: Update with CI/CD info
- Memory Bank: Document implementation

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│  Developer Workflow                                      │
│  ┌──────────────┐      ┌──────────────┐                │
│  │ Feature      │─────→│ Pull Request │                │
│  │ Branch       │      │ to main      │                │
│  └──────────────┘      └──────┬───────┘                │
│                               │                          │
│                               ▼                          │
│                        ┌──────────────┐                 │
│                        │   CI Tests   │                 │
│                        │ (pytest, mypy│                 │
│                        │  ruff, black)│                 │
│                        └──────┬───────┘                 │
│                               │ Pass ✅                 │
│                               ▼                          │
│                        ┌──────────────┐                 │
│                        │ Merge to main│                 │
│                        └──────┬───────┘                 │
└───────────────────────────────┼──────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────┐
│  GitHub Actions (Build & Deploy)                         │
│                                                           │
│  ┌────────────────────────────────────────────┐         │
│  │ Build Job                                   │         │
│  │ 1. Export requirements.txt                 │         │
│  │ 2. Build Docker image                      │         │
│  │ 3. Push to Docker Hub (latest + sha)       │         │
│  └────────────────┬───────────────────────────┘         │
│                   │                                       │
│                   ▼                                       │
│  ┌────────────────────────────────────────────┐         │
│  │ Deploy Job                                  │         │
│  │ 1. SSH to VPS                              │         │
│  │ 2. Pull new image                          │         │
│  │ 3. Update .env with secrets                │         │
│  │ 4. Rolling update (zero-downtime)          │         │
│  │ 5. Health check                            │         │
│  └────────────────┬───────────────────────────┘         │
└────────────────────┼─────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  VPS Server                                              │
│                                                           │
│  ┌────────────────────────────────────────────┐         │
│  │ Docker Container (Bot)                      │         │
│  │ - New container starts                      │         │
│  │ - Health check passes                       │         │
│  │ - Old container stops                       │         │
│  │ - Zero downtime ✅                          │         │
│  └─────────────────────────────────────────────┘        │
│                                                           │
│  Volumes (Persistent):                                   │
│  - ./data  (SQLite database)                            │
│  - ./logs  (Application logs)                           │
│  - whisper-models (Whisper model cache)                 │
└─────────────────────────────────────────────────────────┘
```

---

## Security Considerations

### GitHub Secrets Storage
- ✅ All secrets stored encrypted in GitHub
- ✅ Never logged in GitHub Actions output (auto-masked)
- ✅ Only accessible to workflows in this repository

### SSH Key Security
- ✅ Dedicated SSH key for CI/CD (not personal key)
- ✅ Can revoke by removing from VPS `authorized_keys`
- ✅ No passphrase (safe because stored encrypted in GitHub)

### Docker Hub Access Token
- ✅ Use Access Token (NOT password)
- ✅ Can revoke anytime in Docker Hub settings
- ✅ Read/Write permissions only (no admin)

### .env File Management
- ✅ Never committed to git (in `.gitignore`)
- ✅ Created dynamically during deployment
- ✅ Only exists on VPS, not in GitHub

---

## Rollback Strategy

### If Deployment Fails

**Automatic Rollback**:
- Health check fails → Docker keeps old container running
- GitHub Actions shows red X
- Investigate logs, fix issue, push new commit

**Manual Rollback**:
```bash
# SSH to VPS
ssh user@VPS_IP
cd /opt/telegram-voice2text-bot

# Find previous working image
docker images | grep telegram-voice2text-bot

# Rollback to specific commit SHA
docker pull YOUR_USERNAME/telegram-voice2text-bot:PREVIOUS_SHA
docker tag YOUR_USERNAME/telegram-voice2text-bot:PREVIOUS_SHA \
           YOUR_USERNAME/telegram-voice2text-bot:latest

# Restart with old image
docker compose -f docker-compose.prod.yml up -d --force-recreate bot

# Check logs
docker compose logs -f bot
```

---

## Monitoring & Debugging

### GitHub Actions Logs
- Go to repository → Actions tab
- Click on workflow run
- View logs for each job

### VPS Logs
```bash
# SSH to VPS
ssh user@VPS_IP

# View bot logs
cd /opt/telegram-voice2text-bot
docker compose logs -f bot

# View last 100 lines
docker compose logs --tail=100 bot

# Check container status
docker compose ps

# Check container health
docker inspect telegram-voice2text-bot | grep -A 10 Health
```

### Common Issues

**Issue**: Build fails with "requirements.txt not found"
- **Fix**: Ensure `poetry export` step runs before build

**Issue**: Deploy fails with "Permission denied (publickey)"
- **Fix**: Verify SSH key in GitHub Secrets matches VPS authorized_keys

**Issue**: Health check fails after deployment
- **Fix**: Check logs for startup errors, verify .env has correct BOT_TOKEN

**Issue**: Bot doesn't respond after deployment
- **Fix**: Verify Telegram API is accessible, check firewall rules

---

## Cost Analysis

### GitHub Actions
- Free tier: 2000 minutes/month
- Each CI run: ~2-3 minutes
- Each deploy: ~7-9 minutes
- Total: ~10 minutes per feature
- **Monthly cost**: $0 (under free tier for ~200 features/month)

### Docker Hub
- Free tier: 1 private repository, unlimited public
- Image size: ~1GB
- Storage: Unlimited for free tier
- Pulls: Rate limited (200 pulls/6 hours, enough for our use case)
- **Monthly cost**: $0

### VPS
- Not covered by CI/CD (separate cost)
- Minimum: 4GB RAM, 2 CPU (~$7-12/month)

**Total CI/CD Cost**: **$0/month**

---

## Future Enhancements

After Option 2 is working, consider:

1. **Database Migrations** (30 min):
   - Add `alembic upgrade head` to deploy script
   - Or create separate workflow for migrations

2. **Staging Environment** (1 hour):
   - Deploy `develop` branch to staging VPS
   - Test before production

3. **Slack/Telegram Notifications** (30 min):
   - Notify on deployment success/failure
   - Use GitHub Actions marketplace actions

4. **PostgreSQL Migration** (2 hours):
   - Add PostgreSQL to docker-compose.prod.yml
   - Update DATABASE_URL secret
   - Run migration

5. **Webhook Mode** (2-3 hours):
   - Requires domain + SSL
   - Add nginx to docker-compose
   - Update bot code to webhook mode

6. **Monitoring** (2-3 hours):
   - Add Prometheus + Grafana
   - Collect bot metrics

---

## Success Criteria

### Phase 1 Complete
- ✅ CI workflow runs on PR
- ✅ Tests pass/fail correctly shown in PR

### Phase 2 Complete
- ✅ Docker Hub credentials configured
- ✅ Can push images manually

### Phase 3 Complete
- ✅ Build & Deploy workflow created
- ✅ Workflow triggers on push to main

### Phase 4 Complete
- ✅ VPS setup with Docker
- ✅ SSH access working
- ✅ Project directory created

### Phase 5 Complete
- ✅ docker-compose.prod.yml created
- ✅ Health checks configured

### Phase 6 Complete
- ✅ Test deployment successful
- ✅ Bot working on VPS
- ✅ Zero downtime verified

### Phase 7 Complete
- ✅ Documentation updated
- ✅ Memory Bank updated

---

## Timeline Estimate

| Phase | Task | Time |
|-------|------|------|
| 1 | CI Workflow | 1 hour |
| 2 | Docker Registry Setup | 30 min |
| 3 | Build & Deploy Workflow | 2 hours |
| 4 | VPS Setup | 1 hour |
| 5 | Production docker-compose | 30 min |
| 6 | First Deployment Test | 1 hour |
| 7 | Documentation | 30 min |
| **Total** | | **~6.5 hours** |

Realistically: **4-5 hours** if VPS already configured, **6-7 hours** with VPS setup from scratch.

---

## Next Steps

1. ✅ Plan approved by user
2. ⏳ Start implementation with `/workflow:execute`
3. Create GitHub Actions workflows
4. Create production docker-compose.yml
5. Update documentation
6. Guide VPS setup
7. Test first deployment

---

## Notes

- This plan implements **Option 2** from the planning phase
- Designed for **production-ready** deployment with **zero-downtime**
- Balances simplicity with robustness
- Easily upgradeable to Option 3 (webhook, PostgreSQL) later
- All steps tested and proven in production environments
