# Implementation Plan: Flexible Whisper Providers with Benchmark Mode

**Date:** 2025-10-20
**Status:** Approved - Ready for Implementation
**Feature Branch:** `feature/flexible-whisper-providers`
**Estimated Time:** 9-11 hours

---

## Executive Summary

Implement a flexible, provider-based architecture for Whisper transcription that allows:
1. Easy switching between different Whisper implementations (faster-whisper, original Whisper, OpenAI API)
2. Testing multiple model sizes and parameters through environment configuration
3. **Automated benchmarking** - one voice message tests all configurations and generates comparative report
4. Future support for hybrid routing strategies (duration-based, fallback, user-tier, etc.)

**Primary Goal:** Test local Whisper models on CPU to find configuration matching OpenAI API quality without GPU costs.

---

## Architecture: Option 1+ (Extended Provider Pattern)

### Component Hierarchy

```
┌─────────────────────────────────────────┐
│      Telegram Bot Handler               │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│     TranscriptionRouter                 │
│  - Metrics collection                   │
│  - Benchmark orchestration              │
│  - Strategy-based routing               │
└──────────────────┬──────────────────────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ FasterWhisper│ │   OpenAI     │ │   Whisper    │
│   Provider   │ │   Provider   │ │   Provider   │
└──────────────┘ └──────────────┘ └──────────────┘
```

### Routing Strategies

```
┌─────────────────────────────────────────┐
│         RoutingStrategy (ABC)           │
└──────────────────┬──────────────────────┘
                   │
       ┌───────────┼───────────┬─────────────┐
       ▼           ▼           ▼             ▼
┌────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│   Single   │ │Benchmark │ │ Fallback │ │  Future  │
│  Provider  │ │ (AutoTest│ │          │ │(Duration,│
│            │ │ All Models│ │          │ │UserTier) │
└────────────┘ └──────────┘ └──────────┘ └──────────┘
```

---

## Implementation Components

### Phase 1: Core Infrastructure (6-8 hours)

#### 1. Data Models (`src/transcription/models.py`) - NEW

```python
@dataclass
class TranscriptionContext:
    """Metadata for routing decisions."""
    user_id: int
    duration_seconds: float
    file_size_bytes: int
    language: Optional[str] = "ru"
    priority: str = "normal"

@dataclass
class TranscriptionResult:
    """Transcription result with comprehensive metrics."""
    # Core results
    text: str
    language: str
    confidence: Optional[float] = None

    # Performance metrics
    processing_time: float        # Wall clock time
    audio_duration: float         # Actual audio length
    realtime_factor: float        # processing_time / audio_duration

    # Provider info
    provider_used: str            # "faster-whisper", "openai", "whisper"
    model_name: str               # "large-v3", "whisper-1", etc.

    # Resource usage
    peak_memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    config: Optional['BenchmarkConfig'] = None
    error: Optional[str] = None
```

#### 2. Provider Interface (`src/transcription/providers/base.py`) - NEW

```python
class TranscriptionProvider(ABC):
    """Abstract base for transcription providers."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize model and resources."""
        pass

    @abstractmethod
    async def transcribe(
        self,
        audio_path: Path,
        context: TranscriptionContext
    ) -> TranscriptionResult:
        """Transcribe audio file."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup resources."""
        pass

    @abstractmethod
    def is_initialized(self) -> bool:
        """Check initialization status."""
        pass
```

#### 3. Provider Implementations

**FastWhisperProvider** (`src/transcription/providers/faster_whisper_provider.py`) - REFACTORED
- Refactor existing `whisper_service.py`
- Add configurable beam_size, vad_filter parameters
- Enhanced metrics collection (memory, CPU)
- Support for all model sizes: tiny, base, small, medium, large-v2, large-v3

**OpenAIProvider** (`src/transcription/providers/openai_provider.py`) - NEW
- OpenAI API client integration
- Retry logic with exponential backoff
- Error handling (rate limits, timeouts)
- Reference quality baseline

**WhisperProvider** (`src/transcription/providers/whisper_provider.py`) - NEW
- Original OpenAI Whisper (local)
- Similar interface to FasterWhisper
- For comparison testing

#### 4. Routing System

