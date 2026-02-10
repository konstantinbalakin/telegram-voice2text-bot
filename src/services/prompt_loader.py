"""Utility for loading LLM prompts from files."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache for loaded prompts
_prompt_cache: dict[str, str] = {}


def load_prompt(prompt_name: str, project_root: Path | None = None) -> str:
    """
    Load a prompt from the prompts/ directory.

    Args:
        prompt_name: Name of the prompt file (without .md extension)
        project_root: Project root directory (auto-detected if None)

    Returns:
        Prompt text with placeholders

    Raises:
        FileNotFoundError: If prompt file doesn't exist
        IOError: If prompt file can't be read

    Examples:
        >>> load_prompt("structured")
        "Твоя задача: структурировать текст..."
    """
    # Check cache first
    if prompt_name in _prompt_cache:
        logger.debug(f"Using cached prompt: {prompt_name}")
        return _prompt_cache[prompt_name]

    # Auto-detect project root if not provided
    if project_root is None:
        # Start from this file's directory and go up to find project root
        current = Path(__file__).resolve()
        while current.parent != current:
            if (current / "prompts").exists():
                project_root = current
                break
            current = current.parent
        else:
            # Fallback: assume prompts/ is in current working directory
            project_root = Path.cwd()

    # Build prompt file path
    prompt_file = project_root / "prompts" / f"{prompt_name}.md"

    # Load prompt
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt_text = f.read()

        # Cache the prompt
        _prompt_cache[prompt_name] = prompt_text
        logger.info(f"Loaded prompt: {prompt_name} ({len(prompt_text)} chars)")

        return prompt_text

    except FileNotFoundError:
        logger.error(f"Prompt file not found: {prompt_file}")
        raise FileNotFoundError(f"Prompt '{prompt_name}' not found at {prompt_file}")

    except IOError as e:
        logger.error(f"Failed to read prompt file {prompt_file}: {e}")
        raise IOError(f"Failed to read prompt '{prompt_name}': {e}")


def clear_cache() -> None:
    """Clear the prompt cache (useful for tests or hot-reloading)."""
    global _prompt_cache
    _prompt_cache.clear()
    logger.debug("Prompt cache cleared")
