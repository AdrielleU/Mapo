"""Detect technology stack from raw HTML using simple string / regex matching."""

from __future__ import annotations

import re
from typing import Optional

# Each entry: (technology_name, list_of_signatures, optional_cms_label, optional_framework_label)
_SIGNATURES: list[tuple[str, list[str], Optional[str], Optional[str]]] = [
    # CMS platforms
    ("WordPress",    ["wp-content", "wp-includes"],                     "WordPress",    None),
    ("Shopify",      ["cdn.shopify.com", "Shopify.theme"],              "Shopify",      None),
    ("Wix",          ["wix.com", "X-Wix"],                              "Wix",          None),
    ("Squarespace",  ["squarespace.com", "static.squarespace"],         "Squarespace",  None),
    ("Webflow",      ["webflow.com"],                                   "Webflow",      None),
    ("Ghost",        ["ghost.org"],                                     "Ghost",        None),
    ("Drupal",       ["drupal.js", "Drupal.settings"],                  "Drupal",       None),
    ("Joomla",       ["/media/jui/"],                                   "Joomla",       None),
    # Frameworks
    ("React",        ["_reactRoot", "__REACT", "react-root"],           None,           "React"),
    ("Next.js",      ["__NEXT_DATA__", "_next/"],                       None,           "Next.js"),
    ("Vue.js",       ["__vue", "Vue.js"],                               None,           "Vue.js"),
    ("Angular",      ["ng-version", "ng-app"],                          None,           "Angular"),
]

# Additional technology signatures that are not CMS or framework
_EXTRA_TECH: list[tuple[str, list[str]]] = [
    ("WooCommerce",     ["woocommerce", "wc-ajax"]),
    ("jQuery",          ["jquery.min.js", "jquery.js"]),
    ("Bootstrap",       ["bootstrap.min.css", "bootstrap.min.js"]),
    ("Tailwind CSS",    ["tailwindcss", "tailwind.min.css"]),
    ("Google Tag Manager", ["googletagmanager.com/gtm.js"]),
]


def detect_tech_stack(html: str) -> dict:
    """Scan *html* for known technology signatures.

    Returns::

        {
            "technologies": ["WordPress", "WooCommerce", ...],
            "cms": "WordPress" | None,
            "framework": "React" | None,
        }
    """
    if not html:
        return {"technologies": [], "cms": None, "framework": None}

    html_lower = html.lower()
    technologies: list[str] = []
    cms: Optional[str] = None
    framework: Optional[str] = None

    for tech_name, signatures, cms_label, fw_label in _SIGNATURES:
        for sig in signatures:
            if sig.lower() in html_lower:
                if tech_name not in technologies:
                    technologies.append(tech_name)
                if cms_label and cms is None:
                    cms = cms_label
                if fw_label and framework is None:
                    framework = fw_label
                break  # one match is enough for this technology

    for tech_name, signatures in _EXTRA_TECH:
        for sig in signatures:
            if sig.lower() in html_lower:
                if tech_name not in technologies:
                    technologies.append(tech_name)
                break

    return {
        "technologies": technologies,
        "cms": cms,
        "framework": framework,
    }