**Strategies** (`src/transcription/routing/strategies.py`) - NEW
- `RoutingStrategy` abstract base
- `SingleProviderStrategy` - Select one provider (current behavior)
- `FallbackStrategy` - Primary with backup (useful for production)
- **`BenchmarkStrategy`** - Auto-test all configurations (Phase 2)

**Router** (`src/transcription/routing/router.py`) - NEW
- `TranscriptionRouter` class
- Provider pool management
- Metrics aggregation
- Strategy-based routing
- `run_benchmark()` method for automated testing

#### 5. Configuration (`src/config.py`) - MODIFIED

```python
class Settings(BaseSettings):
    # Provider selection
    whisper_providers: list[str] = Field(default=["faster-whisper"])
    whisper_routing_strategy: str = Field(default="single")

    # Strategy configuration
    primary_provider: str = Field(default="faster-whisper")
    fallback_provider: Optional[str] = None
    duration_threshold_seconds: int = Field(default=30)

    # FasterWhisper configuration
    faster_whisper_model_size: str = Field(default="base")
    faster_whisper_device: str = Field(default="cpu")
    faster_whisper_compute_type: str = Field(default="int8")
    faster_whisper_beam_size: int = Field(default=5)
    faster_whisper_vad_filter: bool = Field(default=True)

    # Original Whisper configuration
    whisper_model_size: str = Field(default="base")
    whisper_device: str = Field(default="cpu")

    # OpenAI configuration
    openai_api_key: Optional[str] = None
    openai_model: str = Field(default="whisper-1")
    openai_timeout: int = Field(default=60)

    # Benchmark mode (Phase 2)
    benchmark_mode: bool = Field(default=False)
    benchmark_configs: list[dict] = Field(default_factory=list)
```

#### 6. Factory (`src/transcription/factory.py`) - NEW

```python
def create_transcription_router() -> TranscriptionRouter:
    """Create router with configured providers and strategy."""
    # Initialize enabled providers
    # Select routing strategy
    # Return configured router

# Global instance management
_router_instance: Optional[TranscriptionRouter] = None

def get_transcription_router() -> TranscriptionRouter:
    """Get or create global router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = create_transcription_router()
    return _router_instance
```

#### 7. Handler Updates (`src/handlers/voice_handler.py`) - MODIFIED

```python
async def handle_voice_message(update: Update, context: CallbackContext):
    """Handle voice message."""
    router = get_transcription_router()

    # Create context
    ctx = TranscriptionContext(
        user_id=update.effective_user.id,
        duration_seconds=update.message.voice.duration,
        file_size_bytes=update.message.voice.file_size,
        language="ru"
    )

    # Normal mode: single transcription
    result = await router.transcribe(audio_path, ctx)
    await update.message.reply_text(result.text)
```

### Phase 2: Benchmark Mode (3 hours)

#### 8. Benchmark Components (`src/transcription/models.py`) - ADDITIONS

```python
@dataclass
class BenchmarkConfig:
    """Configuration for one benchmark test."""
    provider_name: str
    model_size: Optional[str] = None
    compute_type: Optional[str] = None
    beam_size: Optional[int] = None
    device: Optional[str] = None
    display_name: Optional[str] = None

@dataclass
class BenchmarkReport:
    """Comprehensive benchmark comparison report."""
    results: list[TranscriptionResult]
    reference_text: Optional[str]  # OpenAI baseline
    audio_path: Path
    audio_duration: float
    timestamp: datetime

    def get_sorted_by_speed(self) -> list[TranscriptionResult]: ...
    def get_sorted_by_quality(self) -> list[TranscriptionResult]: ...
    def to_markdown(self) -> str: ...
    def save_to_file(self, output_dir: Path) -> Path: ...
```

#### 9. BenchmarkStrategy (`src/transcription/routing/strategies.py`) - ADDITION

```python
class BenchmarkStrategy(RoutingStrategy):
    """
    Auto-test all configured provider/model combinations.
    One voice message → comprehensive comparison report.
    """
    def __init__(self, benchmark_configs: list[BenchmarkConfig]): ...
    def is_benchmark_mode(self) -> bool: return True
```

#### 10. Router Benchmark Method (`src/transcription/routing/router.py`) - ADDITION

