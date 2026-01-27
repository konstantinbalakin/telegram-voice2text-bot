# LLM Integration (DeepSeek V3)

[← Back to Documentation](../README.md)

## Overview

The bot uses **DeepSeek V3** for intelligent text processing. This powers all interactive features: structuring, beautification, and summarization.

**Why DeepSeek?**
- ✅ Excellent quality (comparable to GPT-4)
- ✅ 30x cheaper than OpenAI (~$0.0002 per request)
- ✅ Fast response times (2-5 seconds)
- ✅ Great Russian language support
- ✅ $5 free credit for new accounts

## Architecture

### High-Level Flow

```mermaid
graph LR
    A[Transcription] --> B[TextProcessor]
    B --> C[DeepSeek API]
    C --> D[Processed Text]
    D --> E[Cache in DB]
    E --> F[Show to User]
```

### Components

**1. LLM Service Layer** (`src/services/llm_service.py`):
```python
class LLMService:
    async def refine_transcription(text: str, custom_prompt: str) -> str:
        # Load prompt from file
        # Call DeepSeek API
        # Handle retries and errors
        # Return processed text
```

**2. Text Processor** (`src/services/text_processor.py`):
```python
class TextProcessor:
    async def create_structured(text: str) -> str:
        prompt = self._load_prompt("structured.md")
        return await self.llm_service.refine_transcription(text, prompt)

    async def create_magic(text: str) -> str:
        prompt = self._load_prompt("magic.md")
        return await self.llm_service.refine_transcription(text, prompt)

    async def create_summary(text: str) -> str:
        prompt = self._load_prompt("summary.md")
        return await self.llm_service.refine_transcription(text, prompt)
```

**3. Prompt Templates** (`prompts/*.md`):
- `structured.md` - Structuring instructions
- `magic.md` - Beautification instructions
- `summary.md` - Summarization instructions
- `emoji.md` - Emoji enhancement instructions
- `length_*.md` - Length adjustment instructions

## Configuration

### Required Settings

```env
# Enable LLM processing
LLM_REFINEMENT_ENABLED=true

# Provider and model
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com

# API key (get from https://platform.deepseek.com/api_keys)
LLM_API_KEY=sk-your-deepseek-api-key-here

# Timeout for API requests
LLM_TIMEOUT=30
```

### Optional Settings

```env
# Debug mode (shows draft vs refined comparison)
LLM_DEBUG_MODE=false

# Progress bar duration estimate
LLM_PROCESSING_DURATION=30
```

## Prompt Engineering

### Structure of Prompts

All prompts follow this pattern:

```markdown
# Role and Context
You are an expert text editor specializing in [specific task].

# Task
Transform the following voice transcription by [specific instructions].

# Guidelines
- Guideline 1
- Guideline 2
- ...

# Important Rules
- Rule 1
- Rule 2
- ...

# Input Format
The text is a raw transcription from voice recognition.

# Output Format
Return only the processed text, no explanations.
```

### Example: Structured Mode

**Prompt** (`prompts/structured.md`):
```markdown
# Role
You are a text structuring expert.

# Task
Transform this voice transcription into well-structured text.

# Guidelines
- Break into logical paragraphs
- Add headings where appropriate
- Convert lists to bullet points
- Add moderate emojis (1-2 per section)
- Preserve author's voice and tone

# Rules
- Don't change meaning
- Don't add information not in original
- Keep conversational tone if present
- Use simple, clear language

# Output
Return only the structured text.
```

### Example: Magic Mode

**Prompt** (`prompts/magic.md`):
```markdown
# Role
You are a professional editor who transforms transcriptions into publication-ready posts.

# Task
Transform this transcription into engaging, readable text for Telegram channel.

# Guidelines
- Preserve author's unique voice and personality
- Add warmth and conversational tone
- Make text flow naturally
- Use author's vocabulary and expressions
- Add emojis sparingly (enhance, don't overwhelm)
- Break into readable paragraphs

# Critical Rules
- NEVER change the author's style to corporate/formal
- KEEP author's colloquialisms and unique phrases
- PRESERVE emotional tone
- DON'T add information not in original

# Output
Publication-ready text maintaining author's voice.
```

### Customizing Prompts

To customize processing behavior:

1. Edit prompt files in `prompts/` directory
2. No code changes needed!
3. Bot loads prompts dynamically at runtime
4. Fallback to hardcoded prompts if files missing

**Example customization:**
```bash
# Edit structuring behavior
nano prompts/structured.md

# Change emoji level
# From: "Add moderate emojis (1-2 per section)"
# To: "Add emojis generously to make text lively"

# Restart bot
docker-compose restart
```

## Error Handling

### Graceful Degradation

If LLM processing fails, bot falls back to original text:

```python
try:
    refined_text = await llm_service.refine_transcription(text, prompt)
    return refined_text
except (LLMTimeoutError, LLMAPIError, Exception) as e:
    logger.error(f"LLM refinement failed: {e}")
    return original_text  # Fallback
```

**Error types handled:**
- Timeout errors (30s limit)
- API errors (rate limits, invalid key)
- Network errors
- Unexpected failures

### Retry Logic

Built-in retry with exponential backoff:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPError))
)
async def _call_api(self, text: str, prompt: str) -> str:
    # API call here
