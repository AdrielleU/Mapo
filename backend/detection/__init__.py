"""Detection features for Mapo — scans HTML for tech stack, ad pixels, contact forms, and website quality."""

from backend.detection.techstack import detect_tech_stack
from backend.detection.adpixels import detect_ad_pixels
from backend.detection.contactform import detect_contact_form
from backend.detection.website_analysis import analyze_website, score_website


def detect_all(html: str, url: str = "") -> dict:
    """Run all detectors on the given HTML and return combined results."""
    tech = detect_tech_stack(html)
    analysis = analyze_website(html, url)
    analysis["website_quality_score"] = score_website(analysis)

    return {
        "tech_stack": tech,
        "ad_pixels": detect_ad_pixels(html),
        "contact_form": detect_contact_form(html),
        "website_analysis": analysis,
    }


__all__ = [
    "detect_all",
    "detect_tech_stack",
    "detect_ad_pixels",
    "detect_contact_form",
    "analyze_website",
    "score_website",
]
