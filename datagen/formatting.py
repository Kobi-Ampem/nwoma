"""How numbers, dates and ranges are printed in each language."""

from datetime import date

from datagen.models import Lang

_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fmt_number(x: float, decimals: int, lang: Lang) -> str:
    text = f"{x:.{decimals}f}"
    # French uses a decimal comma.
    return text.replace(".", ",") if lang == "fr" else text


def fmt_date(d: date, lang: Lang) -> str:
    if lang == "fr":
        return d.strftime("%d/%m/%Y")
    return f"{d.day:02d} {_MONTHS_EN[d.month - 1]} {d.year}"


def fmt_range(low: str | None, high: str | None) -> str | None:
    if low is not None and high is not None:
        return f"{low} - {high}"
    if low is not None:
        return f"> {low}"
    if high is not None:
        return f"< {high}"
    return None
