# VPS Deployment Learnings

**Date**: 2025-10-27
**Phase**: Initial deployment and troubleshooting

## Deployment Timeline

### Initial State
- VPS: 1GB RAM, 1 vCPU, Ubuntu
- Goal: Deploy bot with medium/int8 model
- Expected: Working bot with acceptable performance

### Issues Encountered & Solutions

## Issue #1: Database Directory Creation
**Date**: 2025-10-27
**PR**: #11

**Error**:
```
sqlite3.OperationalError: unable to open database file
```

**Root Cause**:
- Docker volume mount `./data:/app/data` replaces container's directory
- Host directory `./data` doesn't exist on first deploy
- SQLite can't create file without parent directory

**Solution**:
Added directory creation in `init_db()` function (src/storage/database.py:72-87):
```python
# Extract path from DATABASE_URL and create parent directories
db_url = settings.database_url
match = re.search(r"sqlite\+aiosqlite:///(.*)", db_url)
if match:
    db_path = match.group(1).lstrip("/")
    if db_path.startswith("/"):
        db_file = Path(db_path)
    else:
        db_file = Path(db_path).resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
```

**Lesson**: Volume mounts require explicit directory management; container setup isn't sufficient.

## Issue #2: DNS Resolution Failure
**Date**: 2025-10-27
**PR**: #12

**Error**:
```
failed to lookup address information: No address associated with hostname
Target: transfer.xethub.hf.co
```

**Root Cause**:
- Container couldn't inherit DNS settings from VPS host (198.18.18.18)
- Blocked HuggingFace model downloads during initialization
- Model cache was empty, requiring download on first run

**Solution**:
Added explicit DNS configuration in docker-compose.prod.yml:
```yaml
dns:
  - 198.18.18.18  # VPS host DNS
  - 8.8.8.8       # Google DNS (fallback)
  - 8.8.4.4       # Google DNS (fallback)
```

**Lesson**: Docker DNS inheritance can fail; explicit configuration ensures reliability.

## Issue #3: OOM Killer (Exit Code 137)
**Date**: 2025-10-27

**Error**:
```
Container status: Restarting (137)
```

**Root Cause**:
- Model loading requires ~1.3GB memory peak
- 1GB VPS RAM insufficient without swap
- Linux OOM killer terminated container during model initialization

**Analysis**:
```
# Memory breakdown for medium/int8 model:
- Model files: ~1.5GB on disk
- Runtime memory: ~1.3GB peak during loading
- Operating system: ~200-300MB
- Docker overhead: ~50-100MB
Total needed: ~1.6-1.8GB minimum
```

