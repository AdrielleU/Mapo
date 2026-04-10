"""
AI-powered lead scoring with ICP (Ideal Customer Profile) support.

Sends place data + your ICP definition to an LLM and returns a structured
lead assessment: score, pitch summary, approach, and ICP match reasoning.
"""
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_MIN_CALL_INTERVAL = 1.0
_last_call_time: float = 0.0


SYSTEM_PROMPT = """\
You are a B2B lead qualification expert. Analyze the business data and score it
as a potential lead. If an Ideal Customer Profile (ICP) is provided, score
specifically against that ICP.

Return a JSON object with exactly these keys:

- "lead_score": integer 1-10 (10 = perfect ICP match, best lead)
- "icp_match": one of "strong", "moderate", "weak", "no_match"
- "pitch_summary": a 1-2 sentence tailored pitch for this specific business
- "suggested_approach": one of "cold_call", "cold_email", "linkedin", "in_person", "skip"
- "reasoning": brief explanation of the score and ICP match

Return ONLY valid JSON, no markdown fences or extra text.
"""


def _build_user_prompt(place: dict, product_description: str = "", icp: str = "") -> str:
    """Build the user prompt from place data, product, and ICP."""
    parts = ["Analyze this business as a potential lead:\n"]

    field_map = {
        "name": "Business Name",
        "main_category": "Category",
        "categories": "All Categories",
        "rating": "Rating",
        "reviews": "Review Count",
        "website": "Website",
        "phone": "Phone",
        "address": "Address",
        "description": "Description",
        "is_spending_on_ads": "Spending on Google Ads",
        "can_claim": "Unclaimed Listing",
    }

    for key, label in field_map.items():
        value = place.get(key)
        if value is not None and value != "" and value != []:
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            parts.append(f"- {label}: {value}")

    if icp:
        parts.append(f"\n--- IDEAL CUSTOMER PROFILE (ICP) ---\n{icp}")
        parts.append("Score this business specifically against this ICP.")

    if product_description:
        parts.append(f"\n--- PRODUCT/SERVICE ---\n{product_description}")
        parts.append("Tailor the pitch specifically for this product/service.")

    if not icp and not product_description:
        parts.append("\nNo ICP or product specified. Score as a general B2B lead.")

    return "\n".join(parts)


def score_lead(
    place: dict,
    product_description: str = "",
    icp: str = "",
) -> Optional[dict]:
    """
    Score a business as a potential lead using an LLM.

    Args:
        place: Dict with place data (name, category, reviews, rating, website, etc.)
        product_description: What you're selling ("websites for restaurants")
        icp: Your Ideal Customer Profile definition, e.g.:
             "Small restaurants with 50-200 reviews, 4+ stars, no website,
              in major US cities, spending on Google Ads preferred"

    Returns:
        Dict with lead_score, icp_match, pitch_summary, suggested_approach,
        reasoning. Or None on failure.
    """
    global _last_call_time

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

    user_prompt = _build_user_prompt(place, product_description, icp)

    # Rate limiting
    elapsed = time.monotonic() - _last_call_time
    if elapsed < _MIN_CALL_INTERVAL:
        time.sleep(_MIN_CALL_INTERVAL - elapsed)

    try:
        _last_call_time = time.monotonic()
        raw = client.chat(SYSTEM_PROMPT, user_prompt)

        # Strip markdown fences if model wraps them
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        result = json.loads(text)

        # Validate expected keys
        required = {"lead_score", "pitch_summary", "suggested_approach", "reasoning"}
        if not required.issubset(result.keys()):
            logger.warning("LLM response missing keys: %s", required - result.keys())
            return None

        # Clamp lead_score to 1-10
        result["lead_score"] = max(1, min(10, int(result["lead_score"])))

        # Ensure icp_match exists
        if "icp_match" not in result:
            result["icp_match"] = "unknown"

        return result

    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM response as JSON: %s", exc)
        return None
    except Exception as exc:
        logger.error("Lead scoring API error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Email ranking — picks best email for outreach using business + ICP context
# ---------------------------------------------------------------------------

EMAIL_RANK_SYSTEM_PROMPT = """\
You are evaluating contact emails for B2B cold outreach. Given a business and a
list of emails, rank them by outreach quality.

Consider:
- Domain match: emails on the business's own domain beat Gmail/Yahoo/Outlook
- Decision-maker indicators: names matching owner, founder, CEO, manager
- ICP fit: does this person likely match the ideal customer profile?
- Avoid generics: info@, support@, noreply@, admin@, webmaster@, contact@
- Personal name patterns (firstname.lastname@) suggest a real person

Return a JSON object with exactly these keys:
- "best_email": string (the top-ranked email)
- "best_email_reasoning": brief explanation (1 sentence)
- "ranked_emails": array of {"email": str, "rank": int, "reason": str}, ordered best to worst

Return ONLY valid JSON, no markdown fences.
"""


def rank_emails_with_ai(
    emails: list[str],
    place: dict,
    icp: str = "",
    product_description: str = "",
) -> Optional[dict]:
    """Use LLM to rank emails by outreach value, considering business + ICP context.

    Only useful when 2+ emails exist. Returns None on failure or single-email lists.
    """
    global _last_call_time

    # Filter to valid emails
    valid_emails = [e for e in emails if e and "@" in str(e)]
    if len(valid_emails) < 2:
        return None

    try:
        from backend.ai import get_llm_client
    except ImportError:
        return None

    try:
        client = get_llm_client()
    except RuntimeError:
        return None

    # Build user prompt
    parts = [f"Business: {place.get('name', 'Unknown')}"]
    if place.get("main_category"):
        parts.append(f"Category: {place['main_category']}")
    if place.get("address"):
        parts.append(f"Address: {place['address']}")
    if place.get("website"):
        parts.append(f"Website: {place['website']}")
    if place.get("owner"):
        parts.append(f"Owner: {place['owner']}")

    parts.append("\nEmails to rank:")
    for i, e in enumerate(valid_emails, 1):
        parts.append(f"{i}. {e}")

    if icp:
        parts.append(f"\nIdeal Customer Profile:\n{icp}")
    if product_description:
        parts.append(f"\nProduct/Service:\n{product_description}")

    user_prompt = "\n".join(parts)

    # Rate limiting
    elapsed = time.monotonic() - _last_call_time
    if elapsed < _MIN_CALL_INTERVAL:
        time.sleep(_MIN_CALL_INTERVAL - elapsed)

    try:
        _last_call_time = time.monotonic()
        raw = client.chat(EMAIL_RANK_SYSTEM_PROMPT, user_prompt)

        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        result = json.loads(text)
        if "best_email" not in result:
            return None
        return result

    except json.JSONDecodeError as exc:
        logger.error("Failed to parse email ranking response: %s", exc)
        return None
    except Exception as exc:
        logger.error("Email ranking API error: %s", exc)
        return None
