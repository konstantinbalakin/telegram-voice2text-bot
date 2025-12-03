# LLM Prompts

This directory contains LLM prompts used for interactive transcription features.

## Purpose

Prompts are stored as separate Markdown files to:
- Make them easy to edit without changing code
- Allow version control of prompt iterations
- Enable prompt experimentation and A/B testing
- Keep prompts organized and maintainable

## Available Prompts

### `refinement.md`
Used for refining raw transcription text (Hybrid Transcription Strategy).

**Purpose**: Fix transcription errors while preserving meaning. Used in hybrid mode to improve draft transcriptions from fast models.

**Placeholders**:
- `{text}` - The draft transcription text to refine

**Usage**:
```python
from src.services.prompt_loader import load_prompt

refinement_prompt = load_prompt("refinement")
# Used by LLMService internally
```

### `structured.md`
Used for structuring raw transcription text (Phase 2: Text Structuring).

**Purpose**: Add proper punctuation, paragraphs, and formatting while preserving all content and meaning.

**Placeholders**:
- `{text}` - The raw transcription text to structure

**Usage**:
```python
from src.services.prompt_loader import load_prompt

prompt_template = load_prompt("structured")
prompt = prompt_template.format(text="raw transcription...")
```

### `length_shorter.md`
Used for making text shorter while preserving key information (Phase 3: Length Variations).

**Purpose**: Reduce text length by approximately 20% by removing less important details and repetitions.

**Placeholders**:
- `{text}` - The current text to shorten
- `{mode}` - Text mode (structured/summary)

**Usage**:
```python
from src.services.prompt_loader import load_prompt

prompt_template = load_prompt("length_shorter")
prompt = prompt_template.format(text="text to shorten", mode="structured")
```

### `length_longer.md`
Used for making text longer with additional details (Phase 3: Length Variations).

**Purpose**: Expand text length by approximately 20% by elaborating key points and adding context.

**Placeholders**:
- `{text}` - The current text to expand
- `{mode}` - Text mode (structured/summary)

**Usage**:
```python
from src.services.prompt_loader import load_prompt

prompt_template = load_prompt("length_longer")
prompt = prompt_template.format(text="text to expand", mode="structured")
```

## Adding New Prompts

1. Create a new `.md` file in this directory
2. Use `{placeholder}` syntax for dynamic content
3. Document the prompt purpose in this README
4. Load it using `load_prompt("filename")` (without `.md` extension)

## Prompt Guidelines

When writing prompts:
1. Be specific and clear about the task
2. Include concrete requirements and constraints
3. Specify output format expectations
4. Use Russian language for Russian text processing
5. Keep prompts focused on a single task
6. Include examples if helpful for complex tasks

## Caching

Prompts are cached in memory after first load for performance. To clear cache (useful in tests):

```python
from src.services.prompt_loader import clear_cache
clear_cache()
```

## Future Prompts

Planned prompts for upcoming phases:
- `summary.md` - Text summarization (Phase 4)
- `emoji.md` - Adding emojis to text (Phase 5)
