# API Costs Guide

[← Back to Documentation](../README.md)

## Overview

Production bot uses two paid APIs:
1. **OpenAI Whisper API** - Voice transcription
2. **DeepSeek V3** - Text processing (структурирование, резюме, "сделать красиво")

This guide helps you estimate and optimize costs.

## Pricing Breakdown

### OpenAI Whisper API

**Official pricing:** https://openai.com/api/pricing/

| Model | Cost per Minute | Speed | Quality | Use Case |
|-------|----------------|-------|---------|----------|
| whisper-1 | $0.006 | Normal | Excellent | Production ⭐ |
| gpt-4o-transcribe | $0.012 | Fast | Better | Premium |
| gpt-4o-mini-transcribe | $0.012 | Faster | Good | Quick transcription |

**Recommendations:**
- **whisper-1**: Best value, excellent quality, production default
- **gpt-4o models**: 2x cost, slightly better quality - use if budget allows

### DeepSeek V3 LLM

**Official pricing:** https://platform.deepseek.com/

| Type | Cost per 1M Tokens | Cost per 1K Tokens |
|------|-------------------|-------------------|
| Input (prompts) | $0.27 | $0.00027 |
| Output (responses) | $1.10 | $0.00110 |

**Typical request:**
- Input: ~500 tokens (transcription + prompt)
- Output: ~500 tokens (structured text)
- **Average cost**: ~$0.0002 per processing

**Free tier:** $5 credit (enough for ~25,000 structured texts!)

## Cost Calculator

### Per Voice Message

**Scenario: 60 second voice message with all 3 buttons**

```
Transcription (OpenAI whisper-1):
60 seconds × ($0.006/60) = $0.006

Text Processing (DeepSeek V3):
- "Структурировать" = $0.0002
- "Сделать красиво" = $0.0002
- "О чем этот текст" = $0.0002
Subtotal = $0.0006

Total per message: $0.0066 (~$0.007)
```

**Note:** Variants are cached - repeated button clicks cost $0!

### Monthly Cost Estimates

#### Small Bot (10 messages/day)

```
10 messages/day × 30 days = 300 messages/month

Transcription: 300 × $0.006 = $1.80
Text Processing: 300 × 3 buttons × $0.0002 = $0.18
Total: ~$2/month
```

#### Medium Bot (100 messages/day)

```
100 messages/day × 30 days = 3,000 messages/month

Transcription: 3,000 × $0.006 = $18.00
Text Processing: 3,000 × 3 buttons × $0.0002 = $1.80
Total: ~$20/month
```

#### Large Bot (1000 messages/day)

```
1,000 messages/day × 30 days = 30,000 messages/month

Transcription: 30,000 × $0.006 = $180.00
Text Processing: 30,000 × 3 buttons × $0.0002 = $18.00
Total: ~$200/month
```

### By Audio Duration

| Daily Audio Minutes | OpenAI/month | DeepSeek/month | Total/month |
|-------------------|--------------|----------------|-------------|
| 10 min | $1.80 | $0.20 | **$2** |
| 30 min | $5.40 | $0.60 | **$6** |
| 60 min | $10.80 | $1.20 | **$12** |
| 100 min | $18.00 | $2.00 | **$20** |
| 500 min | $90.00 | $10.00 | **$100** |
| 1000 min | $180.00 | $20.00 | **$200** |

## Cost Optimization Strategies

### 1. Variant Caching (Free Optimization!)

**Already implemented in production:**
```python
# First click: Costs $0.0002 (LLM processing)
user clicks "Структурировать" → DeepSeek processes → Cache result

# Repeat clicks: Costs $0 (database lookup)
user clicks "Структурировать" again → Load from cache instantly!
```

**Savings:**
- Users often switch between modes multiple times
- Each cached access saves $0.0002
- With 3 buttons, potential 3x cost reduction per user

**Configuration:**
```env
MAX_CACHED_VARIANTS_PER_TRANSCRIPTION=10  # Cache up to 10 variants
VARIANT_CACHE_TTL_DAYS=7  # Keep cache for 7 days
```

