"""Text processing service for interactive transcription modes."""

import logging

from src.services.llm_service import LLMService, LLMError
from src.services.prompt_loader import load_prompt
from src.utils.markdown_utils import sanitize_markdown

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

    async def create_structured(
        self, original_text: str, length_level: str = "default", emoji_level: int = 0
    ) -> str:
        """
        Structure raw transcription text.

        Adds proper punctuation, paragraphs, and formatting while preserving
        all content and meaning.

        Args:
            original_text: Raw transcription text
            length_level: Length level (Phase 3 - not yet implemented)
            emoji_level: Emoji level (0=none, 1=few, 2=moderate, 3=many)

        Returns:
            Structured text with proper formatting

        Raises:
            ValueError: If length_level is not 'default' (Phase 3 feature)
        """
        if length_level != "default":
            raise NotImplementedError(f"Length variations not yet implemented. Got: {length_level}")

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
9. {emoji_instruction}

Верни ТОЛЬКО исправленный текст, без пояснений и комментариев."""

        # Modify prompt based on emoji_level
        if emoji_level == 0:
            emoji_instruction = "НЕ используй эмодзи"
        elif emoji_level == 1:
            emoji_instruction = (
                "Добавь немного эмодзи в тему, но чтобы не перегружало. "
                "И не используй несколько эмодзи подряд"
            )
        elif emoji_level == 2:
            emoji_instruction = "Добавь эмодзи в тему умеренно (1-2 на абзац)"
        elif emoji_level == 3:
            emoji_instruction = "Добавь эмодзи активно для выразительности"
        else:
            # Default to level 1 for unknown values
            emoji_instruction = (
                "Добавь немного эмодзи в тему, но чтобы не перегружало. "
                "И не используй несколько эмодзи подряд"
            )
            logger.warning(f"Unknown emoji_level: {emoji_level}, using default (1)")

        prompt = prompt_template.format(text=original_text, emoji_instruction=emoji_instruction)
        logger.info(
            f"Creating structured text ({len(original_text)} chars, emoji_level={emoji_level})..."
        )

        try:
            # Use custom prompt for structuring
            structured_text = await self._refine_with_custom_prompt(original_text, prompt)

            # Sanitize to remove any HTML tags LLM may have inserted
            structured_text = sanitize_markdown(structured_text)

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

            # Sanitize markdown formatting
            adjusted_text = sanitize_markdown(adjusted_text)

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

    async def summarize_text(self, original_text: str, length_level: str = "default") -> str:
        """
        Create text summary ("What's the text about?").

        Phase 4: Generate concise summary with main topic and key points.

        Args:
            original_text: Original transcription text
            length_level: Length level (default/short/shorter/long/longer)

        Returns:
            Summary text with topic and bullet points

        Raises:
            LLMError: If summarization fails
        """
        # Load prompt from file
        try:
            prompt_template = load_prompt("summary")
        except (FileNotFoundError, IOError) as e:
            logger.error(f"Failed to load summary prompt: {e}")
            # Fallback to inline prompt
            prompt_template = """Твоя задача: создать краткое резюме текста, отвечая на вопрос "О чем этот текст?"

Исходный текст:
{text}

Требования:
1. Выделить главную тему/идею одним предложением
2. Перечислить ключевые моменты (3-5 пунктов буллетами)
3. Объём резюме: примерно 25-30% от оригинала
4. Структура:
   - Первая строка: "О чем текст: <краткое описание темы>"
   - Пустая строка
   - "Ключевые моменты:"
   - Буллеты (•) с основными пунктами
5. Сохранить важные детали и факты
6. НЕ выдумывать информацию
7. НЕ добавлять ничего от себя

Формат ответа:
О чем текст: <краткое описание>

Ключевые моменты:
• <пункт 1>
• <пункт 2>
• <пункт 3>