```

**Retry strategy:**
- Attempt 1: Immediate
- Attempt 2: Wait 2 seconds
- Attempt 3: Wait 4 seconds
- After 3 attempts: Fall back to original text

## Performance

### Typical Response Times

| Text Length | Processing Time |
|-------------|----------------|
| <500 chars  | 2-3 seconds    |
| 500-1500    | 3-5 seconds    |
| 1500-3000   | 5-7 seconds    |
| >3000       | 7-10 seconds   |

### Caching Strategy

Processed variants are cached in database:

**Benefits:**
- Instant re-display (0ms)
- Cost savings (no repeated LLM calls)
- Consistent results

**Implementation:**
```python
# Check cache first
variant = await variant_repo.get_variant(
    usage_id=usage_id,
    mode="magic",
    length_level="default",
    emoji_level=1
)

if variant:
    return variant.text_content  # Instant!
else:
    # Process with LLM
    text = await text_processor.create_magic(original_text)
    # Cache result
    await variant_repo.create(...)
    return text
```

## Cost Analysis

### DeepSeek V3 Pricing

**Official rates:**
- Input: $0.27 per 1M tokens (~$0.00027 per 1K tokens)
- Output: $1.10 per 1M tokens (~$0.00110 per 1K tokens)

**Typical request:**
- Input: ~500 tokens (transcription + prompt)
- Output: ~500 tokens (processed text)
- **Cost**: ~$0.0002 per request

### Cost Comparison

| Provider | Model | Cost per Request | Relative Cost |
|----------|-------|------------------|---------------|
| DeepSeek | V3 | $0.0002 | 1x ⭐ |
| OpenAI | GPT-4o | $0.0060 | 30x |
| OpenAI | GPT-4 | $0.0150 | 75x |
| Anthropic | Claude Sonnet | $0.0045 | 22.5x |

### Monthly Cost Estimate

**Scenario: 100 voice messages/day**

```
100 messages/day × 30 days = 3000 messages/month

Per message:
- 3 button modes (structured, magic, summary)
- Each cached after first use
- Average: 2 LLM calls per message (some cached)

3000 messages × 2 calls × $0.0002 = $1.20/month
```

**With heavy usage (1000 messages/day):** ~$12/month

## Monitoring

### Logging

All LLM calls are logged:

```python
logger.info(
    f"LLM refinement: provider={provider}, "
    f"model={model}, duration={duration:.2f}s, "
    f"input_length={len(text)}, output_length={len(result)}"
)
```

### Database Tracking

Variant records track LLM usage:

```python
class TranscriptionVariant:
    llm_model: str  # "deepseek-chat"
    processing_time_seconds: float  # How long it took
    created_at: datetime  # When processed
    last_accessed_at: datetime  # Last retrieval
```

### Debug Mode

Enable to see draft vs refined comparison:

```env
LLM_DEBUG_MODE=true
```

**Output:**
```
✅ Оригинал:
[Raw transcription...]

🔄 После обработки:
[Processed text...]
```

**Warning:** Only use in testing! Sends extra messages to users.

## Troubleshooting

### "LLM_API_KEY not set"
```bash
# Add to .env
LLM_API_KEY=sk-your-deepseek-key-here

# Verify it loads
uv run python -c "from src.config import settings; print(settings.llm_api_key[:10])"
```

### "LLM refinement failed: timeout"
- Increase timeout: `LLM_TIMEOUT=60`
- Check network connectivity
- Verify DeepSeek API status

### "Rate limit exceeded"
- DeepSeek has generous free tier limits
- Upgrade to pay-as-you-go if needed
- Implement request throttling

### Poor quality results
- Review and edit prompt files
- Test with `LLM_DEBUG_MODE=true`
- Try different emoji/length levels
- Check if input text quality is good

### Variant caching not working
- Check database write permissions
- Verify `MAX_CACHED_VARIANTS_PER_TRANSCRIPTION > 0`
- Look for unique constraint violations in logs

## Alternative Providers

While production uses DeepSeek, the architecture supports other providers:

### OpenAI (expensive but powerful)

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_API_KEY=sk-your-openai-key
LLM_BASE_URL=https://api.openai.com/v1
```

**Cost:** ~30x higher (~$0.006 per request)

### GigaChat (Russian alternative)

```env
LLM_PROVIDER=gigachat
LLM_MODEL=GigaChat
LLM_API_KEY=your-gigachat-key
LLM_BASE_URL=https://gigachat.devices.sberbank.ru/api/v1
```

**Note:** Requires Russian verification

### Adding New Providers

Extend `LLMProvider` base class:

```python
class MyCustomProvider(LLMProvider):
    async def refine_text(self, text: str, prompt: str) -> str:
        # Your implementation
        pass

    async def close(self) -> None:
        # Cleanup
        pass
```

Register in `LLMFactory`:
```python
if settings.llm_provider == "mycustom":
    return MyCustomProvider(...)
```

## Best Practices

1. **Always enable caching** - Saves costs and improves UX
2. **Use graceful fallback** - Return original text on errors
3. **Monitor costs** - Track LLM usage in production
4. **Customize prompts** - Adjust for your use case
5. **Test thoroughly** - Use DEBUG mode before production
6. **Set reasonable timeouts** - Balance UX and reliability
7. **Handle rate limits** - Implement backoff strategies

## Related Documentation

- [Interactive Modes](interactive-modes.md) - How features use LLM
- [Configuration Guide](../getting-started/configuration.md) - Setup instructions
- [Costs Guide](../deployment/costs.md) - Detailed pricing breakdown
- [Architecture](../development/architecture.md) - Technical implementation
