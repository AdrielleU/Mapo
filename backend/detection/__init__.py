"""Detection features for Mapo — scans HTML for tech stack, ad pixels, and contact forms."""

from backend.detection.techstack import detect_tech_stack
from backend.detection.adpixels import detect_ad_pixels
from backend.detection.contactform import detect_contact_form


def detect_all(html: str) -> dict:
    """Run all detectors on the given HTML and return combined results.

    Returns a dict with keys: ``tech_stack``, ``ad_pixels``, ``contact_form``.
    """
    return {
        "tech_stack": detect_tech_stack(html),
        "ad_pixels": detect_ad_pixels(html),
        "contact_form": detect_contact_form(html),
    }


__all__ = [
    "detect_all",
    "detect_tech_stack",
    "detect_ad_pixels",
    "detect_contact_form",
]