Верни ТОЛЬКО резюме в таком формате, без пояснений и комментариев."""

        prompt = prompt_template.format(text=original_text)
        logger.info(f"Creating summary text ({len(original_text)} chars)...")

        try:
            # Use custom prompt for summarization
            summary_text = await self._refine_with_custom_prompt(original_text, prompt)

            # Sanitize markdown formatting
            summary_text = sanitize_markdown(summary_text)

            logger.info(f"Summary created: {len(original_text)} → {len(summary_text)} chars")

            # If length level is not default, apply length adjustment
            if length_level != "default":
                logger.info(f"Adjusting summary to length level: {length_level}")
                # Determine direction based on level
                if length_level in ["short", "shorter"]:
                    # Make shorter from default
                    if length_level == "short":
                        summary_text = await self.adjust_length(
                            summary_text, "shorter", "default", mode="summary"
                        )
                    else:  # shorter
                        temp = await self.adjust_length(
                            summary_text, "shorter", "default", mode="summary"
                        )
                        summary_text = await self.adjust_length(
                            temp, "shorter", "short", mode="summary"
                        )
                else:  # long or longer
                    # Make longer from default
                    if length_level == "long":
                        summary_text = await self.adjust_length(
                            summary_text, "longer", "default", mode="summary"
                        )
                    else:  # longer
                        temp = await self.adjust_length(
                            summary_text, "longer", "default", mode="summary"
                        )
                        summary_text = await self.adjust_length(
                            temp, "longer", "long", mode="summary"
                        )

            return summary_text

        except LLMError as e:
            logger.error(f"Failed to create summary: {e}")
            # Fallback: return original text
            logger.warning("Falling back to original text")
            return original_text

    async def create_magic(self, original_text: str) -> str:
        """
        Create publication-ready text from transcription (Magic mode).

        Transforms raw transcription into warm, readable post for Telegram
        while preserving author's voice, tone, and authenticity.

        Args:
            original_text: Raw transcription text

        Returns:
            Publication-ready text with formatting and emojis

        Raises:
            LLMError: If processing fails
        """
        # Load prompt from file
        try:
            prompt_template = load_prompt("magic")
        except (FileNotFoundError, IOError) as e:
            logger.error(f"Failed to load magic prompt: {e}")
            # Fallback to inline prompt (shortened version)
            prompt_template = """Преобразуй диктофонную транскрипцию в готовый текст для публикации в Telegram.

Исходный текст:
{text}

Требования:
1. Сохрани смысл, интонацию и стиль автора
2. Сделай связный, читабельный текст
3. Добавь эмодзи умеренно (по смыслу)
4. Используй Markdown-форматирование если уместно: **жирный**, *курсив*, `код`
5. НЕ используй HTML-теги
6. Для списков используй текст: • или 1.
7. Разговорный, живой тон (без канцелярщины)

Верни ТОЛЬКО готовый текст, без пояснений."""

        prompt = prompt_template.format(text=original_text)
        logger.info(f"Creating magic text ({len(original_text)} chars)...")

        try:
            # Use custom prompt for magic transformation
            magic_text = await self._refine_with_custom_prompt(original_text, prompt)

            # Sanitize markdown formatting
            magic_text = sanitize_markdown(magic_text)

            logger.info(f"Magic text created: {len(original_text)} → {len(magic_text)} chars")
            return magic_text

        except LLMError as e:
            logger.error(f"Failed to create magic text: {e}")
            # Fallback: return original text
            logger.warning("Falling back to original text")
            return original_text

    async def add_emojis(self, text: str, emoji_level: int, current_level: int = 0) -> str:
        """
        Add emojis to text based on level.

        Phase 5: Add appropriate emojis to enhance text readability and emotional tone.
        Uses relative instructions (add more/less) for smoother transitions.

        Args:
            text: Text to add emojis to (can be base text or text with existing emojis)
            emoji_level: Target emoji level (0=none, 1=few, 2=moderate, 3=many)
            current_level: Current emoji level (for incremental adjustments)

        Returns:
            Text with adjusted emoji count

        Raises:
            ValueError: If emoji_level is invalid
            LLMError: If emoji addition fails
        """
        if emoji_level not in [0, 1, 2, 3]:
            raise ValueError(f"Invalid emoji_level: {emoji_level}. Must be 0, 1, 2, or 3")

        # Level 0 = remove all emojis using LLM
        if emoji_level == 0:
            # Load remove emoji prompt
            try:
                prompt_template = load_prompt("emoji_remove")
            except (FileNotFoundError, IOError) as e:
                logger.warning(f"Failed to load emoji_remove prompt: {e}, using fallback")
                # Fallback inline prompt
                prompt_template = """Убери ВСЕ эмодзи из текста, сохраняя только чистый текст без символов.

