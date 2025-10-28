# Active Context: Telegram Voice2Text Bot

## Current Status

**Phase**: Phase 5 - VPS Deployment COMPLETE, CI/CD Optimization COMPLETE
**Date**: 2025-10-28
**Stage**: Bot deployed and stable on 1GB VPS, CI/CD optimized for docs-only changes
**Branch**: `main`
**Completed**: Initial deployment, database fix, DNS configuration, swap setup, CI/CD path filtering
**Next Phase**: RAM/CPU optimization experiments to achieve target RTF ~0.3x

## Production Configuration Finalized ✅

**Decision**: `faster-whisper / medium / int8 / beam1`

After comprehensive manual analysis of benchmark transcripts (30+ configurations tested across 7s, 24s, 163s audio samples):

- **Performance**: RTF ~0.3x (3x faster than audio duration)
  - 7s audio → ~2s processing
  - 30s audio → ~10s processing
  - 60s audio → ~20s processing
- **Quality**: Excellent for Russian language, good accuracy on long informal speech
- **Resources**: ~2GB RAM peak (actual production testing, not 3.5GB as initially measured)
- **Tradeoff**: Prioritized quality over speed for better user experience
- **Note**: Initial benchmark memory measurements were incorrect (3.5GB); real-world testing shows ~2GB peak

Alternative faster configurations (tiny, small) showed unacceptable quality degradation (22-78% similarity on some samples).

📄 Full analysis: `memory-bank/benchmarks/final-decision.md`

## Recent Changes

### CI/CD Path Filtering Optimization ✅ NEW (2025-10-28)
**Achievement**: Workflows now intelligently skip operations for documentation-only changes

**Problem Solved**: Previously used `paths-ignore` which prevented workflows from running entirely for docs-only PRs. This caused GitHub's required status checks to never be created, blocking PR merges even when no code was changed.

**Solution Implemented** (#15):
- Replaced `paths-ignore` with `tj-actions/changed-files@v45` action
- Added conditional steps (`if: steps.changed-files.outputs.any_changed == 'true'`) to expensive operations
- Ensured workflows always run (status checks created) but skip heavy steps when only docs change

**Files Modified**:
- `.github/workflows/ci.yml`: Conditional test execution, linting, type checking
- `.github/workflows/build-and-deploy.yml`: Conditional build and deploy jobs

**Benefits**:
- ✅ Required status checks always created (no merge blocks)
- ✅ CI minutes saved on docs-only changes (skips tests, build, deploy)
- ✅ Workflows complete successfully even when skipping steps
- ✅ Maintains code quality gates for actual code changes

**Pattern**: Conditional execution with always-run workflows for required status checks

### VPS Deployment SUCCESS ✅ (2025-10-27)
**Achievement**: Bot successfully deployed and operational on 1GB VPS

**Issues Resolved**:
1. **Database Directory Issue** (#11)
   - Error: `sqlite3.OperationalError: unable to open database file`
   - Fix: Added directory creation in `init_db()` (src/storage/database.py:72-87)
   - Handles volume mount replacing container directories

2. **DNS Resolution Failure** (#12)
   - Error: `failed to lookup address information` for transfer.xethub.hf.co
   - Fix: Added DNS servers in docker-compose.prod.yml (VPS host + Google DNS)
   - Enables HuggingFace model downloads

3. **OOM Killer (Exit Code 137)**
   - Issue: Container killed during model loading (medium requires ~1.3GB peak)
   - Fix: Created 1GB swap file on VPS
   - Result: **Bot stable and healthy**

**Production Metrics** (2025-10-27):
- **Memory Usage**: 516 MB RAM + 755 MB swap = **1.27 GB total**
- **Model**: medium/int8 successfully loaded
- **Status**: Container healthy, bot responding
- **Performance**: RTF **3.04x** (9s audio → 27s processing)
  - 10x slower than local benchmark (0.3x)
  - Bottleneck: 1 vCPU + heavy swap usage

### Performance Gap Identified 🎯
**Current**: RTF 3.04x (3x slower than audio)
**Target**: RTF 0.3x (3x faster than audio, as measured locally)
**Gap**: **10x performance difference** vs local machine

**Root Causes**:
1. **Swap bottleneck**: 755 MB active swap usage severely degrades I/O
2. **Limited CPU**: 1 vCPU vs multi-core local machine
3. **Resource contention**: System using swap for model data access

**Next Steps**: Systematically test different VPS configurations

### Provider Architecture Cleanup ✅
- **Removed**: openai-whisper provider (original Whisper)
  - Deleted: `src/transcription/providers/whisper_provider.py`
  - Deleted: `tests/unit/test_whisper_service.py`
  - Removed from factory, router, all imports

- **Dependencies Optimized**:
  - Removed: `openai-whisper`, `torch` from pyproject.toml
  - `requirements-docker.txt`: 75 → 50 dependencies (~2-3GB Docker image savings)
  - Deleted: `requirements-full.txt`, `docker-compose.prod.yml` (obsolete)

- **Updated Defaults**:
  - `FASTER_WHISPER_MODEL_SIZE`: base → **medium**
  - `FASTER_WHISPER_BEAM_SIZE`: 5 → **1** (greedy decoding, faster)
  - All documentation updated with production benchmarks

- **Provider Tests Added**:
  - `tests/unit/test_faster_whisper_provider.py` (6 tests)
  - `tests/unit/test_openai_provider.py` (7 tests)
  - All 45 unit tests passing ✅

### Quality Assurance ✅
- ✅ mypy: No type errors
- ✅ ruff: All checks passed
- ✅ black: Code formatted
- ✅ pytest: 45/45 tests passing

## Performance Optimization Plan (NEXT)

**Objective**: Achieve RTF ~0.3x (target performance from local benchmarks)

**Hypothesis**: Swap usage is primary bottleneck, need sufficient RAM for model

**Experimental Strategy**:
1. **Test 2GB RAM** (eliminate swap)
   - Expected: RTF 0.5-1.0x (significant improvement)
   - Cost: Minimal increase (~$1-2/month)

2. **Test 2 vCPU** (if RAM alone insufficient)
   - Expected: RTF 0.3-0.5x (parallel processing)
   - Cost: Moderate increase (~$2-3/month)

3. **Test 2GB RAM + 2 vCPU** (optimal config)
   - Expected: RTF ~0.3x (match local performance)
   - Cost: Combined increase (~$3-5/month total)

**Testing Protocol**:
- Send same test audio (9s sample) to each configuration
- Measure RTF via logs (LOG_LEVEL=INFO)
- Record memory/swap/CPU metrics
- Document in Memory Bank

**VPS Advantage**: Daily billing allows cost-effective experimentation

**Completed**:
- ✅ VPS deployment automation (CI/CD)
- ✅ Database directory creation
- ✅ DNS configuration
- ✅ Swap file creation (1GB)
- ✅ Bot operational and stable
- ✅ Baseline metrics captured (RTF 3.04x, 1.27GB total memory)

## Current Infrastructure

**VPS Configuration**:
- Provider: Russian VPS (~$3-5/month)
- RAM: 1GB + 1GB swap
- CPU: 1 vCPU
- OS: Ubuntu (clean)
- Docker: Installed and operational

**Deployment**:
- Method: Automated via GitHub Actions
- Trigger: Push to main branch
- Process: Build → Push to Docker Hub → SSH deploy
- Status: Fully operational

**Monitoring**:
- Container: `docker stats` for resources
- Logs: `docker logs telegram-voice2text-bot`
- Health: Container health checks passing
