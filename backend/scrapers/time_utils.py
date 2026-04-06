"""
Relative date parsing for Google Maps review timestamps.

Converts localized relative date strings (e.g., "2 months ago", "3 semanas atras")
into absolute datetime strings.
"""
from datetime import datetime

import regex as re
from dateutils import relativedelta
from unidecode import unidecode

LANGUAGE_MAPS = {
    "pt-br": {
        "one_regex": r"^uma?",
        "ago_regex": r"\s*atrás$",
        "time_unit": {
            "ano": "years", "anos": "years",
            "mes": "months", "meses": "months",
            "semana": "weeks", "semanas": "weeks",
            "dia": "days", "dias": "days",
            "hora": "hours", "horas": "hours",
            "minuto": "minutes", "minutos": "minutes",
            "segundo": "seconds", "segundos": "seconds",
        },
    },
    "en": {
        "one_regex": r"^a",
        "ago_regex": r"\s*ago$",
        "time_unit": {
            "year": "years", "years": "years",
            "month": "months", "months": "months",
            "week": "weeks", "weeks": "weeks",
            "day": "days", "days": "days",
            "hour": "hours", "hours": "hours",
            "minute": "minutes", "minutes": "minutes",
            "second": "seconds", "seconds": "seconds",
        },
    },
}


def parse_relative_date(relative_date, retrieval_date, hl="en"):
    """
    Convert a localized relative date string to an absolute datetime string.

    Args:
        relative_date: String like "2 months ago"
        retrieval_date: When the review was retrieved (datetime string)
        hl: Language code

    Returns:
        Absolute datetime as string, or None if parsing fails
    """
    if not isinstance(relative_date, str) or relative_date == "":
        return None

    lang_map = LANGUAGE_MAPS.get(hl, LANGUAGE_MAPS["en"])

    text = unidecode(relative_date).lower().strip()
    text = re.sub(lang_map["one_regex"], "1", text)
    text = re.sub(lang_map["ago_regex"], "", text)

    parts = text.split(" ")
    if len(parts) < 2:
        return None

    number_str, time_unit = parts[0], parts[1]

    try:
        number = float(number_str)
    except ValueError:
        if "an" in unidecode(relative_date).lower():
            number = 1
        else:
            return None

    unit = lang_map["time_unit"].get(time_unit)
    if not unit:
        return None

    review_date = datetime.strptime(
        retrieval_date, "%Y-%m-%d %H:%M:%S.%f"
    ) - relativedelta(**{unit: number})

    return str(review_date)
