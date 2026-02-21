"""LLM service for text refinement."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    """Result from LLM text refinement."""

    text: str
    truncated: bool = False


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def refine_text(self, text: str, prompt: str) -> LLMResult:
        """
        Refine transcribed text.

        Args:
            text: Draft transcription text
            prompt: System prompt for refinement

        Returns:
            LLMResult with refined text and truncation info

        Raises:
            LLMError: If refinement fails
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Cleanup resources."""
        pass


class LLMError(Exception):
    """Base exception for LLM errors."""

    pass


class LLMTimeoutError(LLMError):
    """LLM request timeout."""

    pass


class LLMAPIError(LLMError):
    """LLM API error."""

    pass


class DeepSeekProvider(LLMProvider):
    """DeepSeek V3 provider for text refinement."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout: int = 30,
        max_tokens: int = 4000,
    ):
        """
        Initialize DeepSeek provider.

        Args:
            api_key: DeepSeek API key
            model: Model name (e.g., deepseek-chat)
            base_url: API base URL
            timeout: Request timeout in seconds
            max_tokens: Maximum tokens for response
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def refine_text(self, text: str, prompt: str) -> LLMResult:
        """
        Refine text using DeepSeek API.

        Args:
            text: Draft text to refine
            prompt: System prompt

        Returns:
            LLMResult with refined text and truncation flag

        Raises:
            LLMTimeoutError: Request timeout
            LLMAPIError: API error
        """
        if not text or not text.strip():
            logger.debug("refine_text: empty text, returning as-is")
            return LLMResult(text=text)

        api_key_masked = self.api_key[:4] + "..." if self.api_key else "None"
        logger.debug(
            f"refine_text: model={self.model}, text_length={len(text)}, "
            f"prompt_length={len(prompt)}, api_key={api_key_masked}"
        )
        logger.debug(f"[LLM REQUEST] system_prompt:\n{prompt}")
        logger.debug(f"[LLM REQUEST] user_text:\n{text}")

        try:
            logger.debug(f"Sending request to {self.base_url}/v1/chat/completions")
            response = await self.client.post(
                "/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.3,  # Low temperature for corrections
                    "max_tokens": self.max_tokens,
                },
            )

            response.raise_for_status()
            data = response.json()

            refined: str = data["choices"][0]["message"]["content"]
            finish_reason = data["choices"][0].get("finish_reason", "stop")
            truncated = finish_reason == "length"

            # Log token usage
            usage = data.get("usage", {})
            logger.debug(
                f"DeepSeek response: refined_length={len(refined)}, "
                f"prompt_tokens={usage.get('prompt_tokens', 0)}, "
                f"completion_tokens={usage.get('completion_tokens', 0)}, "
                f"total_tokens={usage.get('total_tokens', 0)}"
            )
            logger.debug(f"[LLM RESPONSE] finish_reason={finish_reason}, text:\n{refined}")
            logger.info(
                f"DeepSeek refinement: "
                f"input={usage.get('prompt_tokens', 0)} tokens, "
                f"output={usage.get('completion_tokens', 0)} tokens, "
                f"total={usage.get('total_tokens', 0)} tokens"
            )

            if truncated:
                logger.warning(
                    f"DeepSeek output truncated (finish_reason=length): "
                    f"text_length={len(text)}, "
                    f"output_tokens={usage.get('completion_tokens', 0)}, "
                    f"max_tokens={self.max_tokens}, "
                    f"model={self.model}"
                )

            return LLMResult(text=refined.strip(), truncated=truncated)

        except httpx.TimeoutException as e:
            logger.error(f"DeepSeek timeout: {e}")
            raise LLMTimeoutError(f"DeepSeek request timeout after {self.timeout}s") from e

        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek API error: {e.response.status_code} - {e.response.text}")
            raise LLMAPIError(f"DeepSeek API error: {e.response.status_code}") from e

        except Exception as e:
            logger.error(f"DeepSeek unexpected error: {e}")
            raise LLMAPIError(f"DeepSeek error: {e}") from e

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


class LLMFactory:
    """Factory for creating LLM providers."""

    @staticmethod
    def create_provider(settings: Settings) -> Optional[LLMProvider]:
        """
        Create LLM provider from settings.

        Args:
            settings: Application settings

        Returns:
            LLM provider instance or None if disabled

        Raises:
            ValueError: Unknown provider
        """
        if not settings.llm_refinement_enabled:
            logger.info("LLM refinement disabled")
            return None

        if not settings.llm_api_key:
            logger.warning("LLM refinement enabled but no API key provided")
            return None

        provider_name = settings.llm_provider.lower()

        if provider_name == "deepseek":
            # Use reasoner-specific max_tokens for deepseek-reasoner model
            if settings.llm_model == "deepseek-reasoner":
                max_tokens = settings.llm_max_tokens_reasoner
            else:
                max_tokens = settings.llm_max_tokens

            logger.info(
                f"Creating DeepSeek provider: model={settings.llm_model}, max_tokens={max_tokens}"
            )
            return DeepSeekProvider(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout,
                max_tokens=max_tokens,
            )

        # Future providers: openai, gigachat
        raise ValueError(f"Unknown LLM provider: {provider_name}")


class LLMService:
    """High-level LLM service for text refinement."""

    def __init__(self, provider: Optional[LLMProvider], prompt: str):
        """
        Initialize LLM service.

        Args:
            provider: LLM provider (None = disabled)
            prompt: System prompt for refinement
        """
        self.provider = provider
        self.prompt = prompt

    async def refine_transcription(self, draft_text: str) -> str:
        """
        Refine transcribed text.

        Args:
            draft_text: Draft transcription

        Returns:
            Refined text (or draft if refinement disabled/fails)
        """
        if not self.provider:
            logger.debug("LLM refinement disabled, returning draft")
            return draft_text

        try:
            logger.debug(f"refine_transcription: draft_length={len(draft_text)}")
            logger.info(f"Refining text ({len(draft_text)} chars)...")
            result = await self.provider.refine_text(draft_text, self.prompt)
            logger.debug(f"Refinement result: refined_length={len(result.text)}")
            logger.info("Text refinement successful")
            return result.text

        except LLMTimeoutError:
            logger.warning("LLM timeout, using draft as final")
            return draft_text

        except LLMAPIError as e:
            logger.error(f"LLM API error: {e}, using draft as final")
            return draft_text

        except Exception as e:
            logger.error(f"Unexpected LLM error: {e}, using draft as final")
            return draft_text

    async def close(self) -> None:
        """Cleanup resources."""
        if self.provider:
            await self.provider.close()

    async def initialize(self) -> None:
        """Initialize the service (no-op, ready after __init__)."""
        pass

    async def shutdown(self) -> None:
        """Shutdown the service and cleanup resources."""
        await self.close()

    def is_initialized(self) -> bool:
        """Check if the service is initialized and ready."""
        return True
