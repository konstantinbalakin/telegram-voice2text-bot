"""Text processing service for interactive transcription modes."""

import logging

from src.services.llm_service import LLMService, LLMError
from src.services.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


class TextProcessor:
    """Process transcription text using LLM for different modes."""

    def __init__(self, llm_service: LLMService):
        """
        Initialize text processor.

        Args:
            llm_service: LLM service for text processing
        """
        self.llm_service = llm_service

    async def create_structured(self, original_text: str, length_level: str = "default") -> str:
        """
        Structure raw transcription text.

        Adds proper punctuation, paragraphs, and formatting while preserving
        all content and meaning.

        Args:
            original_text: Raw transcription text
            length_level: Length level (Phase 3 - not yet implemented)

        Returns:
            Structured text with proper formatting

        Raises:
            ValueError: If length_level is not 'default' (Phase 3 feature)
        """
        if length_level != "default":
            raise NotImplementedError(
                f"Length variations will be available in Phase 3. Got: {length_level}"
            )

        # Load prompt from file
        try:
            prompt_template = load_prompt("structured")
        except (FileNotFoundError, IOError) as e:
            logger.error(f"Failed to load structured prompt: {e}")
            # Fallback to inline prompt
            prompt_template = """Твоя задача: структурировать текст голосовой транскрипции.

Исходный текст (сырая транскрипция):
{text}

Требования:
1. Исправить грамматические ошибки и опечатки
2. Добавить правильную пунктуацию (точки, запятые, вопросительные/восклицательные знаки)
3. Разбить на абзацы по смыслу (каждая новая мысль - новый абзац)
4. Выделить списки буллетами если уместно (символ •)
5. Сохранить весь смысл и все детали из оригинала
6. НЕ добавлять ничего от себя, только исправления
7. НЕ сокращать текст (это не резюме, а структурирование)
8. Сохранить стиль речи (неформальный/формальный)

Верни ТОЛЬКО исправленный текст, без пояснений и комментариев."""

        prompt = prompt_template.format(text=original_text)
        logger.info(f"Creating structured text ({len(original_text)} chars)...")

        try:
            # Use custom prompt for structuring
            structured_text = await self._refine_with_custom_prompt(original_text, prompt)
            logger.info(
                f"Structured text created: {len(original_text)} → {len(structured_text)} chars"
            )
            return structured_text

        except LLMError as e:
            logger.error(f"Failed to create structured text: {e}")
            # Fallback: return original text
            logger.warning("Falling back to original text")
            return original_text

    async def _refine_with_custom_prompt(self, text: str, prompt: str) -> str:
        """
        Refine text with a custom prompt.

        Args:
            text: Text to refine
            prompt: Custom system prompt

        Returns:
            Refined text

        Raises:
            LLMError: If refinement fails
        """
        if not self.llm_service.provider:
            logger.debug("LLM provider not available, returning original text")
            return text

        # Use the provider directly for custom prompts
        refined = await self.llm_service.provider.refine_text(text, prompt)
        return refined