### 2. Audio Duration Limits

Prevent excessive costs from very long audio:

```env
MAX_VOICE_DURATION_SECONDS=120  # 2 minutes max
```

**Impact:**
- Blocks audio >2 minutes
- Typical voice message: 15-60 seconds
- Prevents abuse and cost overruns

### 3. Disable Optional Features

Save costs by enabling only essential features:

```env
# Essential features (keep enabled)
ENABLE_STRUCTURED_MODE=true  # Most popular
ENABLE_MAGIC_MODE=true  # High value
ENABLE_SUMMARY_MODE=true  # Useful

# Optional features (disable to save costs)
ENABLE_LENGTH_VARIATIONS=false  # +2 LLM calls per use
ENABLE_EMOJI_OPTION=false  # +3 LLM calls per use
ENABLE_TIMESTAMPS_OPTION=false  # Free (no LLM)
ENABLE_RETRANSCRIBE=false  # Expensive (full re-transcription)
```

**Savings:**
- Length variations: 2 additional LLM calls = $0.0004
- Emoji options: 3 additional LLM calls = $0.0006
- Disabling these saves up to 50% on LLM costs

### 4. Structure Strategy Threshold

Show draft for long audio before processing:

```env
STRUCTURE_DRAFT_THRESHOLD=20  # Show draft if audio ≥20s
```

**User flow:**
- Audio <20s: Direct structured result
- Audio ≥20s: Show draft first, then structure on confirm

**Why this saves money:**
- Users can review draft before committing to structure
- Prevents wasted LLM calls on unwanted content
- Still provides good UX with progress feedback

### 5. Local Transcription (Development Only)

For development/testing, use local faster-whisper:

```env
WHISPER_PROVIDERS=["faster-whisper"]
WHISPER_ROUTING_STRATEGY=single
LLM_REFINEMENT_ENABLED=false
INTERACTIVE_MODE_ENABLED=false
```

**Costs:**
- OpenAI: $0 (local processing)
- DeepSeek: $0 (disabled)
- **Total**: $0/month

**Trade-offs:**
- No interactive features
- Slower transcription
- Good for testing bot logic

## Monitoring Costs

### Database Tracking

Every transcription is logged:

```sql
SELECT
    DATE(created_at) as date,
    COUNT(*) as transcriptions,
    SUM(voice_duration_seconds) as total_seconds,
    SUM(voice_duration_seconds) * 0.0001 as estimated_openai_cost
FROM usage
WHERE created_at >= date('now', '-30 days')
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### Variant Usage Analysis

Track which modes users prefer:

```sql
SELECT
    mode,
    COUNT(*) as uses,
    COUNT(*) * 0.0002 as estimated_cost
FROM transcription_variants
WHERE created_at >= date('now', '-30 days')
GROUP BY mode
ORDER BY uses DESC;
```

Example output:
```
mode         | uses | estimated_cost
-------------|------|---------------
structured   | 5420 | $1.08
magic        | 3210 | $0.64
summary      | 1890 | $0.38
```

### Cost Alert Queries

Set up alerts for unusual usage:

```sql
-- Daily cost exceeds threshold
SELECT
    DATE(created_at) as date,
    COUNT(*) * 0.007 as estimated_daily_cost
