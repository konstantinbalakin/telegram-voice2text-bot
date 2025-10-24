# Fast-Whisper Benchmark Summary

## Data Sources
- `docs/quality_compare/2025-10-22_00_07.md`
- `docs/quality_compare/2025-10-22_00_22.md`
- `docs/quality_compare/2025-10-22_01_51.md`

All runs executed via the internal `benchmark` mode, using the OpenAI Whisper API output as the reference transcription for quality scoring.

## Test Setup
- Audio samples: 3 Telegram voice messages (7s, 24s, 163s)
- Hardware: local development machine (CPU only)
- Metrics captured per configuration: processing time, realtime factor (RTF), peak memory, quality score vs reference
- Models compared: OpenAI Whisper API, `whisper` (tiny/base/small/medium) local models, `faster-whisper` (tiny/base/small/medium) with multiple beam sizes and compute types (`int8`, `float32`)

## Key Findings
- **Fastest configuration**: `faster-whisper / tiny / int8 / beam3`
  - 0.40–0.71 s processing time (RTF 0.03–0.05x)
  - Memory footprint under 1 GB
  - Quality 22–78% vs reference; acceptable only for short, clear audio
- **Best quality among local models**: `faster-whisper / medium / int8 / beam3/5/7`
  - 5.1–5.7 s processing time on 7 s clip (RTF 0.65–0.72x)
  - Up to 5.6 GB RAM usage
  - Achieved 100% similarity on short samples; ~54–57% on long sample
- **Best balance (speed vs quality)**: `faster-whisper / small / int8 / beam1`
  - 1.9–2.0 s processing time (RTF 0.08–0.18x)
  - 2.3–2.5 GB RAM
  - Quality ~90% on 24 s sample; 53% on short clip; 52% on long clip
- **Baseline**: OpenAI Whisper API remains highest quality (reference) with 2.4–7.5 s latency, but requires paid API and external data transfer
- **Legacy `whisper` models** demand >2.4 GB RAM and deliver inconsistent quality compared to `faster-whisper`

## Operational Implications
- VPS sizing should consider ~3 GB reserved RAM for `faster-whisper / small / int8` workloads; reserve headroom if experimenting with `medium`
- Quality gap widens on longer, informal speech; manual inspection needed before locking default configuration
- Existing environment toggle for Whisper modes is sufficient for production experiments; document recommended presets for `tiny`, `small`, and `medium`

## Next Actions
1. Manually review transcripts and quality deltas to pick the production default (likely `faster-whisper / small / int8 / beam1` pending accuracy tolerance)
2. Collect VPS-specific latency and memory metrics after deployment to validate local assumptions
3. Update Memory Bank once the production model is chosen and document tuning guidance for alternative modes