Исходный текст:
{text}

Верни ТОЛЬКО текст без эмодзи, без пояснений и комментариев."""

            prompt = prompt_template.format(text=text)
            logger.info(f"Removing emojis from text: {len(text)} chars...")

            try:
                result = await self._refine_with_custom_prompt(text, prompt)
                logger.info(f"Emojis removed: {len(text)} → {len(result)} chars")
                return result
            except Exception as e:
                logger.error(f"Failed to remove emojis: {e}")
                raise LLMError(f"Failed to remove emojis: {e}") from e

        # Determine instruction based on level
        instructions = {
            1: "Добавь немного эмодзи в текст, чтобы было уместно и не отвлекало.",
            2: "Добавь немного эмодзи в текст, чтобы смотрелось не слишком избыточно и пёстро",
            3: "Добавь щедрое количество эмодзи в текст",
        }

        instruction = instructions[emoji_level]

        # Load prompt from file
        try:
            prompt_template = load_prompt("emoji")
        except (FileNotFoundError, IOError) as e:
            logger.warning(f"Failed to load emoji prompt: {e}, using fallback")
            # Fallback inline prompt
            prompt_template = """{instruction}

Текст:
{text}

Требования:
1. Эмодзи должны подчеркивать смысл
2. Размещать в начале абзацев или перед важными фразами
3. Использовать разнообразные эмодзи
4. НЕ менять сам текст
5. Распределяй эмодзи равномерно по всему тексту

Верни текст с эмодзи."""

        prompt = prompt_template.format(text=text, instruction=instruction)
        logger.info(
            f"Adding emojis to text: level={emoji_level} (from {current_level}), "
            f"{len(text)} chars..."
        )

        try:
            text_with_emojis = await self._refine_with_custom_prompt(text, prompt)

            # Sanitize markdown formatting
            text_with_emojis = sanitize_markdown(text_with_emojis)

            logger.info(
                f"Emojis adjusted: {len(text)} → {len(text_with_emojis)} chars "
                f"(level={emoji_level})"
            )
            return text_with_emojis

        except LLMError as e:
            logger.error(f"Failed to add emojis: {e}")
            # Fallback: return original text
            logger.warning("Falling back to original text")
            return text

    def format_with_timestamps(self, segments: list, base_text: str, mode: str = "original") -> str:
        """
        Add timestamps to text from transcription segments.

        Phase 6: Format segments as [MM:SS] text for better navigation.
        For original/structured modes: each segment gets a timestamp.
        For summary mode: simplified approach with first segment timestamp.

        Args:
            segments: List of TranscriptionSegment objects
            base_text: Base text to add timestamps to (used for summary mode)
            mode: Text mode (original/structured/summary)

        Returns:
            Text with timestamps in format [MM:SS] or [HH:MM:SS]
        """
        if not segments:
            logger.warning("No segments provided for timestamp formatting")
            return base_text

        if mode == "summary":
            # For summary: simplified approach - add first segment timestamp
            return self._format_timestamps_summary(segments, base_text)
        else:
            # For original/structured: format each segment with timestamp
            lines = []
            for seg in segments:
                timestamp = self._format_time(seg.start_time)
                lines.append(f"[{timestamp}] {seg.text}")
            return "\n".join(lines)

    def _format_time(self, seconds: float) -> str:
        """
        Format seconds as MM:SS or HH:MM:SS.

        Args:
            seconds: Time in seconds

        Returns:
            Formatted time string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    def _format_timestamps_summary(self, segments: list, summary_text: str) -> str:
        """
        Format timestamps for summary mode.

        Simplified approach: add timestamp of first segment before summary.
        More sophisticated matching of bullet points to segments would be
        complex and error-prone, so we use this simple heuristic.

        Args:
            segments: List of TranscriptionSegment objects
            summary_text: Summary text

        Returns:
            Summary with timestamp prefix
        """
        if not segments:
            return summary_text

        first_timestamp = self._format_time(segments[0].start_time)
        return f"[{first_timestamp}] {summary_text}"

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