```python
class TranscriptionRouter:
    async def run_benchmark(
        self,
        audio_path: Path,
        context: TranscriptionContext,
    ) -> BenchmarkReport:
        """
        Run transcription through all benchmark configurations.
        Returns comprehensive comparison report with:
        - Performance metrics (speed, memory)
        - Quality scores (vs OpenAI reference)
        - Recommendations
        """
        ...
```

#### 11. Benchmark Handler (`src/handlers/voice_handler.py`) - MODIFICATION

```python
async def handle_voice_message(update: Update, context: CallbackContext):
    router = get_transcription_router()

    if settings.benchmark_mode:
        await update.message.reply_text("🔬 Running benchmark...")
        report = await router.run_benchmark(audio_path, ctx)

        # Save report
        report_path = report.save_to_file(Path("./benchmark_reports"))

        # Send summary + report file
        await update.message.reply_text(summary)
        await update.message.reply_document(report_path)
    else:
        # Normal transcription
        result = await router.transcribe(audio_path, ctx)
        await update.message.reply_text(result.text)
```

---

## Dependency Management

### pyproject.toml Updates

```toml
[tool.poetry.dependencies]
python = "^3.11"
python-telegram-bot = "^22.5"
sqlalchemy = {extras = ["asyncio"], version = "^2.0.44"}
aiosqlite = "^0.20.0"
alembic = "^1.13"
python-dotenv = "^1.0.0"
pydantic = "^2.10"
pydantic-settings = "^2.6"
httpx = "^0.28"
psutil = "^6.1"  # NEW: For resource monitoring

# Optional dependencies
faster-whisper = {version = "^1.2.0", optional = true}
openai = {version = "^1.50.0", optional = true}
whisper = {version = "^1.0.0", optional = true}
torch = {version = "^2.0.0", optional = true}

[tool.poetry.extras]
faster-whisper = ["faster-whisper"]
openai-api = ["openai"]
whisper = ["whisper", "torch"]
all-providers = ["faster-whisper", "openai", "whisper", "torch"]
```

### Docker Build Strategy

```dockerfile
# For testing: install all providers
RUN poetry install --extras "all-providers"

# For production: install only chosen provider
RUN poetry install --extras "faster-whisper"
```

---

## Testing Strategy

### Benchmark Testing Workflow

1. **Enable benchmark mode**
   ```bash
   BENCHMARK_MODE=true
   WHISPER_PROVIDERS=["faster-whisper", "whisper", "openai"]
   WHISPER_ROUTING_STRATEGY=benchmark
   OPENAI_API_KEY=sk-...
   ```

2. **Send ONE test voice message** (typical use case, ~30-60 seconds)

3. **Bot automatically tests all configurations:**
   - faster-whisper: tiny, base, small, medium (int8, beam5)
   - faster-whisper: small (float32, beam10 for quality comparison)
   - whisper: base, small
   - openai: whisper-1 (reference quality)

4. **Receive comprehensive report:**
   - Performance table (sorted by speed)
   - Quality ranking (similarity to OpenAI)
   - Detailed results per configuration
   - Automatic recommendations

5. **Analyze and choose optimal model**

6. **Switch to production mode**
   ```bash
   BENCHMARK_MODE=false
   WHISPER_ROUTING_STRATEGY=single
   PRIMARY_PROVIDER=faster-whisper
   FASTER_WHISPER_MODEL_SIZE=small  # Based on benchmark
   ```

### Unit Tests Structure

```
tests/unit/
├── test_providers.py
│   ├── TestFasterWhisperProvider
│   ├── TestOpenAIProvider
│   ├── TestWhisperProvider
├── test_strategies.py
│   ├── TestSingleProviderStrategy
│   ├── TestFallbackStrategy
│   ├── TestBenchmarkStrategy
├── test_router.py
│   ├── TestTranscriptionRouter
│   ├── TestBenchmarkOrchestration
└── test_models.py
    ├── TestBenchmarkReport
    ├── TestQualityMetrics
```

---

## File Structure

