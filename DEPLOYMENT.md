# Deployment Guide

Complete guide for deploying the Telegram Voice2Text Bot to VPS with CI/CD automation.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [GitHub Setup](#github-setup)
- [VPS Setup](#vps-setup)
- [First Deployment](#first-deployment)
- [Ongoing Development](#ongoing-development)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Rollback](#rollback)

---

## Overview

**CI/CD Pipeline**:
```
Feature Branch → PR → CI Tests → Merge to main → Build Docker Image → Deploy to VPS
```

**Technologies**:
- **CI/CD**: GitHub Actions
- **Registry**: Docker Hub
- **Deployment**: Zero-downtime rolling update
- **VPS**: Docker + docker-compose

**Zero Downtime**: New container starts and passes health check before old container stops.

---

## Prerequisites

### Required

- ✅ GitHub repository: `konstantinbalakin/telegram-voice2text-bot`
- ✅ Docker Hub account
- ✅ VPS server (minimum 4GB RAM, 2 CPU cores)
- ✅ Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### VPS Requirements

**Minimum specs**:
- RAM: 4GB
- CPU: 2 cores
- Disk: 20GB
- OS: Ubuntu 22.04 or newer (or any Linux with Docker support)

**Recommended providers**:
- Hetzner (~$7/month)
- DigitalOcean (~$12/month)
- Vultr (~$10/month)
- Linode (~$12/month)

---

## GitHub Setup

### 1. Docker Hub Access Token

1. Go to [Docker Hub](https://hub.docker.com/)
2. Click your avatar → **Account Settings** → **Security**
3. Click **New Access Token**
4. Name: `github-actions-deploy`
5. Access permissions: **Read, Write**
6. Click **Generate**
7. **Copy the token** (you won't see it again!)

### 2. Configure GitHub Secrets

1. Go to your GitHub repository
2. **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secrets:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `DOCKER_USERNAME` | your-dockerhub-username | Docker Hub username |
| `DOCKER_PASSWORD` | token-from-step-1 | Docker Hub access token |
| `TELEGRAM_BOT_TOKEN` | 1234567890:ABC... | Telegram Bot Token from @BotFather |
| `VPS_HOST` | 1.2.3.4 | VPS IP address or domain |
| `VPS_USER` | root | SSH username (usually `root` or `ubuntu`) |
| `VPS_SSH_KEY` | -----BEGIN OPENSSH... | SSH private key (see below) |

### 3. Generate SSH Key for GitHub Actions

On your **local machine**:

```bash
# Generate SSH key pair
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_deploy

# Press Enter twice (no passphrase needed for CI/CD)

# Display private key (copy this to GitHub Secret VPS_SSH_KEY)
cat ~/.ssh/github_actions_deploy

# Display public key (we'll add this to VPS authorized_keys)
cat ~/.ssh/github_actions_deploy.pub
```

**Copy the entire private key output** (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`) to GitHub Secret `VPS_SSH_KEY`.

---

## VPS Setup

### 1. Connect to VPS

```bash
ssh root@YOUR_VPS_IP
# or
ssh ubuntu@YOUR_VPS_IP
```

### 2. Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add current user to docker group
sudo usermod -aG docker $USER

# Logout and login again to apply group changes
exit
# SSH back in
ssh root@YOUR_VPS_IP
```

Verify Docker:
```bash
docker --version
docker compose version
```

### 3. Add GitHub Actions SSH Key

```bash
# Create .ssh directory if it doesn't exist
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Add public key to authorized_keys
echo "YOUR_PUBLIC_KEY_FROM_STEP_3" >> ~/.ssh/authorized_keys

# Set correct permissions
chmod 600 ~/.ssh/authorized_keys
```

Replace `YOUR_PUBLIC_KEY_FROM_STEP_3` with the content from `~/.ssh/github_actions_deploy.pub`.

### 4. Setup Project Directory

```bash
# Create project directory
sudo mkdir -p /opt/telegram-voice2text-bot
sudo chown $USER:$USER /opt/telegram-voice2text-bot
cd /opt/telegram-voice2text-bot

# Clone repository
git clone https://github.com/konstantinbalakin/telegram-voice2text-bot.git .

# Create directories for persistence
mkdir -p data logs

# Verify structure
ls -la
```

### 5. Test SSH from Local Machine

From your **local machine**, test the SSH connection:

```bash
ssh -i ~/.ssh/github_actions_deploy root@YOUR_VPS_IP "echo 'SSH connection works!'"
```

If you see "SSH connection works!", you're good to go!

---

## First Deployment

### Option 1: Trigger via Git Push (Recommended)

```bash
# On your local machine
git checkout main
git pull origin main

# Make a small change to trigger deployment
echo "" >> README.md
git add README.md
git commit -m "chore: trigger first deployment"
git push origin main
```

**Watch deployment**:
1. Go to GitHub → **Actions** tab
2. See "Build and Deploy" workflow running
3. Wait for both "build" and "deploy" jobs to complete (~7-10 minutes)

### Option 2: Manual Deployment on VPS

If you want to deploy manually first (useful for testing):

```bash
# SSH to VPS
ssh root@YOUR_VPS_IP
cd /opt/telegram-voice2text-bot

# Create .env file
cat > .env <<EOF
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
BOT_MODE=polling
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
DATABASE_URL=sqlite+aiosqlite:////app/data/bot.db
LOG_LEVEL=INFO
TRANSCRIPTION_TIMEOUT=120
MAX_CONCURRENT_WORKERS=3
IMAGE_NAME=YOUR_DOCKERHUB_USERNAME/telegram-voice2text-bot:latest
EOF

# Pull Docker image (if you've already built it)
docker pull YOUR_DOCKERHUB_USERNAME/telegram-voice2text-bot:latest

# Start bot
docker compose -f docker-compose.prod.yml up -d

# Check logs
docker compose -f docker-compose.prod.yml logs -f bot
```

Press `Ctrl+C` to stop following logs.

### Verify Deployment

```bash
# Check container status
docker compose -f docker-compose.prod.yml ps

# Should show:
# NAME                      STATUS         PORTS
# telegram-voice2text-bot   Up (healthy)

# Check logs
docker compose -f docker-compose.prod.yml logs --tail=50 bot

# Test bot in Telegram
# Send /start command to your bot
```

---

## Ongoing Development

### Workflow

```
1. Create feature branch
   ↓
2. Make changes, commit
   ↓
3. Push to GitHub
   ↓
4. Create Pull Request
   ↓
5. CI runs (tests, linting, type checking)
   ↓
6. Merge PR to main
   ↓
7. Build & Deploy workflow triggers automatically
   ↓
8. Bot updates on VPS with zero downtime
```

### Example

```bash
# Create feature branch
git checkout -b feature/add-summary-command

# Make changes
# ... edit files ...

# Commit and push
git add .
git commit -m "feat: add /summary command"
git push origin feature/add-summary-command

# Create PR
gh pr create --title "feat: add /summary command" --body "Adds summary generation for transcribed text"

# CI will run automatically
# Review PR, then merge via GitHub or CLI:
gh pr merge --merge --delete-branch

# Build & Deploy workflow runs automatically
# Wait ~7-10 minutes
# Bot updates on VPS
```

### Check Deployment Status

**On GitHub**:
- Go to **Actions** tab
- See recent workflows
- Green checkmark = success
- Red X = failure (check logs)

**On VPS**:
```bash
ssh root@YOUR_VPS_IP
cd /opt/telegram-voice2text-bot
docker compose -f docker-compose.prod.yml logs --tail=100 bot
```

---

## Monitoring

### View Logs

```bash
# SSH to VPS
ssh root@YOUR_VPS_IP
cd /opt/telegram-voice2text-bot

# Follow live logs
docker compose -f docker-compose.prod.yml logs -f bot

# View last 100 lines
docker compose -f docker-compose.prod.yml logs --tail=100 bot

# View logs from last hour
docker compose -f docker-compose.prod.yml logs --since 1h bot
```

### Check Container Health

```bash
# Container status
docker compose -f docker-compose.prod.yml ps

# Detailed health status
docker inspect telegram-voice2text-bot | grep -A 10 Health

# Resource usage
docker stats telegram-voice2text-bot
```

### Database

```bash
# SSH to VPS
cd /opt/telegram-voice2text-bot

# Check database size
ls -lh data/bot.db

# Backup database
cp data/bot.db data/bot.db.backup.$(date +%Y%m%d)

# Check database integrity
docker compose -f docker-compose.prod.yml exec bot \
  python -c "from src.storage.database import init_db; import asyncio; asyncio.run(init_db())"
```

---

## Troubleshooting

### Build Fails

**Issue**: "Error: buildx failed with: ERROR: failed to solve..."

**Solution**:
1. Check Dockerfile syntax
2. Verify requirements.txt is being exported correctly
3. Check Docker Hub credentials in GitHub Secrets

### Deploy Fails with SSH Error

**Issue**: "Permission denied (publickey)"

**Solution**:
1. Verify `VPS_SSH_KEY` secret contains **entire private key** including BEGIN/END lines
2. Verify public key is in VPS `~/.ssh/authorized_keys`
3. Check VPS firewall allows SSH (port 22)
4. Test SSH manually: `ssh -i ~/.ssh/github_actions_deploy root@VPS_IP`

### Health Check Fails

**Issue**: Container starts but health check fails

**Solution**:
```bash
# Check logs for startup errors
docker compose -f docker-compose.prod.yml logs bot

# Common issues:
# - BOT_TOKEN invalid → check GitHub Secret
# - Database locked → check permissions on data/ directory
# - Out of memory → check VPS resources
```

### Bot Not Responding

**Issue**: Container healthy but bot doesn't respond to messages

**Solutions**:
```bash
# 1. Check bot is actually running
docker compose -f docker-compose.prod.yml ps

# 2. Check logs for errors
docker compose -f docker-compose.prod.yml logs bot | grep -i error

# 3. Verify BOT_TOKEN
docker compose -f docker-compose.prod.yml exec bot \
  python -c "from src.config import settings; print(settings.bot_token[:10])"

# 4. Test Telegram API connectivity
docker compose -f docker-compose.prod.yml exec bot \
  python -c "import httpx; print(httpx.get('https://api.telegram.org').status_code)"

# 5. Restart bot
docker compose -f docker-compose.prod.yml restart bot
```

### Out of Disk Space

**Issue**: VPS runs out of disk space

**Solution**:
```bash
# Check disk usage
df -h

# Clean up old Docker images
docker system prune -a --volumes

# Check Docker disk usage
docker system df

# Remove old images (keep last 3)
docker images | grep telegram-voice2text-bot | tail -n +4 | awk '{print $3}' | xargs docker rmi
```

---

## Rollback

### Automatic Rollback

If health check fails, Docker keeps the old container running.

### Manual Rollback

```bash
# SSH to VPS
ssh root@YOUR_VPS_IP
cd /opt/telegram-voice2text-bot

# Find previous images
docker images | grep telegram-voice2text-bot

# Example output:
# konstantinbalakin/telegram-voice2text-bot  latest    abc123  ...
# konstantinbalakin/telegram-voice2text-bot  def456    def456  ...  (previous)

# Rollback to specific commit SHA
PREVIOUS_SHA=def456  # Replace with actual SHA from output above
docker pull konstantinbalakin/telegram-voice2text-bot:$PREVIOUS_SHA
docker tag konstantinbalakin/telegram-voice2text-bot:$PREVIOUS_SHA \
           konstantinbalakin/telegram-voice2text-bot:latest

# Update .env
echo "IMAGE_NAME=konstantinbalakin/telegram-voice2text-bot:latest" >> .env

# Restart with old image
docker compose -f docker-compose.prod.yml up -d --force-recreate bot

# Verify
docker compose -f docker-compose.prod.yml logs --tail=50 bot
```

---

## Advanced Topics

### PostgreSQL Migration

When you're ready to migrate from SQLite to PostgreSQL:

1. Uncomment `postgres` service in `docker-compose.prod.yml`
2. Add GitHub Secrets:
   - `POSTGRES_USER`
   - `POSTGRES_PASSWORD`
   - `POSTGRES_DB`
3. Update `DATABASE_URL` in deploy workflow
4. Deploy and run migrations

### Webhook Mode

For production with a domain:

1. Get domain and point to VPS IP
2. Setup SSL certificate (Let's Encrypt)
3. Add nginx reverse proxy
4. Update bot code for webhook mode
5. Change `BOT_MODE=webhook` in deploy workflow

### Monitoring

Add Prometheus + Grafana for metrics:

```bash
# Add monitoring stack
docker-compose -f docker-compose.monitoring.yml up -d
```

---

## Security Best Practices

1. **GitHub Secrets**: Never commit secrets to git
2. **SSH Keys**: Use dedicated key for CI/CD, rotate regularly
3. **Docker Hub**: Use Access Token (not password)
4. **VPS**: Enable firewall, allow only SSH and bot ports
5. **Updates**: Keep VPS and Docker updated
6. **Backups**: Backup database regularly

---

## Support

**Issues**:
- GitHub: https://github.com/konstantinbalakin/telegram-voice2text-bot/issues
- Check logs: `docker compose -f docker-compose.prod.yml logs bot`

**Documentation**:
- Implementation Plan: `.claude/memory-bank/plans/2025-10-17-cicd-pipeline-plan.md`
- Project README: `README.md`
- Git Workflow: `.github/WORKFLOW.md`
