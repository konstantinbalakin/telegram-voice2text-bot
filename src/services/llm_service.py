"""LLM service for text refinement."""

import logging
from abc import ABC, abstractmethod
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


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def refine_text(self, text: str, prompt: str) -> str:
        """
        Refine transcribed text.

        Args:
            text: Draft transcription text
            prompt: System prompt for refinement

        Returns:
            Refined text

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
    ):
        """
        Initialize DeepSeek provider.

        Args:
            api_key: DeepSeek API key
            model: Model name (e.g., deepseek-chat)
            base_url: API base URL
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
    async def refine_text(self, text: str, prompt: str) -> str:
        """
        Refine text using DeepSeek API.

        Args:
            text: Draft text to refine
            prompt: System prompt

        Returns:
            Refined text

        Raises:
            LLMTimeoutError: Request timeout
            LLMAPIError: API error
        """
        if not text or not text.strip():
            logger.debug("refine_text: empty text, returning as-is")
            return text

        api_key_masked = self.api_key[:8] + "..." if self.api_key else "None"
        logger.debug(
            f"refine_text: model={self.model}, text_length={len(text)}, "
            f"prompt_length={len(prompt)}, api_key={api_key_masked}"
        )

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
                    "max_tokens": 4000,
                },
            )

            response.raise_for_status()
            data = response.json()

            refined: str = data["choices"][0]["message"]["content"]

            # Log token usage
            usage = data.get("usage", {})
            logger.debug(
                f"DeepSeek response: refined_length={len(refined)}, "
                f"prompt_tokens={usage.get('prompt_tokens', 0)}, "
                f"completion_tokens={usage.get('completion_tokens', 0)}, "
                f"total_tokens={usage.get('total_tokens', 0)}"
            )
            logger.info(
                f"DeepSeek refinement: "
                f"input={usage.get('prompt_tokens', 0)} tokens, "
                f"output={usage.get('completion_tokens', 0)} tokens, "
                f"total={usage.get('total_tokens', 0)} tokens"
            )

            return refined.strip()

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
            logger.info("Creating DeepSeek provider")
            return DeepSeekProvider(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout,
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
            refined = await self.provider.refine_text(draft_text, self.prompt)
            logger.debug(f"Refinement result: refined_length={len(refined)}")
            logger.info("Text refinement successful")
            return refined

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