**Solution**:
Created 1GB swap file on VPS:
```bash
fallocate -l 1G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

**Result**:
- Container stable and healthy
- Memory usage: 516 MB RAM + 755 MB swap = 1.27 GB total
- Model successfully loaded
- Bot operational

**Lesson**: Model size documentation was accurate (~2GB), but 1GB VPS requires swap to work.

## Performance Analysis

### Baseline Metrics (1GB RAM, 1 vCPU, with swap)
**Date**: 2025-10-27

**Test Sample**: 9-second Russian voice message

**Results**:
```
Audio duration: 8.91s
Processing time: 27.08s
RTF (Real-Time Factor): 3.04x
Memory: 516 MB RAM + 755 MB swap (1.27 GB total)
CPU: 0.02% idle, peaks during transcription
```

**Interpretation**:
- RTF 3.04x means transcription takes 3x longer than audio duration
- 10x slower than local benchmark (RTF 0.3x)
- Performance acceptable for functionality, but below target

### Bottleneck Identification

**Primary Bottleneck**: Swap usage (755 MB active)
- Swap is disk I/O based, much slower than RAM
- Model weights accessed from swap during inference
- Each inference triggers disk reads

**Secondary Bottleneck**: Single vCPU
- Local benchmarks used multi-core CPUs
- Whisper benefits from parallelization

**Evidence**:
```bash
# VPS metrics during transcription:
RAM: 516 MB / 960 MB (54%)
Swap: 755 MB / 1024 MB (74%)
CPU: Sustained 80-100% during processing
```

### Performance Expectations

| Configuration | Expected RTF | Confidence | Cost Increase |
|---------------|--------------|------------|---------------|
| Current (1GB + 1vCPU) | 3.0x | ✅ Confirmed | Baseline |
| 2GB RAM + 1vCPU | 0.5-1.0x | High | +$1-2/mo |
| 1GB RAM + 2vCPU | 1.5-2.0x | Medium | +$2-3/mo |
| 2GB RAM + 2vCPU | 0.3-0.5x | High | +$3-5/mo |

**Reasoning**:
- **2GB RAM**: Eliminates swap entirely, should cut processing time by 50-70%
- **2 vCPU**: Enables parallel processing, faster-whisper can use multiple cores
- **Combined**: Should approach local benchmark performance

## Key Learnings

### Architecture Decisions Validated
1. ✅ **Docker + docker-compose**: Simplified deployment significantly
2. ✅ **Automated CI/CD**: Caught issues early, fast iteration
3. ✅ **Health checks**: Detected failures automatically
4. ✅ **Logging**: Essential for debugging remote issues

### Unexpected Discoveries
1. **Volume mounts break directory initialization**: Need explicit directory creation
2. **DNS can fail silently**: Explicit configuration prevents mysterious download failures
3. **Swap enables minimal VPS**: 1GB VPS can work, but with severe performance penalty
4. **Model memory accurate**: Documentation was correct (~2GB recommended)

### Best Practices Established
1. **Always create parent directories**: Don't assume volume mounts preserve structure
2. **Explicit DNS configuration**: Don't rely on container DNS inheritance
3. **Swap is safety net, not solution**: Use for stability, not primary memory
4. **Log verbosity matters**: Changed LOG_LEVEL=INFO for troubleshooting
5. **Metrics collection critical**: Can't optimize what you don't measure

## Optimization Strategy

### Phase 1: Baseline (COMPLETE)
- ✅ Deploy on minimal VPS (1GB)
- ✅ Identify and resolve blocking issues
- ✅ Capture performance metrics
- ✅ Understand bottlenecks

### Phase 2: RAM Optimization (NEXT)
**Test**: Upgrade to 2GB RAM
**Goal**: Eliminate swap usage
**Expected**: RTF 0.5-1.0x (2-3x improvement)
**Method**:
1. Upgrade VPS to 2GB RAM
2. Restart bot
3. Send same 9s test audio
4. Compare RTF, memory, CPU metrics
5. Document results

### Phase 3: CPU Optimization (IF NEEDED)
**Test**: Add second vCPU
**Goal**: Enable parallelization
**Expected**: RTF 0.3-0.5x (additional 2x improvement)
**Method**: Same as Phase 2

### Phase 4: Optimal Configuration
**Test**: 2GB RAM + 2 vCPU
**Goal**: Match local benchmark performance
**Expected**: RTF ~0.3x (10x improvement over baseline)

## Cost Analysis

### Daily Billing Advantage
VPS provider uses daily billing, allowing:
- Low-risk experimentation
- Quick scaling tests
- Cost-effective optimization
- Easy rollback if budget constrained

### Budget Projections
| Configuration | Monthly Cost | RTF | Cost per 1s audio |
|---------------|--------------|-----|-------------------|
| 1GB + 1vCPU | $3-5 | 3.0x | Baseline |
| 2GB + 1vCPU | $4-7 | 0.5-1.0x | 3-6x better |
| 2GB + 2vCPU | $6-10 | 0.3-0.5x | 6-10x better |

**Recommendation**: Target 2GB + 2vCPU for production if performance critical.

## Technical Debt

### Items to Address
1. **Remove version from docker-compose**: Warning about obsolete `version` attribute
2. **Memory metrics collection**: Add automated performance tracking
3. **Benchmark comparison tool**: Script to compare against local benchmarks
4. **Performance alerting**: Notify if RTF exceeds threshold

### Documentation Improvements
1. ✅ Deployment learnings captured
2. ⏳ VPS sizing guide (pending experiments)
3. ⏳ Troubleshooting playbook
4. ⏳ Performance tuning guide

## Next Session Checklist

When returning to optimize performance:

1. **Review this document** - Understand current state and hypothesis
2. **Check VPS metrics** - Verify bot still healthy, get current baseline
3. **Plan experiment** - Which configuration to test (2GB first recommended)
4. **Execute test** - Upgrade VPS, restart, measure
5. **Document results** - Update this file with findings
6. **Iterate** - Continue until target RTF achieved or budget exhausted

## References

- PR #11: Database directory fix
- PR #12: DNS configuration
- activeContext.md: Current focus
- progress.md: Phase completion status
- Logs: `docker logs telegram-voice2text-bot`
- Metrics: `docker stats telegram-voice2text-bot`
