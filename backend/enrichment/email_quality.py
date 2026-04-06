"""
Email quality analysis and scoring.

Classifies emails found via enrichment into categories and scores
them for outbound outreach effectiveness.
"""
from __future__ import annotations

import re
from typing import Optional


# Generic prefixes that usually go to shared inboxes
GENERIC_PREFIXES = {
    "info", "contact", "hello", "hi", "support", "help", "admin",
    "office", "reception", "enquiries", "enquiry", "inquiry",
    "general", "mail", "email", "team", "staff", "service",
    "customerservice", "customer-service", "feedback", "noreply",
    "no-reply", "donotreply", "do-not-reply", "webmaster",
    "postmaster", "abuse", "security", "privacy",
}

# Role-based prefixes — better than generic, but still not personal
ROLE_PREFIXES = {
    "sales", "marketing", "billing", "accounts", "accounting",
    "hr", "jobs", "careers", "hiring", "recruiting", "recruitment",
    "press", "media", "pr", "partnerships", "legal",
    "operations", "ops", "tech", "it", "dev", "engineering",
    "ceo", "cto", "cfo", "coo", "founder", "owner", "director",
    "manager", "president", "vp",
}

# Executive/owner prefixes — highest value
EXECUTIVE_PREFIXES = {
    "ceo", "cto", "cfo", "coo", "founder", "owner", "director",
    "president", "vp", "partner", "principal", "managing",
}


def classify_email(email: str) -> dict:
    """
    Classify a single email address for outreach quality.

    Returns:
        {
            "email": "drsmith@smiledental.com",
            "type": "personal",  # personal, executive, role, generic, unknown
            "outreach_score": 8,  # 1-10
            "prefix": "drsmith",
            "domain": "smiledental.com",
            "is_free_provider": False,
            "recommendation": "Good for outreach — likely the owner/dentist"
        }
    """
    if not email or "@" not in email:
        return {"email": email, "type": "invalid", "outreach_score": 0,
                "recommendation": "Invalid email"}

    email = email.lower().strip()
    prefix, domain = email.rsplit("@", 1)
    prefix_clean = prefix.replace(".", "").replace("-", "").replace("_", "")

    is_free = domain in FREE_PROVIDERS

    # Classify
    if prefix_clean in GENERIC_PREFIXES or prefix in GENERIC_PREFIXES:
        return {
            "email": email,
            "type": "generic",
            "outreach_score": 2,
            "prefix": prefix,
            "domain": domain,
            "is_free_provider": is_free,
            "recommendation": "Generic inbox — low response rate. Use only if no better option.",
        }

    if prefix_clean in EXECUTIVE_PREFIXES:
        return {
            "email": email,
            "type": "executive",
            "outreach_score": 9,
            "prefix": prefix,
            "domain": domain,
            "is_free_provider": is_free,
            "recommendation": "Executive/owner email — high value for outreach.",
        }

    if prefix_clean in ROLE_PREFIXES:
        score = 5
        rec = "Role-based email — may reach the right department."
        if prefix_clean in ("sales", "marketing"):
            score = 4
            rec = "Sales/marketing inbox — they get pitched all day. Personalize heavily."
        elif prefix_clean in ("billing", "accounts"):
            score = 3
            rec = "Billing email — not ideal for cold outreach."
        return {
            "email": email,
            "type": "role",
            "outreach_score": score,
            "prefix": prefix,
            "domain": domain,
            "is_free_provider": is_free,
            "recommendation": rec,
        }

    # Check if it looks like a personal name (has letters, not just numbers)
    if re.match(r'^[a-z]+\.?[a-z]*$', prefix_clean) and len(prefix_clean) > 2:
        score = 8
        rec = "Likely personal email — good for outreach."
        if is_free:
            score = 6
            rec = "Personal email on free provider (Gmail, etc.) — may be the owner's personal email."
        return {
            "email": email,
            "type": "personal",
            "outreach_score": score,
            "prefix": prefix,
            "domain": domain,
            "is_free_provider": is_free,
            "recommendation": rec,
        }

    # First initial + last name pattern (e.g., jsmith@)
    if re.match(r'^[a-z]\.[a-z]+$|^[a-z][a-z]{2,}$', prefix):
        return {
            "email": email,
            "type": "personal",
            "outreach_score": 7,
            "prefix": prefix,
            "domain": domain,
            "is_free_provider": is_free,
            "recommendation": "Looks like a personal name email — good for outreach.",
        }

    return {
        "email": email,
        "type": "unknown",
        "outreach_score": 4,
        "prefix": prefix,
        "domain": domain,
        "is_free_provider": is_free,
        "recommendation": "Could not determine email type — test with a personalized message.",
    }


def analyze_emails(emails: list[str]) -> dict:
    """
    Analyze a list of emails and return the best one for outreach.

    Returns:
        {
            "all_emails": [{"email": ..., "type": ..., "outreach_score": ...}, ...],
            "best_email": "drsmith@smiledental.com",
            "best_score": 8,
            "best_type": "personal",
            "total_emails": 3,
            "has_personal": True,
            "has_executive": False,
            "recommendation": "Use drsmith@smiledental.com — likely the owner"
        }
    """
    if not emails:
        return {
            "all_emails": [],
            "best_email": None,
            "best_score": 0,
            "best_type": None,
            "total_emails": 0,
            "has_personal": False,
            "has_executive": False,
            "recommendation": "No emails found. Try cold calling.",
        }

    analyzed = [classify_email(e) for e in emails if e and "@" in str(e)]
    if not analyzed:
        return {
            "all_emails": [],
            "best_email": None,
            "best_score": 0,
            "best_type": None,
            "total_emails": 0,
            "has_personal": False,
            "has_executive": False,
            "recommendation": "No valid emails found. Try cold calling.",
        }

    # Sort by outreach score descending
    analyzed.sort(key=lambda x: x["outreach_score"], reverse=True)
    best = analyzed[0]

    return {
        "all_emails": analyzed,
        "best_email": best["email"],
        "best_score": best["outreach_score"],
        "best_type": best["type"],
        "total_emails": len(analyzed),
        "has_personal": any(e["type"] == "personal" for e in analyzed),
        "has_executive": any(e["type"] == "executive" for e in analyzed),
        "recommendation": best["recommendation"],
    }


# Common free email providers
FREE_PROVIDERS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "mail.com", "protonmail.com", "zoho.com", "yandex.com",
    "gmx.com", "live.com", "msn.com", "me.com", "inbox.com",
    "fastmail.com", "tutanota.com", "pm.me", "proton.me",
}
