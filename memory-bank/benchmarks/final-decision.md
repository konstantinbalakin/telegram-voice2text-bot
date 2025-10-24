# Final Model Decision: faster-whisper medium/int8/beam1

**Date**: 2025-10-24
**Status**: ✅ APPROVED FOR PRODUCTION

## Decision Summary

After comprehensive benchmarking of multiple Whisper configurations (30+ tested), the **production default** configuration is:

- **Model**: faster-whisper
- **Size**: medium
- **Compute Type**: int8
- **Beam Size**: 1 (greedy decoding)

## Benchmark Results

Tested on 3 representative Telegram voice clips:
- Short: 7 seconds
- Medium: 24 seconds
- Long: 163 seconds

### Performance Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| **RTF (Realtime Factor)** | ~0.3x | 3x faster than audio duration |
| **Peak Memory** | ~3.5 GB | Acceptable for 4GB+ VPS |
| **Quality** | Excellent | 100% similarity on short clips, 54-57% on long informal speech vs OpenAI reference |
| **7s audio** | ~2s processing | Very fast |
| **30s audio** | ~10s processing | Acceptable UX |
| **60s audio** | ~20s processing | Within tolerance |

### Quality Assessment

**Strengths**:
- Excellent Russian language recognition
- Perfect accuracy on short, clear speech
- Good handling of technical terms
- Low hallucination rate

**Limitations**:
- Long informal speech (~3 min) shows quality degradation compared to OpenAI API
- Acceptance criterion: good enough for general use, premium users can use OpenAI fallback

## Alternatives Considered

| Configuration | RTF | Memory | Quality | Decision |
|---------------|-----|--------|---------|----------|
| tiny/int8/beam3 | 0.05x | <1GB | 22-78% | ❌ Too low quality |
| base/int8/beam1 | 0.1x | ~1.5GB | ~90% | ⚠️ Fallback option |
| small/int8/beam1 | 0.2x | ~2.4GB | ~90% | ⚠️ Alternative |
| **medium/int8/beam1** | **0.3x** | **~3.5GB** | **~95%** | ✅ **PRODUCTION** |
| medium/int8/beam5 | 0.7x | ~5GB | ~96% | ❌ Too slow |
| OpenAI API | varies | N/A | 100% (ref) | 💰 Fallback (costs $0.006/min) |

## Implementation Changes

### Code Defaults Updated

1. **src/config.py**:
   ```python
   faster_whisper_model_size: str = "medium"  # was "base"
   faster_whisper_beam_size: int = 1  # was 5
   ```

2. **.env.example**:
   - Updated model recommendations with benchmark data
   - Added RTF examples for user guidance
   - Removed original openai-whisper references

3. **README.md**:
   - Added Production Configuration section
   - Documented processing time examples

## VPS Requirements

**Minimum Recommended**:
- RAM: 4GB (to accommodate 3.5GB peak + system overhead)
- CPU: 2 cores
- Storage: 5GB (model ~1.5GB, system, logs)

**Initial Deployment**:
- Target: Russian VPS (cheaper for testing)
- Configuration: faster-whisper only, no OpenAI fallback
- Migration plan: European VPS when OpenAI API access needed

## Fallback Strategy

The architecture supports multi-provider routing:

1. **Production (Phase 1)**: faster-whisper/medium only
2. **Future (Phase 2)**: Add OpenAI API as fallback for premium users or long audio

## References

- Full benchmark reports: `docs/quality_compare/*.md`
- Benchmark rollup: `memory-bank/benchmarks/fast-whisper.md`
- Configuration examples: `.env.example`

## Approval

✅ **Approved by**: User (manual transcript review completed)
✅ **Implemented**: 2025-10-24 (this PR)
✅ **Status**: Ready for VPS deployment