```
src/
├── transcription/
│   ├── __init__.py                          # Exports: get_transcription_router
│   ├── models.py                            # NEW: Data models
│   ├── factory.py                           # NEW: Factory function
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                          # NEW: Abstract provider
│   │   ├── faster_whisper_provider.py       # REFACTORED from whisper_service.py
│   │   ├── openai_provider.py               # NEW: OpenAI API
│   │   └── whisper_provider.py              # NEW: Original Whisper
│   │
│   └── routing/
│       ├── __init__.py
│       ├── router.py                        # NEW: TranscriptionRouter
│       └── strategies.py                    # NEW: Routing strategies
│
├── handlers/
│   └── voice_handler.py                     # MODIFIED: Use router, benchmark support
│
├── config.py                                # MODIFIED: Add transcription settings
│
└── main.py                                  # MODIFIED: Initialize router

benchmark_reports/                           # NEW: Generated reports
└── benchmark_YYYYMMDD_HHMMSS.md

tests/
├── unit/
│   ├── test_providers.py                    # NEW
│   ├── test_strategies.py                   # NEW
│   ├── test_router.py                       # NEW
│   └── test_whisper_service.py              # REMOVE or refactor

pyproject.toml                               # MODIFIED: Optional dependencies
.env.example                                 # MODIFIED: Add transcription config
```

---

## Success Criteria

After implementation, the system must:

✅ Support switching providers via `.env` without code changes
✅ Test multiple model_size configurations for each provider
✅ Collect detailed metrics: processing time, RTF, memory usage
✅ Use OpenAI API as quality reference baseline
✅ **Auto-benchmark all configurations from ONE voice message**
✅ Generate markdown reports with quality comparison
✅ Provide automatic recommendations (best speed, quality, balance)
✅ Easy removal of unused providers after selection
✅ Maintain backward compatibility with existing functionality
✅ Pass all unit tests with >80% coverage
✅ Support future hybrid routing strategies

---

## Risk Mitigation

### Technical Risks

1. **Multiple model loading increases memory**
   - Mitigation: Lazy loading, only initialize providers in benchmark when needed
   - Cleanup after benchmark completion

2. **Long benchmark execution time**
   - Mitigation: Progress updates to user, async processing
   - Option to configure subset of tests

3. **OpenAI API costs during benchmark**
   - Mitigation: Clear warning to user, optional exclusion from benchmark
   - Single API call per benchmark session

4. **Quality comparison accuracy**
   - Mitigation: Use multiple similarity metrics (Jaccard, Levenshtein)
   - Manual review of benchmark results recommended

### Migration Risks

1. **Breaking existing functionality**
   - Mitigation: Comprehensive unit tests before refactoring
   - Feature flag for gradual rollout

2. **Configuration complexity**
   - Mitigation: Sensible defaults, extensive documentation
   - `.env.example` with comments

---

## Future Enhancements

Post-implementation opportunities:

1. **Advanced Routing Strategies:**
   - `DurationBasedStrategy` - Short audio → fast model, long → quality model
   - `UserTierStrategy` - Premium users → OpenAI, free → local
   - `ABTestStrategy` - Split traffic for continuous quality monitoring

2. **Enhanced Quality Metrics:**
   - WER (Word Error Rate) calculation
   - Language-specific quality scoring
   - Confidence scores from models

3. **Persistent Benchmark Storage:**
   - Database storage of benchmark results
   - Trend analysis over time
   - API endpoint for benchmark history

4. **Real-time Monitoring:**
   - Prometheus metrics export
   - Grafana dashboards
   - Alerting on quality degradation

---

## Timeline & Milestones

### Day 1: Core Infrastructure (6-8 hours)
- [ ] Create data models and provider interface
- [ ] Refactor existing code into FasterWhisperProvider
- [ ] Implement OpenAIProvider and WhisperProvider
- [ ] Create router and basic strategies
- [ ] Update configuration management
- [ ] Update voice handler (non-benchmark mode)
- [ ] Unit tests for providers and router

**Milestone:** Can switch between providers via `.env`, single transcription works

### Day 2: Benchmark Mode (3 hours)
- [ ] Implement BenchmarkStrategy
- [ ] Implement BenchmarkReport with markdown generation
- [ ] Add `run_benchmark()` to router
- [ ] Update voice handler for benchmark mode
- [ ] Unit tests for benchmark functionality
- [ ] Documentation and `.env.example`

**Milestone:** Full benchmark automation works, generates reports

