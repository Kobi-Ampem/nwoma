"""How numbers, dates, names and flags are printed, per language and layout style."""

from datetime import date

from datagen.layouts import DateStyle, FlagStyle, NameStyle
from datagen.models import Lang

_MONTHS: dict[Lang, tuple[str, ...]] = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "fr": (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ),
}

_FLAGS: dict[FlagStyle, dict[Lang, dict[str, str]]] = {
    # French reports flag low results "B" (bas).
    "letter": {"en": {"H": "H", "L": "L"}, "fr": {"H": "H", "L": "B"}},
    "word": {"en": {"H": "High", "L": "Low"}, "fr": {"H": "Haut", "L": "Bas"}},
    "arrow": {"en": {"H": "↑", "L": "↓"}, "fr": {"H": "↑", "L": "↓"}},
}

_SEX: dict[str, dict[Lang, dict[str, str]]] = {
    "word": {"en": {"M": "Male", "F": "Female"}, "fr": {"M": "Masculin", "F": "Féminin"}},
    "letter": {"en": {"M": "M", "F": "F"}, "fr": {"M": "M", "F": "F"}},
}


def fmt_number(x: float, decimals: int, lang: Lang) -> str:
    text = f"{x:.{decimals}f}"
    # French uses a decimal comma.
    return text.replace(".", ",") if lang == "fr" else text


def fmt_date(d: date, lang: Lang, style: DateStyle = "dmy_slash") -> str:
    if style == "iso":
        return d.isoformat()
    if style == "dmy_dot":
        return d.strftime("%d.%m.%Y")
    if style == "d_mon_y":
        return f"{d.day:02d} {_MONTHS[lang][d.month - 1]} {d.year}"
    return d.strftime("%d/%m/%Y")


def fmt_name(given: str, family: str, style: NameStyle) -> str:
    if style == "family_upper_given":
        return f"{family.upper()} {given}"
    if style == "family_comma_given":
        return f"{family}, {given}"
    return f"{given} {family}"


def fmt_flag(flag: str, lang: Lang, style: FlagStyle) -> str:
    return _FLAGS[style][lang][flag]


def fmt_sex(sex: str, lang: Lang, style: str) -> str:
    return _SEX[style][lang][sex]


def fmt_range(low: str | None, high: str | None) -> str | None:
    if low is not None and high is not None:
        return f"{low} - {high}"
    if low is not None:
        return f"> {low}"
    if high is not None:
        return f"< {high}"
    return None
