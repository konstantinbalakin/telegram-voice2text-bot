"""Text chunking for processing long texts in parts."""

import logging
import re

logger = logging.getLogger(__name__)

# Sentence boundary pattern: split after . ! ? followed by whitespace
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    """
    Split text into chunks on sentence boundaries.

    Each chunk tries to stay within max_chars, splitting at sentence boundaries
    (., !, ?). If a single sentence exceeds max_chars, it becomes its own chunk.

    Args:
        text: Text to split
        max_chars: Maximum characters per chunk (soft limit)

    Returns:
        List of text chunks
    """
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    # Split into sentences
    sentences = SENTENCE_BOUNDARY.split(text)

    chunks: list[str] = []
    current_chunk = ""

    for sentence in sentences:
        # If adding this sentence would exceed the limit
        if current_chunk and len(current_chunk) + len(sentence) + 1 > max_chars:
            chunks.append(current_chunk)
            current_chunk = sentence
        else:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)

    logger.info(
        f"Split text into {len(chunks)} chunks: "
        f"total_chars={len(text)}, max_chars={max_chars}, "
        f"chunk_sizes={[len(c) for c in chunks]}"
    )

    return chunks


def merge_processed_chunks(chunks: list[str]) -> str:
    """
    Merge processed chunks back into a single text.

    Joins chunks with double newlines for visual separation.

    Args:
        chunks: List of processed text chunks

    Returns:
        Merged text
    """
    if not chunks:
        return ""

    return "\n\n".join(chunk.strip() for chunk in chunks)
