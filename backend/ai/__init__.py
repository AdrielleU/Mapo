"""
AI features for Mapo — lead scoring and review analysis.

Usage::

    from backend.ai import get_llm_client
    client = get_llm_client()
    # client is an AnthropicClient or OpenAIClient wrapper
"""
import logging

from backend.config import config

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper around an LLM provider so callers don't import SDKs directly."""

    def __init__(self, provider: str, api_key: str, model: str):
        self.provider = provider
        self.api_key = api_key
        self.model = model

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request and return the assistant's text."""
        if self.provider == "anthropic":
            return self._chat_anthropic(system_prompt, user_prompt)
        elif self.provider == "openai":
            return self._chat_openai(system_prompt, user_prompt)
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider!r}")

    # ------------------------------------------------------------------
    # Provider-specific implementations (lazy imports)
    # ------------------------------------------------------------------

    def _chat_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        try:
            import anthropic  # noqa: F811
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for Anthropic AI features. "
                "Install it with: pip install anthropic"
            )

        client = anthropic.Anthropic(api_key=self.api_key)
        model = self.model or "claude-sonnet-4-20250514"

        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    def _chat_openai(self, system_prompt: str, user_prompt: str) -> str:
        try:
            import openai  # noqa: F811
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for OpenAI AI features. "
                "Install it with: pip install openai"
            )

        client = openai.OpenAI(api_key=self.api_key)
        model = self.model or "gpt-4o"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1024,
        )
        return response.choices[0].message.content


def get_llm_client() -> LLMClient:
    """
    Factory that reads ``backend.config.config.ai`` and returns the appropriate
    :class:`LLMClient` wrapper.

    Raises:
        RuntimeError: If AI features are disabled or no API key is configured.
    """
    ai_cfg = config.ai

    if not ai_cfg.enabled:
        raise RuntimeError(
            "AI features are disabled. Set ai.enabled=true in mapo.yaml "
            "or export MAPO_AI_API_KEY to enable them."
        )

    if not ai_cfg.api_key:
        raise RuntimeError(
            "No AI API key configured. Set ai.api_key in mapo.yaml "
            "or export MAPO_AI_API_KEY."
        )

    logger.info("Initializing LLM client (provider=%s)", ai_cfg.provider)
    return LLMClient(
        provider=ai_cfg.provider,
        api_key=ai_cfg.api_key,
        model=ai_cfg.model,
    )
