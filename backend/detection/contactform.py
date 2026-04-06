"""Detect contact forms and form-builder providers in HTML."""

from __future__ import annotations

import re
from typing import Optional

# (provider_name, list_of_signatures)
_FORM_PROVIDERS: list[tuple[str, list[str]]] = [
    ("HubSpot",          ["hs-form", "hbspt.forms", "hs-form-"]),
    ("Typeform",         ["typeform.com"]),
    ("JotForm",          ["jotform.com"]),
    ("Gravity Forms",    ["gform", "gform_wrapper"]),
    ("WPForms",          ["wpforms", "wpforms-form"]),
    ("Contact Form 7",   ["wpcf7", "wpcf7-form"]),
    ("Formspree",        ["formspree.io"]),
    ("Netlify Forms",    ["netlify", "data-netlify"]),
]

# Keywords commonly found inside <form> elements that suggest it is a
# contact / inquiry form rather than, say, a search bar or login form.
_CONTACT_KEYWORDS = re.compile(
    r"(?:contact|message|inquiry|enquiry|get.in.touch|email.*us|send.*message)",
    re.IGNORECASE,
)

# Field-name patterns that indicate contact-style input fields.
_CONTACT_FIELD_NAMES = re.compile(
    r"""name\s*=\s*["'](?:email|message|phone|subject|your[_-]?name|full[_-]?name|contact[_-]?name|company)["']""",
    re.IGNORECASE,
)


def detect_contact_form(html: str) -> dict:
    """Scan *html* for contact forms and known form-builder signatures.

    Returns::

        {
            "has_contact_form": True / False,
            "form_provider": "HubSpot" | None,
        }
    """
    if not html:
        return {"has_contact_form": False, "form_provider": None}

    html_lower = html.lower()

    # 1. Check for known form-builder providers first — their presence is
    #    strong evidence of a contact form.
    detected_provider: Optional[str] = None
    for provider, signatures in _FORM_PROVIDERS:
        for sig in signatures:
            if sig.lower() in html_lower:
                detected_provider = provider
                break
        if detected_provider:
            break

    if detected_provider:
        return {"has_contact_form": True, "form_provider": detected_provider}

    # 2. Look for <form> elements that look like contact forms.
    form_blocks = re.findall(r"<form[\s\S]*?</form>", html, re.IGNORECASE)
    for form in form_blocks:
        # Check for contact keywords in the form block
        if _CONTACT_KEYWORDS.search(form):
            return {"has_contact_form": True, "form_provider": None}
        # Check for multiple contact-related field names
        field_hits = _CONTACT_FIELD_NAMES.findall(form)
        if len(field_hits) >= 2:
            return {"has_contact_form": True, "form_provider": None}

    # 3. Broader heuristic: a form action URL containing "contact" or "mail"
    action_urls = re.findall(r'<form[^>]*action\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
    for url in action_urls:
        if re.search(r"contact|mail|inquiry|enquiry|message", url, re.IGNORECASE):
            return {"has_contact_form": True, "form_provider": None}

    return {"has_contact_form": False, "form_provider": None}