FROM usage
WHERE created_at >= date('now', '-1 day')
HAVING estimated_daily_cost > 10.0;  -- Alert if >$10/day
```

## Billing & Payment

### OpenAI

**Payment:** https://platform.openai.com/account/billing
- Credit card required
- Billed monthly
- Usage limits configurable
- Email notifications for high usage

**Set up usage limits:**
1. Go to Usage limits
2. Set monthly limit (e.g., $50)
3. Enable email alerts at 80% threshold

### DeepSeek

**Payment:** https://platform.deepseek.com/usage
- $5 free credit for new users
- Pay-as-you-go after credit exhausted
- Very low minimum top-up (~$10)
- No monthly commitment

**Free tier lasts:**
```
$5 credit / $0.0002 per request = 25,000 requests
If 100 requests/day → 250 days of free usage!
```

## Cost Comparison: API vs Local

### API-Based (Production)

**Pros:**
- ✅ Fast transcription (5-15 seconds)
- ✅ Excellent quality
- ✅ Interactive features (buttons)
- ✅ Structured text, summaries, beautification
- ✅ No server hardware costs
- ✅ Scalable instantly

**Cons:**
- ❌ Ongoing API costs ($2-200/month depending on usage)
- ❌ Requires internet connectivity
- ❌ Subject to API rate limits

**Best for:**
- Production bots
- User-facing applications
- When quality and features matter
- When usage is moderate (<1000 min/day)

### Local Processing (faster-whisper)

**Pros:**
- ✅ No API costs ($0/month)
- ✅ Privacy (all processing local)
- ✅ No rate limits
- ✅ Works offline

**Cons:**
- ❌ Slower (RTF 0.3x = 60s audio takes ~20s)
- ❌ No interactive features
- ❌ Requires powerful server (2-4GB RAM)
- ❌ Less accurate for some languages

**Best for:**
- Development and testing
- Privacy-critical applications
- Very high volume (>10,000 min/day where API costs >$1800/month)
- Offline operation required

**Break-even point:**
```
Server cost: ~$20/month (4GB RAM VPS)
API cost at 100 min/day: ~$20/month

Break-even: ~100 minutes/day
Above this threshold, API may be more cost-effective than server upgrades!
```

## Recommendations

### For Starting Out

```env
# Use API for quality and features
WHISPER_PROVIDERS=["openai"]
OPENAI_MODEL=whisper-1  # Best value

# Enable core features only
ENABLE_STRUCTURED_MODE=true
ENABLE_MAGIC_MODE=true
ENABLE_SUMMARY_MODE=true

# Set conservative limits
MAX_VOICE_DURATION_SECONDS=120
MAX_QUEUE_SIZE=10
```

**Expected cost:** $2-10/month for small user base

### For Growth

```env
# Monitor usage and adjust limits
MAX_VOICE_DURATION_SECONDS=120  # Keep limit
STRUCTURE_DRAFT_THRESHOLD=20  # Save on long audio

# Consider premium models if quality matters
OPENAI_MODEL=gpt-4o-transcribe  # 2x cost, better quality
```

**Expected cost:** $20-100/month

### For Scale

```env
# Optimize aggressively
MAX_CACHED_VARIANTS_PER_TRANSCRIPTION=10  # Max caching
VARIANT_CACHE_TTL_DAYS=30  # Longer cache

# Consider local transcription + API for special features
WHISPER_PROVIDERS=["faster-whisper"]  # Local for basic
# Keep LLM for interactive features
```

**Expected cost:** $100-500/month
Consider dedicated infrastructure at this scale.

## Getting Help

### Cost Estimation Tool

Want accurate estimates for your usage?

```bash
# Analyze your database
sqlite3 data/bot.db << EOF
.mode column
.headers on
SELECT
    'Last 7 days' as period,
    COUNT(*) as messages,
    SUM(voice_duration_seconds)/60.0 as total_minutes,
    ROUND(SUM(voice_duration_seconds) * 0.0001, 2) as openai_cost,
    ROUND(COUNT(*) * 3 * 0.0002, 2) as deepseek_cost,
    ROUND(SUM(voice_duration_seconds) * 0.0001 + COUNT(*) * 3 * 0.0002, 2) as total_cost
FROM usage
WHERE created_at >= datetime('now', '-7 days');
EOF
```

### Support

- **OpenAI Billing Issues**: https://help.openai.com/
- **DeepSeek Support**: Contact via platform
- **Bot Optimization**: Check [Architecture Guide](../development/architecture.md)

## Related Documentation

- [Configuration Guide](../getting-started/configuration.md) - Setup API keys
- [Interactive Features](../features/interactive-modes.md) - What features cost
- [LLM Integration](../features/llm-integration.md) - How DeepSeek works
- [Docker Deployment](docker.md) - Production setup
