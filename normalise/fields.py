"""Turn fields as printed into the normalised values the labels store.

Deterministic on purpose: an LLM asked to convert dates or decimals can return a plausible wrong
value, while code either converts correctly or returns something that visibly fails to match.
"""

import re
import unicodedata
from datetime import date

# English abbreviations, French names without accents. Full English names match on 3 letters.
_EN_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec"
_FR_MONTHS = "janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre"
_MONTHS = {m: i % 12 + 1 for i, m in enumerate((_EN_MONTHS + " " + _FR_MONTHS).split())}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_TITLE = re.compile(r"^(?:dr\.?|docteur|pr\.?|prof\.?)\s+", re.IGNORECASE)


def _plain(text: str) -> str:
    """Lower case without accents: 'Février' -> 'fevrier'."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def norm_date(text: str) -> str:
    """'06/03/1964', '06.03.1964', '1964-03-06', '06 Mar 1964', '6 mars 1964' -> '1964-03-06'."""
    t = _plain(text).strip()
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t):
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        if m := re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", t):
            return date(int(m[3]), int(m[2]), int(m[1])).isoformat()
        if m := re.fullmatch(r"(\d{1,2})\s+([a-z]+)\.?\s+(\d{4})", t):
            month = _MONTHS.get(m[2]) or _MONTHS.get(m[2][:3])
            if month:
                return date(int(m[3]), month, int(m[1])).isoformat()
    except ValueError:  # e.g. day 31 in a 30-day month: not a date
        pass
    return t


def norm_number(text: str) -> str:
    """'12,7' -> '12.7'. Digits are kept as printed; the scorer compares numerically."""
    return text.strip().replace(",", ".").replace(" ", "")


def norm_range(text: str) -> str:
    """'3,5 - 5,1' -> '3.5-5.1', '> 60' -> '60.0-', '< 200' -> '-200.0' (the label format)."""
    numbers = [float(n.replace(",", ".")) for n in _NUMBER.findall(text)]
    if len(numbers) == 1 and any(c in text for c in "<≤"):
        return f"-{numbers[0]}"
    if len(numbers) == 1 and any(c in text for c in ">≥"):
        return f"{numbers[0]}-"
    if len(numbers) == 2:
        return f"{numbers[0]}-{numbers[1]}"
    return text.strip()


def norm_flag(text: str) -> str:
    """'H', 'High', 'Haut', '↑' -> 'H'; 'L', 'Low', 'B', 'Bas', '↓' -> 'L'."""
    t = _plain(text).strip()
    if t in {"h", "high", "haut", "↑"}:
        return "H"
    if t in {"l", "low", "b", "bas", "↓"}:
        return "L"
    return t


def norm_sex(text: str) -> str:
    t = _plain(text).strip()
    if t in {"m", "male", "masculin", "h", "homme"}:
        return "M"
    if t in {"f", "female", "feminin", "femme"}:
        return "F"
    return t


def norm_name(text: str) -> str:
    """'Chauvin, Anne' and 'CHAUVIN Anne' -> 'Anne Chauvin' (family names may stay upper case;
    the scorer compares names without case)."""
    t = " ".join(text.split())
    if "," in t:
        family, given = (p.strip() for p in t.split(",", 1))
        return f"{given} {family}"
    words = t.split(" ")
    upper = 0  # leading all-capitals words are the family name
    while upper < len(words) - 1 and words[upper].isupper() and len(words[upper]) > 1:
        upper += 1
    if 0 < upper < len(words):
        return " ".join(words[upper:] + words[:upper])
    return t


def norm_clinician(text: str) -> str:
    """'Dr. Kwame Boateng' -> 'Kwame Boateng'."""
    return _TITLE.sub("", " ".join(text.split()))
