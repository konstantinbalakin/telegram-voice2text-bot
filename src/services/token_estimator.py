"""Token estimation for LLM output size prediction."""

import logging

logger = logging.getLogger(__name__)

# Average characters per token for different scripts.
# Russian text: ~3 chars per token (empirical from DeepSeek logs)
# English text: ~4 chars per token
# Mixed: ~3.5 chars per token
# We use a conservative estimate (lower chars/token = more tokens estimated)
CHARS_PER_TOKEN_RUSSIAN = 3
CHARS_PER_TOKEN_DEFAULT = 3.5


def estimate_tokens(text: str) -> int:
    """
    Estimate number of tokens for a text string.

    Uses a character-based heuristic. For Russian text, ~1 token ≈ 3 characters.
    This is a rough estimate — actual tokenization depends on the model's tokenizer.

    Args:
        text: Input text to estimate tokens for

    Returns:
        Estimated number of tokens
    """
    if not text:
        return 0

    # Use conservative Russian estimate (most of our text is Russian)
    return int(len(text) / CHARS_PER_TOKEN_RUSSIAN)


def will_exceed_output_limit(text: str, max_output_tokens: int) -> bool:
    """
    Check if processing a text will likely exceed the model's output token limit.

    The output of structured/magic processing is typically similar in size to input
    (or slightly larger for structured mode). We estimate output tokens as roughly
    equal to input text tokens.

    Args:
        text: Input text that will be processed by LLM
        max_output_tokens: Maximum output tokens for the model

    Returns:
        True if the estimated output will likely exceed the limit
    """
    estimated_output_tokens = estimate_tokens(text)

    exceeds = estimated_output_tokens > max_output_tokens

    if exceeds:
        logger.info(
            f"Text will likely exceed output limit: "
            f"estimated_tokens={estimated_output_tokens}, "
            f"max_output_tokens={max_output_tokens}, "
            f"text_length={len(text)}"
        )
    else:
        logger.debug(
            f"Text within output limit: "
            f"estimated_tokens={estimated_output_tokens}, "
            f"max_output_tokens={max_output_tokens}, "
            f"text_length={len(text)}"
        )

    return exceeds
