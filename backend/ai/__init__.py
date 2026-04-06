"""
AI features for Mapo — lead scoring and review analysis.

Supports: Anthropic (Claude), OpenAI (GPT), Google Gemini, vLLM (local/self-hosted).

Usage::

    from backend.ai import get_llm_client
    client = get_llm_client()
    response = client.chat("system prompt", "user prompt")
"""
import logging

from backend.config import config

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper around LLM providers so callers don't import SDKs directly."""

    def __init__(self, provider: str, api_key: str, model: str, base_url: str = ""):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request and return the assistant's text."""
        dispatch = {
            "anthropic": self._chat_anthropic,
            "openai": self._chat_openai,
            "gemini": self._chat_gemini,
            "vllm": self._chat_vllm,
        }
        fn = dispatch.get(self.provider)
        if not fn:
            raise ValueError(f"Unsupported AI provider: {self.provider!r}. Choose from: {list(dispatch.keys())}")
        return fn(system_prompt, user_prompt)

    def _chat_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required. Install: pip install anthropic"
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
            import openai
        except ImportError:
            raise ImportError(
                "The 'openai' package is required. Install: pip install openai"
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

    def _chat_gemini(self, system_prompt: str, user_prompt: str) -> str:
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "The 'google-generativeai' package is required. Install: pip install google-generativeai"
            )
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            model_name=self.model or "gemini-2.0-flash",
            system_instruction=system_prompt,
        )
        response = model.generate_content(user_prompt)
        return response.text

    def _chat_vllm(self, system_prompt: str, user_prompt: str) -> str:
        """Call a vLLM server via its OpenAI-compatible API."""
        try:
            import openai
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for vLLM. Install: pip install openai"
            )
        base_url = self.base_url or "http://localhost:8001/v1"
        client = openai.OpenAI(
            api_key=self.api_key or "not-needed",
            base_url=base_url,
        )
        model = self.model or "default"
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
    """Factory that reads config and returns the appropriate LLM client."""
    ai_cfg = config.ai

    if not ai_cfg.enabled:
        raise RuntimeError(
            "AI features are disabled. Set ai.enabled=true in mapo.yaml "
            "or export MAPO_AI_API_KEY to enable them."
        )

    # vLLM doesn't need an API key
    if ai_cfg.provider != "vllm" and not ai_cfg.api_key:
        raise RuntimeError(
            "No AI API key configured. Set ai.api_key in mapo.yaml "
            "or export MAPO_AI_API_KEY."
        )

    logger.info("Initializing LLM client (provider=%s)", ai_cfg.provider)
    return LLMClient(
        provider=ai_cfg.provider,
        api_key=ai_cfg.api_key,
        model=ai_cfg.model,
        base_url=getattr(ai_cfg, "base_url", ""),
    )
