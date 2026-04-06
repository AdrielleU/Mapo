"""
AI-powered review analysis.

Sends a batch of reviews to an LLM and returns sentiment analysis,
key themes, and a human-readable summary.
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are a customer review analyst. Analyze the provided reviews and return a
JSON object with exactly these keys:

- "sentiment": one of "positive", "negative", "mixed", "neutral"
- "score": float between 0.0 and 1.0 representing overall sentiment (1.0 = very positive)
- "themes": list of up to 8 short theme strings extracted from the reviews
- "summary": a 2-3 sentence summary of the overall customer sentiment

Return ONLY valid JSON, no markdown fences or extra text.
"""


def _build_user_prompt(reviews: list[dict], max_reviews: int) -> str:
    """Build the user prompt from a truncated list of reviews."""
    truncated = reviews[:max_reviews]

    parts = [f"Analyze these {len(truncated)} customer reviews:\n"]
    for i, review in enumerate(truncated, 1):
        text = review.get("review_text", review.get("text", ""))
        rating = review.get("rating", "N/A")
        parts.append(f"Review {i} (rating: {rating}): {text}")

    return "\n".join(parts)


def analyze_reviews(
    reviews: list[dict],
    max_reviews: int = 20,
) -> Optional[dict]:
    """
    Analyze a list of reviews using an LLM.

    Args:
        reviews: List of review dicts, each with at least ``review_text``
                 (or ``text``) and optionally ``rating``.
        max_reviews: Maximum number of reviews to send (controls token usage).

    Returns:
        A dict with keys ``sentiment``, ``score``, ``themes``, and
        ``summary``; or ``None`` on failure.
    """
    if not reviews:
        logger.warning("No reviews to analyze")
        return None

    # Lazy import to avoid circular dependency and allow graceful failure
    try:
        from backend.ai import get_llm_client
    except ImportError:
        logger.error("AI module not available")
        return None

    try:
        client = get_llm_client()
    except RuntimeError as exc:
        logger.warning("Cannot analyze reviews — AI disabled: %s", exc)
        return None

    user_prompt = _build_user_prompt(reviews, max_reviews)

    try:
        raw = client.chat(SYSTEM_PROMPT, user_prompt)

        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()

        result = json.loads(text)

        # Validate expected keys
        required = {"sentiment", "score", "themes", "summary"}
        if not required.issubset(result.keys()):
            logger.warning("LLM response missing keys: %s", required - result.keys())
            return None

        # Clamp score to 0.0-1.0
        result["score"] = max(0.0, min(1.0, float(result["score"])))

        # Ensure themes is a list
        if not isinstance(result["themes"], list):
            result["themes"] = []

        return result

    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM response as JSON: %s", exc)
        return None
    except Exception as exc:
        logger.error("Review analysis API error: %s", exc)
        return None
