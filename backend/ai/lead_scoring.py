"""
AI-powered lead scoring for scraped places.

Sends place data to an LLM and returns a structured lead assessment
including a numeric score, pitch summary, and suggested approach.
"""
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Rate-limiting: minimum seconds between API calls
_MIN_CALL_INTERVAL = 1.0
_last_call_time: float = 0.0


SYSTEM_PROMPT = """\
You are a B2B lead qualification expert. Analyze the business data provided
and return a JSON object with exactly these keys:

- "lead_score": integer 1-10 (10 = best lead)
- "pitch_summary": a 1-2 sentence tailored pitch for this business
- "suggested_approach": one of "cold_call", "cold_email", "linkedin", "in_person", "skip"
- "reasoning": brief explanation of why you scored it this way

Return ONLY valid JSON, no markdown fences or extra text.
"""


def _build_user_prompt(place: dict, product_description: str = "") -> str:
    """Build the user prompt from place data and optional product description."""
    parts = ["Analyze this business as a potential B2B lead:\n"]

    field_map = {
        "name": "Business Name",
        "category": "Category",
        "rating": "Rating",
        "reviews": "Review Count",
        "website": "Website",
        "phone": "Phone",
        "address": "Address",
        "city": "City",
        "description": "Description",
    }

    for key, label in field_map.items():
        value = place.get(key)
        if value:
            parts.append(f"- {label}: {value}")

    if product_description:
        parts.append(f"\nProduct/Service being sold: {product_description}")
        parts.append("Tailor the pitch specifically for this product/service.")

    return "\n".join(parts)


def score_lead(
    place: dict,
    product_description: str = "",
) -> Optional[dict]:
    """
    Score a business place as a potential lead using an LLM.

    Args:
        place: Dict with place data (name, category, reviews, rating, website, etc.)
        product_description: Optional description of the product being pitched.
                             When provided the LLM tailors the pitch to this product.

    Returns:
        A dict with keys ``lead_score``, ``pitch_summary``,
        ``suggested_approach``, and ``reasoning``; or ``None`` on failure.
    """
    global _last_call_time

    # Lazy import to avoid circular dependency and allow graceful failure
    try:
        from backend.ai import get_llm_client
    except ImportError:
        logger.error("AI module not available")
        return None

    try:
        client = get_llm_client()
    except RuntimeError as exc:
        logger.warning("Cannot score lead — AI disabled: %s", exc)
        return None

    user_prompt = _build_user_prompt(place, product_description)

    # Rate limiting
    elapsed = time.monotonic() - _last_call_time
    if elapsed < _MIN_CALL_INTERVAL:
        time.sleep(_MIN_CALL_INTERVAL - elapsed)

    try:
        _last_call_time = time.monotonic()
        raw = client.chat(SYSTEM_PROMPT, user_prompt)

        # Strip markdown fences if the model wraps them anyway
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()

        result = json.loads(text)

        # Validate expected keys
        required = {"lead_score", "pitch_summary", "suggested_approach", "reasoning"}
        if not required.issubset(result.keys()):
            logger.warning("LLM response missing keys: %s", required - result.keys())
            return None

        # Clamp lead_score to 1-10
        result["lead_score"] = max(1, min(10, int(result["lead_score"])))

        return result

    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM response as JSON: %s", exc)
        return None
    except Exception as exc:
        logger.error("Lead scoring API error: %s", exc)
        return None
