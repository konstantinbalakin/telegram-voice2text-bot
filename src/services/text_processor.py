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

    async def adjust_length(
        self,
        current_text: str,
        direction: str,
        current_level: str,
        mode: str = "structured",
    ) -> str:
        """
        Adjust text length (make shorter or longer).

        Phase 3: Incremental generation approach - shorter/longer variants
        are generated from the current level, not from default.

        Args:
            current_text: Current text to adjust
            direction: "shorter" or "longer"
            current_level: Current length level (shorter/short/default/long/longer)
            mode: Text mode (structured or summary)

        Returns:
            Text adjusted to requested length

        Raises:
            ValueError: If direction is invalid
            LLMError: If adjustment fails
        """
        if direction not in ["shorter", "longer"]:
            raise ValueError(f"Invalid direction: {direction}. Must be 'shorter' or 'longer'")

        # Load appropriate prompt
        if direction == "shorter":
            try:
                prompt_template = load_prompt("length_shorter")
            except (FileNotFoundError, IOError) as e:
                logger.warning(f"Failed to load length_shorter prompt: {e}, using fallback")
                prompt_template = """Твоя задача: сократить текст примерно на 20%, сохраняя ключевую информацию.

Текущий текст ({mode}):
{text}

Требования:
1. Убрать менее важные детали и повторы
2. Сохранить основной смысл и ключевые моменты
3. Сократить примерно на 20% по длине
4. Сохранить структуру (абзацы, списки если есть)
5. НЕ добавлять ничего нового
6. Сохранить стиль и тон оригинала

Верни ТОЛЬКО сокращённый текст, без пояснений."""
        else:  # longer
            try:
                prompt_template = load_prompt("length_longer")
            except (FileNotFoundError, IOError) as e:
                logger.warning(f"Failed to load length_longer prompt: {e}, using fallback")
                prompt_template = """Твоя задача: расширить текст примерно на 20%, добавляя детали.

Текущий текст ({mode}):
{text}

Требования:
1. Развернуть ключевые мысли подробнее
2. Добавить уточнения и контекст где уместно
3. Увеличить примерно на 20% по длине
4. Сохранить исходный смысл и логику
5. НЕ выдумывать новые факты
6. Сохранить структуру и стиль

Верни ТОЛЬКО расширенный текст, без пояснений."""

        prompt = prompt_template.format(mode=mode, text=current_text)
        logger.info(
            f"Adjusting text length: {direction} from {current_level} "
            f"({len(current_text)} chars)..."
        )

        try:
            adjusted_text = await self._refine_with_custom_prompt(current_text, prompt)
            logger.info(
                f"Length adjusted: {len(current_text)} → {len(adjusted_text)} chars "
                f"(direction={direction})"
            )
            return adjusted_text

        except LLMError as e:
            logger.error(f"Failed to adjust text length: {e}")
            # Fallback: return original text
            logger.warning("Falling back to original text")
            return current_text

    async def make_shorter(
        self, current_text: str, current_level: str, mode: str = "structured"
    ) -> str:
        """
        Make text shorter (convenience wrapper).

        Args:
            current_text: Current text
            current_level: Current length level
            mode: Text mode

        Returns:
            Shortened text
        """
        return await self.adjust_length(current_text, "shorter", current_level, mode)

    async def make_longer(
        self, current_text: str, current_level: str, mode: str = "structured"
    ) -> str:
        """
        Make text longer (convenience wrapper).

        Args:
            current_text: Current text
            current_level: Current length level
            mode: Text mode

        Returns:
            Lengthened text
        """
        return await self.adjust_length(current_text, "longer", current_level, mode)

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