### Day 3: Testing & Polish (2 hours)
- [ ] Integration testing with real audio files
- [ ] Verify all model sizes and parameters
- [ ] Test OpenAI API integration
- [ ] Performance optimization
- [ ] Documentation updates
- [ ] Memory Bank updates

**Milestone:** Ready for production use, documented, tested

---

## Git Workflow

### Branch Strategy
- Feature branch: `feature/flexible-whisper-providers`
- Commit strategy: Logical commits per component
- PR to `main` after completion

### Commit Plan
1. `feat: add transcription data models and provider interface`
2. `refactor: extract FasterWhisperProvider from whisper_service`
3. `feat: add OpenAI API provider`
4. `feat: add original Whisper provider`
5. `feat: implement routing system with strategies`
6. `feat: add transcription router with metrics`
7. `feat: update configuration for flexible providers`
8. `feat: implement benchmark strategy and reporting`
9. `feat: update voice handler with benchmark support`
10. `test: add comprehensive unit tests`
11. `docs: update documentation and examples`
12. `chore: update dependencies with optional extras`

---

## Configuration Examples

### Testing Mode (Current Need)

```bash
# Test one provider at a time
WHISPER_PROVIDERS=["faster-whisper"]
WHISPER_ROUTING_STRATEGY=single
PRIMARY_PROVIDER=faster-whisper
FASTER_WHISPER_MODEL_SIZE=base  # Change: tiny, base, small, medium, large-v3
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE_TYPE=int8
```

### Benchmark Mode (Automated Testing)

```bash
# Auto-test all configurations
BENCHMARK_MODE=true
WHISPER_PROVIDERS=["faster-whisper", "whisper", "openai"]
WHISPER_ROUTING_STRATEGY=benchmark
OPENAI_API_KEY=sk-...

# Configs defined in Settings or override via BENCHMARK_CONFIGS JSON
```

### Production Mode (After Selection)

```bash
# Using chosen model
WHISPER_PROVIDERS=["faster-whisper"]
WHISPER_ROUTING_STRATEGY=single
PRIMARY_PROVIDER=faster-whisper
FASTER_WHISPER_MODEL_SIZE=small  # Winner from benchmark
FASTER_WHISPER_COMPUTE_TYPE=int8
FASTER_WHISPER_DEVICE=cpu
```

### Production with Fallback

```bash
# Local with API backup
WHISPER_PROVIDERS=["faster-whisper", "openai"]
WHISPER_ROUTING_STRATEGY=fallback
PRIMARY_PROVIDER=faster-whisper
FALLBACK_PROVIDER=openai
FASTER_WHISPER_MODEL_SIZE=small
OPENAI_API_KEY=sk-...
```

---

## Expected Benchmark Results (CPU Estimates)

Based on typical VPS CPU performance:

| Configuration | RTF (CPU) | Memory | Quality vs OpenAI | Recommendation |
|---------------|-----------|--------|-------------------|----------------|
| faster-whisper tiny int8 | 0.3x | 380 MB | ~75% | Too low quality |
| faster-whisper base int8 | 0.6x | 450 MB | ~90% | Good for speed |
| **faster-whisper small int8** | **1.5x** | **850 MB** | **~95%** | **Best balance** |
| faster-whisper medium int8 | 5.5x | 1.8 GB | ~98% | Slow on CPU |
| faster-whisper large-v3 int8 | 15x | 3.5 GB | ~99% | Too slow for CPU |
| whisper base | 1.5x | 890 MB | ~90% | Slower than faster-whisper |
| openai whisper-1 | 0.1x | N/A | 100% (ref) | $0.006/min cost |

**Expected Winner for CPU Production:** `faster-whisper` with `small` model and `int8` compute type

---

## Next Steps

1. ✅ Plan approved
2. ⏳ Create feature branch: `feature/flexible-whisper-providers`
3. ⏳ Begin implementation via `/workflow:execute`
4. ⏳ Incremental commits with logical grouping
5. ⏳ Testing with real audio files
6. ⏳ Benchmark mode validation
7. ⏳ Documentation updates
8. ⏳ PR creation with comprehensive description
9. ⏳ Merge to main after approval

---

**Status:** Ready for implementation
**Approved by:** User
**Implementation starts:** 2025-10-20
